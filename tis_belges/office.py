"""Pilotage d'Excel et d'Outlook via COM (Windows uniquement).

Excel reste l'outil qui actualise la requête ODBC : c'est ce qui garantit que le fichier
produit est identique à celui de la procédure manuelle (connexion et queryTable conservés).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

import win32com.client

log = logging.getLogger("tis")

XL_UP = -4162
XL_OPEN_XML_WORKBOOK = 51
MSO_AUTOMATION_FORCE_DISABLE = 3


class OfficeError(Exception):
    """Erreur Excel ou Outlook : l'exécution est relancée jusqu'à l'heure limite."""


def _excel_pids() -> set[int]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    ).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "excel.exe" and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


class ExcelApp:
    """Instance Excel dédiée. Ne touche jamais aux classeurs ouverts par l'utilisatrice :
    seul le processus créé ici peut être arrêté, et seulement en cas de délai dépassé."""

    def __init__(self) -> None:
        before = _excel_pids()
        self.app = win32com.client.DispatchEx("Excel.Application")
        self.pids = _excel_pids() - before
        self.app.Visible = False
        self.app.DisplayAlerts = False
        self.app.AskToUpdateLinks = False
        self.app.AutomationSecurity = MSO_AUTOMATION_FORCE_DISABLE
        self._timed_out = False
        self._workbooks: list = []

    def __enter__(self) -> "ExcelApp":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self, path: Path, read_only: bool = False):
        wb = self.app.Workbooks.Open(str(path), 0, read_only)
        self._workbooks.append(wb)
        return wb

    def _kill(self) -> None:
        self._timed_out = True
        for pid in self.pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)

    def refresh(self, wb, timeout_s: int) -> None:
        """Actualise toutes les connexions en synchrone, avec délai maximum.

        Un délai dépassé signifie en général une boîte de dialogue d'identifiants ODBC
        restée ouverte : on arrête l'instance Excel dédiée et on signale l'erreur."""
        for i in range(1, wb.Connections.Count + 1):
            conn = wb.Connections.Item(i)
            for attr in ("OLEDBConnection", "ODBCConnection"):
                try:
                    getattr(conn, attr).BackgroundQuery = False
                except Exception:
                    pass

        timer = threading.Timer(timeout_s, self._kill)
        timer.start()
        try:
            wb.RefreshAll()
            self.app.CalculateUntilAsyncQueriesDone()
        except Exception as exc:
            if self._timed_out:
                raise OfficeError(
                    f"Délai d'actualisation de {timeout_s // 60} min dépassé "
                    "(boîte de dialogue ouverte, ou base injoignable)."
                ) from exc
            raise OfficeError(f"Actualisation Excel en erreur : {exc}") from exc
        finally:
            timer.cancel()

    def close(self) -> None:
        for wb in self._workbooks:
            try:
                wb.Close(False)
            except Exception:
                pass
        self._workbooks.clear()
        try:
            self.app.Quit()
        except Exception:
            pass
        if self.pids and self._pids_alive():
            self._kill()

    def _pids_alive(self) -> bool:
        return bool(self.pids & _excel_pids())


def refresh_master(
    master: Path,
    work: Path,
    target: str,
    param_sheet: str,
    param_cell: str,
    timeout_s: int,
) -> None:
    """Copie le maître, fixe la date dans Paramètres, actualise la requête et sauvegarde
    le résultat dans `work`. Le fichier maître n'est jamais modifié."""
    work.parent.mkdir(parents=True, exist_ok=True)
    src = work.with_name("source_" + work.name)
    shutil.copy2(master, src)
    if work.exists():
        work.unlink()

    with ExcelApp() as xl:
        wb = xl.open(src)
        ws = wb.Worksheets(param_sheet)
        ws.Range(param_cell).NumberFormat = "@"
        ws.Range(param_cell).Value = target
        xl.refresh(wb, timeout_s)
        wb.SaveCopyAs(str(work))
    src.unlink(missing_ok=True)


def append_valor(history: Path, sheet: str, rows: list[tuple]) -> None:
    """Ajoute les lignes Valor en bas de l'historique, puis sauvegarde."""
    with ExcelApp() as xl:
        wb = xl.open(history)
        ws = wb.Worksheets(sheet)
        last = ws.Cells(ws.Rows.Count, 1).End(XL_UP).Row
        first = last + 1
        last_written = first + len(rows) - 1
        ws.Range(f"A{first}:H{last_written}").Value = tuple(tuple(r) for r in rows)
        wb.Save()


def build_am_file(work: Path, am: Path, param_sheet: str) -> None:
    """Supprime l'onglet Paramètres du fichier actualisé et l'enregistre sous le nom
    final. Appelé après l'archivage, qui doit conserver l'onglet."""
    am.parent.mkdir(parents=True, exist_ok=True)
    if am.exists():
        am.unlink()
    with ExcelApp() as xl:
        wb = xl.open(work)
        wb.Worksheets(param_sheet).Delete()
        wb.SaveAs(str(am), XL_OPEN_XML_WORKBOOK)


def _outlook_account(session, address: str):
    accounts = session.Accounts
    for i in range(1, accounts.Count + 1):
        acc = accounts.Item(i)
        if str(acc.SmtpAddress).lower() == address.lower():
            return acc
    return None


def send_mail(
    sender: str,
    to: list[str],
    subject: str,
    body: str,
    attachments: list[Path],
) -> None:
    """Envoie le mail via Outlook. Utilise le compte de l'expéditeur s'il est configuré
    dans Outlook, sinon « envoi de la part de » sur la boîte partagée."""
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
    except Exception as exc:
        raise OfficeError(f"Outlook inaccessible : {exc}") from exc

    mail = outlook.CreateItem(0)
    account = _outlook_account(outlook.Session, sender)
    if account is not None:
        mail.SendUsingAccount = account
    else:
        mail.SentOnBehalfOfName = sender
    mail.To = "; ".join(to)
    mail.Subject = subject
    mail.Body = body
    for path in attachments:
        mail.Attachments.Add(str(path))
    mail.Send()
    log.info("Mail envoyé à %s (pièces : %s)", to, [p.name for p in attachments])


def outlook_sender_status(sender: str) -> str:
    """'compte' si la boîte est un compte Outlook configuré, 'délégation' si l'envoi se fait
    « de la part de » (droit à vérifier), ou lève OfficeError si Outlook est inaccessible."""
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
    except Exception as exc:
        raise OfficeError(f"Outlook inaccessible : {exc}") from exc
    return "compte" if _outlook_account(outlook.Session, sender) else "délégation"
