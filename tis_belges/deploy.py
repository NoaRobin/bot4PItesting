"""Préparation du poste pour TIS Belges. Bibliothèque standard uniquement.

Appelé par TIS_Belges.bat :
  --is-ready      code 0 si tout est installé pour ce dossier (le .bat ouvre alors l'app)
  --setup         installation : environnement, composants, contrôle, tâche, raccourci
  --wait-server   attend que l'application réponde avant d'ouvrir sa fenêtre

L'environnement Python est créé dans %LOCALAPPDATA%\\TISBelges\\venv, hors du dossier de
l'application : rien de lourd n'est synchronisé si le dossier est dans OneDrive. L'installation
est refaite automatiquement si le dossier a été déplacé ou si les composants requis ont changé.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WINDOWS = os.name == "nt"
APP = Path(__file__).resolve().parent
HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TISBelges"
VENV = HOME / "venv"
MARKER = HOME / "installation.json"
PORT = 8765


def say(message: str = "") -> None:
    print(message, flush=True)


def venv_python(windowed: bool = False) -> Path:
    if WINDOWS:
        return VENV / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return VENV / "bin" / "python"


def fingerprint() -> dict:
    """Ce qui, s'il change, impose de refaire l'installation."""
    requirements = (APP / "requirements.txt").read_bytes()
    return {
        "folder": str(APP).lower() if WINDOWS else str(APP),
        "requirements": hashlib.sha256(requirements).hexdigest()[:16],
    }


def is_ready() -> bool:
    if not MARKER.exists() or not venv_python().exists():
        return False
    try:
        saved = json.loads(MARKER.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return {k: saved.get(k) for k in ("folder", "requirements")} == fingerprint()


# ---------------------------------------------------------------- installation

def run_app(*args: str) -> int:
    return subprocess.run([str(venv_python()), "tis_belges.py", *args], cwd=APP).returncode


def task_exists() -> bool:
    code = "import sys, system; sys.exit(0 if system.task_exists() else 1)"
    return subprocess.run([str(venv_python()), "-c", code], cwd=APP).returncode == 0


def stop_dashboard() -> None:
    """Arrête une application déjà ouverte, pour que la version installée soit rechargée."""
    if not WINDOWS:
        return
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        # Le libellé d'état est traduit selon la langue de Windows : on repère l'écoute
        # par l'adresse distante 0.0.0.0:0.
        if len(parts) >= 5 and parts[1].endswith(f":{PORT}") and parts[2] == "0.0.0.0:0":
            subprocess.run(["taskkill", "/PID", parts[4], "/F"], capture_output=True)


def unblock_files(folder: Path) -> None:
    """Retire la marque « téléchargé depuis Internet » posée par Windows sur le zip extrait."""
    if WINDOWS:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-ChildItem -LiteralPath $env:TIS_FOLDER -Recurse | Unblock-File"],
            env={**os.environ, "TIS_FOLDER": str(folder)},
            capture_output=True,
        )


def create_shortcut(launcher: Path) -> bool:
    if not WINDOWS:
        return False
    script = APP / "dashboard" / "create_shortcut.ps1"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Target", str(launcher)],
    )
    return result.returncode == 0


def setup(launcher: Path | None) -> int:
    if sys.version_info < (3, 9):
        say(f"Python {sys.version.split()[0]} est trop ancien : la version 3.9 ou plus récente est requise.")
        return 1

    first_install = not MARKER.exists()
    total = 5

    say(f"\n[1/{total}] Préparation")
    stop_dashboard()
    unblock_files(launcher.parent if launcher else APP)
    HOME.mkdir(parents=True, exist_ok=True)

    say(f"\n[2/{total}] Environnement Python et composants (openpyxl, pywin32)")
    if venv_python().exists() and subprocess.run([str(venv_python()), "-c", "pass"]).returncode != 0:
        say("    Environnement existant inutilisable (Python mis à jour ?) : recréation.")
        shutil.rmtree(VENV, ignore_errors=True)
    if not venv_python().exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    pip = [str(venv_python()), "-m", "pip", "--disable-pip-version-check"]
    subprocess.run([*pip, "install", "-q", "--upgrade", "pip"], check=False)
    subprocess.run([*pip, "install", "-q", "-r", str(APP / "requirements.txt")], check=True)
    say("    OK")

    say(f"\n[3/{total}] Contrôle du poste")
    check_ok = run_app("check") == 0

    say(f"\n[4/{total}] Envoi automatique")
    if not check_ok:
        say("    Non programmé : des points bloquants subsistent (voir ci-dessus).")
        say("    Corrigez-les, puis activez l'envoi automatique dans l'application.")
    elif first_install or task_exists():
        # Recréée aussi quand le dossier a changé, pour pointer vers le nouvel emplacement.
        run_app("install-task")
    else:
        say("    Laissé désactivé, comme avant.")

    say(f"\n[5/{total}] Raccourci « TIS Belges » sur le bureau")
    if launcher and create_shortcut(launcher):
        say("    OK")
    else:
        say("    Non créé : ouvrez l'application avec TIS_Belges.bat.")

    MARKER.write_text(
        json.dumps({**fingerprint(), "installed": datetime.now().isoformat(timespec="seconds")}, indent=2),
        encoding="utf-8",
    )
    say("\nInstallation terminée.")
    return 0


def wait_server(timeout_s: float = 15) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                return 0
        time.sleep(0.25)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Préparation du poste pour TIS Belges")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--is-ready", action="store_true")
    mode.add_argument("--setup", action="store_true")
    mode.add_argument("--wait-server", action="store_true")
    parser.add_argument("--launcher", type=Path, help="chemin de TIS_Belges.bat (cible du raccourci)")
    args = parser.parse_args(argv)

    if args.is_ready:
        return 0 if is_ready() else 1
    if args.wait_server:
        return wait_server()
    return setup(args.launcher.resolve() if args.launcher else None)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        say(f"\nERREUR : la commande a échoué ({exc.returncode}) : {' '.join(map(str, exc.cmd))}")
        sys.exit(1)
