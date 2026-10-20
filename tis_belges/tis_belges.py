"""TIS Belges : production et envoi quotidien du fichier à Six Financial Information.

Commandes :
  python tis_belges.py check                  contrôle de l'installation
  python tis_belges.py run [--date yyyymmdd]  exécution complète (utilisée par la tâche planifiée)
  python tis_belges.py run --test             exécution à blanc : aucun envoi à Six, rien d'écrit
                                              dans les dossiers réels, mail seulement à l'opérateur
  python tis_belges.py run --now              pas d'attente jusqu'à l'heure de calcul
  python tis_belges.py install-task           crée la tâche planifiée (lun.-ven. à run_at)
  python tis_belges.py uninstall-task         supprime la tâche planifiée

Codes de sortie : 0 succès ou rien à faire, 1 échec (alerte envoyée), 2 vérification manuelle requise.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl

import office
import rules
import system
from config import load_config
from rules import ValidationError

HERE = Path(__file__).resolve().parent
log = logging.getLogger("tis")


# ---------------------------------------------------------------- configuration

@dataclass
class Layout:
    """Tous les chemins utilisés pour une date donnée, réels ou de test."""

    master: Path
    history: Path
    archive: Path
    am_file: Path
    work: Path
    state: Path
    lock: Path


def make_layout(cfg: dict, target: date, test: bool) -> Layout:
    key = rules.date_key(target)
    suffix = "_test" if test else ""
    base = Path(cfg["base_dir"])
    data = Path(cfg["data_dir"])
    master = base / cfg["master_name"]
    history_rel = Path(cfg["history_relpath"])

    if test:
        root = data / "test"
        history = root / history_rel
        if not history.exists():
            history.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / history_rel, history)
        archive_dir = root / str(target.year)
        am_dir = root
    else:
        history = base / history_rel
        archive_dir = base / str(target.year)
        am_dir = base

    return Layout(
        master=master,
        history=history,
        archive=archive_dir / f"TISBE_PROD_{key}.xlsx",
        am_file=am_dir / cfg["output_name"],
        work=data / "work" / f"{key}{suffix}" / "refreshed.xlsx",
        state=data / "state" / f"{key}{suffix}.json",
        lock=data / "run.lock",
    )


def setup_logging(cfg: dict, target_key: str) -> None:
    logs = Path(cfg["data_dir"]) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tis")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(logs / f"tis_belges_{target_key}.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    if sys.stdout is not None:  # absent sous pythonw, lancé par la tâche planifiée
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)


# ---------------------------------------------------------------- état des étapes

class State:
    """Points de contrôle persistés : une relance reprend là où l'exécution précédente
    s'est arrêtée, sans jamais refaire un envoi déjà effectué."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, key: str):
        return self.data.get(key)

    def mark(self, key: str) -> None:
        self.data[key] = datetime.now().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- étapes

def read_tis(path: Path, cfg: dict, target_key: str) -> list[tuple]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if cfg["tis_sheet"] not in wb.sheetnames:
            raise ValidationError(f"Onglet '{cfg['tis_sheet']}' absent du fichier.")
        rows = rules.extract_tis_rows(wb[cfg["tis_sheet"]].iter_rows(values_only=True))
    finally:
        wb.close()

    errors = rules.validate_tis_rows(rows, target_key, cfg["validation"])
    if errors:
        raise ValidationError(" | ".join(errors))
    return rows


def obtain_validated_rows(cfg: dict, lay: Layout, target_key: str, retry: bool) -> list[tuple]:
    """Actualise la requête puis valide. En mode planifié, réessaie toutes les
    retry_every_minutes jusqu'à retry_until (données pas encore publiées, base lente)."""
    deadline = datetime.combine(
        datetime.strptime(target_key, "%Y%m%d").date(),
        datetime.strptime(cfg["retry_until"], "%H:%M").time(),
    )
    attempt = 0
    while True:
        attempt += 1
        try:
            office.refresh_master(
                lay.master,
                lay.work,
                target_key,
                cfg["param_sheet"],
                cfg["param_cell"],
                cfg["refresh_timeout_minutes"] * 60,
            )
            rows = read_tis(lay.work, cfg, target_key)
            log.info("Fichier valide : %d lignes à la date %s.", len(rows), target_key)
            return rows
        except (office.OfficeError, ValidationError) as exc:
            log.warning("Tentative %d échouée : %s", attempt, exc)
            if not retry or datetime.now() >= deadline:
                raise
        time.sleep(cfg["retry_every_minutes"] * 60)


def archive(lay: Layout, st: State) -> None:
    if st.get("archived"):
        return
    if lay.archive.exists():
        raise RuntimeError(
            f"{lay.archive} existe déjà sans trace de l'exécution : vérification manuelle requise."
        )
    lay.archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lay.work, lay.archive)
    log.info("Archivé : %s", lay.archive)
    st.mark("archived")


def update_valor_history(cfg: dict, lay: Layout, rows: list[tuple], target_key: str, st: State) -> None:
    if st.get("valor_done"):
        return
    valor_rows = rules.select_valor_rows(rows, cfg["valor_name"])
    if not valor_rows:
        raise ValidationError(f"Aucune ligne « {cfg['valor_name']} » dans le fichier.")

    existing = count_history(lay.history, cfg["history_sheet"], target_key)
    if existing == len(valor_rows):
        log.info("Historique Valor déjà à jour pour %s : rien ajouté.", target_key)
    elif existing == 0:
        office.append_valor(lay.history, cfg["history_sheet"], valor_rows)
        written = count_history(lay.history, cfg["history_sheet"], target_key)
        if written != len(valor_rows):
            raise RuntimeError(
                f"Historique Valor : {written} lignes trouvées après écriture, "
                f"{len(valor_rows)} attendues."
            )
        log.info("Historique Valor : %d lignes ajoutées.", len(valor_rows))
    else:
        raise RuntimeError(
            f"Historique Valor : {existing} lignes déjà présentes pour {target_key}, "
            f"{len(valor_rows)} attendues. Vérification manuelle requise."
        )
    st.mark("valor_done")


def count_history(history: Path, sheet: str, target_key: str) -> int:
    wb = openpyxl.load_workbook(history, read_only=True, data_only=True)
    try:
        values = (r[0] for r in wb[sheet].iter_rows(min_col=4, max_col=4, values_only=True))
        return rules.count_date(values, target_key)
    finally:
        wb.close()


def build_am_file(cfg: dict, lay: Layout, expected_rows: int, st: State) -> None:
    if st.get("am_built"):
        return
    office.build_am_file(lay.work, lay.am_file, cfg["param_sheet"])

    wb = openpyxl.load_workbook(lay.am_file, read_only=True, data_only=True)
    try:
        if cfg["param_sheet"] in wb.sheetnames:
            raise RuntimeError("Le fichier final contient encore l'onglet Paramètres.")
        final_rows = rules.extract_tis_rows(wb[cfg["tis_sheet"]].iter_rows(values_only=True))
    finally:
        wb.close()
    if len(final_rows) != expected_rows:
        raise RuntimeError(
            f"Fichier final : {len(final_rows)} lignes, {expected_rows} attendues."
        )
    log.info("Fichier final prêt : %s", lay.am_file)
    st.mark("am_built")


def send(cfg: dict, lay: Layout, target: date, st: State, test: bool) -> None:
    if st.get("sent_at"):
        return
    if st.get("send_started"):
        raise RuntimeError(
            "Un envoi a été démarré sans confirmation. Vérifiez les éléments envoyés "
            "avant toute nouvelle tentative."
        )
    st.mark("send_started")
    subject = cfg["subject"]
    to = cfg["recipients"]
    if test:
        subject = f"[TEST] {subject}"
        to = [cfg["operator_email"]]
    office.send_mail(cfg["sender"], to, subject, cfg["body"], [lay.am_file])
    st.mark("sent_at")
    log.info("Envoi confirmé pour le %s.", rules.date_key(target))


def alert(cfg: dict, subject: str, body: str) -> None:
    try:
        office.send_mail(cfg["sender"], cfg["alert_recipients"], f"[TIS Belges] {subject}", body, [])
    except Exception:
        log.exception("Impossible d'envoyer l'alerte par mail.")


def sleep_until(moment: datetime) -> None:
    seconds = (moment - datetime.now()).total_seconds()
    if seconds > 0:
        log.info("Attente jusqu'à %s.", moment.strftime("%H:%M"))
        time.sleep(seconds)


# ---------------------------------------------------------------- commandes

def run(cfg: dict, target: date, test: bool, wait: bool) -> int:
    key = rules.date_key(target)
    lay = make_layout(cfg, target, test)
    st = State(lay.state)
    setup_logging(cfg, key)
    log.info("=== Exécution TIS Belges pour %s%s ===", key, " (TEST)" if test else "")

    if st.get("sent_at"):
        log.info("Déjà envoyé pour %s : rien à faire.", key)
        return 0
    if st.get("send_started"):
        msg = f"Envoi du {key} démarré mais non confirmé. Vérifier Éléments envoyés."
        log.error(msg)
        alert(cfg, "Vérification requise", msg)
        return 2

    is_today = target == date.today()
    run_at = datetime.combine(target, datetime.strptime(cfg["run_at"], "%H:%M").time())
    retry_mode = wait

    with system.run_lock(lay.lock):
        if wait and is_today:
            sleep_until(run_at)

        if st.get("validated") and lay.work.exists():
            rows = read_tis(lay.work, cfg, key)
        else:
            rows = obtain_validated_rows(cfg, lay, key, retry=retry_mode)
            st.mark("validated")

        # En test, l'archive et l'historique Valor sont redirigés vers le dossier de test
        # (layout test), donc ces étapes s'exécutent sans toucher aux fichiers réels.
        archive(lay, st)
        update_valor_history(cfg, lay, rows, key, st)
        build_am_file(cfg, lay, len(rows), st)
        send(cfg, lay, target, st, test)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="TIS Belges")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("install-task")
    sub.add_parser("uninstall-task")
    p_run = sub.add_parser("run")
    p_run.add_argument("--date", help="Date VL au format yyyymmdd (défaut : aujourd'hui)")
    p_run.add_argument("--test", action="store_true")
    p_run.add_argument("--now", action="store_true", help="ne pas attendre l'heure de calcul")
    args = parser.parse_args(argv)

    cfg = load_config()

    if args.cmd == "check":
        from checks import run_checks
        return run_checks(cfg)
    if args.cmd == "install-task":
        system.install_task(cfg["run_at"])
        print(f"Tâche « {system.TASK_NAME} » créée : lundi-vendredi à {cfg['run_at']}.")
        return 0
    if args.cmd == "uninstall-task":
        system.uninstall_task()
        print("Tâche supprimée.")
        return 0

    target = (
        datetime.strptime(args.date, "%Y%m%d").date() if args.date else date.today()
    )
    if not args.date and not rules.is_business_day(target, cfg["skip_dates"]):
        print(f"{rules.date_key(target)} : jour non ouvré, rien à faire.")
        return 0

    key = rules.date_key(target)
    setup_logging(cfg, key)
    try:
        return run(cfg, target, args.test, wait=not args.now)
    except Exception as exc:  # toute erreur est journalisée et alertée
        log.exception("Échec de l'exécution.")
        if not args.test:
            alert(cfg, f"Échec du {key}", f"{type(exc).__name__} : {exc}\n\nJournal : {Path(cfg['data_dir']) / 'logs'}")
        return 2 if "vérification manuelle" in str(exc).lower() else 1


if __name__ == "__main__":
    sys.exit(main())
