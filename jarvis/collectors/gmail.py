"""Unread mail of the last N hours over IMAP with an app password (read-only, no flag changes)."""
from __future__ import annotations

import email
import imaplib
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Any


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def parse_headers(raw: bytes) -> dict[str, Any]:
    msg = email.message_from_bytes(raw)
    date = None
    try:
        date = parsedate_to_datetime(msg.get("Date", "")).astimezone().isoformat(timespec="minutes")
    except Exception:
        pass
    return {"from": _decode(msg.get("From")), "subject": _decode(msg.get("Subject"))[:140], "date": date}


def fetch(user: str, app_password: str, hours: int = 48, limit: int = 30,
          host: str = "imap.gmail.com") -> dict[str, Any]:
    since = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(host) as m:
        m.login(user, app_password)
        m.select("INBOX", readonly=True)
        typ, data = m.search(None, "UNSEEN", "SINCE", since)
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        items = []
        for uid in ids[-limit:][::-1]:
            typ, parts = m.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ == "OK" and parts and isinstance(parts[0], tuple):
                items.append(parse_headers(parts[0][1]))
    return {"unread": len(ids), "items": items, "hours": hours}
