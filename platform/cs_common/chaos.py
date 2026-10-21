"""Fault injection (contracts/control_api.md, guide 5.5). The routes exist only when
CHAOS_ENABLED=1 and need X-CS-Token. Services call `await inject()` where the fault belongs."""

import asyncio
import logging
import os
import random
import time

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from cs_common.redis_client import log_action, require_token
from cs_common.settings import settings

log = logging.getLogger("chaos")
LEAK_CAP_MB = 120  # guide 5.5 cap on leaked memory
RSS_CAP_MB = 140  # and the process stays under the 160 MB container limit: slow, not OOM-killed
MB = 1024 * 1024

faults = {"latency_ms": 0, "latency_until": 0.0, "error_rate": 0.0, "errors_until": 0.0}
leak: dict = {"blocks": [], "task": None}


async def inject() -> None:
    """Raise a 500 for a fraction of calls, then add the configured delay."""
    now = time.time()
    if now < faults["errors_until"] and random.random() < faults["error_rate"]:
        raise HTTPException(500, "chaos: injected error")
    if now < faults["latency_until"]:
        await asyncio.sleep(faults["latency_ms"] / 1000)


def leaked_mb() -> int:
    return len(leak["blocks"])


def rss_mb() -> float:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / MB
    except OSError:
        return 0.0  # not Linux: rely on LEAK_CAP_MB alone


def can_leak() -> bool:
    return leaked_mb() < LEAK_CAP_MB and rss_mb() < RSS_CAP_MB


def clear() -> None:
    faults.update(latency_ms=0, latency_until=0.0, error_rate=0.0, errors_until=0.0)
    if leak["task"]:
        leak["task"].cancel()
        leak["task"] = None
    leak["blocks"].clear()  # the held memory is released here, not when the leak ends


async def _leak(mb_per_s: float, seconds: float) -> None:
    end, owed = time.time() + seconds, 0.0
    while time.time() < end and can_leak():
        owed += mb_per_s
        while owed >= 1 and can_leak():
            leak["blocks"].append(b"\x01" * MB)  # written bytes, so the pages are really resident
            owed -= 1
        await asyncio.sleep(1)


class LatencyBody(BaseModel):
    extra_ms: int
    seconds: float = 120


class LeakBody(BaseModel):
    mb_per_s: float
    seconds: float = 180


class ErrorsBody(BaseModel):
    rate: float
    seconds: float = 60


router = APIRouter(prefix="/chaos", dependencies=[Depends(require_token)])


@router.post("/latency")
async def chaos_latency(b: LatencyBody):
    faults.update(latency_ms=max(0, b.extra_ms), latency_until=time.time() + b.seconds)
    await log_action("chaos", "latency", b.extra_ms, f"{settings.service_name} +{b.extra_ms} ms for {b.seconds:.0f} s")
    return {"ok": True, **faults}


@router.post("/leak")
async def chaos_leak(b: LeakBody):
    if leak["task"]:
        leak["task"].cancel()
    leak["task"] = asyncio.create_task(_leak(b.mb_per_s, b.seconds))
    await log_action("chaos", "leak", b.mb_per_s, f"{settings.service_name} {b.mb_per_s} MB/s for {b.seconds:.0f} s")
    return {"ok": True, "cap_mb": LEAK_CAP_MB, "rss_cap_mb": RSS_CAP_MB}


@router.post("/errors")
async def chaos_errors(b: ErrorsBody):
    faults.update(error_rate=min(1.0, max(0.0, b.rate)), errors_until=time.time() + b.seconds)
    await log_action("chaos", "errors", b.rate, f"{settings.service_name} {b.rate:.0%} errors for {b.seconds:.0f} s")
    return {"ok": True, **faults}


@router.post("/clear")
async def chaos_clear():
    clear()
    await log_action("chaos", "clear", "all", f"{settings.service_name} faults cleared")
    return {"ok": True}


@router.get("/state")
async def chaos_state():
    now = time.time()
    return {"latency_ms": faults["latency_ms"] if now < faults["latency_until"] else 0,
            "error_rate": faults["error_rate"] if now < faults["errors_until"] else 0.0,
            "leaked_mb": leaked_mb(), "rss_mb": round(rss_mb(), 1)}


def install(app: FastAPI) -> None:
    if settings.chaos_enabled:
        app.include_router(router)
        log.warning("chaos hooks enabled")
