"""Local answers for the everyday questions, without `claude -p`.

"Ce aștepți de la mine?", "ce e roșu?", "ce termene am?", "ce am de făcut mâine?"
are answered straight from the board snapshot (same fields `context.compact`
feeds the brain), in well under a second instead of 3-4 s. Anything the rules
do not fully cover — a "de ce"/"cum", or a part no intent explains — returns
None and goes to Claude as before: a wrong fast answer is worse than a slow one.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any

MAX_ITEMS = 5

INTENTS: dict[str, list[str]] = {
    "pending": ["astepti de la mine", "asteapta de la mine", "ai nevoie de la mine", "ce decizii", "trebuie sa decid"],
    "alerts": ["rosu", "rosii", "alerte", "alerta", "ce a picat", "ce a esuat", "probleme"],
    "deadlines": ["termene", "termen", "porti", "deadline", "deadlineuri"],
    "day": ["ce am de facut", "ce am azi", "ce am maine", "ce e azi", "ce e maine", "ce fac azi", "ce fac maine"],
}
BLOCKERS = ["de ce", "cum", "explica", "ce crezi", "compara", "analizeaza", "detalii", "verifica", "scrie"]
# spoken word -> project key (config `projects[].key`); several words may point to one project
PROJECTS = {"site": "site", "magazin": "shop", "shop": "shop", "licenta": "thesis", "lucrare": "thesis",
            "date": "data", "pipeline": "data", "cariera": "career", "content": "content"}
FILLER = {"ce", "si", "acum", "la", "pentru", "mai", "e", "este", "sunt", "azi", "maine", "jarvis", "te", "rog",
          "imi", "mi", "spune", "zi", "care", "ai", "am", "de", "ceva", "tot", "toate", "eu", "pe", "in", "din",
          "o", "un", "ma", "mine", "nou", "noi"}
MONTHS = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
          "septembrie", "octombrie", "noiembrie", "decembrie"]


def _norm(text: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def _find(phrase: str, s: str) -> re.Match[str] | None:
    return re.search(rf"\b{re.escape(phrase)}\b", s)


def match(text: str) -> dict[str, Any] | None:
    """Question -> {"intents": [...in question order], "project": key|None, "day": "azi"|"maine"|None}, or None."""
    s = _norm(text)
    if not s or any(_find(b, s) for b in BLOCKERS):
        return None
    found: list[tuple[int, str]] = []
    rest = s
    for intent, phrases in INTENTS.items():
        for p in phrases:
            m = _find(p, s)
            if m:
                found.append((m.start(), intent))
                rest = re.sub(rf"\b{re.escape(p)}\b", " ", rest)
    if not found:
        return None
    project = None
    for word, key in PROJECTS.items():
        if _find(word, rest):
            project = key
            rest = re.sub(rf"\b{re.escape(word)}\b", " ", rest)
    if any(w not in FILLER for w in rest.split()):
        return None
    intents = list(dict.fromkeys(i for _, i in sorted(found)))
    day = ("maine" if _find("maine", s) else "azi") if "day" in intents else None
    return {"intents": intents, "project": project, "day": day}


def _days(n: int) -> str:
    if n == 1:
        return "o zi"
    return f"{n} de zile" if n % 100 >= 20 or (n and n % 100 == 0) else f"{n} zile"


PATH = re.compile(r"\S*[/\\]\S*\.\w+")   # only real paths; a bare "MEMORY.md" is information


def _speakable(text: str, limit: int = 120) -> str:
    """Pending/alert texts are written as "headline; detail (path)": keep what is worth hearing."""
    t = re.sub(r"\s*\([^)]*\)", "", str(text))      # whole parentheticals
    t = t.split("(")[0]                              # one cut open by an upstream truncation
    head = t.split("; ")[0]
    t = head if len(head) >= 20 else t
    t = re.sub(r"\s+", " ", PATH.sub("", t)).strip()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0]
    return t.rstrip(" .?!;:,—-")


def _capped(items: list[str]) -> str:
    out = " ".join(items[:MAX_ITEMS])
    return out + (f" Și încă {len(items) - MAX_ITEMS}." if len(items) > MAX_ITEMS else "")


def _pending(d: dict[str, Any], project: str | None) -> str:
    items = [p for p in d.get("pending") or [] if not project or p.get("project") == project]
    if not items:
        return f"Nimic în așteptare la {project}." if project else "Nu aștept nimic de la tine."
    def line(p: dict[str, Any], who: bool) -> str:
        src = f" ({p['from']})" if who and p.get("from") else ""
        age = p.get("age_days")
        when = "" if age is None else (", de azi" if age == 0 else f", de {_days(age)}")
        return f"{_speakable(p['text'])}{src}{when}."
    mine = [line(p, False) for p in items if p.get("type") == "decizie"]
    others = [line(p, True) for p in items if p.get("type") != "decizie"]
    parts = [f"Decizii de la tine, {len(mine)}: " + _capped(mine) if mine else "Nicio decizie de la tine."]
    if others:
        parts.append(f"De la alții, {len(others)}: " + _capped(others))
    return " ".join(parts)


def _alerts(snap: dict[str, Any], skip_pending: bool) -> str:
    """Red + yellow read out, info only counted. Pending-age alerts repeat the pending
    list, so they are dropped when that list is part of the same answer."""
    all_ = [a for a in snap.get("alerts") or [] if not (skip_pending and a.get("source") == "pending")]
    if not all_:
        return "Nicio alertă."
    order = {"red": 0, "yellow": 1}
    al = sorted((a for a in all_ if a.get("severity") in order), key=lambda a: order[a["severity"]])
    n_info = len(all_) - len(al)
    info = "" if not n_info else (" Și una informativă." if n_info == 1 else f" Și {n_info} informative.")
    if not al:
        return "Nicio alertă roșie sau galbenă." + info
    red = sum(1 for a in al if a["severity"] == "red")
    head = "niciuna roșie" if red == 0 else ("1 roșie" if red == 1 else f"{red} roșii")
    return f"Alerte, {len(al)}: {head}. " + _capped([_speakable(a["text"], 160) + "." for a in al]) + info


def _deadlines(d: dict[str, Any], project: str | None) -> str:
    dl = [x for x in d.get("deadlines") or [] if not project or x.get("project") == project]
    dated = [x for x in dl if not x.get("gate") and x.get("days_left") is not None and x["days_left"] >= 0]
    gates = [x for x in dl if x.get("gate")]
    parts = []
    if dated:
        def when(n: int) -> str:
            return "azi" if n == 0 else ("mâine" if n == 1 else f"în {_days(n)}")
        parts.append(f"Termene, {len(dated)}: " + _capped([f"{x['label']} {when(x['days_left'])} ({x['date']})." for x in dated]))
    else:
        parts.append("Niciun termen în față.")
    if gates:
        parts.append("Porți închise: " + "; ".join(
            x["label"] + (f", se deschide {x['date']}" if x.get("date") else "") for x in gates) + ".")
    return " ".join(parts)


def _day(d: dict[str, Any], m: dict[str, Any], now: datetime) -> str:
    offset = 1 if m["day"] == "maine" else 0
    target = (now + timedelta(days=offset)).date()
    parts = [f"{'Mâine' if offset else 'Azi'}, {target.day} {MONTHS[target.month - 1]}:"]
    project = m["project"]
    due = [x for x in d.get("deadlines") or [] if not x.get("gate") and x.get("days_left") == offset
           and (not project or x.get("project") == project)]
    parts += [f"Termen: {x['label']}." for x in due] or ["Niciun termen."]
    if project:
        parts += [f"{p['label']}: {_speakable(p['next'], 200)}." for p in d.get("projects") or []
                  if p.get("key") == project and p.get("next")]
    if "pending" not in m["intents"]:
        n = sum(1 for p in d.get("pending") or [] if p.get("type") == "decizie" and (not project or p.get("project") == project))
        if n:
            parts.append("Aștept de la tine " + ("o decizie." if n == 1 else f"{n} decizii."))
    cal = d.get("calendar")
    if cal is None:
        parts.append("Calendarul nu e configurat.")
    else:
        ev = [e for e in cal if str(e.get("start", ""))[:10] == target.isoformat()]
        parts += [f"{'toată ziua' if e.get('all_day') else str(e['start'])[11:16]} {e['summary']}." for e in ev] or ["Nimic în calendar."]
    return " ".join(parts)


def answer(m: dict[str, Any], snap: dict[str, Any], now: datetime) -> str:
    d = snap.get("data") or {}
    out = []
    for intent in m["intents"]:
        if intent == "pending":
            out.append(_pending(d, m["project"]))
        elif intent == "alerts":
            out.append(_alerts(snap, skip_pending="pending" in m["intents"]))
        elif intent == "deadlines":
            out.append(_deadlines(d, m["project"]))
        elif intent == "day":
            out.append(_day(d, m, now))
    return " ".join(out)
