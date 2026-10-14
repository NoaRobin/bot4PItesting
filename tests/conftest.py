# -*- coding: utf-8 -*-
"""Fixtures : classeur synthétique (même format que QUESTIONS_1500) et configuration de test."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pia_bench.config import load_config  # noqa: E402

HEADERS = ["ID question", "ID conversation", "Tour", "Groupe", "Thème", "Question utilisateur",
           "Produit cible exact", "Champ exact", "Valeur source brute", "Statut GT"]

# (produit, champ, valeur, statut) — données fictives
FIELDS = [
    ("Fonds Alpha", "Legal Form", "Unit Trust (FCP)", "NOTABLE"),
    ("Fonds Alpha", "Portfolio Manager", "DURAND Claire", "NOTABLE"),
    ("Fonds Alpha", "Official Risk Scale", "4", "NOTABLE"),
    ("Fonds Beta", "Region", "World", "NOTABLE"),
    ("Fonds Beta", "Portfolio Manager backup 3", "", "EXPLORATOIRE"),
]


def make_workbook(path: Path, n_conv: int = 4, orphan: bool = True) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "QUESTIONS_1500"
    ws.append(HEADERS)
    k = 0
    for c in range(1, n_conv + 1):
        for t, (prod, champ, val, gt) in enumerate(FIELDS, 1):
            k += 1
            ws.append([f"Q{k:04d}", f"C{c:03d}", t, "PRIORITAIRE", "Équipe complète",
                       f"[C{c:03d}] Pour {prod}, quelle est la valeur du champ {champ} ?", prod, champ, val, gt])
            if orphan and c == 1 and t == 2:
                ws.append([None, None, None, None, None, None, None, None, "(suite du texte long)", None])
    wb.save(path)
    return path


@pytest.fixture
def workbook(tmp_path):
    return make_workbook(tmp_path / "bench.xlsx")


@pytest.fixture
def cfg(tmp_path, workbook):
    c = load_config(None)
    c.root = tmp_path
    c["catalogue"]["path"] = str(workbook)
    c["campaign"]["runs_dir"] = str(tmp_path / "runs")
    c["scoring"]["equivalences"] = str(Path(__file__).resolve().parents[1] / "equivalences.csv")
    r = c["run"]
    r.update(think_time=0, between_conversations=0, backoff_base=0, rate_limit_cooldown=0, breaker_cooldown=0,
             stable_seconds=0.8, turn_timeout=30)
    return c
