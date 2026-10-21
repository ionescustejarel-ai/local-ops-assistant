"""Windows Task Scheduler + automation jsonl logs.

Two sources are joined per task:
  * `scripts/collect_tasks.ps1` (Get-ScheduledTask/Info as JSON) -> state, last/next
    run, last result, trigger kind and repetition interval.
  * `<automations_log_root>/<YYYY-MM>/<log>.jsonl` -> the last line the task
    itself wrote (idle / rc / summary). Task Scheduler only knows the launcher
    exited 0; the jsonl says whether the chain actually did its job.

Result codes are Task Scheduler HRESULTs. Only a handful mean "fine".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ._run import run_powershell_file

OK_RESULTS = {
    0x0: "ok",
    0x41301: "running",
    0x41303: "never-run",
    0x41325: "queued",
}
KNOWN_FAILURES = {
    0x41306: "terminated by user",
    0x41307: "no valid triggers",
    0x800710E0: "operator/administrator refused the request",
    0x8007010B: "directory name invalid",
    0x80070002: "file not found",
    0x80070005: "access denied",
}

_ISO_INTERVAL = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_iso_interval(text: str | None) -> int | None:
    """'PT30M' -> 1800 seconds. None/empty -> None."""
    if not text:
        return None
    m = _ISO_INTERVAL.match(text)
    if not m:
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + s
    return total or None


def _dt(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def describe_result(code: int | None) -> tuple[bool, str]:
    if code is None:
        return True, "unknown"
    if code in OK_RESULTS:
        return True, OK_RESULTS[code]
    return False, KNOWN_FAILURES.get(code, f"failed (0x{code:08X})")


def expected_interval_seconds(trigger_class: str | None, repetition: str | None) -> int | None:
    """How often the task is supposed to fire; None for logon/on-demand tasks."""
    rep = parse_iso_interval(repetition)
    if rep:
        return rep
    if trigger_class == "MSFT_TaskDailyTrigger":
        return 86400
    return None


def parse_tasks(raw_json: str, now: datetime) -> list[dict[str, Any]]:
    rows = json.loads(raw_json) if raw_json.strip() else []
    if isinstance(rows, dict):
        rows = [rows]
    out: list[dict[str, Any]] = []
    for r in rows:
        code = r.get("LastTaskResult")
        ok, result_text = describe_result(code)
        last = _dt(r.get("LastRunTime"))
        nxt = _dt(r.get("NextRunTime"))
        interval = expected_interval_seconds(r.get("TriggerClass"), r.get("RepetitionInterval"))
        stale = False
        age_s = None
        if last is not None:
            age_s = int((now - last).total_seconds())
            if interval and r.get("State") != "Running":
                stale = age_s > 2 * interval + 300  # two missed cycles + 5 min grace
        out.append({
            "name": r.get("TaskName"),
            "state": r.get("State"),
            "last_run": last.isoformat() if last else None,
            "age_s": age_s,
            "next_run": nxt.isoformat() if nxt else None,
            "result_code": code,
            "result_hex": f"0x{code:08X}" if isinstance(code, int) else None,
            "result_ok": ok,
            "result_text": result_text,
            "missed_runs": r.get("NumberOfMissedRuns") or 0,
            "trigger": (r.get("TriggerClass") or "").replace("MSFT_Task", "").replace("Trigger", "").lower() or None,
            "interval_s": interval,
            "stale": stale,
        })
    return out


# --- automation jsonl ------------------------------------------------------

def _last_line(path: Path) -> str | None:
    """Last non-empty line of a possibly large file, read from the tail."""
    if not path.exists():
        return None
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        chunk = min(size, 65536)
        f.seek(size - chunk)
        data = f.read().decode("utf-8", errors="replace")
    lines = [ln for ln in data.splitlines() if ln.strip()]
    return lines[-1] if lines else None


def parse_log_line(line: str | None) -> dict[str, Any] | None:
    if not line:
        return None
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line[:300], "parse_error": True}
    rcs = {k: v for k, v in rec.items() if k == "rc" or k.endswith("_rc")}
    failed = any(isinstance(v, int) and v != 0 for v in rcs.values())
    summary_keys = [k for k in rec if k.endswith("summary") or k in ("output", "reason")]
    summary = " | ".join(str(rec[k]) for k in summary_keys if rec.get(k))
    return {
        "started_utc": rec.get("started_utc"),
        "idle": bool(rec.get("idle", False)),
        "failed": failed,
        "rcs": rcs,
        "summary": summary[:400],
    }


def read_task_log(log_root: Path, log_name: str, now: datetime) -> dict[str, Any] | None:
    """Last record of <log_root>/<YYYY-MM>/<log_name>.jsonl (current month, then previous)."""
    months = [now.strftime("%Y-%m"), (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")]
    for m in months:
        rec = parse_log_line(_last_line(log_root / m / f"{log_name}.jsonl"))
        if rec:
            rec["log"] = f"{m}/{log_name}.jsonl"
            return rec
    return None


def fetch(script: Path, log_root: Path, log_map: dict[str, str], pattern: str | None = None,
          now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc).astimezone()
    raw = run_powershell_file(script, *([pattern] if pattern else []))
    tasks = parse_tasks(raw, now)
    for t in tasks:
        log_name = log_map.get(t["name"])
        t["log"] = read_task_log(log_root, log_name, now) if log_name else None
    return tasks
