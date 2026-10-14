# -*- coding: utf-8 -*-
"""Orchestration d'une campagne : une conversation du benchmark = un chat neuf.

Politique d'erreur (au lieu de « s'arrêter au premier incident ») :
- un incident sur un tour (envoi non confirmé, délai dépassé, « Oops! Something
  happened », limite de débit) abandonne la tentative et rejoue TOUTE la
  conversation dans un chat neuf : on ne mélange jamais deux chats dans une
  même conversation, et on ne rejoue jamais un tour isolé hors contexte ;
- attente croissante entre tentatives, longue pause sur limite de débit ;
- disjoncteur : plusieurs conversations échouées d'affilée → pause puis
  relance du navigateur ; si cela se répète → arrêt propre, reprise possible ;
- session dégradée (presque que des « aucune information ») → relance du
  navigateur et nouvelle passe des conversations concernées.
La reprise est automatique : les conversations déjà COMPLETE sont sautées.
"""
from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .catalogue import Catalogue, Conversation
from .scoring import is_no_info, technical_kind
from .store import Store, now
from .transports.base import AnswerTimeout, SendError, Transport

log = logging.getLogger("pia_bench")


class CampaignStopped(RuntimeError):
    """Arrêt volontaire et propre de la campagne (reprise possible avec --resume)."""


class AgentTechnicalError(RuntimeError):
    def __init__(self, kind: str, text: str):
        super().__init__(f"{kind}: {text[:120]}")
        self.kind = kind


@dataclass(eq=False)
class Unit:
    conv: Conversation
    repetition: int


# --- campagne -----------------------------------------------------------------
def open_campaign(cfg, name: str | None = None, resume: bool = False) -> tuple[Path, Store]:
    runs = cfg.path(cfg["campaign"]["runs_dir"])
    runs.mkdir(parents=True, exist_ok=True)
    if resume and not name:
        existing = sorted((p for p in runs.iterdir() if (p / "campaign.sqlite3").is_file()),
                          key=lambda p: (p / "campaign.sqlite3").stat().st_mtime)
        if not existing:
            raise CampaignStopped(f"Aucune campagne à reprendre dans {runs}")
        name = existing[-1].name
    name = name or datetime.now().strftime("%Y%m%d_%H%M%S")
    if not re.fullmatch(r"[\w.-]+", name):
        raise ValueError("Nom de campagne : lettres, chiffres, _ . - uniquement")
    folder = runs / name
    return folder, Store(folder / "campaign.sqlite3")


def bind_catalogue(store: Store, catalogue: Catalogue) -> None:
    known = store.get_meta("catalogue_sha256")
    if known and known != catalogue.digest:
        raise CampaignStopped(
            "Le classeur a changé depuis le début de cette campagne (empreinte SHA-256 différente). "
            "Lancez une nouvelle campagne (--campaign autre_nom) plutôt que de mélanger deux versions.")
    if not known:
        store.set_meta("catalogue_sha256", catalogue.digest)
        store.set_meta("catalogue_file", catalogue.path.name)
        store.set_meta("created", now())


def parse_selection(spec: str | None, conversations: list[Conversation]) -> list[Conversation]:
    """« C001-C020,C143 » → conversations correspondantes (ordre du classeur)."""
    if not spec:
        return conversations
    wanted: set[str] = set()
    ids = [c.cid for c in conversations]
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        if "-" in part:
            a, b = (x.strip() for x in part.split("-", 1))
            if a not in ids or b not in ids:
                raise ValueError(f"Bornes inconnues : {part}")
            i, j = ids.index(a), ids.index(b)
            wanted.update(ids[min(i, j):max(i, j) + 1])
        elif part in ids:
            wanted.add(part)
        else:
            raise ValueError(f"Conversation inconnue : {part}")
    return [c for c in conversations if c.cid in wanted]


def plan_units(catalogue: Catalogue, store: Store, selection: str | None = None, start_from: str | None = None,
               limit: int | None = None, repeat: int = 1) -> list[Unit]:
    convs = parse_selection(selection, catalogue.conversations)
    if start_from:
        ids = [c.cid for c in convs]
        if start_from not in ids:
            raise ValueError(f"--from {start_from} : conversation inconnue")
        convs = convs[ids.index(start_from):]
    done = store.completed_units()
    units = [Unit(c, r) for r in range(1, repeat + 1) for c in convs if (c.cid, r) not in done]
    return units[:limit] if limit else units


# --- exécution ----------------------------------------------------------------
class Runner:
    def __init__(self, cfg, store: Store, transport: Transport, folder: Path, sleep=time.sleep):
        self.r = cfg["run"]
        self.store = store
        self.t = transport
        self.folder = folder
        self.shots = folder / "captures"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.sleep = sleep
        self.stats = {"complete": 0, "failed": 0, "attempts": 0, "turns": 0}

    def run(self, units: list[Unit]) -> dict:
        queue = deque(units)
        total = len(queue)
        consecutive_failed = trips = degraded_trips = 0
        window: deque[tuple[int, Unit, bool]] = deque(maxlen=int(self.r["degraded_window"]))
        started = time.monotonic()
        done = 0
        while queue:
            unit = queue.popleft()
            done += 1
            eta = ""
            if done > 1:
                per = (time.monotonic() - started) / (done - 1)
                eta = f" · reste ~{per * (len(queue) + 1) / 60:.0f} min"
            log.info("── %s (répétition %d) · %d/%d%s", unit.conv.cid, unit.repetition, done, total, eta)
            aid = self.run_unit(unit)
            if aid is None:
                self.stats["failed"] += 1
                consecutive_failed += 1
                if consecutive_failed >= self.r["breaker_threshold"]:
                    trips += 1
                    if trips > self.r["breaker_max_trips"]:
                        raise CampaignStopped(
                            f"{consecutive_failed} conversations échouées d'affilée, plusieurs fois : arrêt propre. "
                            "Vérifiez l'agent / la connexion puis relancez avec --resume.")
                    log.warning("Disjoncteur : %d échecs d'affilée → pause %d s puis relance du navigateur",
                                consecutive_failed, self.r["breaker_cooldown"])
                    self.sleep(self.r["breaker_cooldown"])
                    self._recover(hard=True)
                    consecutive_failed = 0
            else:
                self.stats["complete"] += 1
                consecutive_failed = 0
                for q in unit.conv.turns:
                    if q.notable:
                        row = self.store.db.execute("SELECT answer FROM turns WHERE attempt_id=? AND qid=?",
                                                    (aid, q.qid)).fetchone()
                        window.append((aid, unit, is_no_info(row[0] if row else "")))
                if len(window) == window.maxlen and window.maxlen:
                    ratio = sum(x[2] for x in window) / len(window)
                    if ratio >= self.r["degraded_ratio"]:
                        degraded_trips += 1
                        suspects = {x[0]: x[1] for x in window}
                        log.warning("Session dégradée : %.0f %% de « aucune information » sur les %d derniers tours "
                                    "à valeur connue → %d conversation(s) rejouée(s) après relance du navigateur",
                                    ratio * 100, len(window), len(suspects))
                        if degraded_trips > 1:
                            self.store.mark_suspect(suspects, "session dégradée (répétée)")
                            raise CampaignStopped("Session dégradée deux fois : arrêt propre, voir l'historique "
                                                  "de l'agent dans Copilot Studio puis --resume.")
                        self.store.mark_suspect(suspects, "session dégradée : rejouée")
                        for u in reversed(list(dict.fromkeys(suspects.values()))):
                            queue.appendleft(u)
                            total += 1
                        window.clear()
                        self.sleep(self.r["breaker_cooldown"])
                        self._recover(hard=True)
            if queue:
                self.sleep(self.r["between_conversations"])
        return self.stats

    def run_unit(self, unit: Unit) -> int | None:
        conv, rep = unit.conv, unit.repetition
        max_attempts = int(self.r["max_attempts"])
        for attempt in range(1, max_attempts + 1):
            aid, attempt_no = self.store.start_attempt(conv.cid, rep, self.t.name)
            self.stats["attempts"] += 1
            chat = None
            try:
                chat = self.t.new_conversation()
                for i, q in enumerate(conv.turns):
                    self._ask(aid, chat, q)
                    if i < len(conv.turns) - 1:
                        self.sleep(self.r["think_time"])
                self.store.finish_attempt(aid, "COMPLETE", chat_url=getattr(chat, "url", None))
                return aid
            except KeyboardInterrupt:
                self.store.finish_attempt(aid, "ABORTED", "Ctrl+C", chat_url=getattr(chat, "url", None))
                raise
            except Exception as e:
                shot = self.shots / f"{conv.cid}_r{rep}_t{attempt_no}.png"
                shot_ok = self.t.screenshot(shot)
                self.store.finish_attempt(aid, "FAILED", f"{type(e).__name__}: {e}", getattr(chat, "url", None),
                                          shot.name if shot_ok else None)
                log.warning("   ✗ tentative %d/%d : %s: %s", attempt, max_attempts, type(e).__name__, e)
                if attempt == max_attempts:
                    log.error("   %s abandonnée pour cette passe (sera retentée au prochain --resume)", conv.cid)
                    return None
                rate_limited = isinstance(e, AgentTechnicalError) and e.kind == "RATE_LIMIT"
                wait = self.r["rate_limit_cooldown"] if rate_limited else self.r["backoff_base"] * 2 ** (attempt - 1)
                log.info("   nouvelle tentative dans un chat neuf dans %d s", wait)
                self.sleep(wait)
                self._recover(hard=attempt >= 2)
        return None

    def _ask(self, aid: int, chat, q) -> None:
        sent_at = now()
        try:
            reply = chat.ask(q.question, float(self.r["turn_timeout"]), float(self.r["stable_seconds"]))
        except SendError as e:
            self.store.save_turn(aid, q, "SEND_ERROR", None, sent_at, None, str(e))
            raise
        except AnswerTimeout as e:
            self.store.save_turn(aid, q, "TIMEOUT", None, sent_at, None, str(e))
            raise
        except Exception as e:
            self.store.save_turn(aid, q, "ERROR", None, sent_at, None, f"{type(e).__name__}: {e}")
            raise
        kind = technical_kind(reply.text)
        self.store.save_turn(aid, q, kind or "CAPTURED", reply.text, sent_at, reply.latency, meta=reply.meta)
        self.stats["turns"] += 1
        flag = " · aucune info" if is_no_info(reply.text) else ""
        log.info("   %s T%d %s %5.1f s · %d car.%s", q.qid, q.tour, kind or "CAPTURED", reply.latency,
                 len(reply.text), flag)
        if kind:
            raise AgentTechnicalError(kind, reply.text)

    def _recover(self, hard: bool) -> None:
        try:
            self.t.recover(hard=hard)
        except Exception as e:
            log.warning("   remise en état du transport impossible : %s", e)
