"""Environnement Windows : verrou, DSN ODBC, tâche planifiée, contrôles d'installation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

TASK_NAME = "TIS Belges - envoi quotidien"


@contextmanager
def run_lock(path: Path, stale_after: timedelta = timedelta(hours=3)):
    """Empêche deux exécutions simultanées. Un verrou plus ancien que stale_after est ignoré."""
    if path.exists():
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age < stale_after:
            raise RuntimeError(f"Une exécution est déjà en cours (verrou {path}).")
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def dsn_exists(name: str) -> bool:
    """Vrai si le DSN ODBC existe pour l'utilisateur ou au niveau système (32 et 64 bits)."""
    import winreg

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\ODBC\ODBC.INI\{}"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\ODBC\ODBC.INI\{}"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\ODBC\ODBC.INI\{}"),
    ]
    for hive, template in keys:
        try:
            with winreg.OpenKey(hive, template.format(name)):
                return True
        except OSError:
            continue
    return False


def _task_xml(python_w: Path, script: Path, run_at: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
    days = "".join(f"<{d}/>" for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Envoi quotidien des TIS Belges à Six Financial Information</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{today}T{run_at}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>{days}</DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_w}</Command>
      <Arguments>"{script}" run</Arguments>
      <WorkingDirectory>{script.parent}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def install_task(run_at: str) -> None:
    """Crée (ou remplace) la tâche planifiée du lundi au vendredi à run_at."""
    script = Path(__file__).resolve().parent / "tis_belges.py"
    python_w = Path(sys.executable).with_name("pythonw.exe")
    if not python_w.exists():
        python_w = Path(sys.executable)

    xml_path = Path(tempfile.gettempdir()) / "tis_belges_task.xml"
    xml_path.write_text(_task_xml(python_w, script, run_at), encoding="utf-16")
    try:
        subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
            check=True,
        )
    finally:
        xml_path.unlink(missing_ok=True)


def uninstall_task() -> None:
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False)


def task_exists() -> bool:
    try:
        return subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True
        ).returncode == 0
    except OSError:  # schtasks absent (hors Windows)
        return False


def check_writable(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    probe = folder / ".ecriture_test.tmp"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
