"use strict";

/**
 * Call Analysis — Electron main process.
 *
 * Responsibilities:
 *  - Single-instance lock.
 *  - Locate a free TCP port and spawn the Python backend
 *    (dev: `python -m call_analysis.serve`; packaged: bundled PyInstaller exe).
 *  - Wait for /api/health to go green, then load the dashboard.
 *  - Expose backend status/logs to the renderer via preload + IPC.
 *  - Shut the backend down cleanly on quit (POST /api/system/shutdown).
 */

const { app, BrowserWindow, ipcMain, shell, Menu, nativeImage } = require("electron");
const { spawn, execFile } = require("child_process");
const http = require("http");
const net = require("net");
const path = require("path");
const fs = require("fs");

const APP_NAME = "Call Analysis";
const DEFAULT_PORT = 8787;
const HEALTH_TIMEOUT_MS = 90_000; // allow first-run model/ffmpeg warm-up
const HEALTH_INTERVAL_MS = 500;

let mainWindow = null;
let backendProc = null;
let backendPort = null;
let backendState = "starting"; // starting | running | error | stopped
let backendLogs = [];
let isQuitting = false;

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

function log(...args) {
  const line = `[main] ${new Date().toISOString()} ${args.join(" ")}`;
  console.log(line);
  pushLog(line);
}

function pushLog(line) {
  backendLogs.push(line);
  if (backendLogs.length > 1000) backendLogs.shift();
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("backend:log", line);
  }
}

// ---------------------------------------------------------------------------
// Single instance
// ---------------------------------------------------------------------------

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// Free port discovery
// ---------------------------------------------------------------------------

function findFreePort(preferred) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", (err) => {
      if (err.code === "EADDRINUSE" && preferred) {
        // Preferred port busy → let the OS pick a free one.
        findFreePort(null).then(resolve, reject);
      } else {
        reject(err);
      }
    });
    server.listen(preferred || 0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

// ---------------------------------------------------------------------------
// Backend process management
// ---------------------------------------------------------------------------

function pythonExecutable() {
  return process.env.CALL_ANALYSIS_PYTHON || "python";
}

function devBackendCommand(port) {
  const projectRoot = path.resolve(__dirname, "..");
  return {
    cmd: pythonExecutable(),
    args: [
      "-m",
      "call_analysis.serve",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--no-browser",
      "--workers",
      "1",
    ],
    cwd: projectRoot,
    env: {
      ...process.env,
      PYTHONPATH: path.join(projectRoot, "src"),
      CALL_ANALYSIS_NO_BROWSER: "1",
      CALL_ANALYSIS_ELECTRON: "1",
      LOG_FORMAT: process.env.LOG_FORMAT || "console",
    },
  };
}

function packagedBackendCommand(port) {
  const exe = path.join(process.resourcesPath, "backend", "CallAnalysisBackend.exe");
  return {
    cmd: exe,
    args: [
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--no-browser",
      "--workers",
      "1",
    ],
    cwd: path.join(app.getPath("userData"), "backend-cwd"),
    env: {
      ...process.env,
      CALL_ANALYSIS_NO_BROWSER: "1",
      CALL_ANALYSIS_ELECTRON: "1",
    },
  };
}

function startBackend(port) {
  const cmd = app.isPackaged ? packagedBackendCommand(port) : devBackendCommand(port);
  const dataDir = path.join(app.getPath("userData"), "data");

  pushLog(`Spawning backend: ${cmd.cmd} ${cmd.args.join(" ")}`);
  pushLog(`Data dir: ${dataDir}`);

  fs.mkdirSync(dataDir, { recursive: true });
  if (cmd.cwd) fs.mkdirSync(cmd.cwd, { recursive: true });

  const env = {
    ...cmd.env,
    STORAGE_DATA_DIR: dataDir,
    CALL_ANALYSIS_DATA_DIR: dataDir,
  };

  backendProc = spawn(cmd.cmd, cmd.args, {
    cwd: cmd.cwd,
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  backendProc.stdout.on("data", (chunk) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line.trim()) pushLog(`[backend] ${line.trim()}`);
    }
  });

  backendProc.stderr.on("data", (chunk) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line.trim()) pushLog(`[backend:err] ${line.trim()}`);
    }
  });

  backendProc.on("error", (err) => {
    backendState = "error";
    pushLog(`Backend failed to spawn: ${err.message}`);
  });

  backendProc.on("exit", (code, signal) => {
    pushLog(`Backend exited code=${code} signal=${signal}`);
    if (!isQuitting) {
      backendState = "error";
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("backend:state", { state: backendState });
      }
    }
  });
}

function healthCheck(port) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: "127.0.0.1", port, path: "/api/health", timeout: 1500 },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(port) {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (backendState === "error") return false;
    if (await healthCheck(port)) return true;
    await new Promise((r) => setTimeout(r, HEALTH_INTERVAL_MS));
  }
  return false;
}

// ---------------------------------------------------------------------------
// Graceful shutdown
// ---------------------------------------------------------------------------

function requestBackendShutdown(port) {
  return new Promise((resolve) => {
    try {
      const req = http.request(
        {
          host: "127.0.0.1",
          port,
          path: "/api/system/shutdown",
          method: "POST",
          timeout: 3000,
        },
        (res) => {
          res.resume();
          resolve();
        }
      );
      req.on("error", () => resolve());
      req.on("timeout", () => {
        req.destroy();
        resolve();
      });
      req.end();
    } catch {
      resolve();
    }
  });
}

async function stopBackend() {
  if (!backendProc) return;
  isQuitting = true;
  if (backendPort) {
    await requestBackendShutdown(backendPort);
    // Give the server a moment to flush state before forcing.
    await new Promise((r) => setTimeout(r, 600));
  }
  if (!backendProc.killed) {
    try {
      backendProc.kill();
    } catch {
      /* already gone */
    }
  }
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

function createLoadingWindow(port) {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    show: false,
    backgroundColor: "#0b0f14",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "assets", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http")) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    const allowed = url.startsWith(`http://127.0.0.1:${port}`);
    if (!allowed) e.preventDefault();
  });

  // Load the loading screen first.
  win.loadFile(path.join(__dirname, "renderer", "index.html"), {
    query: { port: String(port) },
  });
  return win;
}

function openDashboard() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
}

// ---------------------------------------------------------------------------
// IPC (preload bridge)
// ---------------------------------------------------------------------------

ipcMain.handle("backend:get-status", () => ({
  state: backendState,
  port: backendPort,
  url: backendPort ? `http://127.0.0.1:${backendPort}/` : null,
  logs: backendLogs.slice(-200),
}));

ipcMain.handle("app:quit", async () => {
  app.quit();
  return true;
});

ipcMain.handle("app:open-external", (_e, url) => {
  if (typeof url === "string" && /^https?:\/\//.test(url)) shell.openExternal(url);
  return true;
});

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac
      ? [{ role: "appMenu" }]
      : [
          {
            label: "File",
            submenu: [
              {
                label: "Reload Dashboard",
                accelerator: "Ctrl+R",
                click: () => {
                  if (mainWindow && backendPort) {
                    mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
                  }
                },
              },
              { type: "separator" },
              { role: "quit" },
            ],
          },
        ]),
    { role: "viewMenu" },
    {
      label: "Help",
      submenu: [
        {
          label: "Get a free NVIDIA API key",
          click: () => shell.openExternal("https://build.nvidia.com"),
        },
        {
          label: "About",
          click: () => {
            shell.openExternal("https://github.com/yourorg/call-analysis");
          },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(async () => {
  buildMenu();

  // Keep the app name right for taskbar/notifications on Windows.
  app.setAppUserModelId("com.callanalysis.desktop");

  backendPort = await findFreePort(DEFAULT_PORT).catch(() => DEFAULT_PORT);
  backendState = "starting";
  pushLog(`Using backend port ${backendPort}`);

  mainWindow = createLoadingWindow(backendPort);

  startBackend(backendPort);
  const ok = await waitForBackend(backendPort);

  if (ok) {
    backendState = "running";
    pushLog("Backend healthy — loading dashboard");
    mainWindow.webContents.send("backend:state", { state: "running" });
    setTimeout(openDashboard, 250);
  } else {
    backendState = "error";
    pushLog("Backend did not become healthy in time");
    mainWindow.webContents.send("backend:state", { state: "error" });
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createLoadingWindow(backendPort);
      if (backendState === "running") setTimeout(openDashboard, 250);
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", async (e) => {
  if (isQuitting) return;
  e.preventDefault();
  await stopBackend();
  isQuitting = true;
  app.exit(0);
});

app.on("will-quit", () => {
  if (backendProc && !backendProc.killed) {
    try {
      backendProc.kill();
    } catch {
      /* ignore */
    }
  }
});

// Hard safety net: never leave an orphaned backend.
process.on("exit", () => {
  if (backendProc && !backendProc.killed) {
    try {
      backendProc.kill();
    } catch {
      /* ignore */
    }
  }
});
