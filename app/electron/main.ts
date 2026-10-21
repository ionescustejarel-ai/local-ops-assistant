/**
 * Electron main process: one window, tray, global push-to-talk toggle.
 *
 * Ctrl+Alt+J is a toggle (globalShortcut cannot see key-up): first press starts
 * recording, second press stops and sends. The renderer owns the microphone;
 * main only relays the hotkey over IPC.
 */
import { app, BrowserWindow, globalShortcut, Menu, Tray, nativeImage, ipcMain, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEV_URL = process.env.JARVIS_DEV_URL;
const HOTKEY = "Control+Alt+J";

let win: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;

function createWindow(): void {
  win = new BrowserWindow({
    width: 1720,
    height: 1000,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#1B2431",
    title: "Jarvis",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "..", "electron", "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  if (DEV_URL) {
    void win.loadURL(DEV_URL);
  } else {
    void win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
  // JARVIS_SCREENSHOT=<png path>: capture the loaded board and exit (used for visual verification)
  const shot = process.env.JARVIS_SCREENSHOT;
  if (shot) {
    win.setAlwaysOnTop(true);
    win.webContents.on("console-message", (_e, level, message) => console.log(`[renderer ${level}] ${message}`));
    win.webContents.once("did-finish-load", () => {
      // JARVIS_AUTO_ASK=<text>: type a question into the composer and send it (exercises SSE + TTS in the real renderer)
      const autoAsk = process.env.JARVIS_AUTO_ASK;
      if (autoAsk) {
        setTimeout(() => {
          void win!.webContents.executeJavaScript(`(() => {
            const input = document.querySelector('.compose input');
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(input, ${JSON.stringify(autoAsk)});
            input.dispatchEvent(new Event('input', { bubbles: true }));
            setTimeout(() => document.querySelector('.compose button').click(), 100);
          })()`);
        }, 2500);
      }
      setTimeout(async () => {
        win!.show(); win!.focus();
        await new Promise((r) => setTimeout(r, 300));
        const img = await win!.webContents.capturePage();
        const { writeFileSync } = await import("node:fs");
        const png = img.toPNG();
        console.log(`[screenshot] ${img.getSize().width}x${img.getSize().height} ${png.length} bytes -> ${shot}`);
        writeFileSync(shot, png);
        quitting = true;
        app.quit();
      }, Number(process.env.JARVIS_SCREENSHOT_DELAY ?? 4000));
    });
  }
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });
  win.on("close", (e) => {
    if (!quitting) {
      e.preventDefault();
      win?.hide();
    }
  });
}

function showWindow(): void {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function createTray(): void {
  // 16x16 brass dot, drawn in code so no asset pipeline is needed
  const size = 16;
  const buf = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x - 7.5, dy = y - 7.5;
      const inside = dx * dx + dy * dy <= 42;
      const i = (y * size + x) * 4;
      buf[i] = 0xd9; buf[i + 1] = 0xa5; buf[i + 2] = 0x60; buf[i + 3] = inside ? 255 : 0;
    }
  }
  tray = new Tray(nativeImage.createFromBuffer(buf, { width: size, height: size }));
  tray.setToolTip("Jarvis");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Arată Jarvis", click: showWindow },
    { label: `Vorbește (${HOTKEY})`, click: () => win?.webContents.send("ptt:toggle") },
    { type: "separator" },
    { label: "Pornire cu Windows", type: "checkbox", checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked }) },
    { type: "separator" },
    { label: "Ieșire", click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on("click", showWindow);
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", showWindow);
  app.whenReady().then(() => {
    createWindow();
    createTray();
    const ok = globalShortcut.register(HOTKEY, () => {
      showWindow();
      win?.webContents.send("ptt:toggle");
    });
    if (!ok) console.error(`could not register ${HOTKEY}`);
    ipcMain.handle("app:info", () => ({ hotkey: HOTKEY, version: app.getVersion(), dev: Boolean(DEV_URL) }));
    ipcMain.on("app:show", showWindow);
  });
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => { /* keep running in tray */ });
}
