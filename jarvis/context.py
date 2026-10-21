"""Compact the snapshot into a few KB of Romanian text for the brain prompt.

The point: most questions ("a rulat ingest-ul?", "ce am de făcut la site?") get
answered from this block without a single tool call, which keeps `claude -p`
at one turn.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _age(iso: str | None, now: datetime) -> str:
    if not iso:
        return "niciodată"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    s = (now - dt).total_seconds()
    if s < 0:
        return f"peste {round(-s/60)} min"
    if s < 3600:
        return f"acum {round(s/60)} min"
    if s < 86400:
        return f"acum {s/3600:.1f} h"
    return f"acum {s/86400:.1f} zile"


def compact(snap: dict[str, Any], now: datetime, labels: dict[str, str] | None = None, max_chars: int = 6000) -> str:
    labels = labels or {}
    d = snap.get("data", {})
    lines: list[str] = [f"[STARE CURENTĂ] {now.strftime('%A %d.%m.%Y %H:%M')} (Europe/Bucharest)"]

    alerts = snap.get("alerts") or []
    if alerts:
        lines.append("ALERTE:")
        for a in alerts[:12]:
            lines.append(f"- [{a['severity']}] {a['text']}")
    else:
        lines.append("ALERTE: niciuna.")

    tasks = d.get("tasks") or []
    if tasks:
        lines.append("TASK-URI PROGRAMATE:")
        for t in tasks:
            lab = labels.get(t["name"], t["name"])
            log = t.get("log") or {}
            extra = f"; jurnal: {'idle' if log.get('idle') else ('EROARE' if log.get('failed') else 'ok')} {log.get('summary','')[:90]}" if log else ""
            lines.append(f"- {lab}: {t['result_text']}, ultima {_age(t.get('last_run'), now)}, următoarea {_age(t.get('next_run'), now) if t.get('next_run') else '-'}{extra}")

    svc = d.get("services") or []
    if svc:
        lines.append("SERVICII: " + ", ".join(f"{s['name']} {'ok' if s['ok'] else 'JOS'}" for s in svc))
    dock = d.get("docker") or []
    if dock:
        bad = [c["name"] for c in dock if not c["ok"]]
        lines.append(f"DOCKER: {len(dock)} containere, " + (f"probleme: {', '.join(bad)}" if bad else "toate ok"))
    gpus = d.get("gpu") or []
    if gpus:
        lines.append("GPU: " + "; ".join(f"#{g['index']} {g['mem_used_mib']}/{g['mem_total_mib']} MiB, {g['util_pct']}%" for g in gpus))
    b = d.get("backup")
    if b:
        lines.append(f"BACKUP: {'nemontat' if not b.get('mounted') else (b.get('error') or f'{b.get('status')} {_age(b.get('run_at'), now)}')}")
    disks = d.get("disk") or []
    if disks:
        lines.append("DISC: " + ", ".join(f"{x['path']} {x.get('used_pct')}% ({x.get('free_gb')} GB liberi)" for x in disks if "used_pct" in x))

    projs = d.get("projects") or []
    if projs:
        lines.append("PROIECTE (NEXT / blocanți / ultima sesiune):")
        for p in projs:
            mem = p.get("memory") or {}
            note = p.get("note") or {}
            bits = []
            if p.get("next"):
                bits.append(f"NEXT: {p['next']}")
            if mem.get("blockers"):
                bits.append("BLOCANT: " + "; ".join(mem["blockers"][:2]))
            if note.get("last_session"):
                bits.append(f"ultima sesiune {note['last_session']}")
            if mem.get("rules"):
                bits.append("reguli: " + "; ".join(r[:60] for r in mem["rules"][:2]))
            lines.append(f"- {p['label']}: " + (" | ".join(bits) if bits else mem.get("status_raw", "")[:160]))

    pend = d.get("pending") or []
    if pend:
        lines.append("AȘTEPT (decizii de la utilizator / așteptări externe), cele mai vechi primele:")
        for p in pend[:12]:
            who = "DE LA UTILIZATOR" if p["type"] == "decizie" else f"de la {p.get('from') or '?'}"
            extra = f" (blochează: {p['blocks']})" if p.get("blocks") else ""
            lines.append(f"- [{p['project']}] {who}, {p['age_days']} zile: {p['text'][:140]}{extra}")

    repos = d.get("git") or []
    if repos:
        lines.append("GIT:")
        for r in repos:
            if r.get("error"):
                continue
            files = ", ".join(r.get("changed") or [])[:160]
            named = f" ({files})" if files and (r.get("dirty") or 0) <= 12 else ""
            lines.append(f"- {r['name']} {r.get('branch')}: {r.get('dirty')} necomise{named}, ultimul commit {_age((r.get('last_commit') or {}).get('date'), now)}")

    v = d.get("vault")
    if v and v.get("over_limit"):
        lines.append(f"MEMORY.md: {v['kb']} KB, peste limita de {v['limit_kb']} KB.")

    cal = d.get("calendar")
    if cal is None:
        lines.append("CALENDAR: neconfigurat.")
    elif cal:
        lines.append("CALENDAR (azi + mâine):")
        for e in cal[:10]:
            when = e["start"][:16].replace("T", " ") if not e["all_day"] else e["start"][:10] + " toată ziua"
            lines.append(f"- {when}: {e['summary']}")
    else:
        lines.append("CALENDAR: nimic azi și mâine.")

    gm = d.get("gmail")
    if gm is None:
        lines.append("EMAIL: neconfigurat.")
    else:
        lines.append(f"EMAIL: {gm['unread']} necitite în ultimele {gm['hours']} h" + (":" if gm["items"] else "."))
        for m in gm["items"][:6]:
            lines.append(f"- {m['from'][:40]}: {m['subject'][:80]}")

    dl = d.get("deadlines") or []
    dated = [x for x in dl if not x.get("gate")]
    gates = [x for x in dl if x.get("gate")]
    if dated:
        lines.append("TERMENE: " + "; ".join(f"{x['label']} în {x['days_left']} zile ({x['date']})" for x in dated[:8]))
    if gates:
        lines.append("PORȚI (o singură rulare / nu se atinge până nu se deschid): " + "; ".join(
            x["label"] + (f", se deschide {x['date']}" if x.get("date") else "") + (f", condiție: {x['condition']}" if x.get("condition") else "")
            for x in gates))

    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[:max_chars] + "\n[trunchiat]"
