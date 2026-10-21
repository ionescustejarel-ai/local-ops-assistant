"""Free space per volume."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def fetch(paths: list[str]) -> list[dict[str, Any]]:
    out = []
    for p in paths:
        try:
            u = shutil.disk_usage(Path(p))
        except OSError as e:
            out.append({"path": p, "error": type(e).__name__})
            continue
        out.append({
            "path": p,
            "total_gb": round(u.total / 1e9),
            "free_gb": round(u.free / 1e9),
            "used_pct": round(100 * (u.total - u.free) / u.total, 1) if u.total else None,
        })
    return out
