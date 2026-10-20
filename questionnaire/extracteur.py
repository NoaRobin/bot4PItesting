#!/usr/bin/env python3
"""Extrait les questions d'un questionnaire web : rubriques bleues, listes, questions conditionnelles.

Lancement (Windows) :
    py extracteur.py --url "https://..."

Déroulement :
  1. Le navigateur s'ouvre. Connectez-vous, allez sur le questionnaire, puis appuyez sur Entrée.
  2. Le script liste les rubriques bleues de la colonne de gauche.
  3. Pour chaque rubrique : Entrée (ou « a » pour toutes) ouvre la rubrique, lit toutes les questions,
     teste les listes déroulantes, boutons radio et cases pour révéler les questions conditionnelles,
     puis remet le formulaire dans son état d'origine.

Sécurité :
  - Clics autorisés uniquement : les rubriques bleues de la colonne de gauche, et les réponses des
    questions (boutons radio, cases). Les listes déroulantes sont changées sans clic. Aucun texte n'est saisi.
  - Aucune soumission : les formulaires ne peuvent pas être envoyés, et les requêtes POST, PUT, PATCH
    et DELETE sont annulées (elles sont journalisées).
  - Les réponses testées sont remises à leur valeur d'origine après chaque test et avant chaque changement de rubrique.
  - Rien n'est écrit sur le site : les résultats sont enregistrés localement, dans le dossier « sortie ».
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import queue
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

from playwright.sync_api import Error as ErreurPlaywright
from playwright.sync_api import sync_playwright

ICI = Path(__file__).resolve().parent
CODE_RE = re.compile(r"\b(\d{2,4}[A-Z]{2,6}\d{4,})\b")
METHODES_BLOQUEES = {"POST", "PUT", "PATCH", "DELETE"}
TYPES_AVEC_OPTIONS = ("liste déroulante", "choix unique")

# Utilitaire injecté dans chaque cadre de la page. Tout passe par window.__qx.
JS_LIB = r"""(function () {
  const RE_RUBRIQUE = /^[A-Z]{2,3}\d?\s*[-‐‑‒–—−]\s*\S/;
  const RE_CODE = /\b(\d{2,4}[A-Z]{2,6}\d{4,})\b/;
  const RE_CODE_G = /\b\d{2,4}[A-Z]{2,6}\d{4,}\b/g;
  const IGNORES = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'HEAD', 'META', 'LINK', 'OPTION']);

  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const nettoie = (s) => norm(s.replace(RE_CODE_G, '')).replace(/[\s\-–—*]+$/, '');
  const hash = (s) => {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  };
  const declencher = (el, type) => el.dispatchEvent(new Event(type, { bubbles: true }));
  const estRadio = (el) => el.tagName === 'INPUT' && el.type === 'radio';
  const estCase = (el) => el.tagName === 'INPUT' && el.type === 'checkbox';
  const estControle = (el) =>
    el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' ||
    (el.tagName === 'INPUT' && !['hidden', 'submit', 'button', 'reset', 'image'].includes((el.type || 'text').toLowerCase()));
  const estGras = (cs) => cs.fontWeight === 'bold' || parseInt(cs.fontWeight, 10) >= 600;
  const estPlaceholder = (o) =>
    o.value === '' || /^\s*[-–—]*\s*$/.test(o.text) || /^\s*(seleziona|scegli|select|choose)\b/i.test(o.text);

  // Rubriques bleues : éléments les plus internes dont le texte commence par un code de section (GEA - ..., RFA - ...).
  function liensRubriques() {
    const candidats = [...document.querySelectorAll('*')].filter((el) => {
      if (IGNORES.has(el.tagName)) return false;
      const t = norm(el.textContent);
      // Une rubrique n'a pas de code de question (-082GEA…-) : un texte qui en contient un est une question.
      return t.length > 0 && t.length < 160 && RE_RUBRIQUE.test(t) && !RE_CODE.test(t) &&
             el.getClientRects().length > 0;
    });
    const internes = candidats.filter((el) => !candidats.some((autre) => autre !== el && el.contains(autre)));
    // Le menu des rubriques est sous le titre « Sezioni Questionario ». S'il existe, on ne garde que ce qui suit.
    const titre = [...document.querySelectorAll('*')].find((el) => {
      const t = norm(el.textContent);
      return t.length < 60 && /^sezioni\s+questionario$/i.test(t) && el.getClientRects().length > 0;
    });
    if (titre) {
      const sous = internes.filter((el) => titre.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
      if (sous.length) return sous;
    }
    return internes;
  }

  // Zone du menu : plus petit conteneur commun aux rubriques, s'il ne contient aucun champ de saisie.
  // Sinon, seules les rubriques elles-mêmes sont ignorées lors de l'analyse du contenu.
  function zoneMenu(liens) {
    if (!liens.length) return new Set();
    let anc = liens[0].parentElement;
    while (anc && !liens.every((l) => anc.contains(l))) anc = anc.parentElement;
    if (anc && anc !== document.body && !anc.querySelector('select, textarea, input:not([type=hidden])')) {
      return new Set([anc]);
    }
    return new Set(liens);
  }

  // Informations pour le diagnostic quand aucune rubrique n'est trouvée.
  function diagnostic() {
    const textes = [...document.querySelectorAll('*')]
      .filter((el) => el.children.length === 0 && el.getClientRects().length > 0)
      .map((el) => norm(el.textContent))
      .filter((t) => t.length > 0 && t.length < 160);
    return {
      url: location.href,
      titre: document.title,
      nbAncres: document.querySelectorAll('a').length,
      nbChamps: document.querySelectorAll('select, textarea, input').length,
      textes: [...new Set(textes)].slice(0, 400),
    };
  }

  function typeDe(el) {
    if (el.tagName === 'SELECT') return el.multiple ? 'liste à choix multiples' : 'liste déroulante';
    if (el.tagName === 'TEXTAREA') return 'texte long';
    if (estRadio(el)) return 'choix unique';
    if (estCase(el)) return 'case à cocher';
    const t = (el.type || 'text').toLowerCase();
    if (t === 'file') return 'fichier';
    if (t === 'date' || t === 'month' || t === 'datetime-local') return 'date';
    if (t === 'number' || t === 'range') return 'nombre';
    return 'texte';
  }

  function libelleOption(el) {
    if (el.labels && el.labels.length) return norm(el.labels[0].textContent);
    return norm((el.nextSibling && el.nextSibling.textContent) || '') || el.value;
  }

  // Parcourt le DOM dans l'ordre : lignes de texte (avec gras/italique) et contrôles de saisie.
  function collecte(racine, exclus) {
    const jetons = [];
    const parcours = (noeud) => {
      for (const n of noeud.childNodes) {
        if (n.nodeType === Node.TEXT_NODE) {
          const s = n.nodeValue.replace(/\s+/g, ' ');
          if (s.trim() && n.parentElement) {
            const cs = getComputedStyle(n.parentElement);
            jetons.push({ s, gras: estGras(cs), italique: cs.fontStyle === 'italic' });
          }
        } else if (n.nodeType === Node.ELEMENT_NODE) {
          if (IGNORES.has(n.tagName) || exclus.has(n)) continue;
          const cs = getComputedStyle(n);
          if (cs.display === 'none' || cs.visibility === 'hidden') continue;
          if (n.tagName === 'BR') { jetons.push({ saut: true }); continue; }
          if (estControle(n)) { jetons.push({ ctl: n }); continue; }
          const bloc = cs.display !== 'inline' && cs.display !== 'contents';
          if (bloc) jetons.push({ saut: true });
          parcours(n);
          if (bloc) jetons.push({ saut: true });
        }
      }
    };
    parcours(racine);

    const items = [];
    let cur = null;
    const ferme = () => {
      if (cur && norm(cur.s)) {
        items.push({ line: norm(cur.s), gras: cur.g >= cur.n / 2, italique: cur.i >= cur.n / 2 });
      }
      cur = null;
    };
    for (const j of jetons) {
      if (j.saut) ferme();
      else if (j.ctl) { ferme(); items.push({ ctl: j.ctl }); }
      else {
        cur = cur || { s: '', n: 0, g: 0, i: 0 };
        cur.s += j.s;
        cur.n += j.s.length;
        if (j.gras) cur.g += j.s.length;
        if (j.italique) cur.i += j.s.length;
      }
    }
    ferme();
    return items;
  }

  // Une question = le texte qui précède son contrôle depuis le contrôle précédent.
  // Le libellé est la ligne portant le code (ou la dernière ligne en gras), les consignes sont les lignes après.
  function construire(gap, membres, utilises) {
    const el = membres[0];
    let lab = -1;
    for (let k = gap.length - 1; k >= 0 && lab < 0; k--) if (RE_CODE.test(gap[k].line)) lab = k;
    for (let k = gap.length - 1; k >= 0 && lab < 0; k--) if (gap[k].gras) lab = k;
    if (lab < 0 && gap.length) lab = gap.length - 1;

    let debut = lab;
    let code = '';
    let libelle = '';
    if (lab >= 0) {
      code = (RE_CODE.exec(gap[lab].line) || [])[1] || '';
      libelle = nettoie(gap[lab].line);
      if (libelle.length < 3 && lab > 0) {   // code seul sur sa ligne : le libellé est à la ligne précédente
        debut = lab - 1;
        libelle = nettoie(gap[debut].line);
      }
    }

    const contexte = [];
    const consignes = [];
    gap.forEach((l, k) => {
      if (k >= debut && k <= lab) { utilises.add(l.i); return; }
      if (RE_CODE.test(l.line)) return;   // code sans question : traité comme question en lecture seule
      (k < debut ? contexte : consignes).push(l.line);
    });

    const obligatoire = gap.slice(Math.max(debut, 0), lab + 1).some((l) => /\*\s*$/.test(l.line)) ||
                        consignes.includes('*');
    let options = [];
    if (el.tagName === 'SELECT') {
      options = [...el.options].filter((o) => !o.disabled && !estPlaceholder(o))
                               .map((o) => ({ v: o.value, t: norm(o.text) }));
    } else if (estRadio(el)) {
      options = membres.map((m, j) => ({ v: String(j), t: libelleOption(m) }));
    } else if (estCase(el)) {
      options = [{ v: 'true', t: 'coché' }];
    }
    const desactive = membres.every((m) => m.disabled);
    const declencheur = ((el.tagName === 'SELECT' && !el.multiple) || estRadio(el) || estCase(el)) && !desactive;
    return {
      code, libelle, contexte, consignes: consignes.filter((l) => l !== '*'), obligatoire,
      type: typeDe(el), options, declencheur, desactive,
    };
  }

  function brutDe(items) {
    return items.map((it) => {
      if ('line' in it) return it.line;
      const el = it.ctl;
      let t = '[champ : ' + typeDe(el);
      if (el.tagName === 'SELECT') t += ' ; options : ' + [...el.options].map((o) => norm(o.text)).join(' | ');
      return t + ']';
    }).join('\n');
  }

  function analyser() {
    const liens = liensRubriques();
    const items = collecte(document.body || document.documentElement, zoneMenu(liens));

    // Les boutons radio d'un même name forment une seule question.
    const groupes = new Map();
    items.forEach((it, i) => {
      if (it.ctl && estRadio(it.ctl) && it.ctl.name) {
        if (!groupes.has(it.ctl.name)) groupes.set(it.ctl.name, []);
        groupes.get(it.ctl.name).push({ el: it.ctl, i });
      }
    });

    const consommes = new Set();
    const utilises = new Set();
    const entrees = [];
    let gap = [];
    for (let i = 0; i < items.length; i++) {
      if (consommes.has(i)) continue;
      const it = items[i];
      if ('line' in it) { gap.push({ ...it, i }); continue; }
      let membres = [it.ctl];
      if (estRadio(it.ctl) && it.ctl.name && groupes.has(it.ctl.name)) {
        const g = groupes.get(it.ctl.name);
        membres = g.map((x) => x.el);
        const dernier = g[g.length - 1].i;
        const textes = new Set(membres.map(libelleOption));
        // Libellés des boutons : entre le premier et le dernier bouton, et juste après le dernier (texte exact).
        let fin = dernier + 1;
        while (fin < items.length && !items[fin].ctl) fin++;
        for (let k = i + 1; k < fin; k++) {
          if (k <= dernier || ('line' in items[k] && textes.has(items[k].line))) consommes.add(k);
        }
      }
      entrees.push({ pos: i, membres, q: construire(gap, membres, utilises) });
      gap = [];
    }

    // Lignes avec code qui ne servent de libellé à aucun contrôle : questions en lecture seule.
    items.forEach((it, i) => {
      if (!('line' in it) || utilises.has(i) || consommes.has(i) || !RE_CODE.test(it.line)) return;
      entrees.push({
        pos: i, membres: null,
        q: {
          code: RE_CODE.exec(it.line)[1], libelle: nettoie(it.line), contexte: [], consignes: [],
          obligatoire: false, type: 'lecture seule', options: [], declencheur: false, desactive: false,
        },
      });
    });
    entrees.sort((a, b) => a.pos - b.pos);

    // Clé stable d'une question : son code, sinon un hash de son libellé. Elle sert à retrouver le contrôle.
    const compte = new Map();
    for (const e of entrees) {
      let cle = e.q.code ? 'c' + e.q.code : 'h' + hash(e.q.libelle + '|' + e.q.type);
      const n = (compte.get(cle) || 0) + 1;
      compte.set(cle, n);
      if (n > 1) cle += 'x' + n;
      e.q.cle = cle;
      if (e.membres) {
        e.membres.forEach((m, j) => {
          m.setAttribute('data-qx-key', cle);
          if (estRadio(m)) m.setAttribute('data-qx-idx', String(j));
        });
      }
    }
    return { questions: entrees.map((e) => e.q), valeurs: valeurs(), brut: brutDe(items) };
  }

  // Valeur courante des contrôles qui peuvent révéler des questions (listes, radios, cases).
  function valeurs() {
    const m = {};
    document.querySelectorAll('[data-qx-key]').forEach((el) => {
      const cle = el.getAttribute('data-qx-key');
      if (el.tagName === 'SELECT' && !el.multiple) m[cle] = el.value;
      else if (estRadio(el)) {
        if (!(cle in m)) m[cle] = '-1';
        if (el.checked) m[cle] = el.getAttribute('data-qx-idx');
      } else if (estCase(el)) m[cle] = el.checked ? 'true' : 'false';
    });
    return m;
  }

  // Met une réponse à une valeur. Les événements input et change sont envoyés comme une vraie saisie.
  function definir(cle, valeur) {
    const els = [...document.querySelectorAll('[data-qx-key="' + cle + '"]')];
    if (!els.length) return false;
    const el = els[0];
    if (el.tagName === 'SELECT') {
      if (![...el.options].some((o) => o.value === valeur)) return false;
      el.value = valeur;
      declencher(el, 'input');
      declencher(el, 'change');
      return true;
    }
    if (estRadio(el)) {
      if (valeur === '-1') {
        const coche = els.find((e) => e.checked);
        if (coche) { coche.checked = false; declencher(coche, 'change'); }
        return true;
      }
      const cible = els.find((e) => e.getAttribute('data-qx-idx') === valeur);
      if (!cible) return false;
      // Pas de clic : la valeur est posée et l'événement change est envoyé.
      if (!cible.checked) { cible.checked = true; declencher(cible, 'input'); declencher(cible, 'change'); }
      return true;
    }
    if (estCase(el)) {
      const voulu = valeur === 'true';
      if (el.checked !== voulu) { el.checked = voulu; declencher(el, 'input'); declencher(el, 'change'); }
      return true;
    }
    return false;
  }

  // Attend que le DOM ne bouge plus pendant « calme » ms (plafond « max » ms).
  function attendreCalme(calme, max) {
    return new Promise((resoudre) => {
      let minuterie = null;
      const fin = () => { obs.disconnect(); resoudre(true); };
      const obs = new MutationObserver(() => {
        clearTimeout(minuterie);
        minuterie = setTimeout(fin, calme);
      });
      obs.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
      minuterie = setTimeout(fin, calme);
      setTimeout(fin, max);
    });
  }

  return {
    nomsRubriques: () => [...new Set(liensRubriques().map((a) => norm(a.textContent)))],
    marqueLien: (texte) => {
      document.querySelectorAll('[data-qx-nav]').forEach((a) => a.removeAttribute('data-qx-nav'));
      const lien = liensRubriques().find((a) => norm(a.textContent) === texte);
      if (lien) lien.setAttribute('data-qx-nav', '1');
      return !!lien;
    },
    diagnostic,
    analyser,
    valeurs,
    definir: ([cle, valeur]) => definir(cle, valeur),
    attendreCalme: ([calme, max]) => attendreCalme(calme, max),
  };
})()"""

JS_INIT = "() => { window.__qx = window.__qx || " + JS_LIB + "; return true; }"

# Garde-fou contre les soumissions de formulaire (événement submit, form.submit(), requestSubmit()).
JS_GARDE = """(() => {
  if (window.__gardeSoumission) return;
  window.__gardeSoumission = true;
  document.addEventListener('submit', (e) => {
    e.preventDefault();
    e.stopImmediatePropagation();
    console.warn('[garde] soumission de formulaire bloquée');
  }, true);
  HTMLFormElement.prototype.submit = function () { console.warn('[garde] form.submit() bloqué'); };
  HTMLFormElement.prototype.requestSubmit = function () { console.warn('[garde] requestSubmit() bloqué'); };
})();"""


def qx(cadre, methode: str, argument=None):
    """Appelle une fonction de l'utilitaire JavaScript injecté dans le cadre."""
    cadre.evaluate(JS_INIT)
    return cadre.evaluate(f"(a) => window.__qx.{methode}(a)", argument)


def securiser(texte: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", texte).strip("_") or "rubrique"


class Extracteur:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.dossier = Path(args.sortie) / dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        (self.dossier / "brut").mkdir(parents=True, exist_ok=True)
        self.journal_fichier = self.dossier / "journal.txt"
        self.sections: list[dict] = []
        self.anomalies: list[str] = []
        self.requetes_bloquees: list[str] = []
        self.soumissions_bloquees = 0
        self.brut_precedent: str | None = None
        self.contexte = None
        self.lignes: queue.Queue = queue.Queue()

    # ------------------------------------------------------------------ journal et saisie

    def journal(self, message: str) -> None:
        ligne = f"{dt.datetime.now():%H:%M:%S}  {message}"
        print(ligne, flush=True)
        with self.journal_fichier.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")

    def lire_stdin(self) -> None:
        """Lit le clavier dans un thread à part, pour que le navigateur reste réactif pendant l'attente."""
        for ligne in sys.stdin:
            self.lignes.put(ligne)
        self.lignes.put(None)

    def faire_tourner_playwright(self) -> None:
        """Traite les événements Playwright en attente. Sans cela, le navigateur est bloqué pendant l'attente."""
        if self.contexte is None:
            time.sleep(0.1)
            return
        try:
            self.contexte.wait_for_event("page", timeout=100)
        except ErreurPlaywright:
            pass

    def demander(self, message: str) -> str:
        print(message, end="", flush=True)
        while True:
            try:
                ligne = self.lignes.get(timeout=0.1)
            except queue.Empty:
                self.faire_tourner_playwright()
                continue
            if ligne is None:
                return "q"
            return ligne.strip().lower()

    # ------------------------------------------------------------------ navigateur

    def ouvrir_navigateur(self, p):
        if self.args.cdp:
            navigateur = p.chromium.connect_over_cdp(self.args.cdp)
            contexte = navigateur.contexts[0]
        else:
            options = {
                "headless": self.args.headless,
                "viewport": {"width": 1600, "height": 1000},
                "service_workers": "block",
            }
            if self.args.chemin_navigateur:
                options["executable_path"] = self.args.chemin_navigateur
            elif self.args.navigateur != "chromium":
                options["channel"] = self.args.navigateur
            contexte = p.chromium.launch_persistent_context(str(self.args.profil), **options)
        contexte.set_default_timeout(15000)
        contexte.route("**/*", self.garder_requete)
        contexte.add_init_script(JS_GARDE)
        contexte.on("page", self.surveiller_page)
        for page in contexte.pages:
            self.surveiller_page(page)
        return contexte

    def surveiller_page(self, page) -> None:
        page.on("dialog", self.refuser_dialogue)
        page.on("console", self.noter_console)

    def garder_requete(self, route, requete) -> None:
        if requete.method.upper() in METHODES_BLOQUEES:
            self.requetes_bloquees.append(f"{requete.method} {requete.url}")
            self.journal(f"BLOQUÉ : requête {requete.method} vers {requete.url}")
            route.abort()
        else:
            route.continue_()

    def refuser_dialogue(self, dialogue) -> None:
        self.journal(f"Boîte de dialogue refusée : « {dialogue.message} »")
        dialogue.dismiss()

    def noter_console(self, message) -> None:
        if message.text.startswith("[garde]"):
            self.soumissions_bloquees += 1

    def localiser(self, contexte):
        """Retourne (page, cadre) du cadre qui contient le menu bleu, ou (None, None)."""
        for page in contexte.pages:
            cadre = self.trouver_cadre(page)
            if cadre is not None:
                return page, cadre
        return None, None

    @staticmethod
    def trouver_cadre(page):
        meilleur, nombre = None, 0
        for cadre in page.frames:
            try:
                n = len(qx(cadre, "nomsRubriques"))
            except ErreurPlaywright:
                continue
            if n > nombre:
                meilleur, nombre = cadre, n
        if meilleur is not None:
            meilleur.evaluate(JS_GARDE)
        return meilleur

    # ------------------------------------------------------------------ parcours

    def executer(self) -> None:
        with sync_playwright() as p:
            try:
                contexte = self.ouvrir_navigateur(p)
            except ErreurPlaywright as erreur:
                self.journal(f"Impossible d'ouvrir le navigateur : {erreur}")
                self.journal("Essayez --navigateur chromium (après « playwright install chromium »).")
                return
            self.contexte = contexte
            threading.Thread(target=self.lire_stdin, daemon=True).start()
            try:
                if self.args.url and not self.args.cdp:
                    contexte.pages[0].goto(self.args.url)
                self.journal("Naviguez jusqu'au questionnaire (connexion comprise), puis appuyez sur Entrée.")
                if self.demander("> ") == "q":
                    return
                self.parcourir(contexte)
            finally:
                if not self.args.cdp:
                    contexte.close()

    def parcourir(self, contexte) -> None:
        while True:
            cadre = None
            fin = time.monotonic() + 15   # la page peut encore charger juste après l'Entrée
            while cadre is None and time.monotonic() < fin:
                _, cadre = self.localiser(contexte)
                if cadre is None:
                    time.sleep(0.5)
            if cadre is not None:
                break
            self.diagnostiquer(contexte)
            if self.demander("Menu bleu introuvable (diagnostic.txt écrit) : vérifiez la page, puis Entrée (q = quitter) > ") == "q":
                return

        noms = qx(cadre, "nomsRubriques")
        self.journal(f"{len(noms)} rubriques bleues détectées :")
        for i, nom in enumerate(noms, 1):
            self.journal(f"  {i:2}. {nom}")

        automatique = False
        for i, nom in enumerate(noms, 1):
            if not automatique:
                reponse = self.demander(
                    f"\n[{i}/{len(noms)}] {nom}\n"
                    "  Entrée = traiter · s = passer · a = tout traiter · q = quitter > "
                )
                if reponse == "q":
                    break
                if reponse == "s":
                    continue
                if reponse == "a":
                    automatique = True
            try:
                self.traiter_rubrique(contexte, nom)
            except (ErreurPlaywright, TimeoutError) as erreur:
                self.journal(f"  Erreur sur cette rubrique, rien n'est enregistré : {erreur}")

    def diagnostiquer(self, contexte) -> None:
        """Écrit diagnostic.txt : textes visibles et cadres de chaque page, pour adapter la détection du menu."""
        lignes: list[str] = []
        for numero, page in enumerate(contexte.pages, 1):
            for cadre in page.frames:
                try:
                    info = qx(cadre, "diagnostic")
                except ErreurPlaywright as erreur:
                    lignes.append(f"Page {numero}, cadre {cadre.url} : illisible ({erreur})")
                    continue
                lignes += ["", f"Page {numero}, cadre : {info['url']}", f"titre : {info['titre']}",
                           f"liens <a> : {info['nbAncres']}   champs de saisie : {info['nbChamps']}"]
                lignes += [f"  {t!r}" for t in info["textes"]]
        chemin = self.dossier / "diagnostic.txt"
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        self.journal(f"Diagnostic écrit : {chemin}")

    def traiter_rubrique(self, contexte, nom: str) -> None:
        _, cadre = self.localiser(contexte)
        if cadre is None or not qx(cadre, "marqueLien", nom):
            self.journal(f"  Rubrique introuvable : {nom}")
            return
        self.journal(f"Rubrique : {nom}")
        cadre.locator('[data-qx-nav="1"]').click()
        _, cadre = self.attendre_rubrique(contexte)

        base = qx(cadre, "analyser")
        if base["brut"] == self.brut_precedent:
            self.journal("  Attention : contenu identique à la rubrique précédente, vérifiez le clic.")
        self.brut_precedent = base["brut"]
        self.journal(f"  {len(base['questions'])} questions visibles au départ")

        soumissions_avant = self.soumissions_bloquees
        resultat = self.sonder(cadre, base, nom)
        if self.soumissions_bloquees > soumissions_avant:
            self.journal(f"  {self.soumissions_bloquees - soumissions_avant} soumission(s) de formulaire bloquée(s) "
                         "pendant les essais (aucun envoi)")
        code = re.split(r"\s*[-‐-―−]\s*", nom, maxsplit=1)[0].strip()
        section = {"code": code, "nom": nom, "questions": resultat["questions"], "tests": resultat["tests"]}
        self.sections = [s for s in self.sections if s["code"] != code] + [section]
        self.verifier(section, base["brut"])
        (self.dossier / "brut" / f"{securiser(code)}.txt").write_text(base["brut"], encoding="utf-8")
        self.ecrire_sorties()
        t = resultat["tests"]
        self.journal(f"  {len(section['questions'])} questions enregistrées, {t['essais']} essais")

    def attendre_rubrique(self, contexte):
        time.sleep(self.args.pause / 1000)
        fin = time.monotonic() + 20
        while time.monotonic() < fin:
            page, cadre = self.localiser(contexte)
            if cadre is not None:
                try:
                    if cadre.evaluate("() => document.readyState") == "complete":
                        qx(cadre, "attendreCalme", [self.args.calme, 3000])
                        return page, cadre
                except ErreurPlaywright:
                    pass
            time.sleep(0.3)
        raise TimeoutError("la rubrique ne s'est pas chargée")

    # ------------------------------------------------------------------ tests des questions conditionnelles

    def appliquer(self, cadre, etat, defauts: dict) -> None:
        """Remet tous les contrôles à leur valeur d'origine, puis applique l'état demandé."""
        for cle, valeur in qx(cadre, "valeurs").items():
            if cle in defauts and valeur != defauts[cle]:
                qx(cadre, "definir", [cle, defauts[cle]])
        for cle, valeur in etat:
            qx(cadre, "definir", [cle, valeur])
        qx(cadre, "attendreCalme", [self.args.calme, 3000])
        time.sleep(self.args.pause / 1000)

    def sonder(self, cadre, base: dict, nom: str) -> dict:
        """Essaie les réponses de chaque liste, bouton radio et case, en largeur d'abord.

        Un état = une suite de réponses (contrôle, valeur). Chaque question vue dans un état est
        enregistrée avec la condition qui l'affiche. Les réponses sont restaurées à la fin.
        """
        defauts = dict(base["valeurs"])
        fiches: dict[str, dict] = {}
        ordre: list[str] = []
        apparitions: dict[str, list[tuple[frozenset, str]]] = {}
        disparitions: dict[str, list[tuple[frozenset, str]]] = {}
        cles_base = {q["cle"] for q in base["questions"]}

        def texte_etat(etat) -> str:
            morceaux = []
            for cle, valeur in etat:
                fiche = fiches.get(cle, {})
                option = next((o["t"] for o in fiche.get("options", []) if o["v"] == valeur), valeur)
                morceaux.append(f"{fiche.get('libelle') or cle} = « {option} »")
            return " ET ".join(morceaux)

        def ajouter_minimal(liste: list, empreinte: frozenset, texte: str) -> None:
            """Garde une condition seulement si aucune condition plus simple ne la couvre déjà."""
            if any(existante <= empreinte for existante, _ in liste):
                return
            liste.append((empreinte, texte))

        def inserer(cle: str, liste: list, i: int) -> None:
            avant = [q["cle"] for q in liste[:i] if q["cle"] in ordre]
            apres = [q["cle"] for q in liste[i + 1:] if q["cle"] in ordre]
            if avant:
                position = ordre.index(avant[-1]) + 1
            elif apres:
                position = ordre.index(apres[0])
            else:
                position = len(ordre)
            ordre.insert(position, cle)

        def integrer(instantane: dict, etat) -> None:
            liste = instantane["questions"]
            texte = texte_etat(etat)
            empreinte = frozenset(etat)
            for i, q in enumerate(liste):
                cle = q["cle"]
                if cle not in fiches:
                    fiches[cle] = q
                    inserer(cle, liste, i)
                if etat and cle not in cles_base:
                    ajouter_minimal(apparitions.setdefault(cle, []), empreinte, texte)
            if etat:
                visibles = {q["cle"] for q in liste}
                for cle in cles_base - visibles:
                    ajouter_minimal(disparitions.setdefault(cle, []), empreinte, texte)

        integrer(base, ())
        essais = 0
        complet = True
        file: deque = deque()
        try:
            if not self.args.sans_sondage:
                file = deque([()])
                vus = {frozenset()}
                while file:
                    if essais >= self.args.max_tests:
                        complet = False
                        break
                    etat = file.popleft()
                    self.appliquer(cadre, etat, defauts)
                    instantane = qx(cadre, "analyser")
                    essais += 1
                    valeurs_actuelles = instantane["valeurs"]
                    deja_dans_etat = dict(etat)
                    for cle, valeur in valeurs_actuelles.items():
                        if cle not in defauts and cle not in deja_dans_etat:
                            defauts[cle] = valeur
                    integrer(instantane, etat)
                    if len(etat) >= self.args.profondeur:
                        continue
                    for q in instantane["questions"]:
                        if not q["declencheur"]:
                            continue
                        for option in q["options"]:
                            if option["v"] == valeurs_actuelles.get(q["cle"]):
                                continue
                            nouvel = tuple((c, v) for c, v in etat if c != q["cle"]) + ((q["cle"], option["v"]),)
                            empreinte = frozenset(nouvel)
                            if empreinte not in vus:
                                vus.add(empreinte)
                                file.append(nouvel)
        finally:
            self.restaurer(cadre, defauts)

        if not complet:
            self.anomalies.append(f"{nom} : tests incomplets, limite de {self.args.max_tests} essais atteinte")
        questions = []
        for cle in ordre:
            fiche = fiches[cle]
            toujours = cle in cles_base
            questions.append({
                "code": fiche["code"],
                "libelle": fiche["libelle"],
                "type": fiche["type"],
                "obligatoire": fiche["obligatoire"],
                "contexte": fiche["contexte"],
                "consignes": fiche["consignes"],
                "options": [o["t"] for o in fiche["options"]] if fiche["type"] in TYPES_AVEC_OPTIONS else [],
                "toujours_affichee": toujours,
                "affichee_si": [] if toujours else [t for _, t in apparitions.get(cle, [])],
                "masquee_si": [t for _, t in disparitions.get(cle, [])],
                "desactivee": fiche["desactive"],
            })
        return {"questions": questions, "tests": {"essais": essais, "complet": complet, "limite": self.args.max_tests}}

    def restaurer(self, cadre, defauts: dict) -> None:
        try:
            self.appliquer(cadre, (), defauts)
            restaurees = qx(cadre, "valeurs")
        except ErreurPlaywright as erreur:
            self.journal(f"  Attention : restauration impossible : {erreur}")
            return
        ecarts = [c for c in defauts if restaurees.get(c, defauts[c]) != defauts[c]]
        if ecarts:
            message = f"{len(ecarts)} réponse(s) non restaurée(s) après les essais : vérifiez le formulaire à la main"
            self.anomalies.append(message)
            self.journal(f"  Attention : {message}")

    # ------------------------------------------------------------------ contrôles et sorties

    def verifier(self, section: dict, brut: str) -> None:
        dans_texte = set(CODE_RE.findall(brut))
        extraits = {q["code"] for q in section["questions"] if q["code"]}
        for code in sorted(dans_texte - extraits):
            message = f"{section['code']} : code {code} présent dans le texte mais non extrait (voir brut/)"
            self.anomalies.append(message)
            self.journal(f"  Attention : {message}")

    def ecrire_sorties(self) -> None:
        donnees = {
            "genere_le": dt.datetime.now().isoformat(timespec="seconds"),
            "sections": self.sections,
            "anomalies": self.anomalies,
            "requetes_bloquees": self.requetes_bloquees,
        }
        (self.dossier / "questionnaire.json").write_text(
            json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.dossier / "questionnaire.txt").write_text(self.texte(), encoding="utf-8")
        with (self.dossier / "questionnaire.csv").open("w", encoding="utf-8-sig", newline="") as f:
            ecrivain = csv.writer(f, delimiter=";")
            ecrivain.writerow(["rubrique", "code", "libelle", "type", "obligatoire", "options",
                               "consignes", "affichee_si", "masquee_si", "toujours_affichee"])
            for s in self.sections:
                for q in s["questions"]:
                    ecrivain.writerow([
                        s["nom"], q["code"], q["libelle"], q["type"], "oui" if q["obligatoire"] else "",
                        " | ".join(q["options"]), " / ".join(q["consignes"]),
                        " ; ".join(q["affichee_si"]), " ; ".join(q["masquee_si"]),
                        "oui" if q["toujours_affichee"] else "",
                    ])

    def texte(self) -> str:
        lignes: list[str] = []
        for s in self.sections:
            lignes += ["", "=" * 80, s["nom"], "=" * 80]
            for q in s["questions"]:
                lignes.append("")
                suffixe = "  (obligatoire)" if q["obligatoire"] else ""
                lignes.append(f"[{q['code'] or 'sans code'}] {q['libelle']}{suffixe}")
                if q["contexte"]:
                    lignes.append("    Contexte : " + " / ".join(q["contexte"]))
                if q["consignes"]:
                    lignes.append("    Consignes : " + " / ".join(q["consignes"]))
                lignes.append(f"    Type : {q['type']}")
                if q["options"]:
                    lignes.append("    Options : " + " | ".join(q["options"]))
                if q["affichee_si"]:
                    lignes.append("    Affichée si : " + " ; ".join(q["affichee_si"]))
                elif q["toujours_affichee"]:
                    lignes.append("    Toujours affichée")
                if q["masquee_si"]:
                    lignes.append("    Masquée si : " + " ; ".join(q["masquee_si"]))
        if self.anomalies:
            lignes += ["", "=" * 80, "Anomalies à vérifier", "=" * 80] + [f"- {a}" for a in self.anomalies]
        return "\n".join(lignes).lstrip("\n") + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Extrait les questions d'un questionnaire web.")
    parser.add_argument("--url", help="page d'ouverture du questionnaire (facultatif)")
    parser.add_argument("--cdp", metavar="URL", help="se connecter à un navigateur déjà ouvert, "
                        "lancé avec --remote-debugging-port (ex. http://localhost:9222)")
    parser.add_argument("--navigateur", choices=["msedge", "chrome", "chromium"], default="msedge",
                        help="navigateur à utiliser (défaut : Edge, présent sur Windows)")
    parser.add_argument("--chemin-navigateur", help="chemin d'un exécutable Chromium (remplace --navigateur)")
    parser.add_argument("--profil", default=str(ICI / "profil_navigateur"),
                        help="dossier du profil du navigateur (conserve la connexion)")
    parser.add_argument("--sortie", default=str(ICI / "sortie"), help="dossier des résultats")
    parser.add_argument("--sans-sondage", action="store_true",
                        help="ne pas tester les listes : extraction simple, plus rapide")
    parser.add_argument("--profondeur", type=int, default=3,
                        help="nombre maximum de réponses enchaînées testées (défaut : 3)")
    parser.add_argument("--max-tests", type=int, default=400,
                        help="nombre maximum d'essais par rubrique (défaut : 400)")
    parser.add_argument("--calme", type=int, default=250, help="ms sans changement du DOM avant lecture")
    parser.add_argument("--pause", type=int, default=300, help="ms d'attente après chaque réponse testée")
    parser.add_argument("--headless", action="store_true", help="navigateur sans fenêtre (tests)")
    args = parser.parse_args()
    args.profil = Path(args.profil)

    extracteur = Extracteur(args)
    try:
        extracteur.executer()
    except KeyboardInterrupt:
        extracteur.journal("Interrompu : les résultats déjà lus sont enregistrés.")
    finally:
        extracteur.ecrire_sorties()
        extracteur.journal(f"Résultats : {extracteur.dossier}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
