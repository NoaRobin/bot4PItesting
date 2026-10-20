"""Contrôles d'installation : tout ce qui doit être vrai sur le poste avant la première exécution."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import openpyxl

import office
import system


def _line(status: str, label: str, detail: str = "") -> bool:
    print(f"[{status:^11}] {label}" + (f" : {detail}" if detail else ""))
    return status != "ECHEC"


def run_checks(cfg: dict) -> int:
    results = []

    results.append(_line(
        "OK" if sys.version_info >= (3, 9) else "ECHEC",
        "Python >= 3.9",
        sys.version.split()[0],
    ))

    if importlib.util.find_spec("win32com") is not None:
        results.append(_line("OK", "pywin32 installé"))
    else:
        results.append(_line("ECHEC", "pywin32 installé", "relancer Installer.bat"))
        return _summary(results)

    try:
        with office.ExcelApp() as xl:
            version = xl.app.Version
        results.append(_line("OK", "Excel accessible", f"version {version}"))
    except Exception as exc:
        results.append(_line("ECHEC", "Excel accessible", str(exc)))

    try:
        mode = office.outlook_sender_status(cfg["sender"])
        if mode == "compte":
            results.append(_line("OK", "Boîte expéditrice configurée dans Outlook", cfg["sender"]))
        else:
            results.append(_line(
                "ATTENTION",
                "Boîte expéditrice",
                f"{cfg['sender']} n'est pas un compte Outlook : envoi « de la part de ». "
                "Vérifier le droit d'envoi au nom de cette boîte.",
            ))
    except Exception as exc:
        results.append(_line("ECHEC", "Outlook accessible", str(exc)))

    if system.dsn_exists(cfg["dsn"]):
        results.append(_line("OK", f"DSN ODBC « {cfg['dsn']} » présent"))
    else:
        results.append(_line(
            "ECHEC", f"DSN ODBC « {cfg['dsn']} »",
            "absent. Le créer dans odbcad32 (voir README, étape 3).",
        ))

    base = Path(cfg["base_dir"])
    master = base / cfg["master_name"]
    results.append(_line(
        "OK" if master.exists() else "ECHEC", "Fichier maître TISBE_PROD", str(master),
    ))

    history = base / cfg["history_relpath"]
    if history.exists():
        wb = openpyxl.load_workbook(history, read_only=True)
        has_sheet = cfg["history_sheet"] in wb.sheetnames
        wb.close()
        results.append(_line(
            "OK" if has_sheet else "ECHEC", "Historique Valor",
            f"onglet « {cfg['history_sheet']} »" + ("" if has_sheet else " introuvable"),
        ))
    else:
        results.append(_line("ECHEC", "Historique Valor", str(history)))

    try:
        system.check_writable(base / str(date.today().year))
        results.append(_line("OK", "Dossier d'archives accessible en écriture"))
    except OSError as exc:
        results.append(_line("ECHEC", "Dossier d'archives accessible en écriture", str(exc)))

    try:
        system.check_writable(Path(cfg["data_dir"]))
        results.append(_line("OK", "Dossier de travail local", cfg["data_dir"]))
    except OSError as exc:
        results.append(_line("ECHEC", "Dossier de travail local", str(exc)))

    if system.task_exists():
        results.append(_line("OK", f"Tâche planifiée « {system.TASK_NAME} »"))
    else:
        results.append(_line(
            "ATTENTION", "Tâche planifiée", "absente (lancer : tis_belges.py install-task)",
        ))

    return _summary(results)


def _summary(results: list[bool]) -> int:
    if all(results):
        print("\nInstallation contrôlée : aucun point bloquant.")
        return 0
    print("\nDes points bloquants subsistent. Corriger les lignes ECHEC puis relancer check.")
    return 1
