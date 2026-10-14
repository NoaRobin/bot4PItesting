# -*- coding: utf-8 -*-
"""Juge LLM (optionnel) pour les réponses que les règles ne savent pas trancher.

N'est jamais lancé automatiquement : `python -m pia_bench judge`.
Envoie question, valeur attendue et réponse de l'agent à l'API Claude :
à faire valider par la conformité avant usage sur des données internes.
Clé lue dans ANTHROPIC_API_KEY (ou profil `ant auth login`).
"""
from __future__ import annotations

import logging
from typing import Literal

from . import scoring as S

log = logging.getLogger("pia_bench")

SYSTEM = """Tu évalues les réponses d'un assistant interne (Product Info Assistant) qui lit un référentiel de fonds.
Pour chaque cas, compare la réponse de l'agent à la valeur exportée de la base et rends UN verdict :
- "Correct" : la valeur de la base est restituée. Accepte les équivalences FR/EN (Unit Trust = FCP,
  UCITS = OPCVM, World = Monde…), les reformulations, les traductions fidèles d'un texte long, les nombres
  au format français, et un décalage d'un jour sur une date (export en UTC, réponse en heure de Paris).
- "Pas d’info à tort" : l'agent dit ne pas avoir la donnée alors que la base la contient.
- "Incorrect" : l'agent donne une autre valeur (champ voisin, autre fonds, autre niveau, autre année…).
- "Abstention correcte" : la base est vide pour ce champ et l'agent ne donne pas de valeur.
- "Valeur sur cellule vide" : la base est vide mais l'agent affirme une valeur.
- "À confirmer" : impossible de trancher sans consulter la fiche (ex. libellé traduit inconnu).
Sois strict : une valeur proche mais différente est Incorrect. Justifie en une phrase, en français."""

Verdict = Literal["Correct", "Pas d’info à tort", "Incorrect", "Abstention correcte", "Valeur sur cellule vide",
                  "À confirmer"]


def judge_rows(cfg, rows: list[dict]) -> list[tuple[dict, str, str]]:
    """rows : dicts avec question, champ, produit, attendu, notable, answer. Retourne (row, verdict, justification)."""
    import anthropic
    from pydantic import BaseModel

    class JudgeOut(BaseModel):
        verdict: Verdict
        justification: str

    client = anthropic.Anthropic()
    out = []
    for i, r in enumerate(rows, 1):
        expected = r["attendu"] if r["notable"] else "(cellule vide dans la base)"
        prompt = (f"Fonds : {r['produit']}\nChamp : {r['champ']}\nQuestion posée : {r['question']}\n"
                  f"Valeur dans la base : {expected}\n\nRéponse de l'agent :\n{r['answer']}")
        try:
            resp = client.messages.parse(
                model=cfg["judge"]["model"],
                max_tokens=4000,
                output_config={"effort": cfg["judge"]["effort"]},
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=JudgeOut,
            )
        except anthropic.RateLimitError:
            log.warning("Limite de débit de l'API : arrêt du juge, relancez plus tard (déjà notés conservés)")
            break
        except anthropic.APIStatusError as e:
            log.warning("%s : erreur API %s, cas ignoré", r["qid"], e.status_code)
            continue
        except anthropic.APIConnectionError:
            log.warning("API injoignable : arrêt du juge")
            break
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            log.warning("%s : pas de verdict exploitable (%s)", r["qid"], resp.stop_reason)
            continue
        out.append((r, resp.parsed_output.verdict, resp.parsed_output.justification))
        log.info("[%d/%d] %s → %s", i, len(rows), r["qid"], resp.parsed_output.verdict)
    return out


def needs_judge(verdict: str, only_uncertain: bool) -> bool:
    if verdict in (S.TECH, S.NOT_CAPTURED):
        return False
    return verdict in (S.REVIEW, S.INVENTED) or not only_uncertain
