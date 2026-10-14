# -*- coding: utf-8 -*-
"""Transports : la manière de parler à l'agent.

- edge       : pilote l'interface de chat dans Edge (Playwright), comme un utilisateur ;
- directline : API Direct Line de Copilot Studio (sans navigateur, si le canal est ouvert) ;
- fake       : agent simulé, pour tester toute la chaîne sans consommer l'agent.
"""
from __future__ import annotations

from .base import Reply, Transport, TransportError, SendError, AnswerTimeout


def make_transport(name: str, cfg, campaign_dir, catalogue=None, interactive: bool = True) -> Transport:
    if name == "edge":
        from .edge_ui import EdgeUITransport
        return EdgeUITransport(cfg, campaign_dir, interactive=interactive)
    if name == "directline":
        from .directline import DirectLineTransport
        return DirectLineTransport(cfg)
    if name == "fake":
        from .fake import FakeTransport
        return FakeTransport(cfg, catalogue)
    raise ValueError(f"Transport inconnu : {name!r} (edge | directline | fake)")


__all__ = ["Reply", "Transport", "TransportError", "SendError", "AnswerTimeout", "make_transport"]
