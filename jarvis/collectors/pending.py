"""Decisions waiting on the user and things waiting on other people (vault `_inbox/pending.yaml`).

Any Claude session appends here at session end; a resolved item is deleted. Jarvis
only reads. Age drives severity: yellow from 7 days, red from 14.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

YELLOW_DAYS = 7
RED_DAYS = 14
TYPES = {"decizie": "decizie", "asteptare": "așteptare", "așteptare": "așteptare"}


def _date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def parse(items: Any, today: date) -> list[dict[str, Any]]:
    out = []
    for i, it in enumerate(items or []):
        if not isinstance(it, dict) or not it.get("text"):
            continue
        since = _date(it.get("since"))
        age = (today - since).days if since else None
        sev = "info"
        if age is not None:
            sev = "red" if age >= RED_DAYS else ("yellow" if age >= YELLOW_DAYS else "info")
        out.append({
            "id": f"pending:{i}:{str(it['text'])[:40]}",
            "project": it.get("project"),
            "type": TYPES.get(str(it.get("type", "decizie")).lower(), "decizie"),
            "text": str(it["text"]).strip(),
            "since": since.isoformat() if since else None,
            "age_days": age,
            "from": it.get("from"),
            "blocks": it.get("blocks"),
            "severity": sev,
        })
    return sorted(out, key=lambda x: -(x["age_days"] or 0))


def fetch(path: Path, today: date) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return parse(yaml.safe_load(f), today)
