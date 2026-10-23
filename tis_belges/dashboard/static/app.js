(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name, cls = "ico") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const CHECK_LABEL = "Contrôle de l'installation";
  const STATION_ICONS = { validated: "db", archived: "archive", valor_done: "table", am_built: "file", sent_at: "send" };
  const BADGE_ICONS = { done: "check", failed: "x", warning: "alert" };
  const SHORT_LABELS = { validated: "Requête", am_built: "Fichier" };

  const ui = {
    status: null,
    clockOffset: 0,         // décalage horloge serveur / navigateur
    lastSync: 0,
    offline: false,
    job: { label: null, running: false, offset: 0, lines: [] },
    checkLines: [],
    schedDirty: false,
    prevAllDone: null,
    stationsBuilt: false,
  };

  const now = () => new Date(Date.now() + ui.clockOffset);
  const hhmm = (d) => d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const minutesOf = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };

  // ---------------------------------------------------------------- API & retours

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
    el.innerHTML = `${icon(kind === "err" ? "x" : "check")}<span>${esc(message)}</span>`;
    $("toasts").appendChild(el);
    setTimeout(() => {
      el.classList.add("leaving");
      el.addEventListener("animationend", () => el.remove(), { once: true });
    }, 4200);
  }

  function confirmBox({ title, text, ok, iconName = "send", tone = "" }) {
    return new Promise((resolve) => {
      const trigger = document.activeElement;
      $("modalTitle").textContent = title;
      $("modalText").textContent = text;
      $("modalOk").textContent = ok;
      $("modalIco").className = `modal-ico ${tone}`;
      $("modalIco").innerHTML = icon(iconName);
      $("modal").hidden = false;
      $("modalCancel").focus();

      const focusables = [$("modalCancel"), $("modalOk")];
      const close = (value) => {
        $("modal").hidden = true;
        document.removeEventListener("keydown", onKey);
        $("modal").removeEventListener("click", onBackdrop);
        $("modalOk").onclick = $("modalCancel").onclick = null;
        if (trigger && trigger.focus) trigger.focus();
        resolve(value);
      };
      const onKey = (e) => {
        if (e.key === "Escape") close(false);
        if (e.key === "Tab") {           // focus piégé dans la modale
          const i = focusables.indexOf(document.activeElement);
          e.preventDefault();
          focusables[(i + (e.shiftKey ? -1 : 1) + focusables.length) % focusables.length].focus();
        }
      };
      const onBackdrop = (e) => { if (e.target === $("modal")) close(false); };
      $("modalOk").onclick = () => close(true);
      $("modalCancel").onclick = () => close(false);
      document.addEventListener("keydown", onKey);
      $("modal").addEventListener("click", onBackdrop);
    });
  }

  // ---------------------------------------------------------------- thème

  function applyTheme(theme) {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    const dark = theme ? theme === "dark" : !window.matchMedia("(prefers-color-scheme: light)").matches;
    $("themeBtn").innerHTML = icon(dark ? "sun" : "moon");
    $("themeBtn").setAttribute("aria-label", dark ? "Passer en thème clair" : "Passer en thème sombre");
  }

  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("tis-theme"); } catch (_) { /* stockage indisponible */ }
    applyTheme(saved);
    $("themeBtn").addEventListener("click", () => {
      const isDark = document.documentElement.dataset.theme
        ? document.documentElement.dataset.theme === "dark"
        : !window.matchMedia("(prefers-color-scheme: light)").matches;
      const next = isDark ? "light" : "dark";
      try { localStorage.setItem("tis-theme", next); } catch (_) { /* ignoré */ }
      applyTheme(next);
    });
  }

  // ---------------------------------------------------------------- parcours du fichier

  function leadingDone(steps) {
    let d = 0;
    while (d < steps.length && steps[d].status === "done") d++;
    return d;
  }

  function buildStations(steps) {
    $("stations").innerHTML = steps.map((s) => `
      <li class="station" data-id="${s.id}">
        <div class="st-dot">
          ${icon(STATION_ICONS[s.id] || "file")}
          <span class="st-badge"></span>
        </div>
        <p class="st-label"><span class="st-full">${esc(s.label)}</span><span class="st-short" aria-hidden="true">${esc(SHORT_LABELS[s.id] || s.label)}</span></p>
        <p class="st-meta"></p>
        <span class="sr-only st-sr"></span>
      </li>`).join("");
    ui.stationsBuilt = true;
  }

  function renderJourney(s) {
    const steps = s.steps;
    if (!ui.stationsBuilt) buildStations(steps);

    const statusWord = { done: "terminé", running: "en cours", failed: "en échec", warning: "à vérifier", pending: "à venir" };
    steps.forEach((step, i) => {
      const li = $("stations").children[i];
      li.className = `station ${step.status}`;
      li.querySelector(".st-badge").innerHTML = BADGE_ICONS[step.status] ? icon(BADGE_ICONS[step.status]) : "";
      li.querySelector(".st-meta").innerHTML = step.at
        ? `<span class="st-time">${esc(hhmm(new Date(step.at)))}</span>`
        : esc(step.hint);
      li.querySelector(".st-sr").textContent = `Étape ${i + 1} : ${statusWord[step.status] || ""}`;
    });

    // Où se trouve le fichier : première étape non terminée, ou la dernière si tout est fait.
    const d = leadingDone(steps);
    const allDone = d === steps.length;
    const idx = Math.min(d, steps.length - 1);
    const current = steps[idx];
    let haloState = "idle";
    if (allDone) haloState = "done";
    else if (["running", "failed", "warning"].includes(current.status)) haloState = current.status;

    positionToken(idx, haloState);
    $("trackFill").style.transform = `scaleX(${allDone ? 1 : d / (steps.length - 1)})`;
    $("journey").classList.toggle("is-failed", haloState === "failed");

    // L'avion ne part qu'au moment où l'envoi se termine sous nos yeux.
    if (ui.prevAllDone === false && allDone && !reducedMotion.matches) {
      const plane = $("plane");
      plane.classList.remove("fly");
      void plane.offsetWidth;  // relance l'animation
      plane.classList.add("fly");
    }
    ui.prevAllDone = allDone;
  }

  function positionToken(idx, state) {
    const li = $("stations").children[idx];
    if (!li) return;
    const dot = li.querySelector(".st-dot");
    const journey = $("journey").getBoundingClientRect();
    const box = dot.getBoundingClientRect();
    const x = `${Math.round(box.left - journey.left + box.width / 2)}px`;
    const halo = $("halo");
    if (halo.dataset.state !== state) {
      halo.dataset.state = state;
      if (state === "failed") {          // relance la secousse
        halo.style.animation = "none";
        void halo.offsetWidth;
        halo.style.animation = "";
      }
    }
    halo.style.setProperty("--x", x);
    $("plane").style.setProperty("--x", x);
  }

  // ---------------------------------------------------------------- scène

  function formatNext(iso) {
    if (!iso) return "aucun envoi programmé";
    const d = new Date(iso);
    const today = now();
    const tomorrow = new Date(today.getTime() + 86400000);
    const same = (a, b) => a.toDateString() === b.toDateString();
    if (same(d, today)) return `aujourd'hui à ${hhmm(d)}`;
    if (same(d, tomorrow)) return `demain à ${hhmm(d)}`;
    return `${d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} à ${hhmm(d)}`;
  }

  function countdown(iso) {
    const diff = new Date(iso) - now();
    if (diff <= 0) return null;
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    return h > 0 ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
  }

  function renderStage() {
    const s = ui.status;
    if (!s) return;
    const steps = s.steps;
    const d = leadingDone(steps);
    const idx = Math.min(d, steps.length - 1);
    const procRunning = ui.job.running && ui.job.label !== CHECK_LABEL;
    const isTest = s.mode === "test";
    const failed = steps.find((x) => x.status === "failed");
    const warning = steps.find((x) => x.status === "warning");
    const next = s.schedule.next_run;
    const nextIsToday = next && new Date(next).toDateString() === now().toDateString();

    let title;
    let sub;
    if (procRunning) {
      title = isTest ? "Essai en cours" : "Envoi en cours";
      sub = `Étape ${idx + 1} sur ${steps.length} · ${steps[idx].hint}.`;
    } else if (warning) {
      title = "Vérification requise";
      sub = "Un envoi a démarré sans confirmation. Contrôlez les éléments envoyés de la boîte AMEUDataTeam avant toute relance.";
    } else if (failed) {
      title = `${isTest ? "Essai interrompu" : "Échec"} à l'étape « ${esc(failed.label)} »`;
      sub = "Rien n'a été envoyé à Six. Le détail de l'erreur est dans la console.";
    } else if (d === steps.length && isTest) {
      title = "Essai réussi";
      sub = "Toutes les étapes sont passées. Rien n'a été envoyé à Six : le mail de test est parti vers l'adresse opérateur.";
    } else if (d === steps.length) {
      title = `Envoyé à Six à <span class="num">${esc(hhmm(new Date(steps[steps.length - 1].at)))}</span>`;
      sub = `Prochain envoi ${formatNext(next)}.`;
    } else if (!s.business_day) {
      title = "Pas d'envoi aujourd'hui";
      sub = `Jour non ouvré. Prochain envoi ${formatNext(next)}.`;
    } else if (nextIsToday) {
      title = `Envoi prévu à <span class="num">${esc(s.schedule.run_at)}</span>`;
      const cd = countdown(next);
      sub = s.schedule.enabled
        ? `Départ automatique dans ${cd}. Vous pouvez aussi lancer un essai dès maintenant.`
        : "L'envoi automatique est désactivé : lancez l'envoi quand le fichier est prêt.";
    } else {
      title = "Pas encore envoyé aujourd'hui";
      sub = `L'heure prévue (${esc(s.schedule.run_at)}) est passée. Lancez l'envoi ou consultez les derniers jours.`;
    }

    // N'écrit dans le DOM que ce qui change (le rendu tourne chaque seconde).
    if (ui.lastTitle !== title) {
      ui.lastTitle = title;
      $("stageTitle").innerHTML = title;
      $("liveTitle").textContent = $("stageTitle").textContent;
    }
    const subText = sub.replace(/<[^>]+>/g, "");
    if ($("stageSub").textContent !== subText) $("stageSub").textContent = subText;
    $("modeBadge").hidden = !(isTest && (procRunning || d > 0 || failed));
    $("stageDate").textContent = now().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

    // Boutons d'action
    const busy = ui.job.running;
    const runBtn = $("btnRun");
    runBtn.disabled = busy || s.prod_sent;
    $("btnTest").disabled = busy;
    $("btnCheck").disabled = busy;
    const runState = procRunning && !isTest ? "running" : s.prod_sent ? "sent" : "ready";
    if (ui.lastRunState !== runState) {
      ui.lastRunState = runState;
      runBtn.firstElementChild.outerHTML = { running: icon("loader", "ico spin"), sent: icon("check"), ready: icon("send") }[runState];
      $("btnRunLabel").textContent = { running: "Envoi en cours…", sent: "Déjà envoyé aujourd'hui", ready: "Envoyer à Six" }[runState];
    }
  }

  // ---------------------------------------------------------------- rail de la journée

  function renderRail() {
    const s = ui.status;
    if (!s) return;
    const run = minutesOf(s.schedule.run_at);
    const until = Math.max(minutesOf(s.schedule.retry_until), run);
    const start = Math.max(0, Math.min(7 * 60, Math.floor(run / 60) * 60 - 120));
    const end = Math.min(24 * 60, Math.max(20 * 60, Math.ceil(until / 60) * 60 + 120));
    const pct = (m) => `${((Math.min(Math.max(m, start), end) - start) / (end - start)) * 100}%`;

    $("railWindow").style.left = pct(run);
    $("railWindow").style.width = `calc(${pct(until)} - ${pct(run)})`;
    $("railMark").style.left = pct(run);
    $("railMarkLabel").textContent = `Calcul ${s.schedule.run_at}`;

    const n = now();
    const nowMin = n.getHours() * 60 + n.getMinutes();
    $("railNow").style.left = pct(nowMin);
    $("railNowLabel").textContent = hhmm(n);

    // Graduations toutes les 2 h, sauf sous l'étiquette de l'heure actuelle.
    const span = end - start;
    let ticks = "";
    for (let h = Math.ceil(start / 60); h * 60 <= end; h += 2) {
      if (Math.abs(h * 60 - nowMin) / span < 0.05) continue;
      ticks += `<span style="left:${pct(h * 60)}">${String(h).padStart(2, "0")}h</span>`;
    }
    $("railTicks").innerHTML = ticks;
    $("railText").textContent =
      `Il est ${hhmm(n)}. Calcul prévu à ${s.schedule.run_at}, reprises possibles jusqu'à ${s.schedule.retry_until}.`;
  }

  // ---------------------------------------------------------------- panneaux

  function renderSchedule(s) {
    $("schedChip").className = `chip ${s.schedule.enabled ? "chip-ok" : ""}`;
    $("schedChip").innerHTML = s.schedule.enabled ? `${icon("clock")}Active` : "Désactivée";
    $("retryUntil").textContent = s.schedule.retry_until;
    if (!ui.schedDirty) {
      $("runAt").value = s.schedule.run_at;
      $("schedEnabled").checked = s.schedule.enabled;
    }
    $("nextRun").innerHTML = s.schedule.enabled && s.schedule.next_run
      ? `Prochaine exécution <strong>${esc(formatNext(s.schedule.next_run))}</strong>`
      : "Aucune exécution automatique programmée.";
  }

  function markSchedDirty() {
    const s = ui.status;
    if (!s) return;
    ui.schedDirty = $("runAt").value !== s.schedule.run_at || $("schedEnabled").checked !== s.schedule.enabled;
    $("btnSaveSched").disabled = !ui.schedDirty;
    $("btnSaveSched").className = `btn btn-block ${ui.schedDirty ? "btn-primary" : "btn-secondary"}`;
  }

  function renderDays(runs) {
    const map = {
      "envoyé": ["ok", "check", "Envoyé"],
      "échec": ["err", "x", "Échec"],
      "incomplet": ["warn", "alert", "Incomplet"],
      "non ouvré": ["off", "minus", "Non ouvré"],
    };
    if (!runs.length) {
      $("days").innerHTML = `<li class="none">Aucune exécution enregistrée pour l'instant.</li>`;
      return;
    }
    $("days").innerHTML = runs.slice(0, 10).map((r) => {
      const [cls, ico, word] = map[r.status] || ["off", "minus", r.status];
      const d = new Date(`${r.date.slice(0, 4)}-${r.date.slice(4, 6)}-${r.date.slice(6, 8)}T12:00:00`);
      return `<li class="day ${cls}" title="${esc(word)} · journal ${esc(r.log)}">
        <span class="day-date">${esc(r.date.slice(6, 8))}/${esc(r.date.slice(4, 6))}</span>
        <span class="day-week">${esc(d.toLocaleDateString("fr-FR", { weekday: "short" }))}</span>
        ${icon(ico)}
        <span class="day-status">${esc(word)}</span>
      </li>`;
    }).join("");
  }

  function renderSettings(st) {
    const v = st.validation;
    const rows = [
      ["Expéditeur", st.sender],
      ["Destinataires Six", st.recipients.join(", ")],
      ["Alertes", st.alert_recipients.join(", ")],
      ["Base (DSN ODBC)", st.dsn],
      ["Dossier TIS Belges", st.base_dir],
      ["Lignes attendues", `${v.min_rows} à ${v.max_rows}`],
      ["Devises autorisées", v.currencies.join(", ")],
      ["Jours fériés exclus", st.skip_dates.length ? st.skip_dates.join(", ") : "aucun"],
    ];
    $("settings").innerHTML = rows.map(([k, val]) => `<div><dt>${esc(k)}</dt><dd>${esc(val)}</dd></div>`).join("");
  }

  function renderChecks() {
    const items = ui.checkLines
      .map((l) => l.match(/^\[\s*(OK|ECHEC|ATTENTION)\s*\]\s*(.+?)(?:\s:\s(.*))?$/))
      .filter(Boolean);
    if (!items.length) return;
    const cfg = { OK: ["check-ok", "check"], ECHEC: ["check-err", "x"], ATTENTION: ["check-warn", "alert"] };
    $("checks").innerHTML = items.map(([, st, name, detail]) => {
      const [cls, ico] = cfg[st];
      return `<li class="check ${cls}">${icon(ico)}
        <div><p class="check-name">${esc(name)}</p>${detail ? `<p class="check-detail">${esc(detail)}</p>` : ""}</div>
      </li>`;
    }).join("");
  }

  // ---------------------------------------------------------------- synchronisation

  function renderSync() {
    const el = $("sync");
    if (ui.offline) {
      el.className = "sync offline";
      $("syncText").textContent = "Hors ligne : le serveur ne répond pas";
      return;
    }
    if (!ui.lastSync) return;
    const age = Math.round((Date.now() - ui.lastSync) / 1000);
    el.classList.toggle("stale", age > 15);
    $("syncText").textContent = age < 3 ? "Synchronisé" : `Synchronisé il y a ${age} s`;
  }

  async function refreshStatus() {
    try {
      const s = await api("/api/status");
      ui.status = s;
      ui.clockOffset = new Date(s.server_time) - Date.now();
      ui.lastSync = Date.now();
      ui.offline = false;
      $("sync").className = "sync";
      void $("sync").offsetWidth;
      $("sync").classList.add("flash");

      renderJourney(s);
      renderStage();
      renderRail();
      renderSchedule(s);
      renderDays(s.runs);
      renderSettings(s.settings);
    } catch (_) {
      ui.offline = true;
    }
    renderSync();
  }

  // ---------------------------------------------------------------- console & opérations

  function classify(line) {
    if (/ERROR|ECHEC|Échec|Traceback|Exception|Error/.test(line)) return "l-err";
    if (/WARNING|ATTENTION/.test(line)) return "l-warn";
    if (/^===/.test(line) || /=== /.test(line)) return "l-head";
    if (/confirmé|prêt|ajoutées|valide|\[\s*OK\s*\]|Archivé|terminée/.test(line)) return "l-ok";
    return "";
  }

  function resetConsole() {
    $("console").innerHTML = `<span class="l-empty">La sortie des opérations s'affiche ici en direct.</span>`;
  }

  function appendConsole(lines) {
    if (!lines.length) return;
    const el = $("console");
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
    if (el.querySelector(".l-empty")) el.innerHTML = "";
    el.insertAdjacentHTML("beforeend", lines.map((l) => `<span class="${classify(l)}">${esc(l)}</span>\n`).join(""));
    if (atBottom) el.scrollTop = el.scrollHeight;
  }

  function renderJobChip(job) {
    const chip = $("jobChip");
    if (!job) { chip.className = "chip"; chip.textContent = "Aucune opération"; return; }
    if (job.running) {
      chip.className = "chip chip-run";
      chip.innerHTML = `${icon("loader", "ico spin")}${esc(job.label)}`;
    } else if (job.code === 0) {
      chip.className = "chip chip-ok";
      chip.innerHTML = `${icon("check")}${esc(job.label)} : terminé`;
    } else {
      chip.className = "chip chip-err";
      chip.innerHTML = `${icon("x")}${esc(job.label)} : échec`;
    }
  }

  async function pollJob() {
    try {
      const { job } = await api(`/api/job?offset=${ui.job.offset}`);
      if (!job) return;
      if (job.label !== ui.job.label || job.started !== ui.job.started) {
        Object.assign(ui.job, { label: job.label, started: job.started, offset: 0, lines: [] });
        resetConsole();
        if (job.offset > 0) return;      // relit depuis le début au prochain tour
      }
      const wasRunning = ui.job.running;
      ui.job.running = job.running;
      appendConsole(job.lines);
      ui.job.lines.push(...job.lines);
      ui.job.offset = job.offset;
      renderJobChip(job);

      if (job.label === CHECK_LABEL && !job.running) {
        ui.checkLines = ui.job.lines.filter((l) => /^\[\s*(OK|ECHEC|ATTENTION)\s*\]/.test(l));
        renderChecks();
        if (ui.checkLines.length) $("checkedAt").textContent = `Vérifié à ${hhmm(now())}`;
      }
      if (wasRunning !== job.running) {
        if (wasRunning && !job.running) {
          toast(job.code === 0 ? `${job.label} : terminé` : `${job.label} : échec`, job.code === 0 ? "ok" : "err");
        }
        refreshStatus();
      }
    } catch (_) { /* hors ligne : la synchronisation l'affiche */ }
  }

  async function start(action, label) {
    try {
      await api("/api/job", { method: "POST", body: { action } });
      Object.assign(ui.job, { label, started: null, running: true, offset: 0, lines: [] });
      resetConsole();
      renderJobChip({ label, running: true });
      renderStage();
      if (action !== "check") document.getElementById("journey").scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "nearest" });
      refreshStatus();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  // ---------------------------------------------------------------- actions

  $("btnRun").addEventListener("click", async () => {
    const ok = await confirmBox({
      title: "Envoyer les TIS Belges à Six ?",
      text: "Le fichier sera actualisé, contrôlé, archivé puis envoyé aux deux adresses Six. Si un contrôle échoue, rien ne part.",
      ok: "Envoyer maintenant",
    });
    if (ok) start("run", "Envoi à Six");
  });

  $("btnTest").addEventListener("click", async () => {
    const ok = await confirmBox({
      title: "Lancer un essai ?",
      text: "Même déroulé que l'envoi réel, dans un dossier de test. Le mail part uniquement vers l'adresse opérateur.",
      ok: "Lancer l'essai",
      iconName: "flask",
      tone: "test",
    });
    if (ok) start("test", "Essai sans envoi");
  });

  $("btnCheck").addEventListener("click", () => start("check", CHECK_LABEL));
  $("checks").addEventListener("click", (e) => {
    if (e.target.closest("[data-action='check']")) start("check", CHECK_LABEL);
  });

  $("runAt").addEventListener("input", markSchedDirty);
  $("schedEnabled").addEventListener("change", markSchedDirty);
  $("btnSaveSched").addEventListener("click", async () => {
    const enabled = $("schedEnabled").checked;
    const runAt = $("runAt").value;
    if (enabled && !runAt) { toast("Indiquez une heure de calcul.", "err"); $("runAt").focus(); return; }
    try {
      await api("/api/schedule", { method: "POST", body: { enabled, run_at: runAt } });
      ui.schedDirty = false;
      $("btnSaveSched").disabled = true;
      $("btnSaveSched").className = "btn btn-block btn-secondary";
      toast(enabled ? `Envoi automatique programmé à ${runAt}` : "Envoi automatique désactivé", "ok");
      refreshStatus();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnCopy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("console").innerText);
      toast("Console copiée", "ok");
    } catch (_) {
      toast("Copie impossible dans ce navigateur", "err");
    }
  });
  $("btnClear").addEventListener("click", resetConsole);

  window.addEventListener("resize", () => { if (ui.status) renderJourney(ui.status); });

  // ---------------------------------------------------------------- démarrage

  initTheme();
  resetConsole();
  refreshStatus();
  pollJob();
  setInterval(refreshStatus, 3000);
  setInterval(pollJob, 1000);
  setInterval(() => { renderSync(); renderRail(); renderStage(); }, 1000);
})();
