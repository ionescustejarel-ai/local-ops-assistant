"""Load config/jarvis.yaml (+ optional secrets.yaml, deadlines.yaml)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def load_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config() -> dict[str, Any]:
    cfg = load_yaml(CONFIG_DIR / "jarvis.yaml") or {}
    cfg["secrets"] = load_yaml(CONFIG_DIR / "secrets.yaml") or {}
    cfg["deadlines"] = load_yaml(CONFIG_DIR / "deadlines.yaml") or []
    cfg["_root"] = str(ROOT)
    cfg["_demo"] = os.environ.get("JARVIS_DEMO")  # path to a canned snapshot; no collectors run
    return cfg
