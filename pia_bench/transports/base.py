# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class TransportError(RuntimeError):
    """Problème de transport : la tentative est abandonnée et rejouée dans un chat neuf."""


class SendError(TransportError):
    """La question n'a pas pu être envoyée (rien n'est parti, ou envoi non confirmé)."""


class AnswerTimeout(TransportError):
    """Pas de réponse finale stable avant le délai."""


@dataclass
class Reply:
    text: str
    latency: float
    meta: dict = field(default_factory=dict)


class Conversation:
    url: str | None = None

    def ask(self, question: str, timeout: float, stable: float) -> Reply:  # pragma: no cover
        raise NotImplementedError


class Transport:
    name = "base"

    def start(self) -> None:
        pass

    def new_conversation(self) -> Conversation:  # pragma: no cover
        raise NotImplementedError

    def recover(self, hard: bool = False) -> None:
        """Remet le transport en état (rechargement, relance du navigateur…)."""

    def screenshot(self, path: Path) -> bool:
        return False

    def close(self) -> None:
        pass
