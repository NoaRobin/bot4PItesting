# -*- coding: utf-8 -*-
"""Configuration : valeurs par défaut + surcharge par un fichier TOML (pia_bench.toml).

Tout ce qui dépend de l'écran Copilot (sélecteurs, libellés de boutons, messages
d'attente) est ici, pour qu'un changement d'interface Microsoft se corrige dans
le TOML sans toucher au code.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

DEFAULTS: dict[str, Any] = {
    "catalogue": {
        "path": "Benchmark_Product_Info_1500_questions_COUVERTURE_ELARGIE.xlsx",
        "sheet": "QUESTIONS_1500",
        # 0 = pas de contrôle du nombre de questions
        "expected_questions": 0,
    },
    "campaign": {
        "runs_dir": "runs",
    },
    "run": {
        "transport": "edge",          # edge | directline | fake
        "max_attempts": 3,            # tentatives par conversation (chat neuf à chaque fois)
        "turn_timeout": 360,          # secondes max pour une réponse
        "stable_seconds": 6,          # la réponse doit rester identique ce temps-là
        "think_time": 2,              # pause entre deux tours d'une conversation
        "between_conversations": 3,   # pause entre deux conversations
        "backoff_base": 30,           # attente avant nouvelle tentative (x2 à chaque échec)
        "rate_limit_cooldown": 600,   # attente si l'agent signale une limite de débit
        "breaker_threshold": 3,       # conversations échouées d'affilée avant pause longue
        "breaker_cooldown": 900,
        "breaker_max_trips": 2,       # au-delà : arrêt propre (reprise possible)
        # Détection de session dégradée (cas du premier chat du 28/09) :
        # sur les N derniers tours NOTABLE, si la part de « aucune information »
        # dépasse le ratio, le navigateur est relancé et ces conversations rejouées.
        "degraded_window": 15,
        "degraded_ratio": 0.8,
    },
    "edge": {
        # attach : Edge démarré normalement (connexion Microsoft possible, pas de bandeau
        #          « contrôlé par un logiciel de test automatisé »), le script s'y connecte ;
        # launch : Playwright lance Edge (si la stratégie de l'entreprise bloque le débogage).
        "mode": "attach",
        "cdp_port": 9222,
        "channel": "msedge",          # mode launch : "" = Chromium de Playwright
        "executable_path": "",        # chemin de msedge.exe si non détecté
        "extra_args": [],             # arguments supplémentaires passés à Edge (mode attach)
        "profile_dir": ".edge_profile_pia_bench",
        "headless": False,
        "agent_url": "",              # rempli automatiquement par `setup`
        "agent_name": "Product Info Assistant",
        "strict_agent_check": False,  # exiger le nom de l'agent dans la zone de saisie
        "new_chat": ["url", "button"],  # stratégies pour ouvrir un chat neuf, dans l'ordre
        "page_load_timeout": 90,
        "composer_selectors": [
            '[contenteditable="true"][aria-label="Message Product Info Assistant"]',
            '[contenteditable="true"][data-placeholder="Message Product Info Assistant"]',
            '[role="textbox"][aria-label="Message Product Info Assistant"]',
            '[contenteditable="true"][aria-label*="Message Copilot" i]',
            '[contenteditable="true"][data-placeholder*="Message Copilot" i]',
            '[role="textbox"][aria-label*="Message Copilot" i]',
            'textarea[placeholder*="Message" i]',
            'textarea[aria-label*="message" i]',
        ],
        "user_selectors": [
            '[class*="fai-UserMessage"]',
            '[data-message-author-role="user"]',
            '[data-author="user"]',
        ],
        "assistant_selectors": [
            '[data-testid="copilot-message-reply-div"]',
            '[class*="fai-CopilotMessage"]',
            '[data-message-author-role="assistant"]',
            '[data-author="assistant"]',
            '[aria-label*="Product Info Assistant said" i]',
        ],
        "new_chat_button": r"^(nouvelle conversation|nouveau chat|nouvelle discussion|new chat|start new chat|new conversation)\b",
        "stop_button": r"arr[êe]ter|interrompre|stop generating|stop responding",
        "send_button": r"^(envoyer|send|submit|soumettre)\b",
        "waiting_patterns": [
            "mise en place en cours", "lining things up", "nous travaillons sur une réponse",
            "nous travaillons sur une reponse", "veuillez patienter", "recherche en cours",
            "génération en cours", "generation en cours", "working on it",
        ],
    },
    "directline": {
        "base_url": "https://directline.botframework.com/v3/directline",
        "secret_env": "PIA_DIRECTLINE_SECRET",   # secret du canal (variable d'environnement)
        "token_endpoint": "",                    # ou URL « token endpoint » de Copilot Studio
        "locale": "fr-FR",
        "user_id": "pia-bench",
        "send_start_event": True,
        "poll_interval": 1.0,
    },
    "fake": {
        "no_info_rate": 0.1,
        "wrong_rate": 0.02,
        "tech_error_rate": 0.02,
        "seed": 42,
        "latency": 0.0,
    },
    "scoring": {
        "equivalences": "equivalences.csv",
    },
    "judge": {
        "model": "claude-opus-5-5",
        "effort": "low",
        "only_uncertain": True,
    },
}

TECH_ERROR_PATTERNS = [
    "oops! something happened", "something went wrong", "can you try again",
    "une erreur s'est produite", "une erreur s’est produite", "un problème est survenu",
    "un probleme est survenu", "réessayez plus tard", "reessayez plus tard",
    "sorry, something went wrong", "we're having trouble", "nous rencontrons un problème",
    "une erreur inattendue s’est produite", "une erreur inattendue s'est produite", "code d’erreur : systemerror",
]
# L'agent ne traite pas la question : demande de « scope », question non reçue, contexte perdu,
# renvoi vers un représentant. Comparaison sur le texte normalisé (sans accents ni ponctuation).
OFF_TOPIC_PATTERNS = [
    r"scope de recherche", r"scope dans lequel", r"requete sql", r"reaffectation a un representant",
    r"pas recu de demande exploitable", r"je n ai recu que", r"je n ai pas identifie de demande",
    r"je n ai pas l identification du fonds", r"^pour quel fonds", r"la requete a ete (modifiee|mise a jour)",
    r"je suis a votre disposition pour rechercher", r"pouvez vous (indiquer|preciser) le fonds",
]
RATE_LIMIT_PATTERNS = [
    "too many requests", "trop de requêtes", "trop de demandes", "rate limit",
    "vous avez atteint la limite", "you've reached", "limite de messages",
]


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


class Config(dict):
    """Dictionnaire de configuration avec chemin de base pour les chemins relatifs."""

    root: Path

    def path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else self.root / p


def load_config(path: str | Path | None = None) -> Config:
    data = copy.deepcopy(DEFAULTS)
    root = Path.cwd()
    if path is None and (root / "pia_bench.toml").is_file():
        path = root / "pia_bench.toml"
    if path is not None:
        path = Path(path)
        with path.open("rb") as f:
            _merge(data, tomllib.load(f))
        root = path.resolve().parent
    cfg = Config(data)
    cfg.root = root
    return cfg
