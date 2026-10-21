"""`docker ps -a --format '{{json .}}'` -> containers with a health verdict."""
from __future__ import annotations

import json
from typing import Any

from ._run import run_cmd


def parse_docker(jsonl: str) -> list[dict[str, Any]]:
    out = []
    for line in jsonl.splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        status = c.get("Status", "")
        health = c.get("HealthStatus") or ("healthy" if "(healthy)" in status else "")
        if health in ("none", ""):
            health = None  # container has no healthcheck
        up = status.startswith("Up") or c.get("State") == "running"
        ports = c.get("Ports", "")
        # keep only host->container mappings, drop the IPv6 duplicates
        host_ports = sorted({p.split("->")[0].split(":")[-1] for p in ports.split(", ") if "->" in p and not p.startswith("[::]")})
        out.append({
            "name": c.get("Names"),
            "image": c.get("Image"),
            "status": status,
            "up": up,
            "health": health,
            "ok": up and health in ("healthy", None),
            "ports": host_ports,
        })
    return sorted(out, key=lambda c: c["name"] or "")


def fetch(watch: list[str] | None = None) -> list[dict[str, Any]]:
    """All containers; `watched` marks the ones whose absence/unhealth is an alert."""
    rows = parse_docker(run_cmd(["docker", "ps", "-a", "--format", "{{json .}}"], timeout=15))
    watch = watch or []
    for r in rows:
        r["watched"] = r["name"] in watch
    present = {r["name"] for r in rows}
    for name in watch:
        if name not in present:
            rows.append({"name": name, "image": None, "status": "absent", "up": False, "health": None, "ok": False, "ports": [], "watched": True})
    return rows
