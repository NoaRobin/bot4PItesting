# -*- coding: utf-8 -*-
"""Agent simulé : répond à partir des valeurs attendues du classeur, avec un taux
réglable de « aucune information », de valeurs fausses et d'erreurs techniques."""
from __future__ import annotations

import random
import time

from .base import Conversation, Reply, Transport


class FakeConversation(Conversation):
    def __init__(self, transport: "FakeTransport", n: int):
        self.t = transport
        self.url = f"fake://conversation/{n}"

    def ask(self, question: str, timeout: float, stable: float) -> Reply:
        t = self.t
        start = time.monotonic()
        if t.latency:
            time.sleep(t.latency)
        q = t.by_text.get(question)
        r = t.rng.random()
        if r < t.tech_error_rate:
            text = "Oops! Something happened. Can you try again?"
        elif q is None or not q.notable or r < t.tech_error_rate + t.no_info_rate:
            text = "Résultat Aucune information disponible pour cette demande."
        elif r < t.tech_error_rate + t.no_info_rate + t.wrong_rate:
            text = f"Résultat Information trouvée Pour le fonds {q.produit} : valeur 999."
        else:
            text = f"Résultat Information trouvée Pour le fonds {q.produit}, {q.champ} : {q.attendu}"
        return Reply(text=text, latency=round(time.monotonic() - start, 3))


class FakeTransport(Transport):
    name = "fake"

    def __init__(self, cfg, catalogue):
        f = cfg["fake"]
        self.rng = random.Random(f["seed"])
        self.no_info_rate = f["no_info_rate"]
        self.wrong_rate = f["wrong_rate"]
        self.tech_error_rate = f["tech_error_rate"]
        self.latency = f["latency"]
        self.by_text = {q.question: q for q in (catalogue.questions if catalogue else [])}
        self.count = 0

    def new_conversation(self) -> Conversation:
        self.count += 1
        return FakeConversation(self, self.count)
