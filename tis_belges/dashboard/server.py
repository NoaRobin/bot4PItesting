"""Dashboard local TIS Belges.

Serveur HTTP de la bibliothèque standard, lié à 127.0.0.1 uniquement. Il ne fait qu'appeler
les commandes de tis_belges.py dans un sous-processus, lire l'état du jour et programmer la
tâche planifiée. Aucune logique métier ici.

Lancement : python dashboard/server.py   (ou Lancer.bat, qui ouvre la fenêtre)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent.parent          # dossier tis_belges
STATIC = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(HERE))

from config import load_config, update_config  # noqa: E402
import rules  # noqa: E402
import system  # noqa: E402

PORT = 8765
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

STEPS = [
    ("validated", "Actualisation", "Requête RMMPRD actualisée et données contrôlées"),
    ("archived", "Archive", "Copie datée dans le dossier de l'année"),
    ("valor_done", "Valor", "Lignes R-co Valor ajoutées à l'historique"),
    ("am_built", "Fichier final", "Onglet Paramètres retiré, fichier prêt"),
    ("sent_at", "Six", "Mail envoyé à Six Financial Information"),
]


class Job:
    """Une commande tis_belges.py en cours ou terminée. Une seule à la fois."""

    def __init__(self, label: str, args: list[str]) -> None:
        self.label = label
        self.args = args
        self.lines: list[str] = []
        self.running = True
        self.code: int | None = None
        self.started = datetime.now().isoformat(timespec="seconds")
        self.ended: str | None = None
        self.lock = threading.Lock()

    def view(self, offset: int) -> dict:
        with self.lock:
            return {
                "label": self.label,
                "running": self.running,
                "code": self.code,
                "started": self.started,
                "ended": self.ended,
                "offset": len(self.lines),
                "lines": self.lines[offset:],
            }


JOB: Job | None = None
JOB_LOCK = threading.Lock()


def _python() -> str:
    """Interpréteur console (python.exe) : évite l'ouverture d'une fenêtre pour chaque commande."""
    exe = Path(sys.executable)
    console = exe.with_name("python.exe")
    return str(console if console.exists() else exe)


def start_job(label: str, args: list[str]) -> Job | None:
    global JOB
    with JOB_LOCK:
        if JOB and JOB.running:
            return None
        job = Job(label, args)
        JOB = job

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [_python(), str(HERE / "tis_belges.py"), *args],
        cwd=HERE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )

    def pump() -> None:
        for line in proc.stdout:
            with job.lock:
                job.lines.append(line.rstrip("\n"))
        code = proc.wait()
        with job.lock:
            job.code = code
            job.running = False
            job.ended = datetime.now().isoformat(timespec="seconds")

    threading.Thread(target=pump, daemon=True).start()
    return job


# ---------------------------------------------------------------- lecture de l'état

def _state_file(cfg: dict, key: str) -> Path:
    return Path(cfg["data_dir"]) / "state" / f"{key}.json"


def today_state(cfg: dict, test: bool = False) -> dict:
    key = date.today().strftime("%Y%m%d") + ("_test" if test else "")
    path = _state_file(cfg, key)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _process_job() -> Job | None:
    """Dernière opération d'envoi ou d'essai lancée depuis le dashboard (pas le contrôle)."""
    return JOB if JOB and JOB.args and JOB.args[0] == "run" else None


def current_mode() -> str:
    job = _process_job()
    return "test" if job and "--test" in job.args else "prod"


def steps_view(cfg: dict) -> list[dict]:
    """Statut de chaque étape : done, running, failed, warning ou pending."""
    state = today_state(cfg, test=current_mode() == "test")
    job = _process_job()
    running = bool(job and job.running)
    failed = bool(job and not job.running and job.code not in (0, None))
    result = []
    previous_done = True
    for key, label, hint in STEPS:
        done = bool(state.get(key))
        if key == "sent_at" and state.get("send_started") and not done:
            status = "warning"
        elif done:
            status = "done"
        elif previous_done and running:
            status = "running"
        elif previous_done and failed:
            status = "failed"
        else:
            status = "pending"
        result.append({"id": key, "label": label, "hint": hint, "status": status, "at": state.get(key)})
        previous_done = done
    return result


def next_run(cfg: dict) -> str | None:
    hour, minute = map(int, cfg["run_at"].split(":"))
    now = datetime.now()
    for offset in range(0, 10):
        day = date.today() + timedelta(days=offset)
        moment = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
        if moment > now and rules.is_business_day(day, cfg["skip_dates"]):
            return moment.isoformat(timespec="minutes")
    return None


def recent_runs(cfg: dict, limit: int = 10) -> list[dict]:
    logs = Path(cfg["data_dir"]) / "logs"
    if not logs.exists():
        return []
    runs = []
    for path in sorted(logs.glob("tis_belges_*.log"), reverse=True)[:limit]:
        text = path.read_text(encoding="utf-8", errors="replace")
        key = path.stem.replace("tis_belges_", "")
        if "Envoi confirmé" in text or "Déjà envoyé" in text:
            status = "envoyé"
        elif "ERROR" in text or "Échec" in text:
            status = "échec"
        elif "jour non ouvré" in text:
            status = "non ouvré"
        else:
            status = "incomplet"
        runs.append({"date": key, "status": status, "log": path.name})
    return runs


def status_payload() -> dict:
    cfg = load_config()
    with JOB_LOCK:
        job = JOB.view(sys.maxsize) if JOB else None
        if job:
            job.pop("lines", None)
    return {
        "today": date.today().isoformat(),
        "business_day": rules.is_business_day(date.today(), cfg["skip_dates"]),
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "mode": current_mode(),
        "prod_sent": bool(today_state(cfg).get("sent_at")),
        "steps": steps_view(cfg),
        "job": job,
        "schedule": {
            "enabled": system.task_exists(),
            "run_at": cfg["run_at"],
            "retry_until": cfg["retry_until"],
            "next_run": next_run(cfg),
        },
        "runs": recent_runs(cfg),
        "settings": {
            "sender": cfg["sender"],
            "recipients": cfg["recipients"],
            "alert_recipients": cfg["alert_recipients"],
            "base_dir": cfg["base_dir"],
            "validation": cfg["validation"],
            "dsn": cfg["dsn"],
            "skip_dates": cfg["skip_dates"],
        },
    }


def log_tail(cfg: dict, lines: int = 200) -> list[str]:
    path = Path(cfg["data_dir"]) / "logs" / f"tis_belges_{date.today().strftime('%Y%m%d')}.log"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


# ---------------------------------------------------------------- actions

ACTIONS = {
    "check": ("Contrôle de l'installation", ["check"]),
    "test": ("Essai sans envoi", ["run", "--test", "--now"]),
    "run": ("Envoi à Six", ["run", "--now"]),
}


def set_schedule(enabled: bool, run_at: str) -> None:
    if not enabled:
        system.uninstall_task()
        return
    datetime.strptime(run_at, "%H:%M")  # valide le format HH:MM
    update_config({"run_at": run_at})
    system.install_task(run_at)


# ---------------------------------------------------------------- HTTP

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TISBelges"

    def log_message(self, *_args) -> None:  # silence les logs HTTP
        return

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/api/status":
            return self._json(status_payload())
        if url.path == "/api/job":
            offset = int(parse_qs(url.query).get("offset", ["0"])[0])
            with JOB_LOCK:
                job = JOB.view(offset) if JOB else None
            return self._json({"job": job})
        if url.path == "/api/log":
            return self._json({"lines": log_tail(load_config())})
        return self._static(url.path)

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        try:
            body = self._body()
            if url.path == "/api/job":
                action = ACTIONS.get(body.get("action"))
                if not action:
                    return self._json({"error": "Action inconnue."}, 400)
                job = start_job(*action)
                if job is None:
                    return self._json({"error": "Une opération est déjà en cours."}, 409)
                return self._json({"started": job.label})
            if url.path == "/api/schedule":
                set_schedule(bool(body.get("enabled")), body.get("run_at", load_config()["run_at"]))
                return self._json({"ok": True})
            return self._json({"error": "Route inconnue."}, 404)
        except ValueError as exc:
            return self._json({"error": f"Donnée invalide : {exc}"}, 400)
        except Exception as exc:  # noqa: BLE001 - retour lisible pour l'interface
            return self._json({"error": f"{type(exc).__name__} : {exc}"}, 500)

    def _static(self, path: str) -> None:
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        file = (STATIC / name).resolve()
        if STATIC.resolve() not in file.parents or not file.is_file():
            self.send_error(404)
            return
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(file.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Le dashboard tourne déjà sur http://127.0.0.1:{PORT}")
        return 0
    print(f"Dashboard TIS Belges : http://127.0.0.1:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
