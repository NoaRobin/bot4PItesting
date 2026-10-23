"""Installation et mise à jour de TIS Belges. Bibliothèque standard uniquement.

Appelé par :
  Installer_TIS_Belges.bat  après téléchargement (copie depuis --source vers --target)
  Installer.bat             depuis un dossier déjà présent (--source et --target identiques)

Étapes : copie de l'application (config.json existant conservé, nouvelles options ajoutées),
environnement Python, dépendances, contrôle du poste, tâche planifiée, raccourci, ouverture.
Relancer = mettre à jour. Code de sortie 0 si l'application est installée, même si le
contrôle du poste signale des points à corriger (ils sont visibles dans l'application).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

WINDOWS = os.name == "nt"
EXCLUDE = {".venv", "__pycache__"}
DASHBOARD_PORT = 8765


def say(message: str = "") -> None:
    print(message, flush=True)


def step(n: int, total: int, message: str) -> None:
    say(f"\n[{n}/{total}] {message}")


# ---------------------------------------------------------------- copie

def merge_config(new_path: Path, current_path: Path) -> None:
    """Garde les réglages existants ; ajoute seulement les options apparues dans la nouvelle version."""
    current = json.loads(current_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))
    added = [key for key in new if key not in current]
    for key in added:
        current[key] = new[key]
    if added:
        current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        say(f"    config.json conservé, nouvelles options ajoutées : {', '.join(added)}")
    else:
        say("    config.json conservé")


def copy_app(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in EXCLUDE:
            continue
        dest = target / item.name
        if item.name == "config.json" and dest.exists():
            merge_config(item, dest)
        elif item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*EXCLUDE))
        else:
            shutil.copy2(item, dest)


def write_version(target: Path, archive: Path | None) -> str:
    """GitHub inscrit l'identifiant du commit en commentaire de l'archive zip."""
    commit = ""
    if archive and archive.exists():
        with zipfile.ZipFile(archive) as z:
            commit = z.comment.decode("ascii", errors="ignore").strip()
    version = f"{commit[:7] or 'local'} installé le {datetime.now():%d/%m/%Y %H:%M}"
    (target / "VERSION").write_text(version + "\n", encoding="utf-8")
    return version


# ---------------------------------------------------------------- environnement

def venv_python(target: Path) -> Path:
    return target / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def ensure_venv(target: Path) -> Path:
    py = venv_python(target)
    if not py.exists():
        subprocess.run([sys.executable, "-m", "venv", str(target / ".venv")], check=True)
    return py


def install_requirements(py: Path, target: Path) -> None:
    pip = [str(py), "-m", "pip", "--disable-pip-version-check"]
    subprocess.run([*pip, "install", "-q", "--upgrade", "pip"], check=False)
    subprocess.run([*pip, "install", "-q", "-r", str(target / "requirements.txt")], check=True)


def run_app(py: Path, target: Path, *args: str) -> int:
    return subprocess.run([str(py), "tis_belges.py", *args], cwd=target).returncode


def task_exists(py: Path, target: Path) -> bool:
    code = "import sys, system; sys.exit(0 if system.task_exists() else 1)"
    return subprocess.run([str(py), "-c", code], cwd=target).returncode == 0


def stop_dashboard() -> None:
    """Arrête l'application ouverte, pour que la nouvelle version soit chargée au lancement."""
    if not WINDOWS:
        return
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        # Le libellé d'état est traduit selon la langue de Windows : on repère l'écoute
        # par l'adresse distante 0.0.0.0:0.
        if len(parts) >= 5 and parts[1].endswith(f":{DASHBOARD_PORT}") and parts[2] == "0.0.0.0:0":
            subprocess.run(["taskkill", "/PID", parts[4], "/F"], capture_output=True)


def create_shortcut(target: Path) -> bool:
    if not WINDOWS:
        return False
    script = target / "dashboard" / "create_shortcut.ps1"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Folder", str(target)],
    )
    return result.returncode == 0


def launch(target: Path) -> None:
    if WINDOWS:
        subprocess.Popen(["cmd", "/c", "start", "", str(target / "Lancer.bat")], cwd=target)


# ---------------------------------------------------------------- orchestration

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Installation de TIS Belges")
    parser.add_argument("--source", required=True, type=Path, help="dossier tis_belges téléchargé")
    parser.add_argument("--target", required=True, type=Path, help="dossier d'installation")
    parser.add_argument("--archive", type=Path, help="archive zip téléchargée (pour la version)")
    parser.add_argument("--no-launch", action="store_true", help="ne pas ouvrir l'application à la fin")
    args = parser.parse_args(argv)

    if sys.version_info < (3, 9):
        say(f"Python {sys.version.split()[0]} est trop ancien : la version 3.9 ou plus récente est requise.")
        return 1

    source, target = args.source.resolve(), args.target.resolve()
    first_install = not venv_python(target).exists()
    total = 6

    step(1, total, f"Copie de l'application dans {target}")
    stop_dashboard()
    if source != target:
        copy_app(source, target)
    version = write_version(target, args.archive)
    say(f"    Version : {version}")

    step(2, total, "Environnement Python")
    py = ensure_venv(target)
    say(f"    {py}")

    step(3, total, "Installation des composants (openpyxl, pywin32)")
    install_requirements(py, target)
    say("    OK")

    step(4, total, "Contrôle du poste")
    check_ok = run_app(py, target, "check") == 0

    step(5, total, "Envoi automatique")
    if not check_ok:
        say("    Non programmé : des points bloquants subsistent (voir ci-dessus).")
        say("    Corrigez-les, puis activez l'envoi automatique dans l'application.")
    elif first_install or task_exists(py, target):
        run_app(py, target, "install-task")
    else:
        say("    Laissé désactivé, comme avant la mise à jour.")

    step(6, total, "Raccourci « TIS Belges » sur le bureau")
    if create_shortcut(target):
        say("    OK")
    elif WINDOWS:
        say(f"    Raccourci non créé : ouvrez l'application avec {target / 'Lancer.bat'}")
    else:
        say("    Ignoré (hors Windows).")

    say("\nInstallation terminée.")
    if not args.no_launch:
        launch(target)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        say(f"\nERREUR : la commande a échoué ({exc.returncode}) : {' '.join(map(str, exc.cmd))}")
        sys.exit(1)
