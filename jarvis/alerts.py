"""Pure rules: snapshot -> alerts. No I/O, fully unit-testable.

Severity: "red" needs action now, "yellow" worth a look, "info" FYI.
Each alert has a stable `id` so the UI can dedupe/acknowledge.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

BACKUP_MAX_AGE_H = 26
DISK_PCT = 90
GPU_PCT = 90
DEADLINE_DAYS = 3
EVENT_SOON_MIN = 120


def _a(id_: str, sev: str, text: str, source: str, **extra: Any) -> dict[str, Any]:
    return {"id": id_, "severity": sev, "text": text, "source": source, **extra}


def rules_tasks(tasks: list[dict[str, Any]], labels: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for t in tasks:
        name = t["name"]
        label = labels.get(name, name)
        if not t["result_ok"]:
            out.append(_a(f"task:{name}:result", "red", f"Task-ul „{label}” a eșuat: {t['result_text']} ({t['result_hex']}).", "tasks"))
        if t.get("stale"):
            h = round((t.get("age_s") or 0) / 3600, 1)
            out.append(_a(f"task:{name}:stale", "yellow", f"„{label}” n-a mai rulat de {h} h (interval {round((t['interval_s'] or 0)/60)} min).", "tasks"))
        if t.get("state") == "Disabled":
            out.append(_a(f"task:{name}:disabled", "yellow", f"„{label}” este dezactivat.", "tasks"))
        log = t.get("log")
        if log and log.get("failed"):
            out.append(_a(f"task:{name}:log", "red", f"Ultima rulare „{label}” a raportat eroare în jurnal: {log.get('summary') or log.get('rcs')}.", "tasks"))
    return out


def rules_docker(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    any_watched = any(c.get("watched") for c in containers)
    return [
        _a(f"docker:{c['name']}", "red", f"Containerul {c['name']} nu e sănătos ({c['status']}).", "docker")
        for c in containers if not c["ok"] and (c.get("watched") or not any_watched)
    ]


def rules_services(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in services:
        if not s["ok"]:
            note = f" {s['note']}." if s.get("note") else ""
            out.append(_a(f"svc:{s['name']}", "red" if s["name"] == "reranker" else "yellow",
                          f"Serviciul {s['name']} nu răspunde ({s.get('error') or s.get('status')}).{note}", "services"))
    return out


def rules_gpu(gpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _a(f"gpu:{g['index']}", "yellow", f"GPU {g['index']} la {g['mem_pct']}% VRAM.", "gpu")
        for g in gpus if g["mem_pct"] >= GPU_PCT
    ]


def rules_disk(disks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _a(f"disk:{d['path']}", "yellow", f"Discul {d['path']} e plin {d['used_pct']}% ({d['free_gb']} GB liberi).", "disk")
        for d in disks if d.get("used_pct") is not None and d["used_pct"] >= DISK_PCT
    ]


def rules_backup(b: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not b:
        return []
    if not b.get("mounted"):
        return [_a("backup:mount", "red", "Google Drive nu e montat: backup-ul de la 21:00 nu are unde scrie.", "backup")]
    if b.get("error"):
        return [_a("backup:report", "yellow", f"Backup: {b['error']}.", "backup")]
    out = []
    if b.get("status") and b["status"] != "OK":
        out.append(_a("backup:status", "red", f"Ultimul backup a eșuat: {'; '.join(b.get('failures') or []) or b['status']}.", "backup"))
    if b.get("age_h") is not None and b["age_h"] > BACKUP_MAX_AGE_H:
        out.append(_a("backup:age", "red", f"Ultimul backup reușit e vechi de {round(b['age_h'])} h.", "backup"))
    if b.get("warnings"):
        out.append(_a("backup:warn", "info", f"Backup cu avertismente: {'; '.join(b['warnings'])}.", "backup"))
    return out


def rules_git(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in repos:
        if r.get("error"):
            out.append(_a(f"git:{r['name']}:err", "info", f"Repo {r['name']}: {r['error']}.", "git"))
        elif r.get("alert_dirty", True) and r.get("dirty"):
            out.append(_a(f"git:{r['name']}:dirty", "yellow", f"Repo {r['name']} are {r['dirty']} fișiere modificate necomise.", "git"))
    return out


def rules_pending(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in items:
        if p["severity"] in ("red", "yellow"):
            who = "de la tine" if p["type"] == "decizie" else f"de la {p.get('from') or 'altcineva'}"
            out.append(_a(p["id"], p["severity"], f"Aștept {who} de {p['age_days']} zile: {p['text'][:90]}", "pending"))
    return out


def rules_vault(v: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not v or v.get("error"):
        return []
    if v.get("over_limit"):
        return [_a("vault:memory-size", "yellow", f"MEMORY.md are {v['kb']} KB, peste limita de {v['limit_kb']} KB; mută detaliul în notele de proiect.", "vault")]
    return []


def rules_deadlines(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for d in items:
        if d.get("gate") or d.get("days_left") is None:
            continue  # a gate is a lock, not a countdown
        if d["days_left"] < 0:
            out.append(_a(f"deadline:{d['label']}", "red", f"Termen depășit cu {-d['days_left']} zile: {d['label']}.", "deadlines"))
        elif d["days_left"] <= DEADLINE_DAYS:
            when = "azi" if d["days_left"] == 0 else ("mâine" if d["days_left"] == 1 else f"în {d['days_left']} zile")
            out.append(_a(f"deadline:{d['label']}", "yellow", f"Termen {when}: {d['label']}.", "deadlines"))
    return out


def rules_calendar(events: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    out = []
    for e in events:
        if e.get("all_day"):
            continue
        try:
            start = datetime.fromisoformat(e["start"])
        except (ValueError, TypeError):
            continue
        mins = (start - now).total_seconds() / 60
        if 0 <= mins <= EVENT_SOON_MIN:
            out.append(_a(f"cal:{e['start']}", "yellow", f"În {round(mins)} min: {e['summary']}.", "calendar"))
    return out


def rules_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in projects:
        mem = p.get("memory") or {}
        for b in mem.get("blockers") or []:
            out.append(_a(f"proj:{p['key']}:block:{b[:30]}", "info", f"{p['label']}: blocant — {b}", "projects"))
    return out


def build_alerts(snap: dict[str, Any], labels: dict[str, str], now: datetime) -> list[dict[str, Any]]:
    d = snap.get("data", {})
    alerts: list[dict[str, Any]] = []
    alerts += rules_tasks(d.get("tasks") or [], labels)
    alerts += rules_docker(d.get("docker") or [])
    alerts += rules_services(d.get("services") or [])
    alerts += rules_gpu(d.get("gpu") or [])
    alerts += rules_disk(d.get("disk") or [])
    alerts += rules_backup(d.get("backup"))
    alerts += rules_git(d.get("git") or [])
    alerts += rules_deadlines(d.get("deadlines") or [])
    alerts += rules_calendar(d.get("calendar") or [], now)
    alerts += rules_pending(d.get("pending") or [])
    alerts += rules_vault(d.get("vault"))
    alerts += rules_projects(d.get("projects") or [])
    for name, err in (snap.get("errors") or {}).items():
        alerts.append(_a(f"collector:{name}", "info", f"Colectorul {name} a dat eroare: {err}", "jarvis"))
    order = {"red": 0, "yellow": 1, "info": 2}
    return sorted(alerts, key=lambda a: order[a["severity"]])
