import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from jarvis.fastpath import answer, match

NOW = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Bucharest"))

SNAP = {
    "alerts": [
        {"severity": "yellow", "text": "„Ingest zilnic” n-a mai rulat de 26 h."},
        {"severity": "red", "text": "Backup-ul a eșuat."},
    ],
    "data": {
        "pending": [
            {"project": "site", "type": "decizie", "text": "Alege varianta de homepage", "age_days": 7, "from": "sesiunea site"},
            {"project": "site", "type": "asteptare", "text": "Fotografiile echipei de la designer", "age_days": 4, "from": "designer"},
            {"project": "shop", "type": "asteptare", "text": "Furnizorul confirmă cele 4 puncte", "age_days": 7, "from": "furnizor"},
            {"project": "thesis", "type": "decizie", "text": "Alege sursele pentru capitolul 3", "age_days": 7, "from": "sesiunea licență"},
        ],
        "deadlines": [
            {"label": "Lansarea site-ului", "project": "site", "date": "2026-10-08", "days_left": 8, "gate": False},
            {"label": "Test mâine", "project": "thesis", "date": "2026-10-01", "days_left": 1, "gate": False},
            {"label": "Prezentarea demo", "project": "shop", "date": "2026-09-25", "days_left": -5, "gate": False},
            {"label": "Verdict A/B", "project": "site", "date": "2026-10-07", "days_left": 7, "gate": True, "condition": "≥1000 vizite/variantă"},
        ],
        "projects": [
            {"key": "shop", "label": "Magazin", "next": "Lansare după confirmarea furnizorului"},
            {"key": "data", "label": "Date meteo", "next": "09.10 completare retroactivă O DATĂ"},
        ],
        "calendar": None,
    },
}


# --- match: the two real questions from the Jarvis journal (23.09) ---

def test_match_real_question_pending_and_red():
    assert match("Ce aștepți de la mine acum și ce e roșu?") == {"intents": ["pending", "alerts"], "project": None, "day": None}


def test_match_real_question_tomorrow_and_pending_for_project():
    assert match("Ce am de făcut mâine și ce aștepți de la mine la site?") == {
        "intents": ["day", "pending"], "project": "site", "day": "maine"}


def test_match_ignores_diacritics_and_case():
    assert match("CE ASTEPTI DE LA MINE") == match("ce aștepți de la mine")
    assert match("ce e roşu") is not None  # cedilla ş, not comma ș


def test_match_deadlines():
    assert match("ce termene am?")["intents"] == ["deadlines"]


@pytest.mark.parametrize("q", [
    "De ce e blocat magazinul?",
    "Explică-mi poarta A/B",
    "Cum merge ingest-ul?",
    "Ce părere ai despre Scrapling?",
    "Ce alerte am și ce zice logul de ingest?",   # intent + an uncovered part -> Claude
    "Ce e roșu și de ce?",
    "",
])
def test_match_falls_back_to_claude(q):
    assert match(q) is None


# --- answer ---

def test_answer_pending_lists_decisions_then_others():
    txt = answer(match("ce aștepți de la mine"), SNAP, NOW)
    assert "Decizii de la tine, 2:" in txt
    assert "Alege varianta de homepage, de 7 zile." in txt
    assert "De la alții, 2:" in txt
    assert "Furnizorul confirmă cele 4 puncte (furnizor), de 7 zile." in txt


def test_answer_project_filter():
    txt = answer(match("ce aștepți de la mine la site"), SNAP, NOW)
    assert "homepage" in txt and "Fotografiile" in txt
    assert "capitolul 3" not in txt and "4 puncte" not in txt


def test_answer_alerts_red_first():
    txt = answer(match("ce e roșu"), SNAP, NOW)
    assert txt.index("Backup-ul a eșuat.") < txt.index("n-a mai rulat")
    assert txt.startswith("Alerte, 2: 1 roșie.")


def test_answer_no_alerts():
    assert "Nicio alertă." in answer(match("ce e roșu"), {"alerts": [], "data": {}}, NOW)


def test_answer_deadlines_skip_past_and_list_gates():
    txt = answer(match("ce termene am"), SNAP, NOW)
    assert "Test mâine mâine (2026-10-01)." in txt
    assert "Lansarea site-ului în 8 zile (2026-10-08)." in txt
    assert "Prezentarea demo" not in txt
    assert "Porți închise: Verdict A/B, se deschide 2026-10-07." in txt


def test_answer_day_tomorrow_with_project_next():
    txt = answer(match("ce am de făcut mâine la magazin"), SNAP, NOW)
    assert txt.startswith("Mâine, 1 octombrie:")
    assert "Niciun termen." in txt
    assert "Magazin: Lansare după confirmarea furnizorului." in txt
    assert "Calendarul nu e configurat." in txt


def test_answer_day_counts_pending_when_not_asked_separately():
    txt = answer(match("ce am de făcut mâine"), SNAP, NOW)
    assert "Test mâine." in txt
    assert "Aștept de la tine 2 decizii." in txt


def test_answer_caps_long_lists():
    many = {"alerts": [], "data": {"pending": [
        {"project": "x", "type": "decizie", "text": f"d{i}", "age_days": 1} for i in range(8)]}}
    txt = answer(match("ce aștepți de la mine"), many, NOW)
    assert "d4, de o zi." in txt and "d5" not in txt
    assert "Și încă 3." in txt


def test_answer_romanian_day_counts_and_speakable_text():
    snap = {"alerts": [], "data": {"pending": [
        {"project": "x", "type": "decizie", "text": "Google Ads (C:\\work\\docs\\plan.md) - da / nu?", "age_days": 21}]}}
    txt = answer(match("ce aștepți de la mine"), snap, NOW)
    assert "Google Ads - da / nu, de 21 de zile." in txt


# --- real-data fixes (live run 30.09): pending duplicated in alerts, paths read aloud, mid-word cuts ---

REAL_ALERTS = {"alerts": [
    {"severity": "red", "text": "Termen depășit cu 5 zile: Prezentarea demo.", "source": "deadlines"},
    {"severity": "yellow", "text": "Aștept de la tine de 7 zile: Alege varianta de homepage (A are textul vechi, B are formularul nou;", "source": "pending"},
    {"severity": "yellow", "text": "MEMORY.md are 18 KB.", "source": "vault"},
    {"severity": "info", "text": "Backup ok.", "source": "backup"},
    {"severity": "info", "text": "3 fișiere necomise.", "source": "git"},
], "data": {"pending": [{"project": "site", "type": "decizie", "text": "Alege varianta de homepage", "age_days": 7}]}}


def test_answer_alerts_drop_pending_duplicates_when_pending_also_asked():
    txt = answer(match("ce aștepți de la mine și ce e roșu"), REAL_ALERTS, NOW)
    assert txt.count("homepage") == 1
    assert "Alerte, 2: 1 roșie." in txt


def test_answer_alerts_list_red_and_yellow_summarise_info():
    txt = answer(match("ce e roșu"), REAL_ALERTS, NOW)
    assert "Backup ok." not in txt
    assert txt.endswith("Și 2 informative.")
    assert "Aștept de la tine de 7 zile: Alege varianta de homepage." in txt   # cut at the open parenthesis


def test_speakable_keeps_headline_drops_paths():
    snap = {"alerts": [], "data": {"pending": [{"project": "thesis", "type": "decizie", "age_days": 7, "text":
            "Deschide ghidul de redactare și marchează citările incomplete; lista „neverificat” e în scripts/sources/ro/verification_report.md"}]}}
    txt = answer(match("ce aștepți de la mine"), snap, NOW)
    assert "Deschide ghidul de redactare și marchează citările incomplete, de 7 zile." in txt


def test_speakable_cuts_on_a_word_boundary():
    long = "cuvinte " * 40   # 8 chars each: any fixed limit lands mid-word
    snap = {"alerts": [], "data": {"pending": [{"project": "x", "type": "decizie", "age_days": 2, "text": long}]}}
    txt = answer(match("ce aștepți de la mine"), snap, NOW)
    assert "cuvinte, de 2 zile." in txt
    assert not re.search(r"\bcuvi?n?t?e?,", txt.replace("cuvinte,", ""))


def test_speakable_keeps_bare_file_names_drops_only_paths():
    snap = {"alerts": [{"severity": "yellow", "text": "MEMORY.md are 17.3 KB, peste limita de 17 KB.", "source": "vault"}], "data": {}}
    assert "MEMORY.md are 17.3 KB, peste limita de 17 KB." in answer(match("ce e roșu"), snap, NOW)
    snap2 = {"alerts": [], "data": {"pending": [{"project": "x", "type": "decizie", "age_days": 3,
             "text": "Citește raportul din scripts/sources/ro/verification_report.md înainte de curs"}]}}
    assert "scripts/sources" not in answer(match("ce aștepți de la mine"), snap2, NOW)
