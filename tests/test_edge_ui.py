# -*- coding: utf-8 -*-
"""Test de bout en bout du pilotage navigateur sur une fausse interface Copilot
(tests/fake_copilot/agent.html) : saisie, envoi confirmé, « Mise en place en cours… »
ignoré, streaming, bouton Arrêter, chat neuf automatique, « Oops! » rejoué."""
from __future__ import annotations

import functools
import json
import shutil
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from pia_bench import report as R
from pia_bench import scoring as S
from pia_bench.catalogue import load_catalogue
from pia_bench.runner import Runner, bind_catalogue, open_campaign, plan_units
from pia_bench.transports.edge_ui import EdgeUITransport

FAKE = Path(__file__).resolve().parent / "fake_copilot" / "agent.html"


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def fake_site(tmp_path, cfg):
    cat = load_catalogue(cfg.path(cfg["catalogue"]["path"]))
    site = tmp_path / "site"
    site.mkdir()
    shutil.copy(FAKE, site / "agent.html")
    answers = {q.question: f"Résultat Information trouvée Pour le fonds {q.produit} : {q.attendu}"
               for q in cat.questions if q.notable}
    oops = [cat.conversations[1].turns[2].question]  # tour 3 de C002 : erreur plateforme une fois
    (site / "answers.json").write_text(json.dumps({"answers": answers, "oops_once": oops, "delay": 300}),
                                       encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/agent.html", cat
    server.shutdown()


def chromium_path() -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return p.chromium.executable_path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def edge_cfg(cfg, url, tmp_path, strategies, mode="launch"):
    e = cfg["edge"]
    e.update(channel="", headless=True, agent_url=url, profile_dir=str(tmp_path / "profile"),
             new_chat=strategies, page_load_timeout=15, mode=mode, cdp_port=free_port())
    if mode == "attach":
        e["executable_path"] = chromium_path()  # sur le poste : msedge.exe détecté automatiquement
        e["extra_args"] = ["--no-sandbox"]       # conteneur de test exécuté en root
    return cfg


def close_browser(port: int) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        browser.new_browser_cdp_session().send("Browser.close")


@pytest.mark.parametrize("strategies,mode", [(["url"], "attach"), (["button"], "launch")])
def test_edge_campaign_on_fake_copilot(fake_site, cfg, tmp_path, strategies, mode):
    url, cat = fake_site
    edge_cfg(cfg, url, tmp_path, strategies, mode)
    folder, store = open_campaign(cfg, "edge")
    bind_catalogue(store, cat)
    t = EdgeUITransport(cfg, folder, interactive=False)
    t.start()
    try:
        # aucune trace d'automatisation visible par la page (ce qui bloque la connexion Microsoft)
        assert t.page.evaluate("navigator.webdriver") is False
        units = plan_units(cat, store, "C001-C003")
        stats = Runner(cfg, store, t, folder).run(units)
    finally:
        t.close()
    if mode == "attach":
        assert t._cdp_alive()        # Edge reste ouvert (et connecté) après la campagne
        close_browser(cfg["edge"]["cdp_port"])
    assert stats["complete"] == 3 and stats["failed"] == 0

    final = store.final_turns()
    assert len(final) == 15
    by_cid: dict[str, set[str]] = {}
    for row in final:
        # la fausse interface signe chaque réponse avec la position dans SON chat et l'id du chat
        assert f"[tour {row['tour']} chat " in row["answer"]
        assert "Mise en place" not in row["answer"]
        by_cid.setdefault(row["cid"], set()).add(row["answer"].rsplit("chat ", 1)[1])
    assert all(len(ids) == 1 for ids in by_cid.values())          # une conversation = un seul chat
    if strategies == ["url"]:
        assert len(set().union(*by_cid.values())) == 3            # trois chats différents (rechargement)

    attempts = [(a["cid"], a["status"]) for a in store.attempts()]
    assert ("C002", "FAILED") in attempts                          # « Oops! » → conversation rejouée
    shots = [a["screenshot"] for a in store.attempts() if a["status"] == "FAILED"]
    assert shots and (folder / "captures" / shots[0]).is_file()

    R.score_campaign(cfg, cat, store)
    verdicts = {r.verdict for r in R.collect(cat, store, include_missing=False)}
    assert verdicts == {S.CORRECT, S.ABSTENTION}
    store.close()
