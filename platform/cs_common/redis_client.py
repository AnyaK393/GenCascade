"""One async Redis pool per service plus helpers for the control keys (contracts/redis_keys.md).
Every helper swallows Redis errors: the platform must keep answering if Redis hiccups."""

import json
import logging
import time

import redis.asyncio as aioredis
from fastapi import Header, HTTPException

from cs_common.settings import settings

log = logging.getLogger(__name__)

rds = aioredis.Redis(host=settings.redis_host, port=settings.redis_port,
                     password=settings.redis_password or None, decode_responses=True,
                     socket_timeout=0.5, socket_connect_timeout=0.5, max_connections=50)

HEARTBEAT, LEVEL, BREAKER, EXAM, ACTIONS = (
    "cs:control:heartbeat", "cs:mode:level", "cs:breaker:llm", "cs:mode:exam", "cs:actions")


async def control_keys() -> dict:
    """Fedora's advice in one round trip. Missing keys (or Redis down) come back as None."""
    try:
        hb, lvl, brk, exam = await rds.mget(HEARTBEAT, LEVEL, BREAKER, EXAM)
    except Exception:
        return {"heartbeat_age": None, "level": None, "breaker": None, "exam": None}
    return {"heartbeat_age": round(time.time() - float(hb), 2) if hb else None,
            "level": int(lvl) if lvl is not None else None,
            "breaker": brk, "exam": json.loads(exam) if exam else None}


async def get_level() -> int | None:
    return (await control_keys())["level"]


async def get_breaker() -> str | None:
    return (await control_keys())["breaker"]


async def heartbeat_age() -> float | None:
    return (await control_keys())["heartbeat_age"]


async def log_action(actor: str, action: str, value, reason: str,
                     risk: float | None = None, extra: dict | None = None) -> None:
    fields = {"ts": f"{time.time():.3f}", "actor": actor, "action": action,
              "value": str(value), "reason": reason}
    if risk is not None:
        fields["risk"] = f"{risk:.4f}"
    if extra:
        fields["extra"] = json.dumps(extra)
    try:
        await rds.xadd(ACTIONS, fields, maxlen=10_000, approximate=True)
    except Exception:
        log.warning("could not log action %s=%s", action, value)


def require_token(x_cs_token: str | None = Header(None)) -> None:
    if x_cs_token != settings.cs_token:
        raise HTTPException(401, "bad X-CS-Token")
