# -*- coding: utf-8 -*-
"""Journal durable d'une campagne (SQLite, WAL, synchronous=FULL).

Unité de travail = (conversation, répétition). Chaque passage dans un chat neuf
est une « tentative » ; les tours sont enregistrés un par un, avant le suivant.
Une conversation est terminée dès qu'une tentative est COMPLETE.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS attempts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cid TEXT NOT NULL, repetition INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
    status TEXT NOT NULL,            -- RUNNING | COMPLETE | FAILED | ABORTED | SUSPECT
    started TEXT, finished TEXT, error TEXT, transport TEXT, chat_url TEXT, screenshot TEXT
);
CREATE INDEX IF NOT EXISTS attempts_cid ON attempts(cid, repetition);
CREATE TABLE IF NOT EXISTS turns(
    attempt_id INTEGER NOT NULL REFERENCES attempts(id),
    qid TEXT NOT NULL, cid TEXT, tour INTEGER, question TEXT,
    status TEXT,                     -- CAPTURED | TECH_ERROR | RATE_LIMIT | TIMEOUT | SEND_ERROR | ERROR
    answer TEXT, sent_at TEXT, finished_at TEXT, latency REAL, error TEXT, meta TEXT,
    PRIMARY KEY(attempt_id, qid)
);
CREATE TABLE IF NOT EXISTS verdicts(
    qid TEXT NOT NULL, repetition INTEGER NOT NULL, source TEXT NOT NULL,  -- rules | llm | human
    attempt_id INTEGER, verdict TEXT, reason TEXT, detail TEXT, updated TEXT,
    PRIMARY KEY(qid, repetition, source)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- méta -------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: Any) -> None:
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        with self.db:
            self.db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))

    # --- tentatives -------------------------------------------------------
    def start_attempt(self, cid: str, repetition: int, transport: str) -> tuple[int, int]:
        row = self.db.execute(
            "SELECT COALESCE(MAX(attempt_no),0) FROM attempts WHERE cid=? AND repetition=?", (cid, repetition)
        ).fetchone()
        attempt_no = row[0] + 1
        with self.db:
            cur = self.db.execute(
                "INSERT INTO attempts(cid,repetition,attempt_no,status,started,transport) VALUES(?,?,?,?,?,?)",
                (cid, repetition, attempt_no, "RUNNING", now(), transport),
            )
        return cur.lastrowid, attempt_no

    def finish_attempt(self, attempt_id: int, status: str, error: str | None = None,
                       chat_url: str | None = None, screenshot: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "UPDATE attempts SET status=?, finished=?, error=?, chat_url=COALESCE(?,chat_url),"
                " screenshot=COALESCE(?,screenshot) WHERE id=?",
                (status, now(), error, chat_url, screenshot, attempt_id),
            )

    def mark_suspect(self, attempt_ids: Iterable[int], reason: str) -> None:
        with self.db:
            for aid in attempt_ids:
                self.db.execute("UPDATE attempts SET status='SUSPECT', error=? WHERE id=?", (reason, aid))

    def recover_running(self) -> int:
        """Tentatives restées RUNNING après un arrêt brutal → ABORTED (seront rejouées)."""
        with self.db:
            cur = self.db.execute("UPDATE attempts SET status='ABORTED', error='arrêt du script' WHERE status='RUNNING'")
        return cur.rowcount

    def completed_units(self) -> set[tuple[str, int]]:
        rows = self.db.execute("SELECT DISTINCT cid, repetition FROM attempts WHERE status='COMPLETE'")
        return {(r[0], r[1]) for r in rows}

    # --- tours ------------------------------------------------------------
    def save_turn(self, attempt_id: int, q, status: str, answer: str | None, sent_at: str | None,
                  latency: float | None, error: str | None = None, meta: dict | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(attempt_id,qid) DO UPDATE SET"
                " status=excluded.status, answer=excluded.answer, finished_at=excluded.finished_at,"
                " latency=excluded.latency, error=excluded.error, meta=excluded.meta",
                (attempt_id, q.qid, q.cid, q.tour, q.question, status, answer, sent_at, now(), latency, error,
                 json.dumps(meta or {}, ensure_ascii=False)),
            )

    def final_turns(self) -> list[sqlite3.Row]:
        """Un tour par (qid, répétition) : celui de la dernière tentative COMPLETE,
        à défaut la dernière tentative tout court (pour voir les échecs)."""
        return list(self.db.execute(
            """
            WITH ranked AS (
              SELECT a.*, ROW_NUMBER() OVER (
                PARTITION BY a.cid, a.repetition
                ORDER BY (a.status='COMPLETE') DESC, a.attempt_no DESC) AS rk
              FROM attempts a WHERE a.status <> 'RUNNING')
            SELECT t.*, r.repetition, r.attempt_no, r.status AS attempt_status, r.chat_url
            FROM ranked r JOIN turns t ON t.attempt_id = r.id
            WHERE r.rk = 1 ORDER BY t.qid, r.repetition
            """
        ))

    def attempts(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM attempts ORDER BY id"))

    def all_turns(self) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT t.*, a.repetition, a.attempt_no, a.status AS attempt_status FROM turns t"
            " JOIN attempts a ON a.id=t.attempt_id ORDER BY t.attempt_id, t.tour"))

    # --- verdicts ---------------------------------------------------------
    def save_verdicts(self, rows: Iterable[tuple]) -> None:
        """rows : (qid, repetition, source, attempt_id, verdict, reason, detail_dict)."""
        with self.db:
            for qid, rep, source, aid, verdict, reason, detail in rows:
                self.db.execute(
                    "INSERT INTO verdicts VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(qid,repetition,source) DO UPDATE SET"
                    " attempt_id=excluded.attempt_id, verdict=excluded.verdict, reason=excluded.reason,"
                    " detail=excluded.detail, updated=excluded.updated",
                    (qid, rep, source, aid, verdict, reason, json.dumps(detail or {}, ensure_ascii=False), now()),
                )

    def verdicts(self) -> dict[tuple[str, int, str], sqlite3.Row]:
        return {(r["qid"], r["repetition"], r["source"]): r for r in self.db.execute("SELECT * FROM verdicts")}
