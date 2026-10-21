"""edge-tts (Microsoft neural voices, ro-RO) -> mp3 bytes. Online, free, no key."""
from __future__ import annotations

import re

import edge_tts

_SENT_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZĂÂÎȘȚ„\"(0-9])")


def split_sentences(text: str) -> list[str]:
    """Split streamed text into speakable sentences; keeps abbreviations like 'ex.' mostly intact."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [s.strip() for s in _SENT_END.split(text) if s.strip()]


async def synthesize(text: str, voice: str = "ro-RO-EmilNeural", rate: str = "+0%") -> bytes:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)
