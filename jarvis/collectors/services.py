"""HTTP liveness of local services (reranker :8009, web UI :8011, api :8008...)."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


def classify(status_code: int | None, body: str, expect: str | None) -> bool:
    if status_code is None or status_code >= 500:
        return False
    if expect:
        return expect in body
    return status_code < 400


async def check_one(client: httpx.AsyncClient, svc: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    status, body, err = None, "", None
    try:
        r = await client.get(svc["url"])
        status, body = r.status_code, r.text[:4000]
    except Exception as e:  # connection refused, timeout...
        err = type(e).__name__
    return {
        "name": svc["name"],
        "url": svc["url"],
        "ok": classify(status, body, svc.get("expect")),
        "status": status,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "error": err,
        "note": svc.get("note"),
    }


async def fetch(services: list[dict[str, Any]], timeout: float = 2.0) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return list(await asyncio.gather(*(check_one(client, s) for s in services)))
