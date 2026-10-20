(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  const state = { status: null, offset: 0, jobLabel: null, jobRunning: false, jobLines: [], checkLines: [] };

  // ---------------------------------------------------------------- utilitaires

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Erreur ${res.status}`);
    return data;
  }

  function toast(message, kind = "") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    $("toasts").appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function confirmBox(title, text, okLabel = "Confirmer") {
    return new Promise((resolve) => {
      $("modalTitle").textContent = title;
      $("modalText").textContent = text;
      $("modalOk").textContent = okLabel;
      $("modal").hidden = false;
      $("modalOk").focus();
      const close = (value) => {
        $("modal").hidden = true;
        $("modalOk").onclick = $("modalCancel").onclick = null;
        document.removeEventListener("keydown", onKey);
        resolve(value);
      };
      const onKey = (e) => {
        if (e.key === "Escape") close(false);
      };
      $("modalOk").onclick = () => close(true);
      $("modalCancel").onclick = () => close(false);
      document.addEventListener("keydown", onKey);
    });
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const today = new Date();
    const tomorrow = new Date(today.getTime() + 86400000);
    const sameDay = (a, b) => a.toDateString() === b.toDateString();
    const time = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    if (sameDay(d, today)) return `aujourd'hui à ${time}`;
    if (sameDay(d, tomorrow)) return `demain à ${time}`;
    return `${d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} à ${time}`;
  }

  function countdown(iso) {
    if (!iso) return "";
    const diff = new Date(iso) - new Date();
    if (diff <= 0) return "";
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    if (h >= 24) return "";
    return h > 0 ? `dans ${h} h ${String(m).padStart(2, "0")}` : `dans ${m} min`;
  }

  // ---------------------------------------------------------------- horloge

  function tickClock() {
    $("clock").textContent = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    renderHero();
  }

  // ---------------------------------------------------------------- rendu

  function renderPipeline(steps) {
    $("pipeline").innerHTML = steps.map((s, i) => {
      const mark = s.status === "done" ? "✓" : s.status === "warning" ? "!" : s.status === "running" ? "…" : String(i + 1);
      return `
        <li class="step ${s.status}">
          <div class="step-dot" aria-hidden="true">${mark}</div>
          <div>
            <div class="step-label">${esc(s.label)}</div>
            <div class="step-hint">${esc(s.hint)}</div>
          </div>
          <span class="sr-only">${statusText(s.status)}</span>
        </li>`;
    }).join("");
  }

  function statusText(status) {
    return { done: "terminé", running: "en cours", warning: "à vérifier", pending: "à faire" }[status] || "";
  }

  function renderHero() {
    const s = state.status;
    if (!s) return;
    const hasRun = state.jobRunning;
    const sent = s.steps.find((x) => x.id === "sent_at")?.status === "done";
    const warning = s.steps.some((x) => x.status === "warning");

    if (hasRun) {
      $("heroEyebrow").textContent = "En cours";
      $("heroTime").textContent = state.jobLabel || "Opération";
      $("heroSub").textContent = "Suivez l'avancement dans la console ci-dessous.";
    } else if (warning) {
      $("heroEyebrow").textContent = "Action requise";
      $("heroTime").textContent = "Vérifier avant de relancer";
      $("heroSub").textContent = "Un envoi a démarré sans confirmation. Contrôlez les éléments envoyés de la boîte AMEUDataTeam avant toute relance.";
    } else if (sent) {
      $("heroEyebrow").textContent = "Aujourd'hui";
      $("heroTime").textContent = "Envoi effectué ✓";
      $("heroSub").textContent = `Prochain envoi : ${formatDate(s.schedule.next_run)}.`;
    } else if (!s.business_day) {
      $("heroEyebrow").textContent = "Jour non ouvré";
      $("heroTime").textContent = "Pas d'envoi aujourd'hui";
      $("heroSub").textContent = `Prochain envoi : ${formatDate(s.schedule.next_run)}.`;
    } else {
      $("heroEyebrow").textContent = "Prochain envoi";
      $("heroTime").textContent = formatDate(s.schedule.next_run);
      const cd = countdown(s.schedule.next_run);
      $("heroSub").textContent = s.schedule.enabled
        ? (cd ? `${cd}. L'envoi part automatiquement.` : "L'envoi part automatiquement.")
        : "L'envoi automatique est désactivé. Vous pouvez le lancer manuellement.";
    }

    const hero = $("heroCard");
    hero.dataset.state = hasRun ? "run" : warning ? "warn" : sent ? "ok" : "";
    $("btnRun").disabled = hasRun;
    $("btnTest").disabled = hasRun;
    $("btnCheck").disabled = hasRun;
  }

  function renderTask(s) {
    const pill = $("taskPill");
    if (s.schedule.enabled) {
      pill.className = "pill pill-ok";
      pill.textContent = `Automatique · ${s.schedule.run_at}`;
    } else {
      pill.className = "pill pill-warn";
      pill.textContent = "Automatique désactivé";
    }
    $("schedPill").className = `pill ${s.schedule.enabled ? "pill-ok" : "pill-soft"}`;
    $("schedPill").textContent = s.schedule.enabled ? "Activée" : "Désactivée";
    $("nextRun").textContent = s.schedule.enabled && s.schedule.next_run
      ? `Prochaine exécution : ${formatDate(s.schedule.next_run)}`
      : "Aucune exécution programmée.";
  }

  function renderRuns(runs) {
    const map = { "envoyé": "pill-ok", "échec": "pill-err", "incomplet": "pill-warn", "non ouvré": "pill-soft" };
    $("runs").innerHTML = runs.length
      ? runs.map((r) => `
          <li>
            <span class="date">${esc(r.date.slice(6, 8))}/${esc(r.date.slice(4, 6))}/${esc(r.date.slice(0, 4))}</span>
            <span class="pill ${map[r.status] || "pill-soft"}">${esc(r.status)}</span>
          </li>`).join("")
      : `<li class="empty">Aucune exécution enregistrée.</li>`;
  }

  function renderSettings(st) {
    const v = st.validation;
    const rows = [
      ["Expéditeur", st.sender],
      ["Destinataires Six", st.recipients.join(", ")],
      ["Alertes", st.alert_recipients.join(", ")],
      ["Base RMMPRD (DSN)", st.dsn],
      ["Dossier TIS Belges", st.base_dir],
      ["Plage de lignes", `${v.min_rows} à ${v.max_rows}`],
      ["Devises autorisées", v.currencies.join(", ")],
      ["Jours fériés exclus", st.skip_dates.length ? st.skip_dates.join(", ") : "aucun"],
    ];
    $("settings").innerHTML = rows.map(([k, val]) => `<div><dt>${esc(k)}</dt><dd>${esc(val)}</dd></div>`).join("");
  }

  function renderChecklist() {
    const lines = state.checkLines;
    if (!lines.length) return;
    const items = lines
      .map((l) => l.match(/^\[\s*(OK|ECHEC|ATTENTION)\s*\]\s*(.+?)(?:\s:\s(.*))?$/))
      .filter(Boolean);
    $("checklist").innerHTML = items.map(([, status, name, detail]) => {
      const cls = status === "OK" ? "check-ok" : status === "ECHEC" ? "check-err" : "check-warn";
      const icon = status === "OK" ? "✓" : status === "ECHEC" ? "✕" : "!";
      return `<li class="${cls}">
        <span class="check-icon" aria-hidden="true">${icon}</span>
        <div><div class="check-name">${esc(name)}</div>${detail ? `<div class="check-detail">${esc(detail)}</div>` : ""}</div>
      </li>`;
    }).join("");
  }

  // ---------------------------------------------------------------- console

  function classify(line) {
    if (/ERROR|ECHEC|Échec|Traceback|Exception/i.test(line)) return "ln-err";
    if (/WARNING|ATTENTION|warning/i.test(line)) return "ln-warn";
    if (/confirmé|prêt|ajoutée|OK\b|installé|terminé|valide/i.test(line)) return "ln-ok";
    if (/^===/.test(line)) return "ln-head";
    return "";
  }

  function appendConsole(lines) {
    if (!lines.length) return;
    const el = $("console");
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
    if (el.querySelector(".ln-empty")) el.innerHTML = "";
    el.insertAdjacentHTML("beforeend", lines.map((l) => `<span class="${classify(l)}">${esc(l)}</span>\n`).join(""));
    if (atBottom) el.scrollTop = el.scrollHeight;
  }

  function resetConsole() {
    $("console").innerHTML = `<span class="ln-empty">La sortie de l'opération apparaîtra ici.</span>`;
  }

  // ---------------------------------------------------------------- polling

  async function refreshStatus() {
    try {
      const s = await api("/api/status");
      state.status = s;
      renderPipeline(s.steps);
      renderTask(s);
      renderRuns(s.runs);
      renderSettings(s.settings);
      $("pipeDate").textContent = new Date(s.today).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
      if (!$("runAt").matches(":focus")) $("runAt").value = s.schedule.run_at;
      if (!$("schedEnabled").matches(":focus")) $("schedEnabled").checked = s.schedule.enabled;
      renderHero();
    } catch (err) {
      $("taskPill").className = "pill pill-err";
      $("taskPill").textContent = "Dashboard hors ligne";
    }
  }

  async function pollJob() {
    try {
      const { job } = await api(`/api/job?offset=${state.offset}`);
      if (!job) return;
      if (job.label !== state.jobLabel) {
        state.jobLabel = job.label;
        state.offset = 0;
        state.jobLines = [];
        resetConsole();
      }
      const wasRunning = state.jobRunning;
      state.jobRunning = job.running;
      appendConsole(job.lines);
      state.jobLines.push(...job.lines);
      state.offset = job.offset;
      $("jobState").textContent = job.running
        ? `${job.label} en cours…`
        : job.code === 0 ? `${job.label} terminé` : `${job.label} : code ${job.code}`;

      if (job.label === "Contrôle de l'installation" && !job.running) {
        state.checkLines = collectChecks(state.jobLines);
        renderChecklist();
        $("checkedAt").textContent = `Vérifié à ${new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
      }
      if (wasRunning && !job.running) {
        toast(job.code === 0 ? `${job.label} : terminé` : `${job.label} : échec (code ${job.code})`, job.code === 0 ? "ok" : "err");
        refreshStatus();
      }
    } catch (_) { /* hors ligne : on réessaie */ }
  }

  function collectChecks(lines) {
    // Le contrôle écrit une ligne par point, au format « [ OK ] libellé : détail ».
    return lines.filter((l) => /^\[\s*(OK|ECHEC|ATTENTION)\s*\]/.test(l));
  }

  // ---------------------------------------------------------------- actions

  async function start(action, label) {
    try {
      await api("/api/job", { method: "POST", body: { action } });
      state.jobLabel = label;
      state.jobRunning = true;
      state.offset = 0;
      state.jobLines = [];
      resetConsole();
      $("jobState").textContent = `${label} en cours…`;
      renderHero();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  $("btnRun").addEventListener("click", async () => {
    const ok = await confirmBox(
      "Envoyer les TIS Belges à Six ?",
      "Le fichier sera actualisé, contrôlé, archivé puis envoyé aux deux destinataires Six. Une date déjà envoyée ne sera jamais renvoyée.",
      "Envoyer maintenant",
    );
    if (ok) start("run", "Envoi à Six");
  });

  $("btnTest").addEventListener("click", () => start("test", "Essai sans envoi"));
  $("btnCheck").addEventListener("click", () => start("check", "Contrôle de l'installation"));

  $("btnSaveSched").addEventListener("click", async () => {
    const enabled = $("schedEnabled").checked;
    const runAt = $("runAt").value;
    if (enabled && !runAt) return toast("Indiquez une heure.", "err");
    const ok = enabled
      ? await confirmBox("Enregistrer la programmation ?", `Envoi automatique chaque jour ouvré à ${runAt}.`, "Enregistrer")
      : await confirmBox("Désactiver l'envoi automatique ?", "Aucun envoi ne partira sans intervention manuelle.", "Désactiver");
    if (!ok) return;
    try {
      await api("/api/schedule", { method: "POST", body: { enabled, run_at: runAt } });
      toast(enabled ? `Programmation enregistrée : ${runAt}` : "Envoi automatique désactivé", "ok");
      refreshStatus();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnCopy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("console").innerText);
      toast("Console copiée");
    } catch (_) {
      toast("Copie impossible ici", "err");
    }
  });
  $("btnClear").addEventListener("click", resetConsole);

  // ---------------------------------------------------------------- démarrage

  resetConsole();
  tickClock();
  setInterval(tickClock, 1000);
  refreshStatus();
  setInterval(refreshStatus, 5000);
  pollJob();
  setInterval(pollJob, 1000);
})();
