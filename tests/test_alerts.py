from datetime import datetime
from zoneinfo import ZoneInfo

from jarvis import alerts

NOW = datetime(2026, 9, 23, 13, 0, tzinfo=ZoneInfo("Europe/Bucharest"))


def test_task_rules():
    tasks = [
        {"name": "A", "result_ok": False, "result_text": "operator refused", "result_hex": "0x800710E0", "stale": False, "state": "Ready", "log": None},
        {"name": "B", "result_ok": True, "result_text": "ok", "result_hex": "0x0", "stale": True, "age_s": 7200, "interval_s": 1800, "state": "Ready",
         "log": {"failed": True, "summary": "rc 1"}},
        {"name": "C", "result_ok": True, "result_text": "ok", "result_hex": "0x0", "stale": False, "state": "Disabled", "log": {"failed": False}},
    ]
    out = alerts.rules_tasks(tasks, {"A": "Backup"})
    ids = {a["id"]: a for a in out}
    assert ids["task:A:result"]["severity"] == "red" and "Backup" in ids["task:A:result"]["text"]
    assert ids["task:B:stale"]["severity"] == "yellow"
    assert ids["task:B:log"]["severity"] == "red"
    assert ids["task:C:disabled"]["severity"] == "yellow"


def test_backup_rules():
    assert alerts.rules_backup({"mounted": False})[0]["severity"] == "red"
    ok = alerts.rules_backup({"mounted": True, "error": None, "status": "OK", "age_h": 15.0, "failures": [], "warnings": []})
    assert ok == []
    old = alerts.rules_backup({"mounted": True, "error": None, "status": "OK", "age_h": 40.0, "failures": [], "warnings": ["x"]})
    assert {a["id"] for a in old} == {"backup:age", "backup:warn"}


def test_git_and_deadlines_and_calendar():
    g = alerts.rules_git([{"name": "shop", "dirty": 3, "alert_dirty": True}, {"name": "big", "dirty": 999, "alert_dirty": False}])
    assert [a["id"] for a in g] == ["git:shop:dirty"]
    d = alerts.rules_deadlines([{"label": "x", "days_left": -2}, {"label": "y", "days_left": 1}, {"label": "z", "days_left": 10}])
    assert [a["severity"] for a in d] == ["red", "yellow"]
    c = alerts.rules_calendar([{"start": "2026-09-23T14:00:00+03:00", "summary": "Dentist", "all_day": False},
                               {"start": "2026-09-23", "summary": "ziua", "all_day": True}], NOW)
    assert len(c) == 1 and "60 min" in c[0]["text"]


def test_build_sorted():
    snap = {"data": {"tasks": [], "docker": [{"name": "x", "ok": False, "status": "Exited"}],
                     "disk": [{"path": "C:/", "used_pct": 95, "free_gb": 10}]}, "errors": {"gmail": "auth"}}
    out = alerts.build_alerts(snap, {}, NOW)
    assert [a["severity"] for a in out] == ["red", "yellow", "info"]
