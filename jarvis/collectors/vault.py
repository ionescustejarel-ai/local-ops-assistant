"""Health of the memory bootloader itself: MEMORY.md must stay under ~17 KB (read limit ≈24 KB)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

MEMORY_MAX_BYTES = 17 * 1024


def fetch(memory_md: Path) -> dict[str, Any]:
    if not memory_md.exists():
        return {"memory_md": str(memory_md), "error": "missing"}
    st = memory_md.stat()
    return {
        "memory_md": str(memory_md),
        "bytes": st.st_size,
        "kb": round(st.st_size / 1024, 1),
        "over_limit": st.st_size > MEMORY_MAX_BYTES,
        "limit_kb": MEMORY_MAX_BYTES // 1024,
        "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="minutes"),
        "error": None,
    }
