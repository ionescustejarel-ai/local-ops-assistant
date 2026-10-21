"""Runs every collector on its own interval and keeps one in-memory snapshot.

Collectors are blocking (subprocess/IMAP) except services/calendar which are
async; blocking ones run in the default thread pool so the event loop stays
free for the WebSocket and the voice endpoints. A collector failure never
takes the others down: the error lands in `snapshot["errors"][name]` and the
previous good value is kept.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from .alerts import build_alerts
from .collectors import backup, calendar, deadlines, disk, docker, git, gmail, gpu, pending, projects, services, tasks, vault

log = logging.getLogger("jarvis.snapshot")


class Snapshot:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.get("tz", "Europe/Bucharest"))
        self.data: dict[str, Any] = {}
        self.updated: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self.alerts: list[dict[str, Any]] = []
        self.version = 0
        self._subscribers: set[asyncio.Queue] = set()
        self._tasks: list[asyncio.Task] = []

    # --- public ------------------------------------------------------------
    def now(self) -> datetime:
        return datetime.now(self.tz)

    def as_dict(self) -> dict[str, Any]:
        return {"version": self.version, "generated": self.now().isoformat(timespec="seconds"),
                "data": self.data, "updated": self.updated, "errors": self.errors, "alerts": self.alerts}

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def start(self) -> None:
        if self.cfg.get("_demo"):
            self._load_demo(Path(self.cfg["_demo"]))
            return
        iv = self.cfg["intervals"]
        specs: list[tuple[str, int, Callable[[], Awaitable[Any] | Any]]] = [
            ("tasks", iv["tasks"], self._tasks_),
            ("docker", iv["docker"], lambda: asyncio.to_thread(docker.fetch, self.cfg.get("docker", {}).get("watch"))),
            ("gpu", iv["gpu"], lambda: asyncio.to_thread(gpu.fetch)),
            ("services", iv["services"], self._services),
            ("git", iv["git"], self._git),
            ("projects", iv["projects"], self._projects),
            ("backup", iv["backup"], self._backup),
            ("disk", iv["disk"], lambda: asyncio.to_thread(disk.fetch, self.cfg["disks"])),
            ("deadlines", iv["deadlines"], self._deadlines),
            ("calendar", iv["calendar"], self._calendar),
            ("gmail", iv["gmail"], self._gmail),
            ("pending", iv.get("pending", 120), self._pending),
            ("vault", iv.get("vault", 300), self._vault),
        ]
        self._tasks = [asyncio.create_task(self._loop(name, secs, fn), name=f"collector:{name}") for name, secs, fn in specs]

    def _load_demo(self, path: Path) -> None:
        """Demo mode (JARVIS_DEMO=<snapshot.json>): serve a canned snapshot, run no collectors.
        Alerts are still computed by the real rules, so the board behaves as it would live."""
        demo = json.loads(path.read_text(encoding="utf-8"))
        self.data = demo["data"]
        self.updated = {name: self.now().isoformat(timespec="seconds") for name in self.data}
        self._recompute()

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()

    async def refresh(self, name: str | None = None) -> None:
        """Force an immediate run of one collector (or all); loops poll `_force` every second."""
        self._force = name or "*"

    # --- loop --------------------------------------------------------------
    _force: str | None = None

    async def _loop(self, name: str, interval: int, fn: Callable[[], Any]) -> None:
        while True:
            t0 = time.perf_counter()
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    result = await result
                self.data[name] = result
                self.errors.pop(name, None)
            except Exception as e:  # noqa: BLE001 - one collector must not kill the loop
                log.warning("collector %s failed: %s", name, e)
                self.errors[name] = f"{type(e).__name__}: {str(e)[:200]}"
            self.updated[name] = self.now().isoformat(timespec="seconds")
            self._recompute()
            log.debug("%s in %.0f ms", name, (time.perf_counter() - t0) * 1000)
            slept = 0
            while slept < interval:
                if self._force in ("*", name):
                    if self._force == name:
                        self._force = None
                    break
                await asyncio.sleep(1)
                slept += 1
            if self._force == "*":
                # every loop breaks once on "*"; the last one to notice clears it
                await asyncio.sleep(0.5)
                self._force = None

    def _recompute(self) -> None:
        self.alerts = build_alerts({"data": self.data, "errors": self.errors},
                                   self.cfg["tasks"].get("labels", {}), self.now())
        self.version += 1
        payload = self.as_dict()
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(payload)

    # --- collector adapters (blocking ones wrapped in threads) -------------
    async def _tasks_(self) -> list[dict[str, Any]]:
        p = self.cfg["paths"]
        return await asyncio.to_thread(
            tasks.fetch, Path(p["tasks_script"]), Path(p["automations_log_root"]),
            self.cfg["tasks"].get("log_map", {}), self.cfg["tasks"].get("pattern"), self.now())

    async def _services(self) -> list[dict[str, Any]]:
        return await services.fetch(self.cfg["services"])

    async def _git(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(git.fetch, self.cfg["repos"], self.now())

    async def _projects(self) -> list[dict[str, Any]]:
        p = self.cfg["paths"]
        return await asyncio.to_thread(projects.fetch, Path(p["memory_md"]), self.cfg["projects"], Path(p["vault_root"]))

    async def _backup(self) -> dict[str, Any]:
        return await asyncio.to_thread(backup.fetch, self.now())

    async def _deadlines(self) -> list[dict[str, Any]]:
        from .config import load_yaml, CONFIG_DIR
        items = load_yaml(CONFIG_DIR / "deadlines.yaml") or []
        return deadlines.compute(items, self.now().date())

    async def _pending(self) -> list[dict[str, Any]]:
        p = self.cfg["paths"]
        return await asyncio.to_thread(pending.fetch, Path(p["vault_root"]) / "_inbox" / "pending.yaml", self.now().date())

    async def _vault(self) -> dict[str, Any]:
        return await asyncio.to_thread(vault.fetch, Path(self.cfg["paths"]["memory_md"]))

    async def _calendar(self) -> list[dict[str, Any]] | None:
        url = (self.cfg["secrets"].get("calendar") or {}).get("ics_url")
        if not url:
            return None  # neconfigurat
        return await calendar.fetch(url, self.tz)

    async def _gmail(self) -> dict[str, Any] | None:
        g = self.cfg["secrets"].get("gmail") or {}
        if not g.get("user") or not g.get("app_password"):
            return None
        c = self.cfg.get("gmail", {})
        return await asyncio.to_thread(gmail.fetch, g["user"], g["app_password"], c.get("hours", 48), c.get("limit", 25))
