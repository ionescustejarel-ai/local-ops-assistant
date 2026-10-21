"""nvidia-smi csv -> per-GPU memory / utilisation / temperature."""
from __future__ import annotations

from typing import Any

from ._run import run_cmd

QUERY = "index,name,memory.used,memory.total,utilization.gpu,temperature.gpu"


def parse_nvidia(csv_text: str) -> list[dict[str, Any]]:
    out = []
    for line in csv_text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        used, total = int(parts[2]), int(parts[3])
        out.append({
            "index": int(parts[0]),
            "name": parts[1],
            "mem_used_mib": used,
            "mem_total_mib": total,
            "mem_pct": round(100 * used / total, 1) if total else 0.0,
            "util_pct": int(parts[4]) if parts[4].isdigit() else None,
            "temp_c": int(parts[5]) if parts[5].isdigit() else None,
        })
    return out


def fetch() -> list[dict[str, Any]]:
    raw = run_cmd(["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"], timeout=10)
    return parse_nvidia(raw)
