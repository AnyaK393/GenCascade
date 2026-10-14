"""Writes advice to the platform's Redis. The control room only advises: it never restarts
anything, and if it stops writing the heartbeat the Mac falls back to its local breaker."""

import json
import time

import redis.asyncio as aioredis

HEARTBEAT_KEY = "cs:control:heartbeat"
LEVEL_KEY = "cs:mode:level"
BREAKER_KEY = "cs:breaker:llm"
ACTIONS_KEY = "cs:actions"
ACTIONS_MAXLEN = 10_000


class RedisActuator:
    def __init__(self, r: aioredis.Redis, actor: str = "cascadeshield"):
        self.r = r
        self.actor = actor

    async def heartbeat(self) -> None:
        await self.r.set(HEARTBEAT_KEY, f"{time.time():.3f}", ex=10)

    async def write_risk(self, risks: dict[str, float]) -> None:
        async with self.r.pipeline(transaction=False) as p:
            for svc, risk in risks.items():
                p.set(f"cs:risk:{svc}", f"{risk:.4f}", ex=15)
            await p.execute()

    async def read_state(self) -> tuple[int, str]:
        level, breaker = await self.r.mget(LEVEL_KEY, BREAKER_KEY)
        return int(level or 0), (breaker or "closed")

    async def apply(self, action: str, value: str, reason: str, risk: float | None = None,
                    extra: dict | None = None) -> None:
        key = {"set_level": LEVEL_KEY, "set_breaker": BREAKER_KEY}[action]
        await self.r.set(key, value)
        await self.log_action(action, value, reason, risk, extra)

    async def log_action(self, action: str, value: str, reason: str, risk: float | None = None,
                         extra: dict | None = None, actor: str | None = None) -> None:
        fields = {"ts": f"{time.time():.3f}", "actor": actor or self.actor, "action": action,
                  "value": value, "reason": reason}
        if risk is not None:
            fields["risk"] = f"{risk:.4f}"
        if extra:
            fields["extra"] = json.dumps(extra)
        await self.r.xadd(ACTIONS_KEY, fields, maxlen=ACTIONS_MAXLEN, approximate=True)
