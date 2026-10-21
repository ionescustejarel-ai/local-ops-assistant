"""Project state from the memory bootloader + vault project notes.

Sources:
  * MEMORY.md §"Proiecte ACTIVE" -- one table row per project, Romanian free text
    with markers: ✅ done, 🔴 blocker, ⛔ hard rule, ⚠️ caution, NEXT: ...
  * the project note in the vault -- headings "## Session YYYY-MM-DD ... RESUME HOOK"
    and lines starting with "**NEXT".

The mapping from table row -> note -> repo is config (jarvis.yaml `projects`),
because the table itself only carries loose pointers.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

_ROW = re.compile(r"^\|\s*\*\*(?P<name>[^*]+)\*\*(?P<rest>[^|]*)\|(?P<status>.*)\|\s*$")
_NEXT = re.compile(r"\*{0,2}NEXT[^:=—\-]*[:=—\-]\s*\*{0,2}\s*(?P<text>.+?)(?=(?:\s\[|\s*$|\.\s+[A-ZĂÂÎȘȚ]|\s+Detaliu))", re.S)
_SESSION = re.compile(r"^##\s+Session\s+(?P<date>\d{4}-\d{2}-\d{2})(?P<rest>.*)$", re.M)
_NOTE_NEXT = re.compile(r"^(?:[-*]\s+)?\*\*NEXT(?P<qual>[^\n:=]*?)\s*[:=]\*{0,2}\s*(?P<text>[^\n]+)", re.M)
_TICK_PATH = re.compile(r"`([A-Za-z]:\\[^`]+)`")


def _clean(text: str) -> str:
    """Strip markdown emphasis, trailing pointers in backticks and dangling punctuation."""
    text = re.sub(r"\*\*", "", text)
    # a backticked token that looks like a file path (drive letter or dir/) is a pointer, not content
    text = re.split(r"\s`(?:[A-Za-z]:\\|[\w.-]+/)[^`]*`", text, maxsplit=1)[0]
    # an unmatched ")" closes a parenthetical the marker was inside of: "(NEXT: OK collector). rest" -> "OK collector"
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                text = text[:i]
                break
            depth -= 1
    return text.strip().rstrip(".;,: ")


def _fragments(text: str, marker: str) -> list[str]:
    """Sentences/fragments that start with an emoji marker, e.g. all 🔴 ... pieces."""
    out = []
    for piece in re.split(r"(?=[🔴⛔⚠️✅⭐🏁🎓])", text):
        piece = piece.strip()
        if piece.startswith(marker):
            body = piece[len(marker):].strip(" :;")
            body = re.split(r"(?<=[.;])\s+(?=[A-ZĂÂÎȘȚ„(\[]|\S*🔴)|\s(?=[🔴⛔⚠️✅⭐🏁🎓])", body, maxsplit=1)[0]
            body = re.sub(r"^Blocant\s*[:=]\s*", "", body, flags=re.I)
            body = _clean(body)
            if body:
                out.append(body[:160])
    return out


def parse_memory_table(md: str) -> list[dict[str, Any]]:
    rows = []
    in_section = False
    for line in md.splitlines():
        if line.startswith("## "):
            in_section = "Proiecte ACTIVE" in line
            continue
        if not in_section:
            continue
        m = _ROW.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        status = m.group("status").strip()
        rest = m.group("rest")
        paths = _TICK_PATH.findall(rest) + _TICK_PATH.findall(status)
        nxt = _NEXT.search(status)
        rows.append({
            "name": name,
            "path_hint": paths[0] if paths else None,
            "status_raw": status,
            "next": _clean(nxt.group("text")) if nxt else None,
            "blockers": _fragments(status, "🔴"),
            "rules": _fragments(status, "⛔"),
            "cautions": _fragments(status, "⚠️"),
            "done": bool(re.search(r"✅|🏁", status)),
        })
    return rows


def parse_note(md: str) -> dict[str, Any]:
    sessions = list(_SESSION.finditer(md))
    last = sessions[-1] if sessions else None
    next_lines = []
    for m in _NOTE_NEXT.finditer(md):
        qual = m.group("qual").strip(" -—–*")
        text = _clean(m.group("text"))
        next_lines.append(f"{qual}: {text}" if qual else text)
    # the NEXT closest to the end of the note is the current one
    return {
        "last_session": last.group("date") if last else None,
        "last_session_title": (last.group("rest").strip(" -—") if last else None),
        "sessions": len(sessions),
        "next": next_lines[-1][:240] if next_lines else None,
    }


def _mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="minutes")
    except OSError:
        return None


def fetch(memory_md: Path, project_cfg: list[dict[str, Any]], vault_root: Path) -> list[dict[str, Any]]:
    """Join config projects with their MEMORY.md row and their vault note."""
    md = memory_md.read_text(encoding="utf-8") if memory_md.exists() else ""
    rows = {r["name"]: r for r in parse_memory_table(md)}
    out = []
    for cfg in project_cfg:
        row = next((r for k, r in rows.items() if cfg["match"].lower() in k.lower()), None)
        note_info, note_path = None, None
        if cfg.get("note"):
            note_path = vault_root / cfg["note"]
            if note_path.exists():
                note_info = parse_note(note_path.read_text(encoding="utf-8", errors="replace"))
                note_info["mtime"] = _mtime(note_path)
            else:
                note_info = {"error": "note missing"}
        out.append({
            "key": cfg["key"],
            "label": cfg.get("label") or (row["name"] if row else cfg["key"]),
            "repo": cfg.get("repo"),
            "memory": row,
            "note": note_info,
            "note_path": str(note_path) if note_path else None,
            "next": (row or {}).get("next") or (note_info or {}).get("next"),
        })
    return out
