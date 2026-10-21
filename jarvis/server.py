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
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import load_config
from .snapshot import Snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("jarvis")

CFG = load_config()
SNAP = Snapshot(CFG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await SNAP.start()
    from . import voice_routes  # noqa: F401  (registers /api/stt, /api/tts, /api/ask; loads whisper lazily)
    await voice_routes.startup(app, CFG)
    yield
    await SNAP.stop()


app = FastAPI(title="Jarvis", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "null"],
                   allow_methods=["*"], allow_headers=["*"])


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
