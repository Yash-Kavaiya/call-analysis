/* NVIDIA-themed contact center dashboard */

const state = {
  calls: [],
  selectedId: null,
  detail: null,
  sentimentChart: null,
  pollTimer: null,
};

const $ = (id) => document.getElementById(id);

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    const bar = $("healthBar");
    if (h.nvidia_key_configured) {
      bar.textContent = `NVIDIA NIM ready · ${h.model}`;
      bar.className = "status-bar ok";
    } else {
      bar.textContent = "NVIDIA_API_KEY not configured";
      bar.className = "status-bar bad";
    }
  } catch (e) {
    $("healthBar").textContent = `API offline: ${e.message}`;
    $("healthBar").className = "status-bar bad";
  }
}

async function loadAnalytics() {
  try {
    const a = await api("/api/analytics");
    $("statTotal").textContent = String(a.total_calls ?? 0);
    $("statQa").textContent = a.avg_qa_score != null ? Math.round(a.avg_qa_score) : "—";
    $("statComp").textContent =
      a.avg_compliance_score != null ? Math.round(a.avg_compliance_score) : "—";
    $("statPii").textContent = String(a.total_pii_findings ?? 0);
  } catch (_) {
    /* optional panel */
  }
}

async function loadCalls() {
  const data = await api("/api/calls");
  state.calls = data.calls || [];
  renderCallList();
  await loadAnalytics();
  if (state.selectedId) {
    const still = state.calls.find((c) => c.id === state.selectedId);
    if (still && (still.status === "processing" || still.status === "pending")) {
      schedulePoll();
    }
  } else if (state.calls.some((c) => c.status === "processing" || c.status === "pending")) {
    schedulePoll();
  }
}

function renderCallList() {
  const ul = $("callList");
  ul.innerHTML = "";
  if (!state.calls.length) {
    ul.innerHTML = `<li class="muted" style="cursor:default">No calls yet</li>`;
    return;
  }
  for (const c of state.calls) {
    const li = document.createElement("li");
    if (c.id === state.selectedId) li.classList.add("active");
    const score = c.qa_score != null ? `QA ${Math.round(c.qa_score)}` : "—";
    const pct = Math.round((c.progress_pct || 0) * 100);
    const showProg = c.status === "processing" || c.status === "pending";
    li.innerHTML = `
      <div class="fn" title="${escapeHtml(c.filename)}">${escapeHtml(c.filename)}</div>
      <div class="meta"><span>${escapeHtml(c.status)}${showProg ? " " + pct + "%" : ""}</span><span>${score}</span></div>
      ${showProg ? `<div class="prog"><i style="width:${pct}%"></i></div>` : ""}`;
    li.onclick = () => selectCall(c.id);
    ul.appendChild(li);
  }
}

function schedulePoll() {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(async () => {
    try {
      await loadCalls();
      if (state.selectedId) await loadDetail(state.selectedId, false);
    } catch (_) {}
  }, 2000);
}

async function selectCall(id) {
  state.selectedId = id;
  renderCallList();
  await loadDetail(id, true);
}

async function loadDetail(id, showLoading) {
  if (showLoading) {
    $("callTitle").textContent = "Loading…";
  }
  const d = await api(`/api/calls/${id}`);
  state.detail = d;
  renderDetail(d);
  if (d.status === "processing" || d.status === "pending") schedulePoll();
}

function renderProgress(d) {
  const wrap = $("progressWrap");
  const fill = $("progressFill");
  const label = $("progressLabel");
  if (d.status === "processing" || d.status === "pending") {
    wrap.classList.remove("hidden");
    const pct = Math.round((d.progress_pct || 0) * 100);
    fill.style.width = `${pct}%`;
    label.textContent = `${d.progress_message || d.status} · ${pct}%`;
  } else if (d.status === "failed") {
    wrap.classList.remove("hidden");
    fill.style.width = "100%";
    fill.style.background = "var(--danger)";
    label.textContent = d.error || "Failed";
  } else {
    wrap.classList.add("hidden");
    fill.style.background = "";
  }
}

function renderDetail(d) {
  $("callTitle").textContent = d.filename || d.id;
  const dur = d.duration_sec != null ? `${d.duration_sec.toFixed(1)}s` : "—";
  $("callMeta").textContent = `${d.language || "lang?"} · ${dur} · ${d.status}${
    d.error ? " · " + d.error : ""
  }`;
  $("durationLabel").textContent = dur;
  renderProgress(d);

  const re = $("reanalyzeBtn");
  if (d.id && d.status !== "processing") {
    re.classList.remove("hidden");
  } else {
    re.classList.add("hidden");
  }

  const badges = $("statusBadges");
  badges.innerHTML = "";
  badges.appendChild(
    pill(
      d.status,
      d.status === "completed" ? "ok" : d.status === "failed" ? "err" : "warn"
    )
  );
  if (d.metadata?.asr_device) badges.appendChild(pill(`ASR ${d.metadata.asr_device}`, "ok"));
  if (d.pii_findings?.length)
    badges.appendChild(pill(`${d.pii_findings.length} PII redacted`, "warn"));

  drawWaveform(d.waveform_peaks || []);
  renderScorecards(d.agents || {});
  renderSentiment(d);
  renderTranscript(d);
  renderAgents(d.agents || {});
  $("piiBadge").textContent = d.pii_findings?.length
    ? `${d.pii_findings.length} PII entities scrubbed`
    : "No PII detected";
}

function pill(text, cls) {
  const s = document.createElement("span");
  s.className = `pill ${cls || ""}`;
  s.textContent = text;
  return s;
}

function drawWaveform(peaks) {
  const canvas = $("waveform");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 600;
  const h = 96;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  ctx.strokeStyle = "#1e2a1a";
  ctx.lineWidth = 1;
  for (let y = 0; y < h; y += 16) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  if (!peaks.length) {
    ctx.fillStyle = "#5a5a70";
    ctx.font = "13px Segoe UI";
    ctx.fillText("Waveform appears after analysis", 16, h / 2);
    return;
  }

  const mid = h / 2;
  const n = peaks.length;
  const barW = Math.max(1, w / n - 0.5);
  for (let i = 0; i < n; i++) {
    const amp = Math.max(0.02, peaks[i]) * (h * 0.42);
    const x = (i / n) * w;
    const grad = ctx.createLinearGradient(0, mid - amp, 0, mid + amp);
    grad.addColorStop(0, "#a6ff00");
    grad.addColorStop(0.5, "#76b900");
    grad.addColorStop(1, "#3d6000");
    ctx.fillStyle = grad;
    ctx.fillRect(x, mid - amp, barW, amp * 2);
  }

  ctx.strokeStyle = "rgba(118,185,0,0.35)";
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(w, mid);
  ctx.stroke();
}

function renderScorecards(agents) {
  const el = $("scorecards");
  const keys = [
    ["qa_scorecard", "QA"],
    ["compliance_risk", "Compliance"],
    ["sentiment_emotion", "Sentiment"],
    ["root_cause_intent", "Intent"],
  ];
  el.innerHTML = keys
    .map(([k, label]) => {
      const a = agents[k];
      const val = a && a.score != null ? Math.round(a.score) : "—";
      return `<div class="score"><div class="val">${val}</div><div class="lbl">${label}</div></div>`;
    })
    .join("");
}

function renderSentiment(d) {
  const ctx = $("sentimentChart").getContext("2d");
  const timeline =
    d.agents?.sentiment_emotion?.details?.timeline ||
    (d.segments || []).map((s) => ({
      t: s.start,
      sentiment: s.sentiment ?? 0,
    }));

  const labels = timeline.map((p) => `${Number(p.t).toFixed(0)}s`);
  const data = timeline.map((p) => p.sentiment);

  if (state.sentimentChart) {
    state.sentimentChart.destroy();
  }

  state.sentimentChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels.length ? labels : ["0"],
      datasets: [
        {
          label: "Sentiment",
          data: data.length ? data : [0],
          borderColor: "#76b900",
          backgroundColor: "rgba(118,185,0,0.15)",
          fill: true,
          tension: 0.3,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          min: -1,
          max: 1,
          ticks: { color: "#8b8ba3" },
          grid: { color: "#2a2a3d" },
        },
        x: {
          ticks: { color: "#8b8ba3", maxTicksLimit: 8 },
          grid: { color: "#1e1e2c" },
        },
      },
    },
  });
}

function renderTranscript(d) {
  const el = $("transcript");
  const segs = d.segments || [];
  if (!segs.length) {
    const t = d.scrubbed_transcript || d.full_transcript || "No transcript yet.";
    el.innerHTML = `<pre style="white-space:pre-wrap;margin:0">${escapeHtml(t)}</pre>`;
    return;
  }
  el.innerHTML = segs
    .map((s) => {
      const sp = (s.speaker || "SPEAKER_00").includes("01") ? "s1" : "s0";
      return `<div class="seg ${sp}">
        <div class="who">${escapeHtml(s.speaker)} · ${Number(s.start).toFixed(1)}s–${Number(
        s.end
      ).toFixed(1)}s</div>
        <div>${escapeHtml(s.text)}</div>
      </div>`;
    })
    .join("");
}

function renderAgents(agents) {
  const el = $("agents");
  const order = [
    "qa_scorecard",
    "compliance_risk",
    "sentiment_emotion",
    "root_cause_intent",
    "crm_action_items",
    "call_copilot",
  ];
  const titles = {
    qa_scorecard: "QA Scorecard Agent",
    compliance_risk: "Compliance & Risk Agent",
    sentiment_emotion: "Sentiment & Emotional Vector Agent",
    root_cause_intent: "Root Cause & Intent Mining Agent",
    crm_action_items: "Action Item & CRM Sync Agent",
    call_copilot: "Interactive Call Copilot (RAG)",
  };

  el.innerHTML =
    order
      .filter((k) => agents[k])
      .map((k) => {
        const a = agents[k];
        const extras = [];
        if (a.details?.coaching_tips)
          extras.push(...(a.details.coaching_tips || []).slice(0, 3));
        if (a.details?.flags)
          extras.push(
            ...(a.details.flags || []).slice(0, 2).map((f) => f.severity || f.type)
          );
        if (a.details?.action_items)
          extras.push(
            ...(a.details.action_items || [])
              .slice(0, 3)
              .map((x) => x.action || JSON.stringify(x))
          );
        if (a.details?.root_causes)
          extras.push(...(a.details.root_causes || []).slice(0, 3));
        if (a.details?.key_facts) extras.push(...(a.details.key_facts || []).slice(0, 3));
        const list = extras.length
          ? `<ul>${extras.map((x) => `<li>${escapeHtml(String(x))}</li>`).join("")}</ul>`
          : "";
        return `<div class="agent-card"><h4>${titles[k] || k}</h4><p>${escapeHtml(
          a.summary || ""
        )}</p>${list}</div>`;
      })
      .join("") ||
    `<p class="muted">Agent insights appear after analysis completes.</p>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function importSamples(limit) {
  toast(`Importing ${limit} sample recording(s)…`);
  const data = await api("/api/calls/import-local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit, analyze: true, skip_existing: true }),
  });
  const n = (data.imported || []).length;
  toast(n ? `Imported ${n} call(s)` : "No new files (already imported)");
  await loadCalls();
  const first = data.imported?.[0];
  if (first) await selectCall(first.id);
}

// Events
$("refreshBtn").onclick = () =>
  Promise.all([loadCalls(), loadHealth()]).catch((e) => toast(e.message));

$("fileInput").onchange = async (ev) => {
  const file = ev.target.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    toast("Uploading…");
    const res = await fetch("/api/calls/upload?analyze=true", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    toast(`Queued ${data.filename}`);
    await loadCalls();
    await selectCall(data.id);
  } catch (e) {
    toast(`Upload failed: ${e.message}`);
  } finally {
    ev.target.value = "";
  }
};

$("importBtn").onclick = () => importSamples(1).catch((e) => toast(e.message));
$("importBatchBtn").onclick = () => importSamples(3).catch((e) => toast(e.message));

$("reanalyzeBtn").onclick = async () => {
  if (!state.selectedId) return;
  try {
    await api(`/api/calls/${state.selectedId}/analyze`, { method: "POST" });
    toast("Re-analysis queued");
    schedulePoll();
    await loadDetail(state.selectedId, false);
  } catch (e) {
    toast(e.message);
  }
};

$("copilotForm").onsubmit = async (ev) => {
  ev.preventDefault();
  const q = $("copilotInput").value.trim();
  if (!q || !state.selectedId) return;
  const log = $("copilotLog");
  log.innerHTML += `<div class="q">You: ${escapeHtml(q)}</div>`;
  $("copilotInput").value = "";
  try {
    const data = await api(`/api/calls/${state.selectedId}/copilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    log.innerHTML += `<div class="a">Copilot: ${escapeHtml(data.answer)}</div>`;
    log.scrollTop = log.scrollHeight;
  } catch (e) {
    log.innerHTML += `<div class="a">Error: ${escapeHtml(e.message)}</div>`;
  }
};

window.addEventListener("resize", () => {
  if (state.detail) drawWaveform(state.detail.waveform_peaks || []);
});

// boot
loadHealth();
loadCalls().catch((e) => toast(e.message));
