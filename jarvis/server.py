"""Jarvis backend: FastAPI on loopback.

  uv run python -m jarvis.server

Routes
  GET  /api/snapshot        full snapshot (data + alerts)
  GET  /api/alerts          alerts only
  POST /api/refresh[?name=] force a collector run
  WS   /ws/events           snapshot pushed on every change
  POST /api/stt             audio (webm/wav) -> {"text": ...}           (voice/stt.py)
  POST /api/ask             {"text": ...} -> SSE stream of tokens/sentences (brain.py)
  POST /api/tts             {"text": ...} -> audio/mpeg                  (voice/tts.py)
Loopback only: the brain can read the vault and the DB, so this must never be
reachable from the network.

Loopback is not enough on its own: any web page open in a browser on this
machine can also send requests to 127.0.0.1. So every /api route (except
/api/health) and the WebSocket require a per-launch token. The backend writes
it to a per-user file at startup (token_path()); the Electron main process reads that file
and hands it to the renderer through the preload bridge. A web page cannot
read local files, so it cannot get the token.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import load_config
from .snapshot import Snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("jarvis")

CFG = load_config()
SNAP = Snapshot(CFG)
TOKEN = secrets.token_urlsafe(32)
OPEN_PATHS = {"/api/health"}


def token_path() -> Path:
    """Per-user location, so the OS restricts who can read it: %LOCALAPPDATA% on Windows
    (ACL = current user), ~/.local/state elsewhere. Must match app/electron/main.ts."""
    if os.environ.get("JARVIS_TOKEN_FILE"):
        return Path(os.environ["JARVIS_TOKEN_FILE"])
    base = os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state"
    return Path(base) / "jarvis" / "session.token"


def write_token(path: Path, token: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # owner-only from creation (POSIX); chmod again in case the file existed with looser bits
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(path, 0o600)


def token_ok(supplied: str | None) -> bool:
    return hmac.compare_digest(supplied or "", TOKEN)


@asynccontextmanager
async def lifespan(app: FastAPI):
    write_token(token_path(), TOKEN)
    await SNAP.start()
    from . import voice_routes  # noqa: F401  (registers /api/stt, /api/tts, /api/ask; loads whisper lazily)
    await voice_routes.startup(app, CFG)
    yield
    await SNAP.stop()


app = FastAPI(title="Jarvis", lifespan=lifespan)
# "null" is the origin of the Electron window (loaded from file://); the token below is the real gate
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "null"],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def require_token(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path in OPEN_PATHS:
        return await call_next(request)
    if not token_ok(request.headers.get("x-jarvis-token")):
        return JSONResponse({"error": "missing or wrong X-Jarvis-Token"}, status_code=403)
    return await call_next(request)


@app.get("/api/snapshot")
async def snapshot() -> JSONResponse:
    return JSONResponse(SNAP.as_dict())


@app.get("/api/alerts")
async def alerts() -> JSONResponse:
    return JSONResponse({"version": SNAP.version, "alerts": SNAP.alerts})


@app.post("/api/refresh")
async def refresh(name: str | None = None) -> JSONResponse:
    await SNAP.refresh(name)
    return JSONResponse({"ok": True})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": SNAP.version, "collectors": list(SNAP.updated)})


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    if not token_ok(ws.query_params.get("token")):
        await ws.close(code=1008)  # policy violation; before accept, so the handshake is refused
        return
    await ws.accept()
    q = SNAP.subscribe()
    try:
        await ws.send_json(SNAP.as_dict())
        while True:
            payload = await q.get()
            await ws.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        SNAP.unsubscribe(q)


def main() -> None:
    import uvicorn
    s = CFG["server"]
    uvicorn.run("jarvis.server:app", host=s["host"], port=int(s["port"]), log_level="info", ws_ping_interval=20)


if __name__ == "__main__":
    main()
