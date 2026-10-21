"""The brain: Claude Code headless (`claude -p`) with a minimal context.

Why headless Claude Code and not the API: it reuses the subscription, the
user's CLAUDE.md/memory and the two MCP servers Jarvis needs (vault + DB). Why
minimal: a plain `claude -p` in this account loads ~100 claude.ai MCP servers
and cost ~0.95 $ nominal per trivial call (measured 2026-09-23), so we pass
`--strict-mcp-config` with our own two-server file and inject the board
snapshot as text so most answers need zero tool calls.

Session continuity: one UUID per conversation; first call `--session-id`,
later calls `--resume`. `reset()` starts a fresh one.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from . import fastpath
from .context import compact
from .voice.tts import split_sentences

log = logging.getLogger("jarvis.brain")

READ_TOOLS = [
    "Read", "Grep", "Glob", "LS",
    "Bash(git log*)", "Bash(git status*)", "Bash(git diff*)", "Bash(ls*)", "Bash(dir*)", "Bash(cat*)",
    # no curl/network tools: mail and calendar text reach the prompt, and an injected
    # instruction must not be able to send data anywhere; service health is in the snapshot
    "Bash(head*)", "Bash(tail*)", "Bash(docker ps*)", "Bash(nvidia-smi*)",
    "mcp__mcp-obsidian-advanced__*", "mcp__postgres__*",
]


def parse_stream_line(line: str) -> dict[str, Any] | None:
    """One stream-json line -> normalised event or None."""
    line = line.strip()
    if not line:
        return None
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return {"type": "raw", "text": line[:200]}
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        return {"type": "init", "session_id": ev.get("session_id"), "model": ev.get("model")}
    if t == "stream_event":
        inner = ev.get("event", {})
        if inner.get("type") == "content_block_delta" and inner.get("delta", {}).get("type") == "text_delta":
            return {"type": "token", "text": inner["delta"].get("text", "")}
        if inner.get("type") == "content_block_start" and inner.get("content_block", {}).get("type") == "tool_use":
            return {"type": "tool", "name": inner["content_block"].get("name")}
        if inner.get("type") == "message_stop":
            return {"type": "message_end"}
        return None
    if t == "assistant":
        blocks = ev.get("message", {}).get("content", [])
        tools = [b.get("name") for b in blocks if b.get("type") == "tool_use"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return {"type": "assistant", "text": text, "tools": tools}
    if t == "result":
        return {"type": "result", "ok": ev.get("subtype") == "success", "text": ev.get("result") or "",
                "cost_usd": ev.get("total_cost_usd"), "duration_ms": ev.get("duration_ms"),
                "turns": ev.get("num_turns"), "session_id": ev.get("session_id"), "error": ev.get("error")}
    return None


class Brain:
    _instance: "Brain | None" = None
    _last: dict[str, Any] = {}

    @classmethod
    def get(cls, cfg: dict[str, Any]) -> "Brain":
        if cls._instance is None:
            cls._instance = Brain(cfg)
        return cls._instance

    @classmethod
    def status(cls) -> dict[str, Any]:
        b = cls._instance
        return {"available": shutil.which("claude") is not None, "session_id": b.session_id if b else None,
                "started": b.started if b else False, "busy": b.busy if b else False, "last": cls._last}

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["brain"]
        self.labels = cfg.get("tasks", {}).get("labels", {})
        self.exe = shutil.which("claude")
        self.session_id = str(uuid.uuid4())
        self.started = False
        self.busy = False
        self.lock = asyncio.Lock()
        self.carry: list[tuple[str, str]] = []   # local answers not yet seen by the claude session

    def reset(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.started = False
        self.carry = []

    def _journal(self, now: datetime, question: str, answer: str, result: dict[str, Any]) -> None:
        """Append the exchange to the vault so other Claude sessions can read what the user
        told Jarvis (decisions given by voice were otherwise lost in the -p transcript)."""
        root = self.cfg.get("journal_dir")
        if not root:
            return
        try:
            d = Path(root)
            d.mkdir(parents=True, exist_ok=True)
            f = d / f"{now:%Y-%m-%d}.md"
            new = not f.exists()
            with f.open("a", encoding="utf-8") as fh:
                if new:
                    fh.write(f"# Jarvis — conversații {now:%Y-%m-%d}\n\nCe a spus utilizatorul lui Jarvis (vocal sau scris) și ce a răspuns. "
                             "Deciziile de aici se aplică de sesiunea Claude care lucrează pe proiect; Jarvis doar citește.\n")
                meta = (f"{result.get('duration_ms') or 0} ms · răspuns local" if result.get("fast") else
                        f"{(result.get('duration_ms') or 0)/1000:.1f} s · {result.get('turns') or 1} tură · sesiune {self.session_id[:8]}")
                fh.write(f"\n## {now:%H:%M}\n\n**utilizator:** {question.strip()}\n\n**Jarvis:** {answer.strip()}\n\n<sub>{meta}</sub>\n")
        except OSError as e:
            log.warning("journal write failed: %s", e)

    def command(self, resume: bool) -> list[str]:
        c = self.cfg
        cmd = [self.exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--model", str(c.get("model", "sonnet")), "--max-turns", str(c.get("max_turns", 6)),
               "--effort", str(c.get("effort", "low")),
               "--strict-mcp-config", "--mcp-config", str(c["mcp_config"]),
               "--append-system-prompt-file", str(c["persona"]),
               "--allowedTools", *READ_TOOLS,
               "--disallowedTools", *c.get("disallowed_tools", [])]
        cmd += ["--resume", self.session_id] if resume else ["--session-id", self.session_id]
        return cmd

    async def ask(self, text: str, snapshot: dict[str, Any], new_session: bool = False) -> AsyncIterator[dict[str, Any]]:
        if new_session:
            self.reset()
        m = fastpath.match(text) if self.cfg.get("fastpath") else None
        if m:
            async for ev in self._fast(text, m, snapshot):
                yield ev
            return
        if self.exe is None:
            yield {"type": "error", "text": "claude CLI not found on PATH"}
            return
        async with self.lock:
            self.busy = True
            try:
                async for ev in self._run(text, snapshot):
                    yield ev
            finally:
                self.busy = False

    async def _fast(self, text: str, m: dict[str, Any], snapshot: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        now = datetime.now().astimezone()
        t0 = time.perf_counter()
        ans = fastpath.answer(m, snapshot, now)
        for s in split_sentences(ans):
            yield {"type": "sentence", "text": s}
        ms = int((time.perf_counter() - t0) * 1000)
        self.carry.append((text, ans))
        Brain._last = {"cost_usd": 0, "duration_ms": ms, "turns": 0, "first_token_ms": ms, "fast": True,
                       "at": now.isoformat(timespec="seconds")}
        self._journal(now, text, ans, {"duration_ms": ms, "fast": True})
        yield {"type": "done", "text": ans, "ok": True, "error": None, "cost_usd": 0, "duration_ms": ms,
               "turns": 0, "first_token_ms": ms, "session_id": self.session_id, "fast": True}

    def _prompt(self, text: str, snapshot: dict[str, Any], now: datetime) -> str:
        """Board context + any local answers since the last claude call (so "și de ce?" has context) + question."""
        prior = ""
        if self.carry:
            prior = "\n\n[RĂSPUNSURI LOCALE ANTERIOARE, fără Claude]\n" + "\n".join(
                f"utilizator: {q}\nJarvis: {a}" for q, a in self.carry)
            self.carry = []
        return compact(snapshot, now, self.labels) + prior + "\n\n[ÎNTREBARE] " + text

    async def _run(self, text: str, snapshot: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        now = datetime.now().astimezone()
        prompt = self._prompt(text, snapshot, now)
        cmd = self.command(resume=self.started)
        t0 = time.perf_counter()
        env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cfg.get("cwd") or os.getcwd()), env=env,
            creationflags=0x08000000 if os.name == "nt" else 0)
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        buffer = ""      # text not yet emitted as a sentence
        full = ""
        first_token_ms: int | None = None
        result: dict[str, Any] | None = None
        timeout = float(self.cfg.get("timeout_s", 120))
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
                except asyncio.TimeoutError:
                    yield {"type": "error", "text": f"timeout după {timeout:.0f} s"}
                    proc.kill()
                    break
                if not raw:
                    break
                ev = parse_stream_line(raw.decode("utf-8", errors="replace"))
                if ev is None:
                    continue
                if ev["type"] == "init":
                    self.started = True
                    continue
                if ev["type"] == "token":
                    if first_token_ms is None:
                        first_token_ms = int((time.perf_counter() - t0) * 1000)
                    buffer += ev["text"]
                    full += ev["text"]
                    yield ev
                    sents = split_sentences(buffer)
                    if len(sents) > 1:
                        for s in sents[:-1]:
                            yield {"type": "sentence", "text": s}
                        buffer = sents[-1]
                    continue
                if ev["type"] in ("tool", "message_end"):
                    if ev["type"] == "tool":
                        yield ev
                    for s in split_sentences(buffer):
                        yield {"type": "sentence", "text": s}
                    buffer = ""
                    continue
                if ev["type"] == "result":
                    result = ev
                    self.started = True
        finally:
            stderr = (await proc.stderr.read()).decode("utf-8", errors="replace") if proc.returncode is None or True else ""
            await proc.wait()
        for s in split_sentences(buffer):
            yield {"type": "sentence", "text": s}
        if result is None:
            yield {"type": "error", "text": f"claude a ieșit cu {proc.returncode}: {stderr.strip()[-300:]}"}
            return
        if not full and result.get("text"):
            # no partial stream (older CLI) -> emit final text as sentences
            full = result["text"]
            for s in split_sentences(full):
                yield {"type": "sentence", "text": s}
        Brain._last = {"cost_usd": result.get("cost_usd"), "duration_ms": result.get("duration_ms"),
                       "turns": result.get("turns"), "first_token_ms": first_token_ms, "at": now.isoformat(timespec="seconds")}
        self._journal(now, text, full or result.get("text") or "", result)
        yield {"type": "done", "text": full, "ok": result["ok"], "error": result.get("error"),
               "cost_usd": result.get("cost_usd"), "duration_ms": result.get("duration_ms"),
               "turns": result.get("turns"), "first_token_ms": first_token_ms, "session_id": self.session_id}
