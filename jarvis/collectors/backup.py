"""Nightly Google Drive backup (tools/backup_repos_gdrive.ps1).

Mirrors the script's own root resolution: Get-Volume does not see the Drive
virtual filesystem, so probe `<letter>:/My Drive` (or the Romanian
localisation) directly. The script writes `_last-run.txt` at the root; that
file is the health signal, independent of Task Scheduler's exit code.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_NAMES = ("My Drive", "Contul meu Drive")


def resolve_root(env: dict[str, str] | None = None) -> Path | None:
    env = env if env is not None else dict(os.environ)
    override = env.get("OPS_BACKUP_DIR")
    if override and Path(override).exists():
        return Path(override)
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        for name in ROOT_NAMES:
            cand = Path(f"{letter}:/{name}")
            if cand.exists():
                return cand / "Backups"
    return None


_RUN = re.compile(r"^run:\s*(\d{4}-\d{2}-\d{2})[T_ ]?(\d{2})?[-:]?(\d{2})?\S*\s*(\d{2}:\d{2})?")


def parse_last_run(text: str, now: datetime) -> dict[str, Any]:
    """`_last-run.txt` -> {run_at, status, failures, warnings, age_h}."""
    status, failures, warnings, run_at = None, [], [], None
    section = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("run:"):
            m = _RUN.match(s)
            if m:
                date = m.group(1)
                hhmm = m.group(4) or (f"{m.group(2)}:{m.group(3)}" if m.group(2) and m.group(3) else "00:00")
                try:
                    run_at = datetime.fromisoformat(f"{date}T{hhmm}").replace(tzinfo=now.tzinfo)
                except ValueError:
                    run_at = None
        elif s.startswith("status:"):
            status = s.split(":", 1)[1].strip()
        elif s.startswith("failures:"):
            section = failures
        elif s.startswith("warnings:"):
            section = warnings
        elif s.startswith("- ") and section is not None:
            section.append(s[2:])
    age_h = round((now - run_at).total_seconds() / 3600, 1) if run_at else None
    return {"run_at": run_at.isoformat() if run_at else None, "status": status,
            "failures": failures, "warnings": warnings, "age_h": age_h}


def fetch(now: datetime) -> dict[str, Any]:
    root = resolve_root()
    if root is None:
        return {"root": None, "mounted": False, "error": "Google Drive not mounted"}
    report = root / "_last-run.txt"
    if not report.exists():
        return {"root": str(root), "mounted": True, "error": "_last-run.txt missing"}
    data = parse_last_run(report.read_text(encoding="utf-8-sig"), now)
    data.update({"root": str(root), "mounted": True, "error": None})
    return data
