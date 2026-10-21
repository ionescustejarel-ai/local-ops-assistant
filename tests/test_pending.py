from datetime import date

from jarvis import alerts
from jarvis.collectors import deadlines, git, pending, vault

TODAY = date(2026, 9, 23)


def test_pending_parse_and_severity():
    rows = pending.parse([
        {"project": "site", "type": "asteptare", "text": "Domeniu neconfirmat", "since": "2026-09-07", "from": "registrar"},
        {"project": "data", "type": "decizie", "text": "Spot-check import", "since": "2026-09-23"},
        {"project": "x", "type": "decizie", "text": "vechi de 8 zile", "since": "2026-09-15"},
        {"text": ""},
        "garbage",
    ], TODAY)
    assert [r["age_days"] for r in rows] == [16, 8, 0]
    assert [r["severity"] for r in rows] == ["red", "yellow", "info"]
    assert rows[0]["type"] == "așteptare" and rows[1]["type"] == "decizie"
    a = alerts.rules_pending(rows)
    assert [x["severity"] for x in a] == ["red", "yellow"]
    assert "de la registrar" in a[0]["text"] and "de la tine" in a[1]["text"]


def test_pending_missing_file(tmp_path):
    assert pending.fetch(tmp_path / "nope.yaml", TODAY) == []


def test_vault_size_rule(tmp_path):
    f = tmp_path / "MEMORY.md"
    f.write_text("x" * (17 * 1024 + 1), encoding="utf-8")
    v = vault.fetch(f)
    assert v["over_limit"] is True and v["kb"] == 17.0
    assert alerts.rules_vault(v)[0]["id"] == "vault:memory-size"
    f.write_text("small", encoding="utf-8")
    assert alerts.rules_vault(vault.fetch(f)) == []


def test_gates_are_locks_not_countdowns():
    rows = deadlines.compute([
        {"label": "T0", "type": "poarta", "date": "2026-10-07", "condition": "≥300"},
        {"label": "import", "type": "poarta", "condition": "după spot-check"},
        {"label": "Demo", "date": "2026-09-25"},
    ], TODAY)
    assert [r["label"] for r in rows] == ["Demo", "T0", "import"]
    assert rows[1]["gate"] and rows[1]["days_left"] == 14
    assert rows[2]["gate"] and rows[2]["date"] is None
    a = alerts.rules_deadlines(rows)
    assert [x["id"] for x in a] == ["deadline:Demo"]


def test_git_changed_files():
    porcelain = " M tools/comfy/comfy_gen.py\n M docs/audit-site-2026-09-23.md\n?? new.txt\n"
    assert git.parse_changed(porcelain) == ["tools/comfy/comfy_gen.py", "docs/audit-site-2026-09-23.md", "new.txt"]
    assert git.parse_changed("", 6) == []
