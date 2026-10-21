"""How the control room reaches the platform. It only advises: level and breaker changes go
through the control API (the Mac validates and logs them to cs:actions with risk and SHAP
factors); heartbeat, risk and explanations are written to Redis directly. Nothing here can
restart anything, and if the heartbeat stops the Mac falls back to its local breaker."""

import json
import time

import httpx
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

    async def stop_heartbeat(self) -> None:
        await self.r.delete(HEARTBEAT_KEY)

    async def write_risk(self, risks: dict[str, float], explain: dict[str, list] | None = None) -> None:
        async with self.r.pipeline(transaction=False) as p:
            for svc, risk in risks.items():
                p.set(f"cs:risk:{svc}", f"{risk:.4f}", ex=15)
            for svc, factors in (explain or {}).items():
                p.set(f"cs:explain:{svc}", json.dumps(factors), ex=15)
            await p.execute()

    async def apply(self, action: str, value: str, reason: str, risk: float | None = None,
                    extra: dict | None = None, actor: str | None = None) -> None:
        """Fallback when the control API is unreachable: write the key and log it ourselves."""
        key = {"set_level": LEVEL_KEY, "set_breaker": BREAKER_KEY}[action]
        await self.r.set(key, value)
        await self.log_action(action, value, reason, risk, extra, actor)

    async def log_action(self, action: str, value: str, reason: str, risk: float | None = None,
                         extra: dict | None = None, actor: str | None = None) -> None:
        fields = {"ts": f"{time.time():.3f}", "actor": actor or self.actor, "action": action,
                  "value": value, "reason": reason}
        if risk is not None:
            fields["risk"] = f"{risk:.4f}"
        if extra:
            fields["extra"] = json.dumps(extra)
        await self.r.xadd(ACTIONS_KEY, fields, maxlen=ACTIONS_MAXLEN, approximate=True)


class ControlAPI:
    """Client for the orchestrator's control API (contracts/control_api.md)."""

    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient):
        self.base = base_url.rstrip("/")
        self.hdr = {"X-CS-Token": token}
        self.http = http

    async def state(self) -> dict | None:
        try:
            r = await self.http.get(f"{self.base}/control/state", headers=self.hdr, timeout=1.0)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def post(self, path: str, body: dict) -> httpx.Response:
        r = await self.http.post(f"{self.base}{path}", json=body, headers=self.hdr, timeout=3.0)
        r.raise_for_status()
        return r

    async def decision(self, action: str, value: str, reason: str, risk: float | None,
                       factors: list | None, actor: str = "cascadeshield") -> None:
        body = {"reason": reason, "actor": actor, "risk": risk, "factors": factors}
        if action == "set_level":
            await self.post("/control/mode", {**body, "level": int(value)})
        else:
            await self.post("/control/breaker", {**body, "state": value})
