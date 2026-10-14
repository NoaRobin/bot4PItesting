# -*- coding: utf-8 -*-
"""Notation automatique des réponses (pré-verdicts déterministes).

Reprend les verdicts du classeur de résultats :
  Correct · Pas d’info à tort · Incorrect · Abstention correcte ·
  Valeur sur cellule vide · Échec technique · À confirmer · Non capturé

Neutralise les défauts connus du benchmark (AUDIT_BENCHMARK) :
  - libellés EN dans la base / réponses FR : « Unit Trust (FCP) », table d'équivalences ;
  - dates stockées en UTC : un décalage d'un jour est accepté et signalé ;
  - nombres au format français (0,143 %) ;
  - noms « NOM Prénom » / « Prénom Nom » ;
  - « Information trouvée » + « Aucune information » dans la même réponse : signalé.
Une réponse que les règles ne savent pas trancher part en « À confirmer »
(relecture humaine ou `judge`), plutôt que d'être notée fausse à tort.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .config import RATE_LIMIT_PATTERNS, TECH_ERROR_PATTERNS

CORRECT = "Correct"
NO_INFO = "Pas d’info à tort"
INCORRECT = "Incorrect"
ABSTENTION = "Abstention correcte"
INVENTED = "Valeur sur cellule vide"
TECH = "Échec technique"
REVIEW = "À confirmer"
NOT_CAPTURED = "Non capturé"
ALL_VERDICTS = [CORRECT, NO_INFO, INCORRECT, ABSTENTION, INVENTED, TECH, REVIEW, NOT_CAPTURED]

PARTICLES = {"de", "du", "des", "la", "le", "d", "van", "von", "der", "di", "da"}
WEAK = {"non", "no", "oui", "yes", "e", "s", "g", "n", "y"}

MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

NO_INFO_PATTERNS = [
    r"\baucune (information|donnee|valeur)s?\b(?! (complementaire|supplementaire|pertinente|additionnelle))",
    r"\bpas d (information|donnee)s?\b(?! (complementaire|supplementaire))",
    r"\bje ne (trouve|dispose|vois|parviens|peux pas)",
    r"\b(n est|ne sont) pas (renseigne|disponible|indique|precise|communique|trouve)",
    r"\bnon (renseigne|disponible|communique)e?s?\b",
    r"\bne (figure|figurent|semble) pas\b",
    r"\b(no information|not available|could not find|couldn t find|no data)\b",
    r"\bne permet(tent)? pas (de|d) (confirmer|identifier|determiner|trouver)",
    # « Aucun deuxième gérant secondaire n’est renseigné », « aucune note … n’est indiquée »
    r"\baucune? (\w+ ){0,8}?(n est|ne sont|n a ete|n ont ete) (actuellement |pas )?(renseigne|indique|disponible|enregistre|declare|trouve|identifie|precise)",
]
FOUND_PATTERN = r"\binformation trouvee\b"


def norm(text: str | None) -> str:
    """Minuscules, sans accents, ponctuation → espaces."""
    s = unicodedata.normalize("NFKD", str(text or "")).replace("œ", "oe").replace("Œ", "oe")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[^0-9a-z]+", " ", s)
    return f" {s.strip()} " if s.strip() else " "


def tokens(text: str) -> list[str]:
    return norm(text).split()


def main_part(answer: str) -> str:
    """Partie « Résultat » (avant « Détails complémentaires »)."""
    return re.split(r"d[ée]tails compl[ée]mentaires", answer or "", maxsplit=1, flags=re.I)[0]


def is_no_info(answer: str) -> bool:
    n = norm(main_part(answer))
    return any(re.search(p, n) for p in NO_INFO_PATTERNS)


def is_contradictory(answer: str) -> bool:
    n = norm(answer)
    return bool(re.search(FOUND_PATTERN, n)) and any(re.search(p, norm(main_part(answer))) for p in NO_INFO_PATTERNS)


def technical_kind(answer: str | None) -> str | None:
    """'RATE_LIMIT', 'TECH_ERROR' ou None, d'après le texte de la réponse."""
    low = (answer or "").casefold()
    if any(p in low for p in RATE_LIMIT_PATTERNS):
        return "RATE_LIMIT"
    if any(p in low for p in TECH_ERROR_PATTERNS) and len(low) < 400:
        return "TECH_ERROR"
    return None


# --- équivalences FR/EN --------------------------------------------------------
class Equivalences:
    """Groupes de synonymes, un groupe par ligne : `World;Monde`."""

    def __init__(self, groups: Iterable[Iterable[str]] = ()):
        self.index: dict[str, set[str]] = {}
        for group in groups:
            normed = {norm(x).strip() for x in group if norm(x).strip()}
            for item in normed:
                self.index.setdefault(item, set()).update(normed)

    @classmethod
    def load(cls, path: Path | None) -> "Equivalences":
        if not path or not path.is_file():
            return cls()
        groups = []
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f, delimiter=";"):
                if row and not row[0].lstrip().startswith("#"):
                    groups.append([c for c in row if c.strip()])
        return cls(groups)

    def expand(self, value: str) -> set[str]:
        key = norm(value).strip()
        return self.index.get(key, set()) | {key}


# --- extraction de nombres et de dates ---------------------------------------
_NUM_RE = re.compile(r"(?<![\w.,/])[-+]?(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?(?![\w/])")


def numbers(text: str) -> list[tuple[float, int]]:
    """(valeur, nombre de décimales) des nombres d'un texte, format FR ou EN."""
    out = []
    for m in _NUM_RE.finditer(text or ""):
        raw = re.sub(r"[   ]", "", m.group(0)).replace(",", ".")
        try:
            out.append((float(raw), len(raw.split(".")[1]) if "." in raw else 0))
        except ValueError:
            pass
    return out


def parse_number(value: str) -> float | None:
    v = (value or "").strip().replace(",", ".").rstrip("%").strip()
    try:
        return float(v)
    except ValueError:
        return None


def dates(text: str) -> list[date]:
    found: list[date] = []
    n = norm(text)
    raw = text or ""
    for d, m, y in re.findall(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", raw):
        found.append(_mk(int(y), int(m), int(d)))
    for y, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})", raw):
        found.append(_mk(int(y), int(m), int(d)))
    for d, mon, y in re.findall(rf" (\d{{1,2}})(?:er)? ({_MONTH_RE}) (\d{{4}}) ", n):
        found.append(_mk(int(y), MONTHS[mon], int(d)))
    for mon, d, y in re.findall(rf" ({_MONTH_RE}) (\d{{1,2}}) (?:st |nd |rd |th )?(\d{{4}}) ", n):
        found.append(_mk(int(y), MONTHS[mon], int(d)))
    return [x for x in found if x]


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def expected_dates(value: str) -> tuple[list[date], bool]:
    """Dates attendues ; booléen vrai si l'export porte une heure tardive (UTC)."""
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", value or "")
    if m:
        dt = datetime(*map(int, m.groups()))
        return [dt.date()], dt.hour >= 22
    return dates(value), False


# --- correspondance valeur attendue / réponse ----------------------------------
@dataclass
class Match:
    ok: bool
    how: str = ""
    weak: bool = False
    typed_mismatch: bool = False   # nombre/date/code attendu, un autre a été donné
    competitor: str = ""           # autre valeur connue du même champ trouvée dans la réponse
    flags: list[str] = field(default_factory=list)


def _contains(haystack_norm: str, needle: str) -> bool:
    n = norm(needle)
    return n.strip() != "" and n in haystack_norm


def _is_code(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{6,}", value.strip())) and bool(re.search(r"\d", value)) and bool(re.search(r"[A-Z]", value))


def candidates(expected: str, eq: Equivalences) -> list[set[str]]:
    """Alternatives acceptables. Une liste « A;B » exige chaque élément (liste de groupes)."""
    parts = [p.strip() for p in expected.split(";") if p.strip()] if ";" in expected else [expected.strip()]
    groups = []
    for part in parts:
        alts = {part}
        m = re.fullmatch(r"(.+?)\s*\((.+)\)\s*", part)
        if m:  # « Unit Trust (FCP) », « LAFONT (DE) Alice » est traité par les noms
            alts |= {m.group(1).strip(), m.group(2).strip()}
        expanded: set[str] = set()
        for a in alts:
            expanded |= eq.expand(a)
        groups.append({x for x in expanded if x})
    return groups


def match_value(expected: str, answer: str, champ: str = "", produit: str = "",
                eq: Equivalences | None = None, competitors: Iterable[str] = ()) -> Match:
    eq = eq or Equivalences()
    expected = (expected or "").strip()
    text = answer or ""
    if produit:  # les chiffres du nom du fonds (« Target 2029 ») ne sont pas des réponses
        text = re.sub(re.escape(produit), " ", text, flags=re.I)
    a_norm = norm(text)

    # 1. Dates
    exp_dates, late_hour = expected_dates(expected)
    if exp_dates and len(expected) <= 40 and parse_number(expected) is None:
        got = dates(text)
        for e in exp_dates:
            if e in got:
                return Match(True, "date")
            if any(abs((g - e).days) == 1 for g in got):
                return Match(True, "date ±1 jour (UTC/Paris)", flags=["decalage_date"])
        return Match(False, "date", typed_mismatch=bool(got))

    # 2. Nombres
    exp_num = parse_number(expected)
    if exp_num is not None:
        got = numbers(text)
        exp_dec = len(expected.replace(",", ".").split(".")[1]) if "." in expected.replace(",", ".") else 0
        for value, dec in got:
            if abs(value - exp_num) < 1e-9:
                return Match(True, "nombre", weak=exp_dec == 0 and abs(exp_num) < 10)
            if dec >= 1 and dec < exp_dec and abs(round(exp_num, dec) - value) < 1e-9:
                return Match(True, "nombre arrondi", flags=["arrondi"])
        return Match(False, "nombre", typed_mismatch=bool(got))

    # 3. Codes (LEI, ISIN, code AMF)
    if _is_code(expected):
        if _contains(a_norm, expected):
            return Match(True, "code")
        other = [t for t in re.findall(r"\b[A-Z0-9]{6,}\b", text) if _is_code(t)]
        return Match(False, "code", typed_mismatch=bool(other))

    # 4. Valeurs voisines connues du même champ (ex. « Caceis Bank » vs « CACEIS Bank Luxembourg Branch »)
    comp_found = ""
    exp_n = norm(expected)
    for comp in competitors:
        c = (comp or "").strip()
        if not c or norm(c) == exp_n or len(norm(c).strip()) < 3:
            continue
        if _contains(a_norm, c) and (exp_n.strip() in norm(c) or not _contains(a_norm, expected)):
            comp_found = c if len(c) > len(comp_found) else comp_found

    # 5. Texte / énumérations / noms
    groups = candidates(expected, eq)
    hits = [next((alt for alt in sorted(g, key=len, reverse=True) if _contains(a_norm, alt)), None) for g in groups]
    if all(hits):
        if comp_found and exp_n.strip() in norm(comp_found):
            return Match(False, "valeur voisine plus précise", competitor=comp_found)
        weak = all(h.strip() in WEAK or len(h.strip()) <= 2 for h in hits)
        if weak and not all(_contains(norm(main_part(text)), h) for h in hits):
            return Match(False, "oui/non trouvé seulement dans les détails")
        return Match(True, "texte", weak=weak)

    # Noms : « MARTIN Paul » ↔ « Paul Martin », particules ignorées
    exp_tokens = [t for t in tokens(re.sub(r"[()]", " ", expected)) if t not in PARTICLES]
    ans_tokens = set(tokens(text))
    if 1 < len(exp_tokens) <= 6 and all(t in ans_tokens for t in exp_tokens):
        if comp_found and exp_n.strip() in norm(comp_found):
            return Match(False, "valeur voisine plus précise", competitor=comp_found)
        return Match(True, "mots (ordre libre)")

    # Textes longs (objectif de gestion, allocation…) : rappel des mots porteurs
    content = [t for t in exp_tokens if len(t) > 3]
    if len(content) >= 12:
        recall = sum(t in ans_tokens for t in content) / len(content)
        if recall >= 0.85:
            return Match(True, f"texte long ({recall:.0%} des mots)")
        return Match(False, f"texte long ({recall:.0%} des mots)", flags=["texte_long"])

    return Match(False, "texte", competitor=comp_found)


# --- verdict -----------------------------------------------------------------
@dataclass
class Verdict:
    verdict: str
    reason: str
    flags: list[str] = field(default_factory=list)


def score(expected: str, notable: bool, answer: str | None, champ: str = "", produit: str = "",
          eq: Equivalences | None = None, competitors: Iterable[str] = (), turn_status: str = "CAPTURED") -> Verdict:
    if answer is None or (turn_status not in ("CAPTURED",) and not answer):
        return Verdict(NOT_CAPTURED, turn_status or "pas de réponse")
    if turn_status in ("TECH_ERROR", "RATE_LIMIT") or technical_kind(answer):
        return Verdict(TECH, "message d'erreur de la plateforme")
    flags = ["contradictoire"] if is_contradictory(answer) else []
    no_info = is_no_info(answer)

    if not notable:
        if no_info:
            return Verdict(ABSTENTION, "cellule vide, l'agent n'invente pas", flags)
        return Verdict(INVENTED, "cellule vide mais une valeur est donnée : à vérifier", flags)

    m = match_value(expected, answer, champ, produit, eq, competitors)
    flags += m.flags
    if m.ok and not (no_info and m.weak):
        return Verdict(CORRECT, m.how, flags)
    if no_info:
        return Verdict(NO_INFO, "l'agent dit ne pas avoir la donnée", flags)
    if m.competitor:
        return Verdict(INCORRECT, f"autre valeur du même champ : {m.competitor}", flags)
    if m.typed_mismatch:
        return Verdict(INCORRECT, f"{m.how} différent(e) de l'attendu", flags)
    return Verdict(REVIEW, f"valeur non retrouvée ({m.how}) : libellé traduit ou reformulé ?", flags)
