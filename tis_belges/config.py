"""Lecture et écriture de config.json. Sans dépendance Windows : utilisable par le dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"


def _expand(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def load_config() -> dict:
    return _expand(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def update_config(updates: dict) -> None:
    """Met à jour des clés de config.json en conservant le reste tel quel (chemins non
    développés, mise en forme)."""
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw.update(updates)
    CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
