# -*- coding: utf-8 -*-
"""Pilotage de l'interface de chat dans Edge (Playwright, profil persistant).

Différences avec les scripts v21–v28 :
- le chat neuf est ouvert par le script (URL de l'agent mémorisée au `setup`,
  repli sur le bouton « Nouvelle conversation ») : plus de touche Entrée à presser ;
- l'envoi est confirmé dans la page (message utilisateur apparu, saisie vidée
  ou génération en cours) ; la saisie est vérifiée avant d'appuyer sur Entrée ;
- la réponse est la somme des NOUVELLES bulles de l'agent depuis l'envoi
  (comptage, et non plus comparaison au texte des questions) ;
- un message d'erreur de la plateforme est rendu tel quel : c'est le runner
  qui décide de rejouer la conversation.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..scoring import norm, technical_kind
from .base import AnswerTimeout, Conversation, Reply, SendError, Transport, TransportError


class EdgeConversation(Conversation):
    def __init__(self, t: "EdgeUITransport"):
        self.t = t
        self.url = None

    def ask(self, question: str, timeout: float, stable: float) -> Reply:
        t = self.t
        question = " ".join(question.split())  # pas de retour à la ligne : Entrée enverrait trop tôt
        users_before = len(t.texts(t.c["user_selectors"])[0])
        bots_before = len(t.texts(t.c["assistant_selectors"])[0])
        box = t.composer()
        if box is None:
            raise SendError("Zone de saisie introuvable")
        t.type_into(box, question)
        sent_clock = time.monotonic()
        box.press("Enter")
        if not t.wait_dispatch(box, question, users_before, bots_before, 20):
            raise SendError("Envoi non confirmé dans la page (question peut-être non partie)")
        self.url = t.page.url

        deadline = sent_clock + timeout
        last, since, first_content, selector = None, None, None, None
        while time.monotonic() < deadline:
            texts, selector = t.texts(t.c["assistant_selectors"])
            new = [x for x in texts[bots_before:] if x.strip()]
            current = "\n\n".join(new)
            if current and not t.waiting(current):
                first_content = first_content or time.monotonic()
                if current == last:
                    quiet = time.monotonic() - since
                    if technical_kind(current) and quiet >= 2:
                        break
                    if quiet >= stable and not t.generating():
                        break
                else:
                    last, since = current, time.monotonic()
            else:
                last, since = None, None
            time.sleep(0.5)
        else:
            raise AnswerTimeout(f"Pas de réponse finale stable en {timeout:.0f} s")
        return Reply(
            text=last,
            latency=round(since - sent_clock, 2),
            meta={"first_content_s": round(first_content - sent_clock, 2), "selector": selector, "url": self.url},
        )


class EdgeUITransport(Transport):
    name = "edge"

    def __init__(self, cfg, campaign_dir: Path | None = None, interactive: bool = True):
        self.cfg = cfg
        self.c = cfg["edge"]
        self.interactive = interactive
        self.state_path = cfg.path(".pia_bench_state.json")
        self.profile = cfg.path(self.c["profile_dir"])
        self.new_chat_re = re.compile(self.c["new_chat_button"], re.I)
        self.stop_re = re.compile(self.c["stop_button"], re.I)
        self.send_re = re.compile(self.c["send_button"], re.I)
        self.waiting_patterns = [norm(p).strip() for p in self.c["waiting_patterns"]]
        self.pw = self.ctx = self.page = self.frame = None

    # --- cycle de vie -----------------------------------------------------
    @property
    def agent_url(self) -> str:
        if self.c.get("agent_url"):
            return self.c["agent_url"]
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8")).get("agent_url", "")
        except (OSError, ValueError):
            return ""

    def save_agent_url(self, url: str) -> None:
        self.state_path.write_text(json.dumps({"agent_url": url}, indent=2), encoding="utf-8")

    def start(self) -> None:
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self._launch()
        self._open_agent()

    def _launch(self) -> None:
        kwargs = {"headless": bool(self.c["headless"]), "viewport": None}
        if not self.c["headless"]:
            kwargs["args"] = ["--start-maximized"]
        if self.c.get("executable_path"):
            kwargs["executable_path"] = self.c["executable_path"]
        elif self.c.get("channel"):
            kwargs["channel"] = self.c["channel"]
        self.ctx = self.pw.chromium.launch_persistent_context(str(self.profile), **kwargs)
        self.ctx.set_default_timeout(15_000)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.on("dialog", lambda d: d.accept())

    def _open_agent(self) -> None:
        url = self.agent_url
        if not url:
            if not self.interactive:
                raise TransportError("URL de l'agent inconnue : lancez d'abord `python -m pia_bench setup`")
            self.setup()
            return
        self.page.goto(url, wait_until="domcontentloaded")
        if self.wait_composer(self.c["page_load_timeout"]):
            return
        if not self.interactive:
            raise TransportError("Zone de saisie introuvable après chargement (session expirée ?)")
        print("\nZone de saisie introuvable : connectez-vous dans la fenêtre Edge et ouvrez l'agent,")
        input("puis appuyez sur Entrée ici (une seule fois pour toute la campagne) : ")
        if not self.wait_composer(60):
            raise TransportError("Zone de saisie toujours introuvable")

    def setup(self) -> str:
        """Premier lancement : l'opérateur ouvre l'agent une fois, le script retient l'URL."""
        print("\nDans la fenêtre Edge : connectez-vous, ouvrez Product Info Assistant dans un chat VIERGE.")
        print("N'envoyez aucun message.")
        input("Quand la zone « Message Product Info Assistant » est visible, appuyez sur Entrée : ")
        end = time.monotonic() + 60
        while time.monotonic() < end:
            for page in self.ctx.pages:
                if not page.is_closed() and self._find_composer(page):
                    self.page = page
                    self.wait_composer(5)
                    url = page.url
                    self.save_agent_url(url)
                    print(f"URL de l'agent enregistrée dans {self.state_path.name} : {url}")
                    if "conversation" in url.lower():
                        print("Attention : l'URL semble contenir un identifiant de conversation. "
                              "Si les chats ne repartent pas de zéro, renseignez edge.agent_url à la main.")
                    return url
            time.sleep(1)
        raise TransportError("Aucun onglet avec la zone de saisie de l'agent")

    def recover(self, hard: bool = False) -> None:
        dead = self.page is None or self.page.is_closed()
        if hard or dead:
            try:
                if self.ctx:
                    self.ctx.close()
            except Exception:
                pass
            self._launch()
            self._open_agent()
            return
        try:
            self.page.reload(wait_until="domcontentloaded")
            self.wait_composer(self.c["page_load_timeout"])
        except Exception:
            self.recover(hard=True)

    def screenshot(self, path: Path) -> bool:
        try:
            self.page.screenshot(path=str(path))
            return True
        except Exception:
            return False

    def close(self) -> None:
        for closer in (lambda: self.ctx and self.ctx.close(), lambda: self.pw and self.pw.stop()):
            try:
                closer()
            except Exception:
                pass

    # --- chat neuf --------------------------------------------------------
    def new_conversation(self) -> Conversation:
        errors = []
        for strategy in self.c["new_chat"]:
            try:
                if strategy == "url":
                    if not self.agent_url:
                        continue
                    self.page.goto(self.agent_url, wait_until="domcontentloaded")
                elif strategy == "button":
                    button = self._find_button(self.new_chat_re)
                    if button is None:
                        errors.append("bouton « Nouvelle conversation » introuvable")
                        continue
                    button.click()
                else:
                    raise ValueError(f"Stratégie de chat neuf inconnue : {strategy}")
                if self.wait_blank(self.c["page_load_timeout"]):
                    return EdgeConversation(self)
                errors.append(f"{strategy} : chat non vierge ou zone de saisie absente")
            except Exception as e:  # erreur Playwright : on tente la stratégie suivante
                errors.append(f"{strategy} : {type(e).__name__}: {e}")
        raise TransportError("Impossible d'ouvrir un chat neuf : " + " | ".join(errors))

    def wait_blank(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.wait_composer(min(5, max(0.5, end - time.monotonic()))):
                box = self.composer()
                users = self.texts(self.c["user_selectors"])[0]
                if box is not None and not users and not self.draft(box):
                    return True
            time.sleep(0.5)
        return False

    # --- DOM --------------------------------------------------------------
    def _find_composer(self, page):
        for css in self.c["composer_selectors"]:
            for frame in page.frames:
                try:
                    loc = frame.locator(css)
                    for i in range(loc.count()):
                        el = loc.nth(i)
                        if el.is_visible() and el.is_editable():
                            if self.c["strict_agent_check"] and not self._names_agent(el):
                                continue
                            return frame, el
                except Exception:
                    continue
        return None

    def _names_agent(self, el) -> bool:
        label = " ".join(filter(None, (el.get_attribute("aria-label"), el.get_attribute("data-placeholder"),
                                       el.get_attribute("placeholder"))))
        return self.c["agent_name"].casefold() in label.casefold()

    def wait_composer(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while True:
            found = self._find_composer(self.page)
            if found:
                self.frame = found[0]
                return True
            if time.monotonic() >= end:
                return False
            time.sleep(0.5)

    def composer(self):
        found = self._find_composer(self.page)
        if found:
            self.frame = found[0]
            return found[1]
        return None

    def texts(self, selectors) -> tuple[list[str], str | None]:
        """Textes visibles du premier sélecteur qui trouve quelque chose, dans le frame du chat."""
        frames = [self.frame] if self.frame else self.page.frames
        for css in selectors:
            for frame in frames:
                try:
                    loc = frame.locator(css)
                    n = loc.count()
                    if not n:
                        continue
                    out = []
                    for i in range(n):
                        el = loc.nth(i)
                        if el.is_visible():
                            out.append(el.inner_text(timeout=2000).strip())
                    if out:
                        return out, css
                except Exception:
                    continue
        return [], None

    def draft(self, box) -> str:
        for read in (lambda: box.input_value(timeout=1000), lambda: box.inner_text(timeout=1000)):
            try:
                value = " ".join((read() or "").split())
                if value and value.casefold() not in ("message product info assistant", "message copilot"):
                    return value
            except Exception:
                continue
        return ""

    def type_into(self, box, question: str) -> None:
        if self.draft(box):
            box.click()
            box.press("Control+A")
            box.press("Delete")
        box.click()
        try:
            box.fill(question)
        except Exception:
            pass
        if norm(self.draft(box)) != norm(question):
            box.press("Control+A")
            box.press("Delete")
            self.page.keyboard.insert_text(question)
        if norm(self.draft(box)) != norm(question):
            raise SendError("Saisie non confirmée dans la zone de message ; rien n'a été envoyé")

    def wait_dispatch(self, box, question: str, users_before: int, bots_before: int, seconds: float) -> bool:
        start = time.monotonic()
        clicked = False
        while time.monotonic() - start < seconds:
            if len(self.texts(self.c["user_selectors"])[0]) > users_before:
                return True
            if len(self.texts(self.c["assistant_selectors"])[0]) > bots_before or self.generating():
                return True
            current = self.draft(box) if box.is_visible() else ""
            if not current:
                return True
            if not clicked and time.monotonic() - start > 4 and norm(current) == norm(question):
                button = self._find_button(self.send_re)
                if button is not None:
                    button.click()
                clicked = True
            time.sleep(0.3)
        return False

    def _find_button(self, pattern: re.Pattern):
        frames = [self.frame] if self.frame else []
        frames += [f for f in self.page.frames if f is not self.frame]
        for frame in frames:
            try:
                loc = frame.get_by_role("button", name=pattern)
                for i in range(loc.count()):
                    if loc.nth(i).is_visible() and loc.nth(i).is_enabled():
                        return loc.nth(i)
            except Exception:
                continue
        return None

    def generating(self) -> bool:
        return self._find_button(self.stop_re) is not None

    def waiting(self, text: str) -> bool:
        n = norm(text).strip()
        if n in ("product info assistant", "product info assistant said", norm(self.c["agent_name"]).strip()):
            return True
        return len(n) < 200 and any(p in n for p in self.waiting_patterns)
