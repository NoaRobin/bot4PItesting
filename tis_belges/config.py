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


def _outside_appdata(cfg: dict) -> dict:
    """Le Python du Microsoft Store redirige en silence les écritures dans AppData vers son
    dossier privé : Excel et Outlook, eux, ne voient pas ces fichiers. Les fichiers de travail
    passés à Excel ne doivent donc jamais être dans AppData : on les range dans le dossier
    personnel, jamais redirigé."""
    data = os.path.normcase(os.path.abspath(cfg.get("data_dir", "")))
    for var in ("LOCALAPPDATA", "APPDATA"):
        root = os.environ.get(var)
        if root and data.startswith(os.path.normcase(os.path.abspath(root))):
            cfg["data_dir"] = str(Path.home() / ".tisbelges")
            break
    return cfg


def load_config() -> dict:
    return _outside_appdata(_expand(json.loads(CONFIG_PATH.read_text(encoding="utf-8"))))


def update_config(updates: dict) -> None:
    """Met à jour des clés de config.json en conservant le reste tel quel (chemins non
    développés, mise en forme)."""
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw.update(updates)
    CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
