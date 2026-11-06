"""Test de l'orchestration sans Windows : les fonctions COM sont remplacées par des doublures.
Vérifie : envoi unique, reprise après échec, refus d'un envoi interrompu, mode test sans
écriture dans les dossiers réels.

Lancer : TIS_SAMPLE_DIR=<dossier des exemples> PYTHONPATH=. python -m unittest discover -s tests -v
"""

import os
import shutil
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

SAMPLES = os.environ.get("TIS_SAMPLE_DIR")

# Remplace win32com avant l'import de office (module Windows uniquement).
client = types.ModuleType("win32com.client")
win32com = types.ModuleType("win32com")
win32com.client = client
sys.modules.setdefault("win32com", win32com)
sys.modules.setdefault("win32com.client", client)

import openpyxl  # noqa: E402

import office  # noqa: E402
import tis_belges  # noqa: E402

AM_SAMPLE = "7a2aa24f-TISBE_Rothschild__Co_AM_File.xlsx"
HIST_SAMPLE = "d2fb8b79-TIS_BE_R-co_Valor.xlsx"
TARGET = date(2026, 10, 16)


@unittest.skipUnless(SAMPLES, "TIS_SAMPLE_DIR non défini")
class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "base"
        (self.base / "Historique TIS Belges").mkdir(parents=True)
        shutil.copy2(Path(SAMPLES) / AM_SAMPLE, self.base / "TISBE_PROD.xlsx")
        history = self.base / "Historique TIS Belges" / "TIS BE_R-co Valor.xlsx"
        shutil.copy2(Path(SAMPLES) / HIST_SAMPLE, history)
        # Retire les lignes du 16/10 de la copie pour exercer réellement l'ajout.
        wb = openpyxl.load_workbook(history)
        ws = wb["Sheet2"]
        kept = [r for r in ws.iter_rows(min_row=2, values_only=True) if str(r[3]) != "20261016"]
        ws.delete_rows(2, ws.max_row)
        for r in kept:
            ws.append(list(r))
        wb.save(history)
        self.cfg = {
            "base_dir": str(self.base),
            "data_dir": str(self.tmp / "data"),
            "master_name": "TISBE_PROD.xlsx",
            "output_name": "TISBE_Rothschild & Co AM_File.xlsx",
            "history_relpath": "Historique TIS Belges/TIS BE_R-co Valor.xlsx",
            "history_sheet": "Sheet2",
            "param_sheet": "Paramètres",
            "param_cell": "E4",
            "tis_sheet": "TIS BE",
            "valor_name": "R-co Valor",
            "sender": "box@example.com",
            "recipients": ["six@example.com"],
            "subject": "TIS BELGES",
            "body": "corps",
            "operator_email": "op@example.com",
            "alert_recipients": ["op@example.com"],
            "run_at": "17:00",
            "retry_until": "18:00",
            "retry_every_minutes": 1,
            "refresh_timeout_minutes": 1,
            "skip_dates": [],
            "validation": {"min_rows": 150, "max_rows": 400,
                           "currencies": ["EUR", "USD", "CHF", "GBP"],
                           "types": ["TIBR", "TISF"], "allow_duplicates": False},
        }
        self.sent = []

        def fake_refresh(master, work, target, *_):
            work.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(SAMPLES) / AM_SAMPLE, work)

        def fake_append(history, sheet, rows):
            wb = openpyxl.load_workbook(history)
            ws = wb[sheet]
            for r in rows:
                ws.append(list(r))
            wb.save(history)

        def fake_build_am(work, am, param_sheet):
            am.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work, am)

        def fake_send(sender, to, subject, body, attachments):
            self.sent.append((to, subject, [p.name for p in attachments]))

        self.patches = [
            mock.patch.object(office, "refresh_master", fake_refresh),
            mock.patch.object(office, "append_valor", fake_append),
            mock.patch.object(office, "build_am_file", fake_build_am),
            mock.patch.object(office, "send_mail", fake_send),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_production_run_archives_updates_history_and_sends_once(self):
        self.assertEqual(tis_belges.run(self.cfg, TARGET, test=False, wait=False), 0)
        self.assertEqual(len(self.sent), 1)
        to, subject, attachments = self.sent[0]
        self.assertEqual(to, self.cfg["recipients"])
        self.assertEqual(attachments, [self.cfg["output_name"]])
        self.assertTrue((self.base / "2026" / "TISBE_PROD_20261016.xlsx").exists())

        # Relance : aucun nouvel envoi.
        self.assertEqual(tis_belges.run(self.cfg, TARGET, test=False, wait=False), 0)
        self.assertEqual(len(self.sent), 1)

    def test_history_is_not_duplicated_on_rerun_before_send(self):
        tis_belges.run(self.cfg, TARGET, test=False, wait=False)
        history = self.base / "Historique TIS Belges" / "TIS BE_R-co Valor.xlsx"
        wb = openpyxl.load_workbook(history, read_only=True)
        n = sum(1 for r in wb["Sheet2"].iter_rows(min_col=4, max_col=4, values_only=True)
                if str(r[0]) == "20261016")
        wb.close()
        self.assertEqual(n, 30)

    def test_interrupted_send_is_never_repeated_automatically(self):
        state_dir = Path(self.cfg["data_dir"]) / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "20261016.json").write_text(
            '{"validated": "x", "archived": "x", "valor_done": "x", '
            '"am_built": "x", "send_started": "x"}', encoding="utf-8")
        self.assertEqual(tis_belges.run(self.cfg, TARGET, test=False, wait=False), 2)
        # Seule l'alerte à l'opérateur part ; aucun envoi vers Six.
        self.assertFalse(any(to == self.cfg["recipients"] for to, *_ in self.sent))

    def test_test_mode_writes_nothing_to_real_folders(self):
        before = sorted(p.name for p in self.base.rglob("*"))
        self.assertEqual(tis_belges.run(self.cfg, TARGET, test=True, wait=False), 0)
        self.assertEqual(self.sent[0][0], [self.cfg["operator_email"]])
        self.assertTrue(self.sent[0][1].startswith("[TEST]"))
        self.assertFalse((self.base / "2026").exists())
        after = sorted(p.name for p in self.base.rglob("*"))
        self.assertEqual(before, after)

    def test_bad_file_is_never_sent(self):
        def bad_refresh(master, work, target, *_):
            work.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(SAMPLES) / "733d60dc-TISBE_PROD.xlsx", work)

        with mock.patch.object(office, "refresh_master", bad_refresh):
            with self.assertRaises(tis_belges.ValidationError):
                tis_belges.run(self.cfg, TARGET, test=False, wait=False)
        self.assertEqual(self.sent, [])
        self.assertFalse((self.base / "2026" / "TISBE_PROD_20261016.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
