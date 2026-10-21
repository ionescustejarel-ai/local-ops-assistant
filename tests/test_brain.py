from datetime import datetime
from zoneinfo import ZoneInfo

from jarvis.brain import parse_stream_line
from jarvis.context import compact
from jarvis.voice.tts import split_sentences

NOW = datetime(2026, 9, 23, 13, 0, tzinfo=ZoneInfo("Europe/Bucharest"))


def test_split_sentences():
    assert split_sentences("Salut. Ai două task-uri căzute! Vrei detalii?") == ["Salut.", "Ai două task-uri căzute!", "Vrei detalii?"]
    assert split_sentences("Backup-ul a eșuat la 00:02. Restul e ok") == ["Backup-ul a eșuat la 00:02.", "Restul e ok"]
    assert split_sentences("") == []


def test_parse_stream_events():
    assert parse_stream_line('{"type":"system","subtype":"init","session_id":"abc","model":"claude-sonnet"}') == {"type": "init", "session_id": "abc", "model": "claude-sonnet"}
    tok = parse_stream_line('{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Sal"}}}')
    assert tok == {"type": "token", "text": "Sal"}
    tool = parse_stream_line('{"type":"stream_event","event":{"type":"content_block_start","content_block":{"type":"tool_use","name":"Read"}}}')
    assert tool == {"type": "tool", "name": "Read"}
    res = parse_stream_line('{"type":"result","subtype":"success","result":"ok","total_cost_usd":0.01,"duration_ms":5000,"num_turns":1,"session_id":"abc"}')
    assert res["ok"] and res["cost_usd"] == 0.01
    assert parse_stream_line("") is None
    assert parse_stream_line("garbage")["type"] == "raw"


def test_compact_context():
    snap = {"alerts": [{"severity": "red", "text": "Backup a eșuat."}],
            "data": {"tasks": [{"name": "Ops_Daily_Ingest", "result_text": "ok", "last_run": "2026-09-23T07:40:00+03:00", "next_run": None,
                                "log": {"idle": False, "failed": False, "summary": "matches: 15956"}}],
                     "projects": [{"label": "Site", "next": "alege varianta", "memory": {"blockers": ["designer"], "rules": []}, "note": {"last_session": "2026-09-23"}}],
                     "calendar": None, "gmail": None, "git": [], "deadlines": [{"label": "T0", "days_left": 14, "date": "2026-10-07"}]}}
    txt = compact(snap, NOW, {"Ops_Daily_Ingest": "Ingest zilnic"})
    assert "[STARE CURENTĂ]" in txt
    assert "[red] Backup a eșuat." in txt
    assert "Ingest zilnic: ok, ultima acum 5.3 h" in txt
    assert "Site: NEXT: alege varianta | BLOCANT: designer | ultima sesiune 2026-09-23" in txt
    assert "CALENDAR: neconfigurat." in txt and "EMAIL: neconfigurat." in txt
    assert "T0 în 14 zile" in txt


# --- fast path (jarvis/fastpath.py) wired into Brain.ask ---

from jarvis.brain import Brain  # noqa: E402

FAST_SNAP = {"alerts": [{"severity": "red", "text": "Backup-ul a eșuat."}], "data": {"pending": [], "calendar": None}}


def _brain(tmp_path, fastpath=True):
    return Brain({"brain": {"fastpath": fastpath, "journal_dir": str(tmp_path), "mcp_config": "x", "persona": "x"}})


async def test_fastpath_answers_locally_and_journals(tmp_path):
    b = _brain(tmp_path)
    evs = [ev async for ev in b.ask("Ce e roșu?", FAST_SNAP)]
    assert [e["type"] for e in evs][-1] == "done"
    done = evs[-1]
    assert done["fast"] and done["ok"] and done["turns"] == 0 and done["cost_usd"] == 0
    assert "Backup-ul a eșuat." in done["text"]
    assert any(e["type"] == "sentence" and "Backup-ul a eșuat." in e["text"] for e in evs)
    journal = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "**utilizator:** Ce e roșu?" in journal and "răspuns local" in journal


async def test_fastpath_answer_is_carried_into_next_claude_prompt(tmp_path):
    b = _brain(tmp_path)
    [ev async for ev in b.ask("Ce e roșu?", FAST_SNAP)]
    p = b._prompt("și de ce a eșuat?", FAST_SNAP, NOW)
    assert "utilizator: Ce e roșu?" in p and "Jarvis: Alerte, 1: 1 roșie." in p
    assert p.rstrip().endswith("[ÎNTREBARE] și de ce a eșuat?")
    assert "utilizator: Ce e roșu?" not in b._prompt("altceva", FAST_SNAP, NOW)   # carried once


async def test_fastpath_off_or_unmatched_goes_to_claude(tmp_path):
    b = _brain(tmp_path, fastpath=False)
    b.exe = None   # no subprocess in tests: the claude branch reports the missing CLI
    assert [ev async for ev in b.ask("Ce e roșu?", FAST_SNAP)][0]["type"] == "error"
    b2 = _brain(tmp_path)
    b2.exe = None
    assert [ev async for ev in b2.ask("De ce e roșu backup-ul?", FAST_SNAP)][0]["type"] == "error"
