"""Resilience core: one asyncio process, one loop every CS_LOOP_S seconds.

collect -> risk -> containment -> write advice to Redis, and serve /state and /metrics.
Run: uv run python -m resilience_core.main
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from .actuator import RedisActuator
from .collector import Collector, TelemetryError
from .containment import ControlState, ThresholdPolicy
from .risk import threshold_risk
from .settings import SERVICES, settings

log = logging.getLogger("resilience_core")

LOOP_SECONDS = Histogram("cs_core_loop_seconds", "Duration of one control cycle",
                         buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2))
ACTIONS = Counter("cs_core_actions_total", "Containment actions sent", ["action", "value"])
CYCLES = Counter("cs_core_cycles_total", "Control cycles by outcome", ["outcome"])
RISK = Gauge("cs_core_risk", "Latest risk per service", ["target"])

CONTAINED_SERVICE = "llm_inference"


class Core:
    def __init__(self, collector: Collector, actuator: RedisActuator, http: httpx.AsyncClient):
        self.collector = collector
        self.actuator = actuator
        self.http = http
        self.policy = ThresholdPolicy()
        self.state = ControlState()
        self.snapshot: dict = {"ts": None, "healthy": False, "error": "starting"}

    async def _platform_state(self) -> dict | None:
        try:
            r = await self.http.get(f"{settings.control_api}/control/state",
                                    headers={"X-CS-Token": settings.cs_token}, timeout=1.0)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def cycle(self) -> None:
        now = time.time()
        try:
            telemetry = await self.collector.collect()
        except TelemetryError as e:
            # No fresh data: stop the heartbeat so the Mac's local breaker takes over.
            CYCLES.labels("no_telemetry").inc()
            self.snapshot = {**self.snapshot, "ts": now, "healthy": False, "error": f"telemetry: {e}"}
            log.warning("no telemetry: %s", e)
            return

        risks = {s: threshold_risk((telemetry.get(s) or {}).get("p95_s"), settings.slo_s[s])
                 for s in SERVICES}
        for s, v in risks.items():
            RISK.labels(s).set(v)

        await self.actuator.heartbeat()
        await self.actuator.write_risk(risks)

        # Re-read every cycle so operator changes made through the control API are respected.
        self.state = ControlState(*await self.actuator.read_state())
        risk = risks[CONTAINED_SERVICE]
        decisions = self.policy.decide(risk, now, self.state)
        for d in decisions:
            await self.actuator.apply(d.action, d.value, d.reason, risk=risk,
                                      extra={"policy": "threshold", "open_at": self.policy.open_at})
            ACTIONS.labels(d.action, d.value).inc()
            if d.action == "set_level":
                self.state.level = int(d.value)
            else:
                self.state.breaker = d.value
            log.info("%s -> %s (%s)", d.action, d.value, d.reason)

        self.snapshot = {
            "ts": now,
            "healthy": True,
            "error": None,
            "policy": "threshold",
            "contained_service": CONTAINED_SERVICE,
            "threshold": self.policy.open_at,
            "risk": risks,
            "telemetry": telemetry,
            "slo_s": settings.slo_s,
            "control": {"level": self.state.level, "breaker": self.state.breaker},
            "platform": await self._platform_state(),
            "decisions": [d.__dict__ for d in decisions],
        }
        CYCLES.labels("ok").inc()

    async def run(self) -> None:
        log.info("starting loop every %.1fs", settings.loop_s)
        while True:
            start = time.monotonic()
            try:
                await self.cycle()
            except Exception as e:  # keep the loop alive; a missed cycle just skips a heartbeat
                CYCLES.labels("error").inc()
                self.snapshot = {**self.snapshot, "ts": time.time(), "healthy": False, "error": repr(e)}
                log.exception("cycle failed")
            elapsed = time.monotonic() - start
            LOOP_SECONDS.observe(elapsed)
            await asyncio.sleep(max(0.0, settings.loop_s - elapsed))


core: Core | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global core
    http = httpx.AsyncClient()
    r = aioredis.Redis(host=settings.redis_host, port=settings.redis_port,
                       password=settings.redis_password, decode_responses=True,
                       socket_timeout=2, socket_connect_timeout=2)
    core = Core(Collector(settings.prometheus_url, http), RedisActuator(r), http)
    task = asyncio.create_task(core.run())
    yield
    task.cancel()
    await http.aclose()
    await r.aclose()


app = FastAPI(title="CascadeShield resilience core", lifespan=lifespan)


@app.get("/state")
async def state() -> dict:
    return core.snapshot if core else {"healthy": False, "error": "starting"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run(app, host="0.0.0.0", port=settings.core_port, log_level="warning")
