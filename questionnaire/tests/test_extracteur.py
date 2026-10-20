"""Tests de bout en bout de l'extracteur, sur des pages de test locales (aucun site réel).

Lancement : py -m pytest questionnaire/tests
Pour utiliser un Chromium précis : QX_NAVIGATEUR_TEST=/chemin/vers/chrome py -m pytest questionnaire/tests
"""

import json
import os
import re
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parent
SITE = ICI / "site_test"
EXTRACTEUR = ICI.parent / "extracteur.py"

# Variante : rubriques en <div>, tiret typographique et espace insécable dans le texte.
MENU_VARIANTE = """<div id="menu">
  <div class="rub" data-rub="gea"><span>GEA&nbsp;&#8211;&nbsp;Informazioni generali sulla società candidata</span></div>
  <div class="rub" data-rub="gek"><span>GEK&#8209;Deleghe di gestione</span></div>
  <div class="rub" data-rub="rb1"><span>RB1 - Risultati finanziari - Bilanciato 1</span></div>
  <div class="rouge">Salvare le modifiche prima di cambiare sezione</div>
</div>

<form"""


class Serveur(SimpleHTTPRequestHandler):
    """Sert une page de test et journalise les requêtes interdites (POST, clic sur « /log »)."""

    posts: list[str] = []
    clics: list[str] = []

    def __init__(self, *args, repertoire=SITE, **kwargs):
        super().__init__(*args, directory=str(repertoire), **kwargs)

    def do_POST(self):
        longueur = int(self.headers.get("Content-Length", 0))
        self.rfile.read(longueur)
        Serveur.posts.append(self.path)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/log"):
            Serveur.clics.append(self.path)
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, *args):
        pass


def demarrer_serveur(repertoire: Path) -> ThreadingHTTPServer:
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), partial(Serveur, repertoire=repertoire))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur


def preparer_variante(dossier: Path) -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<div id="menu">.*?<form', MENU_VARIANTE, html, count=1, flags=re.S)
    html = html.replace("document.querySelectorAll('#menu a')", "document.querySelectorAll('[data-rub]')")
    (dossier / "index.html").write_text(html, encoding="utf-8")


def lancer(repertoire: Path, url_page: str, tmp_path_factory, entrees: str) -> dict:
    serveur = demarrer_serveur(repertoire)
    sortie = tmp_path_factory.mktemp("sortie")
    profil = tmp_path_factory.mktemp("profil")
    url = f"http://127.0.0.1:{serveur.server_port}/{url_page}"
    Serveur.posts.clear()
    Serveur.clics.clear()
    commande = [
        sys.executable, str(EXTRACTEUR), "--url", url, "--sortie", str(sortie), "--profil", str(profil),
        "--headless", "--pause", "50", "--calme", "150",
    ]
    navigateur = os.environ.get("QX_NAVIGATEUR_TEST")
    commande += ["--chemin-navigateur", navigateur] if navigateur else ["--navigateur", "chromium"]
    proc = subprocess.run(commande, input=entrees, text=True, encoding="utf-8", capture_output=True, timeout=900)
    serveur.shutdown()
    return {"proc": proc, "sortie": sortie, "posts": list(Serveur.posts), "clics": list(Serveur.clics)}


@pytest.fixture(scope="module")
def execution(tmp_path_factory):
    # Entrée : lancer, puis « a » pour traiter toutes les rubriques.
    resultat = lancer(SITE, "index.html", tmp_path_factory, "\na\n")
    proc = resultat["proc"]
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dossier = next(resultat["sortie"].iterdir())
    donnees = json.loads((dossier / "questionnaire.json").read_text(encoding="utf-8"))
    return {"donnees": donnees, "dossier": dossier, "posts": resultat["posts"], "clics": resultat["clics"]}


@pytest.fixture(scope="module")
def execution_variante(tmp_path_factory):
    dossier_variante = tmp_path_factory.mktemp("variante")
    preparer_variante(dossier_variante)
    resultat = lancer(dossier_variante, "index.html", tmp_path_factory, "\na\n")
    proc = resultat["proc"]
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dossier = next(resultat["sortie"].iterdir())
    donnees = json.loads((dossier / "questionnaire.json").read_text(encoding="utf-8"))
    return {"donnees": donnees, "dossier": dossier, "posts": resultat["posts"], "clics": resultat["clics"]}


def questions(execution):
    return {q["code"]: q for s in execution["donnees"]["sections"] for q in s["questions"]}


def test_rubriques_bleues_detectees(execution):
    assert [s["code"] for s in execution["donnees"]["sections"]] == ["GEA", "GEK", "RB1"]


def test_liste_sans_option_vide(execution):
    q = questions(execution)["082GEA1080559"]
    assert q["type"] == "liste déroulante"
    assert q["options"] == ["France", "Italia", "Germania"]
    assert q["toujours_affichee"]


def test_question_conditionnelle_simple(execution):
    q = questions(execution)["082GEA1080561"]
    assert not q["toujours_affichee"]
    assert q["affichee_si"] == ["GEA - Stato dell'Unione Europea in cui la società ha sede = « Italia »"]


def test_question_conditionnelle_imbriquee(execution):
    q = questions(execution)["082GEA1240627"]
    assert len(q["affichee_si"]) == 2
    assert all("La società è gestita da soggetti terzi? = « Sì »" in c for c in q["affichee_si"])
    assert any("« 2 - Affidata a società del gruppo »" in c for c in q["affichee_si"])
    assert any("« 3 - Affidata a società non appartenente al gruppo »" in c for c in q["affichee_si"])


def test_question_revelee_par_une_case(execution):
    q = questions(execution)["082GEA1080601"]
    assert q["affichee_si"] == ["GEA - Dichiaro la veridicità delle informazioni = « coché »"]


def test_bouton_radio_avec_options(execution):
    q = questions(execution)["082GEA1080570"]
    assert q["type"] == "choix unique"
    assert q["options"] == ["Sì", "No"]
    assert q["toujours_affichee"]


def test_libelle_d_option_pas_pris_pour_contexte(execution):
    assert questions(execution)["082GEA1240626"]["contexte"] == []
    assert questions(execution)["082GEA1080600"]["contexte"] == []


def test_question_en_lecture_seule(execution):
    assert questions(execution)["082GEA1080700"]["type"] == "lecture seule"


def test_question_obligatoire(execution):
    assert questions(execution)["082GEA1082149"]["obligatoire"] is True


def test_question_sans_code_recuperee(execution):
    rb1 = next(s for s in execution["donnees"]["sections"] if s["code"] == "RB1")
    periode = rb1["questions"][0]
    assert periode["code"] == ""
    assert periode["libelle"] == "Periodo di riferimento"
    assert periode["type"] == "date"
    assert periode["obligatoire"] is True


def test_aucune_soumission_ni_clic_interdit(execution):
    assert execution["posts"] == []
    assert execution["clics"] == []


def test_formulaire_restaure_sans_anomalie(execution):
    anomalies = execution["donnees"]["anomalies"]
    assert not [a for a in anomalies if "non restaurée" in a]
    assert not [a for a in anomalies if "non extrait" in a]


def test_fichiers_de_sortie(execution):
    dossier = execution["dossier"]
    assert (dossier / "questionnaire.txt").read_text(encoding="utf-8").count("Affichée si") >= 3
    csv_texte = (dossier / "questionnaire.csv").read_text(encoding="utf-8-sig")
    assert csv_texte.splitlines()[0].startswith("rubrique;code;libelle")
    assert (dossier / "brut" / "GEA.txt").exists()


def test_variante_rubriques_en_div(execution_variante):
    donnees = execution_variante["donnees"]
    assert [s["code"] for s in donnees["sections"]] == ["GEA", "GEK", "RB1"]
    q = {q["code"]: q for s in donnees["sections"] for q in s["questions"]}
    assert q["082GEA1080561"]["affichee_si"] == [
        "GEA - Stato dell'Unione Europea in cui la società ha sede = « Italia »"
    ]
    assert execution_variante["posts"] == []
    assert execution_variante["clics"] == []


def test_diagnostic_si_menu_absent(tmp_path_factory):
    vide = tmp_path_factory.mktemp("vide")
    (vide / "index.html").write_text("<html><body><p>Connexion requise</p></body></html>", encoding="utf-8")
    resultat = lancer(vide, "index.html", tmp_path_factory, "\nq\n")
    assert resultat["proc"].returncode == 0
    dossier = next(resultat["sortie"].iterdir())
    diagnostic = (dossier / "diagnostic.txt").read_text(encoding="utf-8")
    assert "Connexion requise" in diagnostic
