"""Resilience core: one asyncio process, one cycle every CS_LOOP_S seconds.

collect (last 80 s) -> predict per service -> cascade risk over the dependency graph ->
containment engine (with dry-run / approval / kill switch) -> exam calendar -> heartbeat,
risk and SHAP factors to Redis. Serves /state, /history, /metrics and operator endpoints.

Run: uv run python -m resilience_core.main
"""

import asyncio
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
import redis.asyncio as aioredis
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from . import dependency_graph as dg
from .actuator import ControlAPI, RedisActuator
from .calendar import CALENDAR_FILE, Exam, ExamCalendar
from .collector import Collector, TelemetryError
from .containment_engine import ContainmentEngine, Decision, EngineConfig, Observation, reactive_risk
from .features import TARGETS
from .model import load_active
from .predictor import WINDOW_S, Predictor
from .risk import threshold_risk
from .settings import SERVICES, settings

log = logging.getLogger("resilience_core")

LOOP_SECONDS = Histogram("cs_core_loop_seconds", "Duration of one control cycle",
                         buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4))
ACTIONS = Counter("cs_core_actions_total", "Containment decisions", ["action", "value", "mode"])
CYCLES = Counter("cs_core_cycles_total", "Control cycles by outcome", ["outcome"])
RISK = Gauge("cs_core_risk", "Own failure probability per service", ["target"])
CASCADE = Gauge("cs_core_cascade_risk", "Cascade risk per service", ["target"])

CONTAINED = "llm_inference"
CONTROLLERS = ("predictive", "threshold", "reactive")
CAPACITY_USERS = int(os.environ.get("CS_CAPACITY_USERS", "5"))
HISTORY_S = 600


def queue_growth(series, seconds: float = 30) -> float:
    """LLM queue depth change per second over the last `seconds` (the queue_growth_per_s feature)."""
    q = series[series["service"] == CONTAINED].set_index("t")["queue_depth"].dropna().sort_index()
    if len(q) < 2:
        return 0.0
    past = q[q.index <= q.index[-1] - seconds]
    return float((q.iloc[-1] - (past.iloc[-1] if len(past) else q.iloc[0])) / seconds)


class Ops(BaseModel):
    """Operator settings (dashboard sidebar)."""
    dry_run: bool = os.environ.get("CS_DRY_RUN", "0") == "1"
    approval: bool = os.environ.get("CS_APPROVAL", "0") == "1"
    kill_switch: bool = False
    controller: str = os.environ.get("CS_CONTROLLER", "predictive")
    graph_enabled: bool = True
    ladder: str = "full"  # full | binary (ablation: L0/L3 only)


class Core:
    def __init__(self, collector: Collector, actuator: RedisActuator, api: ControlAPI):
        self.collector, self.actuator, self.api = collector, actuator, api
        self.ops = Ops()
        self.predictor: Predictor | None = None
        self.model_error: str | None = None
        self.load_model()
        self.engine = ContainmentEngine(EngineConfig(threshold=self.threshold))
        self.calendar = ExamCalendar.load(CALENDAR_FILE, datetime.now().astimezone())
        self.shadow: dict | None = None  # dry-run: the state the engine believes it has set
        self.pending: dict | None = None  # approval mode: decisions awaiting the operator
        self.history: deque[dict] = deque(maxlen=int(HISTORY_S / settings.loop_s))
        self.snapshot: dict = {"ts": None, "healthy": False, "error": "starting"}

    # --- model ---------------------------------------------------------------------------

    def load_model(self) -> None:
        try:
            bundle = load_active()
            self.predictor = Predictor(bundle) if bundle else None
            self.model_error = None if bundle else "no trained model (models/metadata.json); using threshold risk"
        except Exception as e:  # a feature mismatch must not silently mis-predict
            self.predictor, self.model_error = None, f"model refused: {e}"
            log.error(self.model_error)

    @property
    def controller(self) -> str:
        return "threshold" if self.ops.controller == "predictive" and not self.predictor else self.ops.controller

    @property
    def threshold(self) -> float:
        return self.predictor.bundle.threshold if self.controller == "predictive" else 0.8

    # --- one cycle -------------------------------------------------------------------------

    def own_risks(self, series, telemetry: dict, exam_active: float) -> tuple[dict, dict]:
        """({service: risk or None}, {service: prediction details})."""
        p95 = {s: (telemetry.get(s) or {}).get("p95_s") for s in SERVICES}
        if self.controller == "reactive":
            return {s: reactive_risk(p95[s], settings.slo_s[s]) for s in SERVICES}, {}
        risks = {s: threshold_risk(p95[s], settings.slo_s[s]) for s in SERVICES}
        details: dict = {}
        if self.controller == "predictive":
            details = self.predictor.predict(series, exam_active)
            for s in TARGETS:  # rag and student have no model; they keep the p95/SLO risk
                risks[s] = details.get(s, {}).get("risk")
        return risks, details

    async def act(self, decisions: list[Decision], risk: float, factors: list) -> None:
        if not decisions:
            return
        mode = "dry_run" if self.ops.dry_run else "approval" if self.ops.approval else "live"
        for d in decisions:
            ACTIONS.labels(d.action, d.value, mode).inc()
        if mode == "dry_run":
            for d in decisions:
                await self.actuator.log_action(d.action, d.value, f"[dry-run] {d.reason}", risk,
                                               {"factors": factors}, actor="cascadeshield-dryrun")
                self.shadow["level" if d.action == "set_level" else "breaker"] = (
                    int(d.value) if d.action == "set_level" else d.value)
            return
        if mode == "approval":
            self.pending = {"created": time.time(), "risk": risk, "factors": factors,
                            "decisions": [d.__dict__ for d in decisions]}
            return
        await self.send(decisions, risk, factors)

    async def send(self, decisions: list[Decision], risk: float | None, factors: list | None,
                   actor: str = "cascadeshield") -> None:
        for d in decisions:
            try:
                await self.api.decision(d.action, d.value, d.reason, risk, factors, actor)
            except httpx.HTTPError as e:  # control API down: write the key directly, still logged
                log.warning("control API failed (%s); writing Redis directly", e)
                await self.actuator.apply(d.action, d.value, d.reason, risk, {"factors": factors}, actor)
            log.info("%s -> %s (%s)", d.action, d.value, d.reason)

    async def run_calendar(self) -> list[str]:
        sent = []
        if self.ops.kill_switch:
            return sent
        for due in self.calendar.due(datetime.now().astimezone()):
            e = due.exam
            try:
                if due.step == "prewarm":
                    await self.api.post("/control/prewarm", {"course": e.course, "topics": e.topics,
                                                             "actor": "calendar", "reason": f"exam {e.id} in {e.prewarm_min:g} min"})
                elif due.step == "start":
                    floor = 1 if e.expected_students > CAPACITY_USERS else 0
                    await self.api.post("/control/exam", {"active": True, "course": e.course,
                                                          "ends_at": e.end.isoformat(), "floor": floor,
                                                          "actor": "calendar", "reason": f"exam {e.id} starts"})
                else:
                    await self.api.post("/control/exam", {"active": False, "actor": "calendar",
                                                          "reason": f"exam {e.id} ended"})
                self.calendar.mark(due)
                sent.append(f"{due.step} {e.id}")
            except httpx.HTTPStatusError as e_:
                if e_.response.status_code == 409:  # a pre-warm is already running: fine
                    self.calendar.mark(due)
                else:
                    log.warning("calendar %s %s failed: %s", due.step, e.id, e_.response.text)
            except httpx.HTTPError as e_:
                log.warning("calendar %s %s failed: %s", due.step, e.id, e_)
        return sent

    async def cycle(self) -> None:
        now = time.time()
        calendar_sent = await self.run_calendar()
        try:
            series = await self.collector.range_frame(WINDOW_S)
        except TelemetryError as e:
            # No fresh data: no heartbeat, so the Mac's local breaker takes over.
            CYCLES.labels("no_telemetry").inc()
            self.snapshot = {**self.snapshot, "ts": now, "healthy": False, "error": f"telemetry: {e}"}
            log.warning("no telemetry: %s", e)
            return

        latest = series.sort_values("t").groupby("service").tail(1).set_index("service")
        telemetry = {s: {k: (None if v != v else float(v)) for k, v in row.items() if k != "t"}
                     for s, row in latest.iterrows()}
        platform = await self.api.state()
        exam = (platform or {}).get("exam") or {}
        own, details = self.own_risks(series, telemetry, float(bool(exam.get("active"))))
        known = {s: r for s, r in own.items() if r is not None}
        cascade = dg.cascade_risk(known, weight_scale=1.0 if self.ops.graph_enabled else 0.0)
        blast = dg.blast_radius(known)
        for s, r in known.items():
            RISK.labels(s).set(r)
        for s, r in cascade.items():
            CASCADE.labels(s).set(r)

        R = cascade[CONTAINED] if own.get(CONTAINED) is not None else None
        factors = details.get(CONTAINED, {}).get("factors", [])
        requested = (platform or {}).get("requested") or {}
        if self.shadow is None or not self.ops.dry_run:
            self.shadow = {"level": int(requested.get("level") or 0),
                           "breaker": requested.get("breaker") or "closed"}
        self.engine.cfg.threshold = self.threshold
        self.engine.cfg.ladder = self.ops.ladder
        decisions: list[Decision] = []
        if not self.ops.kill_switch:
            obs = Observation(now, R, self.shadow["level"], self.shadow["breaker"],
                              queue_growth_per_s=queue_growth(series),
                              demand=(telemetry.get("gateway") or {}).get("sessions_active"),
                              admission_limit=(platform or {}).get("admission_limit"))
            decisions = self.engine.decide(obs)
            await self.act(decisions, R, factors)
            await self.actuator.heartbeat()
        await self.actuator.write_risk(known, {s: d.get("factors", []) for s, d in details.items()
                                               if d.get("factors")})

        llm = telemetry.get(CONTAINED) or {}
        self.history.append({
            "t": now, "risk": own.get(CONTAINED), "cascade": R, "threshold": self.threshold,
            "p95_slo": (llm.get("p95_s") or 0) / settings.slo_s[CONTAINED],
            "level": (platform or {}).get("level"), "breaker": (platform or {}).get("breaker"),
            "decisions": [f"{d.action}={d.value}" for d in decisions],
        })
        self.snapshot = {
            "ts": now, "healthy": True, "error": None,
            "controller": self.controller, "model": self.predictor.bundle.name if self.predictor else None,
            "model_error": self.model_error, "contained_service": CONTAINED,
            "threshold": self.threshold, "risk": own, "cascade": cascade, "blast": blast,
            "edges": dg.edges(),
            "predictions": details, "factors": factors,
            "ttf_s": details.get(CONTAINED, {}).get("ttf_s"),
            "telemetry": telemetry, "slo_s": settings.slo_s, "platform": platform,
            "ops": self.ops.model_dump(), "pending": self.pending, "shadow": self.shadow if self.ops.dry_run else None,
            "decisions": [d.__dict__ for d in decisions],
            "calendar": self.calendar.upcoming(datetime.now().astimezone()), "calendar_sent": calendar_sent,
        }
        CYCLES.labels("ok").inc()

    async def run(self) -> None:
        log.info("starting loop every %.1fs, controller %s, model %s", settings.loop_s, self.controller,
                 self.predictor.bundle.name if self.predictor else None)
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
    core = Core(Collector(settings.prometheus_url, http), RedisActuator(r),
                ControlAPI(settings.control_api, settings.cs_token, http))
    task = asyncio.create_task(core.run())
    yield
    task.cancel()
    await http.aclose()
    await r.aclose()


app = FastAPI(title="CascadeShield resilience core", lifespan=lifespan)


def require_token(x_cs_token: str | None = Header(None)) -> None:
    if x_cs_token != settings.cs_token:
        raise HTTPException(401, "bad X-CS-Token")


@app.get("/state")
async def state() -> dict:
    return core.snapshot if core else {"healthy": False, "error": "starting"}


@app.get("/history")
async def history() -> list[dict]:
    return list(core.history) if core else []


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


class OpsUpdate(BaseModel):
    dry_run: bool | None = None
    approval: bool | None = None
    kill_switch: bool | None = None
    controller: str | None = None
    graph_enabled: bool | None = None
    ladder: str | None = None


@app.post("/ops/settings", dependencies=[Depends(require_token)])
async def ops_settings(b: OpsUpdate) -> dict:
    if b.controller is not None and b.controller not in CONTROLLERS:
        raise HTTPException(422, f"controller must be one of {CONTROLLERS}")
    if b.ladder is not None and b.ladder not in ("full", "binary"):
        raise HTTPException(422, "ladder must be full or binary")
    changes = b.model_dump(exclude_none=True)
    before = core.ops.model_dump()
    core.ops = core.ops.model_copy(update=changes)
    for k, v in changes.items():
        if before[k] != v:
            await core.actuator.log_action(k, str(v), f"operator set {k}={v}", actor="operator")
    if changes.get("kill_switch"):
        # Stop advising at once: drop the heartbeat so the Mac's failsafe takes over now, not in 10 s.
        await core.actuator.stop_heartbeat()
        core.pending = None
    if "dry_run" in changes or "controller" in changes or "ladder" in changes:
        core.shadow = None
        core.engine = ContainmentEngine(EngineConfig(threshold=core.threshold))
    return core.ops.model_dump()


@app.post("/ops/pending/{verdict}", dependencies=[Depends(require_token)])
async def ops_pending(verdict: str) -> dict:
    if verdict not in ("approve", "reject"):
        raise HTTPException(404)
    p = core.pending
    if not p:
        raise HTTPException(409, "nothing pending")
    core.pending = None
    if verdict == "approve":
        await core.send([Decision(**d) for d in p["decisions"]], p["risk"], p["factors"], actor="cascadeshield+operator")
    else:
        await core.actuator.log_action("rejected", ",".join(f"{d['action']}={d['value']}" for d in p["decisions"]),
                                       "operator rejected the proposed action", p["risk"], actor="operator")
    return {"ok": True, "verdict": verdict}


class ScheduleExam(BaseModel):
    course: str = "DSA101"
    in_minutes: float = 2
    duration_min: float = 15
    expected_students: int = 120
    topics: list[str] = ["bst", "heaps"]
    prewarm_min: float = 1.5  # demo: pre-warm starts right away instead of 10 min before


@app.post("/ops/exam", dependencies=[Depends(require_token)])
async def ops_exam(b: ScheduleExam) -> dict:
    now = datetime.now().astimezone()
    exam = Exam(course=b.course, start=now + timedelta(minutes=b.in_minutes), duration_min=b.duration_min,
                expected_students=b.expected_students, topics=b.topics, prewarm_min=b.prewarm_min)
    core.calendar.add(exam, now)
    await core.actuator.log_action("schedule_exam", exam.id, f"operator scheduled {b.course} in {b.in_minutes:g} min",
                                   actor="operator")
    return {"ok": True, "exam": exam.id}


@app.post("/ops/reload-model", dependencies=[Depends(require_token)])
async def ops_reload_model() -> dict:
    core.load_model()
    return {"model": core.predictor.bundle.name if core.predictor else None, "error": core.model_error}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run(app, host="0.0.0.0", port=settings.core_port, log_level="warning")
