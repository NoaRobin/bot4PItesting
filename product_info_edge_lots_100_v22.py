#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Product Info Assistant - Edge batches of 100 (V22).

Workflow:
- Opens a dedicated Edge profile but does NOT navigate automatically.
- User manually opens Product Info Assistant in that Edge window.
- One Enter starts the campaign.
- Questions are sent one at a time; each full response is persisted before the next send.
- Every 100 CAPTURED answers, the runner pauses. User manually opens a blank chat,
  then presses Enter once to continue.
- New timestamped SQLite/CSV journal for every fresh run.

Important: UI automation can never be guaranteed at 100%. This runner stops safely on
an uncertain send/capture rather than shifting all subsequent answers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
BOOK = ROOT / "Benchmark_Product_Info_1500_questions_revision_naturelle.xlsx"
SHEET = "QUESTIONS_1500"
PROFILE = ROOT / ".edge_product_info_profile_v22"
RUNS_DIR = ROOT / "runs_v22"

COMPOSER_SELECTORS = (
    '[contenteditable="true"][aria-label="Message Product Info Assistant"]',
    '[contenteditable="true"][data-placeholder="Message Product Info Assistant"]',
    '[role="textbox"][aria-label="Message Product Info Assistant"]',
    '[contenteditable="true"][aria-label="Message Copilot"]',
    '[role="textbox"][aria-label="Message Copilot"]',
)
USER_SELECTORS = (
    '[class*="fai-UserMessage"]',
    '[data-message-author-role="user"]',
    '[data-author="user"]',
)
ASSISTANT_SELECTORS = (
    '[class*="fai-CopilotMessage"]',
    '[data-message-author-role="assistant"]',
    '[data-author="assistant"]',
    '[data-testid*="assistant-message" i]',
    '[aria-label*="Product Info Assistant said" i]',
)
WAITING_PATTERNS = (
    "mise en place en cours",
    "lining things up",
    "nous travaillons sur une réponse",
    "nous travaillons sur une reponse",
    "veuillez patienter",
    "recherche en cours",
    "génération en cours",
    "generation en cours",
)
STOP_RE = re.compile(r"arrêter|arreter|stop generating|stop responding|interrompre", re.I)
SEND_RE = re.compile(r"^(envoyer|send|submit)$", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def norm(value: Any) -> str:
    return clean(value).casefold()


def read_catalogue() -> tuple[list[dict[str, Any]], str]:
    if not BOOK.is_file():
        raise FileNotFoundError(f"Classeur introuvable : {BOOK}")
    wb = load_workbook(BOOK, read_only=True, data_only=True)
    try:
        if SHEET not in wb.sheetnames:
            raise ValueError(f"Onglet {SHEET!r} absent. Onglets disponibles : {wb.sheetnames}")
        ws = wb[SHEET]
        rows = ws.iter_rows(values_only=True)
        headers = [clean(x) for x in next(rows)]
        required = ["ID question", "ID conversation", "Tour", "Question utilisateur"]
        missing = [x for x in required if x not in headers]
        if missing:
            raise ValueError("Colonnes absentes : " + ", ".join(missing))
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for values in rows:
            row = dict(zip(headers, values))
            qid = clean(row.get("ID question"))
            question = clean(row.get("Question utilisateur"))
            if not qid or not question:
                continue
            if qid in seen:
                raise ValueError(f"ID question dupliqué : {qid}")
            seen.add(qid)
            out.append({
                "qid": qid,
                "cid": clean(row.get("ID conversation")),
                "tour": int(row.get("Tour") or 0),
                "question": question,
                "produit": clean(row.get("Produit cible exact")),
                "champ": clean(row.get("Champ exact")),
                "gt": clean(row.get("Valeur source brute")),
                "gt_status": clean(row.get("Statut GT")),
            })
        if not out:
            raise ValueError("Aucune question trouvée")
        raw = json.dumps(out, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return out, hashlib.sha256(raw).hexdigest()
    finally:
        wb.close()


def create_run(catalogue_hash: str) -> tuple[sqlite3.Connection, Path, Path]:
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_path = RUNS_DIR / f"product_info_v22_{stamp}.sqlite3"
    csv_path = RUNS_DIR / f"product_info_v22_{stamp}.csv"
    db = sqlite3.connect(db_path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("""CREATE TABLE turns(
        qid TEXT PRIMARY KEY, cid TEXT, tour INTEGER, question TEXT,
        produit TEXT, champ TEXT, gt TEXT, gt_status TEXT,
        state TEXT, answer TEXT, started TEXT, sent_at TEXT, finished TEXT,
        latency REAL, error TEXT, selector TEXT, batch_no INTEGER
    )""")
    db.execute("INSERT INTO meta VALUES (?,?)", ("catalogue_sha256", catalogue_hash))
    db.execute("INSERT INTO meta VALUES (?,?)", ("created_at", now()))
    db.commit()
    return db, db_path, csv_path


def export_csv(db: sqlite3.Connection, csv_path: Path) -> None:
    tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    columns = [r[1] for r in db.execute("PRAGMA table_info(turns)").fetchall()]
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        w.writerows(db.execute("SELECT * FROM turns ORDER BY qid"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, csv_path)


def visible_frames(page):
    return list(page.frames)


def visible_texts(frame, selector: str) -> list[str]:
    out: list[str] = []
    loc = frame.locator(selector)
    try:
        count = loc.count()
    except Exception:
        return out
    for i in range(count):
        item = loc.nth(i)
        try:
            if not item.is_visible():
                continue
            text = clean(item.inner_text(timeout=1500))
            if text:
                out.append(text)
        except Exception:
            continue
    return out


def find_composer(page):
    matches = []
    for frame in visible_frames(page):
        for css in COMPOSER_SELECTORS:
            loc = frame.locator(css)
            try:
                for i in range(loc.count()):
                    x = loc.nth(i)
                    if x.is_visible() and x.is_editable():
                        matches.append((frame, x, css))
                if matches:
                    break
            except Exception:
                continue
    # De-duplicate same DOM node found by multiple selectors by keeping first visible match.
    if not matches:
        raise RuntimeError("Zone Message Product Info Assistant introuvable")
    return matches[0]


def find_chat_page(context):
    pages = []
    for page in context.pages:
        if page.is_closed():
            continue
        try:
            find_composer(page)
            pages.append(page)
        except Exception:
            pass
    if len(pages) != 1:
        raise RuntimeError(f"Onglets de chat détectés : {len(pages)} (attendu 1)")
    return pages[0]


def get_messages(page, selectors: Iterable[str]) -> tuple[list[str], str]:
    candidates: list[tuple[list[str], str]] = []
    for frame in visible_frames(page):
        for css in selectors:
            vals = visible_texts(frame, css)
            if vals:
                candidates.append((vals, css))
                break
    if not candidates:
        return [], ""
    # Choose the candidate with the most messages. If tied with conflicting payloads, stop.
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    best = candidates[0]
    tied = [c for c in candidates if len(c[0]) == len(best[0])]
    if len(tied) > 1 and any(c[0] != best[0] for c in tied[1:]):
        raise RuntimeError("Plusieurs zones de messages assistant incompatibles")
    return best


def waiting_only(text: str) -> bool:
    low = norm(text)
    return any(p in low for p in WAITING_PATTERNS) and len(low) < 180


def generating(page) -> bool:
    for frame in visible_frames(page):
        try:
            if frame.get_by_role("button", name=STOP_RE).count() > 0:
                for i in range(frame.get_by_role("button", name=STOP_RE).count()):
                    if frame.get_by_role("button", name=STOP_RE).nth(i).is_visible():
                        return True
        except Exception:
            pass
    return False


def composer_text(locator) -> str:
    # Crucial fix: contenteditable does not reliably support input_value().
    try:
        return clean(locator.evaluate("el => el.innerText || el.textContent || ''"))
    except Exception:
        return ""


def fill_and_confirm(locator, question: str) -> None:
    locator.click()
    locator.fill(question)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if clean(composer_text(locator)) == clean(question):
            return
        time.sleep(0.25)
    raise RuntimeError("Saisie non confirmée dans le contenteditable; aucun envoi")


def click_send_or_enter(page, frame, composer) -> str:
    # Prefer an explicit visible Send button. Otherwise Enter is the supported fallback.
    candidates = []
    for role in ("button",):
        try:
            loc = frame.get_by_role(role, name=SEND_RE)
            for i in range(loc.count()):
                b = loc.nth(i)
                if b.is_visible() and b.is_enabled():
                    candidates.append(b)
        except Exception:
            pass
    if len(candidates) == 1:
        candidates[0].click()
        return "send_button"
    composer.press("Enter")
    return "enter"


def wait_question_sent(page, question: str, before_user_count: int, composer, timeout: int = 25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        users, _ = get_messages(page, USER_SELECTORS)
        if len(users) >= before_user_count + 1 and norm(question) in norm(users[-1]):
            return
        # Evidence accepted only together: composer cleared and visible user count increased.
        time.sleep(0.5)
    raise RuntimeError("Question non confirmée comme envoyée")


def wait_final_answer(page, before_count: int, timeout: int, stable_seconds: int) -> tuple[str, str]:
    deadline = time.monotonic() + timeout
    last = ""
    stable_since: float | None = None
    selector = ""
    while time.monotonic() < deadline:
        answers, selector = get_messages(page, ASSISTANT_SELECTORS)
        if len(answers) >= before_count + 1:
            text = answers[-1]
            if text and not waiting_only(text):
                if text != last:
                    last = text
                    stable_since = time.monotonic()
                elif stable_since is not None and not generating(page):
                    if time.monotonic() - stable_since >= stable_seconds:
                        # Re-read once after a short delay to guard late rendering.
                        time.sleep(1.0)
                        reread, _ = get_messages(page, ASSISTANT_SELECTORS)
                        if reread and reread[-1] == last and not waiting_only(last):
                            return last, selector
            else:
                last = ""
                stable_since = None
        time.sleep(0.75)
    raise TimeoutError("Réponse finale non confirmée avant le délai")


def assert_blank_chat(page) -> None:
    users, _ = get_messages(page, USER_SELECTORS)
    answers, _ = get_messages(page, ASSISTANT_SELECTORS)
    _, composer, _ = find_composer(page)
    draft = composer_text(composer)
    if users or answers or draft:
        raise RuntimeError(
            f"Chat non vierge (utilisateur={len(users)}, assistant={len(answers)}, brouillon={len(draft)})"
        )


def save_state(db, row, state: str, batch_no: int, **extra) -> None:
    existing = db.execute("SELECT qid FROM turns WHERE qid=?", (row["qid"],)).fetchone()
    fields = {
        "cid": row["cid"], "tour": row["tour"], "question": row["question"],
        "produit": row["produit"], "champ": row["champ"], "gt": row["gt"],
        "gt_status": row["gt_status"], "state": state, "batch_no": batch_no,
        **extra,
    }
    if existing:
        assignments = ",".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE turns SET {assignments} WHERE qid=?", (*fields.values(), row["qid"]))
    else:
        cols = ["qid", *fields.keys()]
        vals = [row["qid"], *fields.values()]
        db.execute(f"INSERT INTO turns({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", vals)
    db.commit()


def run(args) -> None:
    rows, digest = read_catalogue()
    selection = rows if args.all else rows[:args.pilot]
    print(f"Catalogue: {len(rows)} questions; sélection: {len(selection)}; lots de {args.batch_size}")
    if args.dry_run:
        print("Première:", selection[0]["qid"], selection[0]["question"])
        print("Dernière:", selection[-1]["qid"])
        print("Aucun envoi")
        return

    db, db_path, csv_path = create_run(digest)
    print("Journal SQLite:", db_path.name)
    print("Export CSV:", csv_path.name)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            channel="msedge",
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            print("Dans CETTE fenêtre Edge, ouvrez manuellement Product Info Assistant dans un chat VIERGE.")
            input("Quand la zone Message Product Info Assistant est visible, appuyez UNE fois sur Entrée : ")
            page = find_chat_page(context)
            assert_blank_chat(page)

            captured = 0
            for index, row in enumerate(selection):
                batch_no = index // args.batch_size + 1
                if index > 0 and index % args.batch_size == 0:
                    export_csv(db, csv_path)
                    print(f"\nLOT {batch_no-1} terminé: {captured} réponses capturées.")
                    print("Dans la MÊME fenêtre Edge, ouvrez manuellement un NOUVEAU chat vierge Product Info Assistant.")
                    input("Quand le nouveau chat vierge est prêt, appuyez une fois sur Entrée : ")
                    page = find_chat_page(context)
                    assert_blank_chat(page)

                users_before, _ = get_messages(page, USER_SELECTORS)
                answers_before, _ = get_messages(page, ASSISTANT_SELECTORS)
                started_mono = time.monotonic()
                save_state(db, row, "PREPARED", batch_no, started=now(), error=None)
                export_csv(db, csv_path)

                try:
                    frame, composer, _ = find_composer(page)
                    if composer_text(composer):
                        raise RuntimeError("Brouillon non vide avant la question")
                    fill_and_confirm(composer, row["question"])
                    save_state(db, row, "FILLED", batch_no, started=now())
                    gesture = click_send_or_enter(page, frame, composer)
                    wait_question_sent(page, row["question"], len(users_before), composer)
                    save_state(db, row, "SENT", batch_no, sent_at=now(), selector=gesture)
                    answer, answer_selector = wait_final_answer(
                        page, len(answers_before), args.answer_timeout, args.stable_seconds
                    )
                    save_state(
                        db, row, "CAPTURED", batch_no,
                        answer=answer, finished=now(),
                        latency=round(time.monotonic() - started_mono, 2),
                        selector=answer_selector,
                    )
                    export_csv(db, csv_path)
                    captured += 1
                    print(f"{row['qid']} CAPTURED {captured} / {len(selection)} longueur {len(answer)}")
                except KeyboardInterrupt:
                    save_state(db, row, "UNCERTAIN", batch_no, finished=now(), error="KeyboardInterrupt")
                    export_csv(db, csv_path)
                    raise
                except Exception as exc:
                    save_state(
                        db, row, "UNCERTAIN", batch_no,
                        finished=now(), error=f"{type(exc).__name__}: {exc}"
                    )
                    export_csv(db, csv_path)
                    print(f"ARRÊT {row['qid']} UNCERTAIN: {type(exc).__name__}: {exc}")
                    raise
            print("Campagne terminée. Réponses capturées:", captured)
        finally:
            try:
                export_csv(db, csv_path)
            except Exception:
                pass
            db.close()
            try:
                context.close()
            except Exception:
                print("Note: fermeture Edge incomplète; le journal SQLite reste la source principale.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Product Info Edge V22, lots manuels de 100")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="Traiter tout le catalogue")
    ap.add_argument("--pilot", type=int, default=2, help="Nombre de questions si --all absent")
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--answer-timeout", type=int, default=240)
    ap.add_argument("--stable-seconds", type=int, default=8)
    args = ap.parse_args()
    if not args.run:
        args.dry_run = True
    try:
        run(args)
    except KeyboardInterrupt:
        print("Interruption utilisateur. Le journal conserve le dernier état.")
        sys.exit(130)
    except Exception as exc:
        print("ERREUR:", type(exc).__name__, str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
