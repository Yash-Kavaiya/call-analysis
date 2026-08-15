"use strict";

/**
 * Preload — safe bridge between the sandboxed renderer and the main process.
 * Exposes a minimal, typed surface on `window.desktop`.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  getBackendStatus: () => ipcRenderer.invoke("backend:get-status"),
  quit: () => ipcRenderer.invoke("app:quit"),
  openExternal: (url) => ipcRenderer.invoke("app:open-external", url),
  onBackendLog: (callback) => {
    const listener = (_e, line) => callback(line);
    ipcRenderer.on("backend:log", listener);
    return () => ipcRenderer.removeListener("backend:log", listener);
  },
  onBackendState: (callback) => {
    const listener = (_e, payload) => callback(payload);
    ipcRenderer.on("backend:state", listener);
    return () => ipcRenderer.removeListener("backend:state", listener);
  },
});
