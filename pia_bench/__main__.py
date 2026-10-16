import sys
from pathlib import Path

# Fichiers du package : une copie incomplète (fichiers récupérés un par un) est signalée
# clairement au lieu d'une ImportError obscure plus loin.
REQUIRED = [
    "__init__.py", "catalogue.py", "cli.py", "config.py", "judge.py", "report.py", "runner.py",
    "scoring.py", "store.py", "transports/__init__.py", "transports/base.py", "transports/directline.py",
    "transports/edge_ui.py", "transports/fake.py",
]
missing = [f for f in REQUIRED if not (Path(__file__).resolve().parent / f).is_file()]
if missing:
    print("ERREUR : copie incomplète du package pia_bench, fichiers absents :", ", ".join(missing))
    print("Récupérez la branche complète : git checkout claude/eager-davinci-lgjr5y && git pull")
    sys.exit(1)

from .cli import main  # noqa: E402

sys.exit(main())
