"""Manual deadlines and gates (config/deadlines.yaml).

A dated item is a countdown. An item with `type: poarta` is a gate: a lock that
opens on a date and/or a condition (single-read verdicts, preregistered runs);
it is shown as locked, never as a countdown alert.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

GATE_TYPES = ("poarta", "poartă", "gate")


def _is_gate(it: dict[str, Any]) -> bool:
    return str(it.get("type", "")).lower() in GATE_TYPES


def compute(items: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    out = []
    for it in items:
        d = it.get("date")
        if isinstance(d, datetime):
            d = d.date()
        elif isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                d = None
        gate = _is_gate(it)
        if not isinstance(d, date) and not gate:
            continue
        if not it.get("label"):
            continue
        out.append({
            "label": it["label"],
            "project": it.get("project"),
            "date": d.isoformat() if isinstance(d, date) else None,
            "days_left": (d - today).days if isinstance(d, date) else None,
            "note": it.get("note"),
            "gate": gate,
            "condition": it.get("condition"),
        })
    return sorted(out, key=lambda x: (x["gate"], x["days_left"] if x["days_left"] is not None else 10**6))
