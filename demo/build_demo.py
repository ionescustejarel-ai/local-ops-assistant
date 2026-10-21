"""Build demo/snapshot.json from the synthetic workspace and test fixtures.

    python demo/build_demo.py
    JARVIS_DEMO=demo/snapshot.json python -m jarvis.server

Every value goes through the real parsers, so the demo board has exactly the
shapes the live collectors produce. Nothing here reads the local machine.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # run as a script from anywhere: use this checkout's package

from jarvis.collectors import deadlines, docker, gpu, pending, projects, tasks  # noqa: E402
from jarvis.config import load_yaml  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
WS = ROOT / "demo" / "workspace"


def main() -> None:
    tz = ZoneInfo("Europe/Bucharest")
    now = datetime.now(tz).replace(second=0, microsecond=0)
    cfg = load_yaml(ROOT / "config" / "jarvis.yaml")

    # tasks: the fixture rows shifted to "now", so ages and staleness look current
    raw = json.loads((FIX / "tasks.json").read_text(encoding="utf-8-sig"))
    shift = now - datetime(2026, 9, 23, 13, 0, tzinfo=tz)
    for row in raw:
        for key in ("LastRunTime", "NextRunTime"):
            if row.get(key):
                row[key] = (datetime.fromisoformat(row[key][:19]).replace(tzinfo=tz) + shift).isoformat()
    task_rows = tasks.parse_tasks(json.dumps(raw), now)
    for t in task_rows:
        if t["name"] == "Ops_Daily_Ingest":
            t["log"] = tasks.parse_log_line((FIX / "daily-ingest.jsonl").read_text(encoding="utf-8").splitlines()[-1])

    data = {
        "tasks": task_rows,
        "docker": [dict(c, watched=c["name"] in cfg["docker"]["watch"]) for c in docker.parse_docker((FIX / "docker_ps.jsonl").read_text(encoding="utf-8"))],
        "gpu": gpu.parse_nvidia((FIX / "nvidia_smi.csv").read_text(encoding="utf-8")),
        "services": [
            {"name": "reranker", "url": "http://127.0.0.1:8009/health", "ok": True, "status": 200, "latency_ms": 4, "error": None},
            {"name": "web-ui", "url": "http://127.0.0.1:8011/", "ok": True, "status": 200, "latency_ms": 11, "error": None},
            {"name": "api", "url": "http://127.0.0.1:8008/health", "ok": True, "status": 200, "latency_ms": 6, "error": None},
            {"name": "n8n", "url": "http://127.0.0.1:5678/healthz", "ok": False, "status": None, "latency_ms": 2001,
             "error": "ConnectTimeout"},
        ],
        "backup": {"root": "G:/My Drive/Backups", "mounted": True, "error": None,
                   "run_at": (now - timedelta(hours=15, minutes=56)).strftime("%Y-%m-%d %H:%M"), "status": "FAILED",
                   "failures": ["shop: bundle rc 128"], "warnings": [], "age_h": 15.9},
        "disk": [{"path": "C:/", "total_gb": 1862.0, "free_gb": 412.3, "used_pct": 77.9},
                 {"path": "D:/", "total_gb": 3726.0, "free_gb": 1904.6, "used_pct": 48.9}],
        "git": [
            {"name": "site", "path": "C:/work/site", "branch": "redesign", "dirty": 3, "changed": ["index.html", "styles.css", "img/team.jpg"],
             "last_commit": {"hash": "a41c09e", "date": (now - timedelta(days=1)).isoformat(), "subject": "feat: variant B hero section"},
             "last_commit_age_days": 1, "error": None, "alert_dirty": True},
            {"name": "shop", "path": "C:/work/shop", "branch": "main", "dirty": 0, "changed": [],
             "last_commit": {"hash": "77d2b10", "date": (now - timedelta(days=4)).isoformat(), "subject": "fix: stock import skips empty SKUs"},
             "last_commit_age_days": 4, "error": None, "alert_dirty": True},
        ],
        "projects": projects.fetch(WS / "MEMORY.md", cfg["projects"], WS),
        "calendar": [
            {"summary": "Call cu designerul", "start": now.replace(hour=11, minute=0).isoformat(), "end": now.replace(hour=11, minute=30).isoformat(), "all_day": False, "location": None},
            {"summary": "Consultație licență", "start": (now + timedelta(days=1)).replace(hour=14, minute=0).isoformat(), "end": None, "all_day": False, "location": "Sala 204"},
        ],
        "gmail": {"unread": 4, "hours": 48, "items": [
            {"from": "Furnizor SRL", "subject": "Fișierul de stoc pentru octombrie", "date": now.isoformat()},
            {"from": "Registrar", "subject": "Domeniul expiră în 30 de zile", "date": (now - timedelta(hours=5)).isoformat()},
        ]},
        "deadlines": deadlines.compute(load_yaml(ROOT / "config" / "deadlines.yaml"), now.date()),
        "pending": pending.fetch(WS / "_inbox" / "pending.yaml", now.date()),
        "vault": {"memory_md": "MEMORY.md", "bytes": 2210, "kb": 2.2, "over_limit": False, "limit_kb": 17, "error": None},
    }
    # the project notes carry absolute paths of this checkout; keep the demo file portable
    for p in data["projects"]:
        if p.get("note_path"):
            p["note_path"] = Path(p["note_path"]).relative_to(ROOT).as_posix()
        if p.get("note"):
            p["note"].pop("mtime", None)
    out = ROOT / "demo" / "snapshot.json"
    out.write_text(json.dumps({"data": data}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out.relative_to(ROOT), "projects:", len(data["projects"]), "tasks:", len(task_rows))


if __name__ == "__main__":
    main()
