"""Google Calendar via the private ICS address (no OAuth). Recurring events expanded."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events


def parse_ics(ics_text: str, day: date, tz: ZoneInfo, days: int = 2) -> list[dict[str, Any]]:
    cal = icalendar.Calendar.from_ical(ics_text)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=days)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        dtstart = ev.get("DTSTART").dt
        dtend = ev.get("DTEND").dt if ev.get("DTEND") else None
        all_day = not isinstance(dtstart, datetime)
        if isinstance(dtstart, datetime):
            dtstart = dtstart.astimezone(tz)
        if isinstance(dtend, datetime):
            dtend = dtend.astimezone(tz)
        out.append({
            "summary": str(ev.get("SUMMARY", "")),
            "start": dtstart.isoformat(),
            "end": dtend.isoformat() if dtend else None,
            "all_day": all_day,
            "location": str(ev.get("LOCATION", "")) or None,
        })
    return sorted(out, key=lambda e: e["start"])


async def fetch(ics_url: str, tz: ZoneInfo, day: date | None = None) -> list[dict[str, Any]]:
    day = day or datetime.now(tz).date()
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(ics_url)
        r.raise_for_status()
    return parse_ics(r.text, day, tz)
