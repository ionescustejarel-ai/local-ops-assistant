"""Voice + brain routes, attached to the FastAPI app at startup.

Kept separate from server.py so the board works even if whisper/edge-tts/claude
are unavailable: each route reports a clear error instead of crashing startup.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

log = logging.getLogger("jarvis.voice")
_state: dict[str, Any] = {"stt": None, "stt_error": None, "cfg": None}


async def startup(app: FastAPI, cfg: dict[str, Any]) -> None:
    _state["cfg"] = cfg
    register(app)
    # load whisper in the background so /api/snapshot is up immediately
    asyncio.get_running_loop().run_in_executor(None, _load_stt, cfg["voice"]["stt"])


def _load_stt(stt_cfg: dict[str, Any]) -> None:
    try:
        from .voice.stt import Transcriber
        _state["stt"] = Transcriber(stt_cfg)
        log.info("whisper ready: %s", _state["stt"].describe())
    except Exception as e:  # noqa: BLE001
        _state["stt_error"] = f"{type(e).__name__}: {e}"
        log.exception("whisper failed to load")


def register(app: FastAPI) -> None:
    @app.get("/api/voice/status")
    async def voice_status() -> dict[str, Any]:
        from .brain import Brain
        stt = _state["stt"]
        return {"stt": stt.describe() if stt else None, "stt_error": _state["stt_error"],
                "tts_voice": _state["cfg"]["voice"]["tts"]["voice"], "brain": Brain.status()}

    @app.post("/api/stt")
    async def stt(audio: UploadFile) -> dict[str, Any]:
        t = _state["stt"]
        if t is None:
            raise HTTPException(503, _state["stt_error"] or "whisper still loading")
        data = await audio.read()
        if len(data) < 1000:
            raise HTTPException(400, "audio too short")
        return await asyncio.to_thread(t.transcribe_bytes, data, audio.filename or "audio.webm")

    @app.post("/api/tts")
    async def tts(req: Request) -> Response:
        from .voice.tts import synthesize
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "empty text")
        v = _state["cfg"]["voice"]["tts"]
        mp3 = await synthesize(text, body.get("voice") or v["voice"], v.get("rate", "+0%"))
        return Response(mp3, media_type="audio/mpeg")

    @app.post("/api/ask")
    async def ask(req: Request) -> StreamingResponse:
        """SSE: events `sentence` (text ready for TTS), `token`, `tool`, `done`, `error`."""
        from .brain import Brain
        from .server import SNAP
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "empty text")
        brain = Brain.get(_state["cfg"])

        async def gen():
            async for ev in brain.ask(text, SNAP.as_dict(), new_session=bool(body.get("new_session"))):
                yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/brain/reset")
    async def brain_reset() -> dict[str, Any]:
        from .brain import Brain
        Brain.get(_state["cfg"]).reset()
        return {"ok": True}
