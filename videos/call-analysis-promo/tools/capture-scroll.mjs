// Capture the detail view at specific body scroll offsets.
// Usage: node tools/capture-scroll.mjs <port> <scrollY> <outname> [callSubstring]
const DEBUG_PORT = process.argv[2] || "9222";
const SCROLL = Number(process.argv[3] || 0);
const NAME = process.argv[4] || "detail-shot.png";
const CALL_SUB = process.argv[5] || "completed";
const APP_URL = "http://127.0.0.1:8787/";

let msgId = 0;
const pending = new Map();

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  const ready = new Promise((res, rej) => { ws.onopen = () => res(); ws.onerror = () => rej(new Error("ws")); });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? reject(new Error(m.error.message)) : resolve(m.result);
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

async function waitFor(cdp, expression, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await evalJs(cdp, expression)) return;
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("timeout");
}

const main = async () => {
  let tabs = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`)).json();
  let page = tabs.find((t) => t.type === "page");
  if (!page) {
    await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?about:blank`, { method: "PUT" });
    await new Promise((r) => setTimeout(r, 800));
    tabs = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`)).json();
    page = tabs.find((t) => t.type === "page");
  }
  if (!page) throw new Error("no page tab");
  const cdp = connect(page.webSocketDebuggerUrl);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 2, mobile: false });
  await cdp.send("Page.navigate", { url: APP_URL });
  await waitFor(cdp, `document.querySelectorAll('#callList li').length > 0`);
  await evalJs(cdp, `(() => { const it = [...document.querySelectorAll('#callList li')]; const d = it.find(li => li.textContent.includes(${JSON.stringify(CALL_SUB)})); if (d) d.click(); return true; })()`);
  await waitFor(cdp, `document.getElementById('transcript').children.length > 0`);
  await new Promise((r) => setTimeout(r, 2000));
  await evalJs(cdp, `(() => { window.scrollTo(0, ${SCROLL}); return true; })()`);
  await new Promise((r) => setTimeout(r, 600));
  const { data } = await cdp.send("Page.captureScreenshot", { format: "png", fromSurface: true });
  const fs = await import("node:fs");
  fs.writeFileSync(NAME, Buffer.from(data, "base64"));
  console.log("saved", NAME, "scroll", SCROLL);
  cdp.close();
};
main().catch((e) => { console.error("FAILED:", e.message); process.exit(1); });
