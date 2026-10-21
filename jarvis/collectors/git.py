"""Per-repo git state: branch, tracked dirty count, last commit."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ._run import CommandFailed, run_cmd

SEP = "\x1f"


def parse_status(porcelain: str) -> int:
    return sum(1 for ln in porcelain.splitlines() if ln.strip())


def parse_changed(porcelain: str, limit: int = 6) -> list[str]:
    """Paths of the first changed tracked files (' M tools/x.py' -> 'tools/x.py')."""
    out = []
    for ln in porcelain.splitlines():
        if ln.strip():
            out.append(ln[3:].strip().strip('"'))
        if len(out) >= limit:
            break
    return out


def parse_log(line: str) -> dict[str, Any]:
    h, date, subject = (line.strip().split(SEP, 2) + ["", ""])[:3]
    return {"hash": h[:7], "date": date, "subject": subject[:120]}


def fetch_repo(repo: dict[str, Any], now: datetime) -> dict[str, Any]:
    path = Path(repo["path"])
    base = {"name": repo["name"], "path": str(path), "alert_dirty": repo.get("alert_dirty", True)}
    if not (path / ".git").exists():
        return {**base, "error": "not a git repo"}
    try:
        branch = run_cmd(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"], timeout=10).strip()
        porcelain = run_cmd(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], timeout=30)
        dirty, changed = parse_status(porcelain), parse_changed(porcelain)
        last = parse_log(run_cmd(["git", "-C", str(path), "log", "-1", f"--format=%H{SEP}%cI{SEP}%s"], timeout=10))
    except CommandFailed as e:
        return {**base, "error": str(e)}
    age_days = None
    if last["date"]:
        try:
            age_days = round((now - datetime.fromisoformat(last["date"])).total_seconds() / 86400, 1)
        except ValueError:
            pass
    return {**base, "branch": branch, "dirty": dirty, "changed": changed, "last_commit": last, "last_commit_age_days": age_days, "error": None}


def fetch(repos: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    return [fetch_repo(r, now) for r in repos]
