"""Règles métier pures : validation du fichier TIS Belges, sélection des lignes Valor,
jours ouvrés. Aucune dépendance Windows : ce module est testable n'importe où."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

HEADER = (
    "ISIN",
    "FundName / Description",
    "Currency",
    "Update Date",
    "NAV Estimated",
    "NAV Final",
    "MONTANT TIS",
    "TYPE FISCALITE",
)
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class ValidationError(Exception):
    """Le fichier n'est pas conforme : il ne doit ni être archivé ni envoyé."""


def date_key(day: date) -> str:
    """Date au format yyyymmdd, tel qu'attendu par le paramètre Excel."""
    return day.strftime("%Y%m%d")


def is_business_day(day: date, skip_dates: list[str]) -> bool:
    return day.weekday() < 5 and date_key(day) not in skip_dates


def date_text(value) -> str:
    """Normalise une date lue dans Excel (texte, entier ou flottant) en 'yyyymmdd'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _pad(row, width: int) -> tuple:
    row = tuple(row[:width])
    return row + (None,) * (width - len(row))


def extract_tis_rows(sheet_rows) -> list[tuple]:
    """Retourne les lignes de données (8 colonnes) situées sous l'en-tête.

    Lève ValidationError si l'en-tête est absent ou différent du modèle attendu.
    """
    rows = [tuple(r) for r in sheet_rows]
    header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0] == "ISIN"),
        None,
    )
    if header_idx is None:
        raise ValidationError("En-tête 'ISIN' introuvable dans l'onglet TIS BE.")

    header = _pad(rows[header_idx], len(HEADER))
    if header != HEADER:
        raise ValidationError(f"En-têtes inattendus : {header}")

    return [
        _pad(r, len(HEADER))
        for r in rows[header_idx + 1 :]
        if r and r[0] not in (None, "")
    ]


def validate_tis_rows(rows: list[tuple], target: str, rules: dict) -> list[str]:
    """Contrôles bloquants. Retourne la liste des anomalies (vide = fichier valide)."""
    errors: list[str] = []

    if not rows:
        return ["Aucune ligne de données : le fichier est vide ou la requête n'a rien renvoyé."]

    if not rules["min_rows"] <= len(rows) <= rules["max_rows"]:
        errors.append(
            f"Nombre de lignes {len(rows)} hors de la plage attendue "
            f"[{rules['min_rows']}-{rules['max_rows']}]."
        )

    wrong_dates = Counter(date_text(r[3]) for r in rows if date_text(r[3]) != target)
    if wrong_dates:
        detail = ", ".join(f"{n} ligne(s) datée(s) {d or 'vide'}" for d, n in wrong_dates.items())
        errors.append(
            f"Date de valeur liquidative différente de {target} : {detail}. "
            "Données probablement non rafraîchies ou pas encore publiées."
        )

    bad_isin = [r[0] for r in rows if not ISIN_RE.match(str(r[0]).strip())]
    if bad_isin:
        errors.append(f"ISIN invalide(s) : {', '.join(map(str, bad_isin[:10]))}")

    if any(not str(r[1] or "").strip() for r in rows):
        errors.append("Nom de fonds vide sur au moins une ligne.")

    bad_ccy = {r[2] for r in rows if r[2] not in rules["currencies"]}
    if bad_ccy:
        errors.append(f"Devise(s) non prévue(s) : {sorted(map(str, bad_ccy))}")

    bad_type = {r[7] for r in rows if r[7] not in rules["types"]}
    if bad_type:
        errors.append(f"Type de fiscalité non prévu : {sorted(map(str, bad_type))}")

    not_numeric = [
        r[0] for r in rows
        if isinstance(r[6], bool) or not isinstance(r[6], (int, float))
    ]
    if not_numeric:
        errors.append(f"Montant TIS non numérique : {len(not_numeric)} ligne(s).")

    if not rules["allow_duplicates"]:
        duplicated = [k for k, n in Counter(rows).items() if n > 1]
        if duplicated:
            errors.append(
                f"{len(duplicated)} ligne(s) strictement identique(s) en double "
                f"(ex. ISIN {duplicated[0][0]}, {duplicated[0][1]})."
            )

    return errors


def select_valor_rows(rows: list[tuple], valor_name: str) -> list[tuple]:
    """Lignes du fonds dont le nom est exactement valor_name, prêtes à être collées
    dans l'historique : cellules vides en None, date en nombre (type majoritaire de
    l'historique)."""
    selected = []
    for r in rows:
        if str(r[1] or "").strip() != valor_name:
            continue
        values = list(r[:8])
        values[3] = int(date_text(values[3])) if date_text(values[3]).isdigit() else values[3]
        values[4] = None if values[4] in ("", None) else values[4]
        selected.append(tuple(values))
    return selected


def count_date(values, target: str) -> int:
    """Nombre de cellules de dates égales à target (utilisé sur l'historique)."""
    return sum(1 for v in values if date_text(v) == target)
