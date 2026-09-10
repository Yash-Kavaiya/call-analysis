// Drives headless Chrome via CDP to capture the Call Analysis detail view:
//   shot 1: detail view top (waveform / scorecard / sentiment)
//   shot 2: detail view scrolled (transcript / agents)
//   shot 3: copilot panel with a real answered question
// Usage: node tools/capture-detail.mjs <chrome-debug-port> <out-dir>
const DEBUG_PORT = process.argv[2] || "9222";
const OUT_DIR = process.argv[3] || "capture/screenshots";
const APP_URL = "http://127.0.0.1:8787/";
const OUT = new URL(`file:///${process.cwd().replace(/\\/g, "/")}/${OUT_DIR.replace(/\\/g, "/")}/`).pathname;

let msgId = 0;
const pending = new Map();

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  const ready = new Promise((res, rej) => {
    ws.onopen = () => res();
    ws.onerror = (e) => rej(new Error("WS error"));
  });
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    }
  };
  async function send(method, params = {}) {
    await ready;
    return new Promise((resolve, reject) => {
      const id = ++msgId;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }
  return { send, close: () => ws.close() };
}

async function evalJs(cdp, expression) {
  const r = await cdp.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
  return r.result.value;
}

async function waitFor(cdp, expression, timeoutMs = 20000, label = expression) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await evalJs(cdp, expression)) return true;
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`timeout waiting for: ${label}`);
}

async function shot(cdp, name) {
  const { data } = await cdp.send("Page.captureScreenshot", { format: "png", fromSurface: true });
  const fs = await import("node:fs");
  const path = await import("node:path");
  const file = path.join(OUT_DIR, name);
  fs.writeFileSync(file, Buffer.from(data, "base64"));
  console.log("saved", file);
}

const main = async () => {
  const tabs = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`)).json();
  const page = tabs.find((t) => t.type === "page");
  const cdp = connect(page.webSocketDebuggerUrl);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 2,
    mobile: false,
  });
  await cdp.send("Page.navigate", { url: APP_URL });
  await waitFor(cdp, `document.readyState === 'complete'`);
  // Wait for the call list to render
  await waitFor(cdp, `document.querySelectorAll('#callList li').length > 0`, 30000, "call list");
  console.log("calls rendered");

  // Click the first completed call
  const clicked = await evalJs(cdp, `
    (() => {
      const items = [...document.querySelectorAll('#callList li')];
      const done = items.find(li => li.textContent.includes('Devanshi Pandya TCS'));
      if (!done) return false;
      done.click();
      return true;
    })()
  `);
  if (!clicked) throw new Error("no completed call found");
  console.log("clicked completed call");

  // Wait for transcript to populate (main detail render)
  await waitFor(cdp, `document.getElementById('transcript').children.length > 0`, 40000, "transcript");
  // Charts animate in; give them a moment
  await new Promise((r) => setTimeout(r, 2500));

  // Shot 1: top of detail view
  await evalJs(cdp, `window.scrollTo(0, 0)`);
  await new Promise((r) => setTimeout(r, 300));
  await shot(cdp, "detail-top.png");

  // Shot 2: scroll the main panel to reveal transcript + agents
  await evalJs(cdp, `(document.querySelector('.main')||document.body).scrollTo({top: 99999, behavior: 'instant'})`);
  await new Promise((r) => setTimeout(r, 500));
  await shot(cdp, "detail-scroll.png");

  // Shot 3: ask the copilot a real question
  await evalJs(cdp, `
    (() => {
      const input = document.getElementById('copilotInput');
      const form = document.getElementById('copilotForm');
      if (!input || !form) return false;
      input.value = "What was the customer's main concern, and what action item did the agent commit to?";
      form.requestSubmit();
      return true;
    })()
  `);
  console.log("asked copilot, waiting for answer…");
  await waitFor(cdp, `document.getElementById('copilotLog').children.length >= 2`, 90000, "copilot answer");
  await new Promise((r) => setTimeout(r, 1000));
  await shot(cdp, "detail-copilot.png");

  cdp.close();
  console.log("done");
};

main().catch((e) => {
  console.error("FAILED:", e.message);
  process.exit(1);
});
