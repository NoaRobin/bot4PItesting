# -*- coding: utf-8 -*-
"""Transport Direct Line v3 (canal « site web / application mobile » de Copilot Studio).

Plus fiable que l'interface (pas de sélecteurs, une conversation API = un chat neuf),
mais exige que l'administrateur de l'agent fournisse soit le secret du canal
(variable d'environnement PIA_DIRECTLINE_SECRET), soit l'URL « token endpoint ».
Si l'agent impose l'authentification de l'utilisateur (Entra ID), ce canal ne suffit pas.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .base import AnswerTimeout, Conversation, Reply, SendError, Transport, TransportError


def _http(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise TransportError(f"Direct Line HTTP {e.code} sur {method} {url.split('?')[0]}") from e
    except urllib.error.URLError as e:
        raise TransportError(f"Direct Line injoignable : {e.reason}") from e
    return json.loads(raw) if raw.strip() else {}


class DirectLineConversation(Conversation):
    def __init__(self, t: "DirectLineTransport", conv_id: str, token: str):
        self.t, self.id, self.token = t, conv_id, token
        self.url = f"directline://{conv_id}"
        self.watermark: str | None = None
        self.user_id = t.c["user_id"]

    def _activities(self) -> list[dict]:
        url = f"{self.t.base}/conversations/{self.id}/activities"
        if self.watermark:
            url += f"?watermark={self.watermark}"
        data = _http("GET", url, self.token)
        self.watermark = data.get("watermark", self.watermark)
        return data.get("activities", [])

    def drain(self) -> None:
        self._activities()

    def ask(self, question: str, timeout: float, stable: float) -> Reply:
        self.drain()  # ignore le message d'accueil et tout ce qui précède
        start = time.monotonic()
        try:
            sent = _http("POST", f"{self.t.base}/conversations/{self.id}/activities", self.token, {
                "type": "message", "from": {"id": self.user_id}, "text": question, "locale": self.t.c["locale"],
            })
        except TransportError as e:
            raise SendError(str(e)) from e
        sent_id = sent.get("id", "")
        parts: list[str] = []
        last_new = None
        first = None
        while time.monotonic() - start < timeout:
            for act in self._activities():
                if act.get("from", {}).get("id") == self.user_id:
                    continue
                if act.get("replyToId") and sent_id and act["replyToId"] != sent_id:
                    continue
                if act.get("type") == "message":
                    text = act.get("text") or _attachments_text(act)
                    if text:
                        parts.append(text.strip())
                        first = first or time.monotonic()
                        last_new = time.monotonic()
                elif act.get("type") == "typing":
                    last_new = time.monotonic()
            if parts and last_new and time.monotonic() - last_new >= stable:
                return Reply("\n\n".join(parts), round(last_new - start, 2),
                             {"first_content_s": round(first - start, 2), "url": self.url})
            time.sleep(self.t.c["poll_interval"])
        raise AnswerTimeout(f"Pas de réponse Direct Line en {timeout:.0f} s")


def _attachments_text(act: dict) -> str:
    """Texte des cartes adaptatives (Copilot Studio renvoie parfois la réponse en carte)."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "TextBlock" and node.get("text"):
                out.append(node["text"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for att in act.get("attachments", []) or []:
        walk(att.get("content"))
    return "\n".join(out)


class DirectLineTransport(Transport):
    name = "directline"

    def __init__(self, cfg):
        self.c = cfg["directline"]
        self.base = self.c["base_url"].rstrip("/")

    def _token(self) -> str:
        if self.c.get("token_endpoint"):
            return _http("GET", self.c["token_endpoint"]).get("token") or ""
        secret = os.environ.get(self.c["secret_env"], "")
        if not secret:
            raise TransportError(f"Ni token_endpoint ni variable {self.c['secret_env']} : Direct Line indisponible")
        return secret

    def start(self) -> None:
        self._token()

    def new_conversation(self) -> Conversation:
        token = self._token()
        data = _http("POST", f"{self.base}/conversations", token)
        conv = DirectLineConversation(self, data["conversationId"], data.get("token") or token)
        if self.c.get("send_start_event"):
            _http("POST", f"{self.base}/conversations/{conv.id}/activities", conv.token, {
                "type": "event", "name": "startConversation", "from": {"id": conv.user_id},
                "locale": self.c["locale"],
            })
            time.sleep(1)
        conv.drain()
        return conv
