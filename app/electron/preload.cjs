// Preload (CommonJS: sandboxed preloads cannot be ESM). Exposes a tiny, explicit bridge.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvis", {
  onPttToggle: (cb) => {
    const handler = () => cb();
    ipcRenderer.on("ptt:toggle", handler);
    return () => ipcRenderer.removeListener("ptt:toggle", handler);
  },
  info: () => ipcRenderer.invoke("app:info"),
  token: () => ipcRenderer.invoke("app:token"),
  show: () => ipcRenderer.send("app:show"),
});
