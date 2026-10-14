# -*- coding: utf-8 -*-
"""Intégrité du package : chaque nom importé en interne existe, tous les modules se chargent,
et la liste des fichiers vérifiée au démarrage (__main__.REQUIRED) est à jour."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "pia_bench"
MODULES = sorted(p for p in PKG.rglob("*.py") if p.name != "__main__.py")


def module_name(path: Path) -> str:
    name = ".".join(path.relative_to(PKG.parent).with_suffix("").parts)
    return name.removesuffix(".__init__")


def internal_imports(path: Path):
    package = module_name(path) if path.name == "__init__.py" else module_name(path).rsplit(".", 1)[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.level or (node.module or "").startswith("pia_bench")):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), package) \
                if node.level else node.module
            for alias in node.names:
                yield base, alias.name


@pytest.mark.parametrize("path", MODULES, ids=lambda p: module_name(p))
def test_module_imports_and_internal_names_exist(path):
    importlib.import_module(module_name(path))
    for base, name in internal_imports(path):
        target = importlib.import_module(base)
        if not hasattr(target, name):
            importlib.import_module(f"{base}.{name}")  # sous-module (ex. from .transports import edge_ui)


def test_catalogue_interface_used_by_other_modules():
    from pia_bench import catalogue
    for name in ("Catalogue", "Conversation", "Question", "load_catalogue"):
        assert hasattr(catalogue, name), name
    assert {"conversations", "by_qid", "digest", "questions", "merged_orphans", "warnings", "path"} <= \
        set(dir(catalogue.Catalogue)) | set(catalogue.Catalogue.__dataclass_fields__)
    assert {"notable", "theme", "groupe"} <= set(dir(catalogue.Question))


def test_required_files_list_matches_package():
    src = (PKG / "__main__.py").read_text(encoding="utf-8")
    required = set(ast.literal_eval(src.split("REQUIRED = ", 1)[1].split("]", 1)[0] + "]"))
    actual = {p.relative_to(PKG).as_posix() for p in MODULES}
    assert required == actual


def test_cli_help_runs():
    out = subprocess.run([sys.executable, "-m", "pia_bench", "--help"], cwd=PKG.parent,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "check" in out.stdout and "run" in out.stdout
