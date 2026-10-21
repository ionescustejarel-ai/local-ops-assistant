"""Parser tests on real outputs captured 2026-09-23 (tests/fixtures)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from jarvis.collectors import backup, deadlines, docker, git, gpu, projects, services, tasks

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 23, 13, 0, tzinfo=ZoneInfo("Europe/Bucharest"))


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8-sig")


# --- tasks -----------------------------------------------------------------

def test_iso_interval():
    assert tasks.parse_iso_interval("PT30M") == 1800
    assert tasks.parse_iso_interval("PT3H") == 10800
    assert tasks.parse_iso_interval("P1DT2H") == 93600
    assert tasks.parse_iso_interval(None) is None
    assert tasks.parse_iso_interval("") is None


def test_parse_tasks_real_fixture():
    rows = tasks.parse_tasks(read("tasks.json"), NOW)
    by = {r["name"]: r for r in rows}
    assert len(rows) >= 12
    backup_task = by["Ops_Backup"]
    assert backup_task["result_ok"] is False
    assert backup_task["result_hex"] == "0x800710E0"
    assert "refused" in backup_task["result_text"]
    assert backup_task["trigger"] == "daily"
    assert backup_task["interval_s"] == 86400
    rerank = by["Ops_Reranker"]
    assert rerank["state"] == "Running"
    assert rerank["result_ok"] is True and rerank["result_text"] == "running"
    assert rerank["next_run"] is None
    matchday = by["Ops_Nightly_Sync"]
    assert matchday["interval_s"] == 1800


def test_stale_detection():
    raw = '[{"TaskName":"X","State":"Ready","LastRunTime":"2026-09-23T10:00:00+03:00","LastTaskResult":0,"NextRunTime":null,"TriggerClass":"MSFT_TaskTimeTrigger","RepetitionInterval":"PT30M"}]'
    (row,) = tasks.parse_tasks(raw, NOW)   # 3 h since last run, interval 30 min
    assert row["stale"] is True
    raw_ok = raw.replace("10:00:00", "12:45:00")
    (row,) = tasks.parse_tasks(raw_ok, NOW)
    assert row["stale"] is False


def test_task_log_line():
    rec = tasks.parse_log_line(read("daily-ingest.jsonl").splitlines()[-1])
    assert rec["failed"] is False
    assert rec["rcs"] == {"ingest_rc": 0, "elo_rc": 0}
    assert "15956" in rec["summary"]
    idle = tasks.parse_log_line(read("nightly-sync.jsonl").splitlines()[-1])
    assert idle["idle"] is True
    assert "recoltat" in idle["summary"]
    assert tasks.parse_log_line('{"task":"t","rc":1}')["failed"] is True
    assert tasks.parse_log_line("not json")["parse_error"] is True
    assert tasks.parse_log_line(None) is None


# --- docker ----------------------------------------------------------------

def test_parse_docker():
    rows = docker.parse_docker(read("docker_ps.jsonl"))
    by = {r["name"]: r for r in rows}
    assert by["app_api"]["ok"] and by["app_api"]["health"] == "healthy"
    assert "8008" in by["app_api"]["ports"]
    assert by["n8n"]["ok"] and by["n8n"]["health"] is None
    down = docker.parse_docker('{"Names":"x","Status":"Exited (1) 2 hours ago","Ports":"","Image":"i"}')
    assert down[0]["ok"] is False and down[0]["up"] is False


# --- gpu -------------------------------------------------------------------

def test_parse_gpu():
    rows = gpu.parse_nvidia(read("nvidia_smi.csv"))
    assert [r["index"] for r in rows] == [0, 1]
    assert rows[0]["mem_total_mib"] == 24564
    assert rows[1]["mem_used_mib"] == 0 and rows[1]["mem_pct"] == 0.0


# --- services --------------------------------------------------------------

def test_services_classify():
    assert services.classify(200, '{"status":"ok"}', "ok") is True
    assert services.classify(200, "nope", "ok") is False
    assert services.classify(None, "", None) is False
    assert services.classify(503, "", None) is False


@pytest.mark.asyncio
async def test_services_refused_port():
    (r,) = await services.fetch([{"name": "dead", "url": "http://127.0.0.1:1/"}], timeout=0.5)
    assert r["ok"] is False and r["error"] is not None


# --- backup ----------------------------------------------------------------

def test_backup_last_run_parse():
    text = "run: 2026-09-22 21:04\nroot: G:\\My Drive\\Backups\nstatus: FAILED\nfailures:\n  - shop: bundle rc 128\nwarnings:\n  - weather nested\n"
    d = backup.parse_last_run(text, NOW)
    assert d["status"] == "FAILED"
    assert d["failures"] == ["shop: bundle rc 128"]
    assert d["warnings"] == ["weather nested"]
    assert d["age_h"] == pytest.approx(15.9, abs=0.1)


def test_backup_root_override(tmp_path):
    assert backup.resolve_root({"OPS_BACKUP_DIR": str(tmp_path)}) == tmp_path


# --- git -------------------------------------------------------------------

def test_git_parsers():
    assert git.parse_status(read("git_status.txt")) == 1
    last = git.parse_log(read("git_log.txt"))
    assert last["hash"] == "46ae2e0"
    assert last["subject"].startswith("fix(eval)")


# --- projects --------------------------------------------------------------

def test_memory_table():
    rows = projects.parse_memory_table(read("memory_projects.md"))
    by = {r["name"]: r for r in rows}
    assert len(rows) == 7
    site = by["Site agenție"]
    assert site["path_hint"] == "C:\\work\\site\\"
    assert "fotografiile echipei de la designer" in site["blockers"]
    weather = next(r for r in rows if "meteo" in r["name"])
    assert weather["blockers"] == ["API-ul sursă cere cheie nouă din noiembrie (fix = cont gratuit nou)"]
    assert len(site["rules"]) >= 2
    career = next(r for r in rows if r["name"].startswith("Carier"))
    assert career["next"] and career["next"].startswith("după 24.10")
    assert site["next"] == "alegi varianta de homepage"
    assert by["Plan antrenament"]["done"] is True


def test_note_parse():
    info = projects.parse_note(read("note_project.md"))
    assert info["last_session"] == "2026-09-23"
    assert "RESUME HOOK" in info["last_session_title"]
    assert info["sessions"] >= 2
    assert info["next"] and not info["next"].startswith("NEXT") and "**" not in info["next"]


def test_note_next_cleanup():
    md = "## Session 2026-09-01 - x\n**NEXT:** clientul confirmă cele 4 puncte → aplic. `C:\\work\\x.md`\n"
    assert projects.parse_note(md)["next"] == "clientul confirmă cele 4 puncte → aplic"
    md2 = "**NEXT — blocat pe utilizator (§8 din spec):** (1) de când începe registrul"
    assert projects.parse_note(md2)["next"] == "blocat pe utilizator (§8 din spec): (1) de când începe registrul"


def test_memory_next_cleanup():
    rows = projects.parse_memory_table("## Proiecte ACTIVE\n| **X** | a. **NEXT: după 24.09 adaug orarul real + republic.** [link](l.md) |\n")
    assert rows[0]["next"] == "după 24.09 adaug orarul real + republic"
    rows = projects.parse_memory_table("## Proiecte ACTIVE\n| **Y** | 23.09 Scrapling 24/24 (NEXT: OK collector). `wc2026` = arhivă, doar citit. |\n")
    assert rows[0]["next"] == "OK collector"
    rows = projects.parse_memory_table("## Proiecte ACTIVE\n| **Z** | NEXT = ziua 1 pe S23 (persistență `file://`, Wake Lock); dacă pică → APK. Detaliu: x |\n")
    assert rows[0]["next"] == "ziua 1 pe S23 (persistență `file://`, Wake Lock); dacă pică → APK"


def test_docker_watch_alerts():
    from jarvis import alerts
    rows = [{"name": "dead_old", "ok": False, "status": "Exited (137) 4 months ago", "watched": False},
            {"name": "app_api", "ok": False, "status": "Exited (1)", "watched": True}]
    assert [a["id"] for a in alerts.rules_docker(rows)] == ["docker:app_api"]


# --- deadlines -------------------------------------------------------------

def test_deadlines():
    rows = deadlines.compute([{"label": "Verdict A/B", "date": "2026-10-07"}, {"label": "x", "date": date(2026, 9, 24)}], date(2026, 9, 23))
    assert [r["days_left"] for r in rows] == [1, 14]
