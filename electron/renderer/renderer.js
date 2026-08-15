"use strict";

/** Loading screen renderer — streams backend boot logs and reflects state. */

const statusText = document.getElementById("statusText");
const progressFill = document.getElementById("progressFill");
const logEl = document.getElementById("log");
const keyLink = document.getElementById("keyLink");
const spinner = document.getElementById("spinner");

const STAGE_STEPS = {
  starting: 0.15,
  running: 1.0,
  error: 1.0,
};

function setProgress(pct) {
  progressFill.style.width = `${Math.round(pct * 100)}%`;
}

function setState(state) {
  const pct = STAGE_STEPS[state] ?? 0.15;
  setProgress(pct);
  if (state === "running") {
    statusText.textContent = "Engine ready — opening dashboard…";
    spinner.style.display = "none";
  } else if (state === "error") {
    statusText.textContent = "Failed to start the analysis engine. See log below.";
    spinner.style.display = "none";
  }
}

function appendLog(line) {
  logEl.textContent += `${line}\n`;
  logEl.scrollTop = logEl.scrollHeight;
  // Progress roughly tracks how many backend lines have arrived.
  setProgress(0.15 + Math.min(0.55, logEl.textContent.length / 4000));
}

// Periodic "alive" heartbeat so the bar always moves on first launch.
let heartbeat = 0;
setInterval(() => {
  heartbeat = (heartbeat + 1) % 3;
  if (heartbeat === 0) {
    setProgress(0.15 + (Math.random() * 0.25));
  }
}, 3000);

window.desktop.onBackendLog(appendLog);
window.desktop.onBackendState(({ state }) => setState(state));
keyLink.addEventListener("click", (e) => {
  e.preventDefault();
  window.desktop.openExternal("https://build.nvidia.com");
});

// Pull whatever already accumulated before we subscribed.
window.desktop.getBackendStatus().then((status) => {
  for (const line of status.logs || []) appendLog(line);
  setState(status.state);
});
