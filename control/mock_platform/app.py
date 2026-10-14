"""Mock CascadeShield platform for developing the control room on Fedora.

One module, five roles (CS_SERVICE=gateway|student|orchestrator|curriculum_rag|llm_inference),
following contracts/ closely enough that the control room cannot tell the difference.
The LLM is a queueing simulator: a fixed aggregate token rate shared by the busy slots.
Delete this once the Mac's real services run here with LLM_BACKEND=mock.

Run all five: uv run python -m mock_platform.run_all
"""

import asyncio
import json
import os
import random
import time
from collections import deque

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from resilience_core.settings import SERVICE_PORTS, settings

SERVICE = os.environ.get("CS_SERVICE", "gateway")
PROTECTION_MODE = os.environ.get("PROTECTION_MODE", "cascadeshield")  # none | reactive | cascadeshield
CHAOS_ENABLED = os.environ.get("CHAOS_ENABLED", "1") == "1"
LLM_SLOTS = int(os.environ.get("MOCK_LLM_SLOTS", "4"))
LLM_TPS_TOTAL = float(os.environ.get("MOCK_LLM_TPS", "160"))  # aggregate tokens/s across slots
LLM_TIMEOUT_S = float(os.environ.get("MOCK_LLM_TIMEOUT_S", "30"))
LLM_MODEL = os.environ.get("MOCK_LLM_MODEL", "mock-qwen2.5:0.5b")
GATEWAY_MAX_TUTOR_INFLIGHT = int(os.environ.get("MOCK_GATEWAY_MAX_INFLIGHT", "500"))
LLM_SLO_S = settings.slo_s["llm_inference"]

URL = {s: f"http://127.0.0.1:{p}" for s, p in SERVICE_PORTS.items()}
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 12, 15, 20, 30)
LEVEL_TOKENS = {0: 256, 1: 80}
LEVEL_CHUNKS = {0: 3, 1: 1}
BANNERS = {
    0: "",
    1: "High demand: tutor answers are shorter for now.",
    2: "High demand: answers come from your course notes.",
    3: "Very high demand: you'll get guided hints.",
    4: "Very high demand: your question is saved and queued.",
}

app = FastAPI(title=f"mock {SERVICE}")
rng = random.Random()

# --- shared HTTP metrics --------------------------------------------------------------

REQS = Counter("cs_http_requests_total", "Requests", ["service", "route", "status"])
DUR = Histogram("cs_http_request_duration_seconds", "Latency", ["service", "route"], buckets=BUCKETS)
INFLIGHT = Gauge("cs_inflight_requests", "In-flight requests", ["service"])
INFLIGHT.labels(SERVICE)
SKIP_ROUTES = {"/metrics", "/health"}


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path in SKIP_ROUTES:
        return await call_next(request)
    INFLIGHT.labels(SERVICE).inc()
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "unmatched")
        DUR.labels(SERVICE, route).observe(time.perf_counter() - start)
        REQS.labels(SERVICE, route, str(status)).inc()
        INFLIGHT.labels(SERVICE).dec()


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"ok": True, "service": SERVICE}


def check_token(token: str | None):
    if token != settings.cs_token:
        raise HTTPException(401, "bad X-CS-Token")


http = httpx.AsyncClient(limits=httpx.Limits(max_connections=2000, max_keepalive_connections=200))
rds = aioredis.Redis(host=settings.redis_host, port=settings.redis_port,
                     password=settings.redis_password, decode_responses=True)


async def log_action(actor: str, action: str, value, reason: str, extra: dict | None = None):
    fields = {"ts": f"{time.time():.3f}", "actor": actor, "action": action,
              "value": str(value), "reason": reason}
    if extra:
        fields["extra"] = json.dumps(extra)
    await rds.xadd("cs:actions", fields, maxlen=10_000, approximate=True)


# --- chaos (llm_inference, curriculum_rag) ---------------------------------------------

class Chaos:
    def __init__(self):
        self.clear()

    def clear(self):
        self.extra_ms, self.latency_until = 0.0, 0.0
        self.error_rate, self.errors_until = 0.0, 0.0
        self.leak: list[bytearray] = []
        self.leak_task: asyncio.Task | None = None

    @property
    def leaked_mb(self) -> float:
        return sum(len(b) for b in self.leak) / 1e6

    def extra_s(self) -> float:
        return self.extra_ms / 1000 if time.time() < self.latency_until else 0.0

    def should_fail(self) -> bool:
        return time.time() < self.errors_until and rng.random() < self.error_rate

    async def _leak(self, mb_per_s: float, seconds: float):
        for _ in range(int(seconds)):
            self.leak.append(bytearray(b"x") * int(mb_per_s * 1e6))
            await asyncio.sleep(1)


chaos = Chaos()


class LatencyBody(BaseModel):
    extra_ms: float
    seconds: float


class LeakBody(BaseModel):
    mb_per_s: float
    seconds: float


class ErrorsBody(BaseModel):
    rate: float
    seconds: float


def add_chaos_routes():
    def guard(token):
        if not CHAOS_ENABLED:
            raise HTTPException(404)
        check_token(token)

    @app.post("/chaos/latency")
    async def chaos_latency(b: LatencyBody, x_cs_token: str | None = Header(None)):
        guard(x_cs_token)
        chaos.extra_ms, chaos.latency_until = b.extra_ms, time.time() + b.seconds
        return {"ok": True}

    @app.post("/chaos/leak")
    async def chaos_leak(b: LeakBody, x_cs_token: str | None = Header(None)):
        guard(x_cs_token)
        chaos.leak_task = asyncio.create_task(chaos._leak(b.mb_per_s, b.seconds))
        return {"ok": True}

    @app.post("/chaos/errors")
    async def chaos_errors(b: ErrorsBody, x_cs_token: str | None = Header(None)):
        guard(x_cs_token)
        chaos.error_rate, chaos.errors_until = b.rate, time.time() + b.seconds
        return {"ok": True}

    @app.post("/chaos/clear")
    async def chaos_clear(x_cs_token: str | None = Header(None)):
        guard(x_cs_token)
        if chaos.leak_task:
            chaos.leak_task.cancel()
        chaos.clear()
        return {"ok": True}


# --- llm_inference ------------------------------------------------------------------------

if SERVICE == "llm_inference":
    QDEPTH = Gauge("cs_llm_queue_depth", "Waiting for a slot", ["service"])
    QWAIT = Histogram("cs_llm_queue_wait_seconds", "Slot wait", ["service"], buckets=BUCKETS)
    TOKENS = Counter("cs_llm_tokens_generated_total", "Tokens generated", ["service"])
    TPS = Gauge("cs_llm_tokens_per_second", "Tokens/s, last 10 s", ["service"])
    PROMPT = Histogram("cs_llm_prompt_tokens", "Prompt tokens", ["service"],
                       buckets=(32, 64, 128, 256, 512, 1024, 2048))
    TIMEOUTS = Counter("cs_llm_timeouts_total", "Generation timeouts", ["service"])
    MODEL = Gauge("cs_llm_model_info", "Model in use", ["service", "model"])
    MODEL.labels(SERVICE, LLM_MODEL).set(1)
    QDEPTH.labels(SERVICE).set(0)
    TPS.labels(SERVICE).set(LLM_TPS_TOTAL / LLM_SLOTS)
    TIMEOUTS.labels(SERVICE)

    slots = asyncio.Semaphore(LLM_SLOTS)
    llm = {"waiting": 0, "active": 0}
    recent: deque[tuple[float, int, float]] = deque()  # (finished_at, tokens, gen_seconds)

    def slot_rate() -> float:
        """Per-slot tokens/s: aggregate rate shared by active slots, with mild contention loss,
        slowed further by leaked memory."""
        active = max(1, llm["active"])
        aggregate = LLM_TPS_TOTAL * max(0.5, 1 - 0.05 * (active - 1))
        return aggregate / active / (1 + chaos.leaked_mb / 200)

    def update_tps():
        cutoff = time.time() - 10
        while recent and recent[0][0] < cutoff:
            recent.popleft()
        if recent:
            TPS.labels(SERVICE).set(sum(r[1] for r in recent) / max(1e-6, sum(r[2] for r in recent)))

    class GenerateBody(BaseModel):
        prompt: str
        max_tokens: int = 256

    @app.post("/generate")
    async def generate(b: GenerateBody):
        if chaos.should_fail():
            raise HTTPException(500, "chaos error")
        start = time.monotonic()
        llm["waiting"] += 1
        QDEPTH.labels(SERVICE).set(llm["waiting"])
        try:
            await asyncio.wait_for(slots.acquire(), timeout=LLM_TIMEOUT_S)
        except TimeoutError:
            TIMEOUTS.labels(SERVICE).inc()
            raise HTTPException(504, "timed out waiting for a slot")
        finally:
            llm["waiting"] -= 1
            QDEPTH.labels(SERVICE).set(llm["waiting"])
        QWAIT.labels(SERVICE).observe(time.monotonic() - start)

        llm["active"] += 1
        try:
            prompt_tokens = int(len(b.prompt.split()) * 1.3) + 40
            PROMPT.labels(SERVICE).observe(prompt_tokens)
            target = rng.randint(int(0.6 * b.max_tokens), b.max_tokens)
            await asyncio.sleep(prompt_tokens / 800 + chaos.extra_s())
            gen_start, produced, step = time.monotonic(), 0.0, 0.2
            while produced < target:
                if time.monotonic() - start > LLM_TIMEOUT_S:
                    TIMEOUTS.labels(SERVICE).inc()
                    raise HTTPException(504, "generation timed out")
                await asyncio.sleep(step)
                produced += slot_rate() * step
            gen_s = time.monotonic() - gen_start
            TOKENS.labels(SERVICE).inc(target)
            recent.append((time.time(), target, gen_s))
            update_tps()
            return {"text": f"[{LLM_MODEL}] Let's think about it step by step...",
                    "eval_count": target, "prompt_eval_count": prompt_tokens}
        finally:
            llm["active"] -= 1
            slots.release()

    @app.post("/admin/reset")
    async def llm_reset(x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        if chaos.leak_task:
            chaos.leak_task.cancel()
        chaos.clear()
        recent.clear()
        return {"ok": True}

    add_chaos_routes()


# --- curriculum_rag -------------------------------------------------------------------------

if SERVICE == "curriculum_rag":
    RAGQ = Histogram("cs_rag_query_seconds", "Retrieval time", ["service"], buckets=BUCKETS)
    HITS = Counter("cs_cache_hits_total", "Semantic cache hits", ["service"])
    MISSES = Counter("cs_cache_misses_total", "Semantic cache misses", ["service"])
    HITS.labels(SERVICE)
    MISSES.labels(SERVICE)

    class RetrieveBody(BaseModel):
        question: str
        k: int = 3

    async def _search(k: int) -> float:
        if chaos.should_fail():
            raise HTTPException(500, "chaos error")
        t = 0.015 * k + rng.uniform(0, 0.02) + chaos.extra_s()
        await asyncio.sleep(t)
        RAGQ.labels(SERVICE).observe(t)
        return t

    @app.post("/retrieve")
    async def retrieve(b: RetrieveBody):
        await _search(b.k)
        return {"chunks": [f"syllabus passage {i}" for i in range(b.k)]}

    @app.post("/fallback")
    async def fallback(b: RetrieveBody):
        await _search(1)
        if rng.random() < 0.4:
            HITS.labels(SERVICE).inc()
            return {"answer": "Cached answer: what invariant must hold here?", "source": "cache"}
        MISSES.labels(SERVICE).inc()
        return {"answer": "From your notes: ... Which step would you try first?", "source": "rag"}

    @app.post("/admin/reset")
    async def rag_reset(x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        if chaos.leak_task:
            chaos.leak_task.cancel()
        chaos.clear()
        return {"ok": True}

    add_chaos_routes()


# --- student --------------------------------------------------------------------------------

if SERVICE == "student":
    SUBS = Counter("cs_submissions_total", "Quiz submits", ["service", "status"])
    for s in ("committed", "duplicate", "failed"):
        SUBS.labels(SERVICE, s)
    seen_keys: set[str] = set()

    class SubmitBody(BaseModel):
        student_id: str
        quiz_id: str
        answers: dict | list
        idempotency_key: str

    @app.post("/quiz/submit", status_code=202)
    async def submit(b: SubmitBody):
        await asyncio.sleep(rng.uniform(0.005, 0.02))
        if b.idempotency_key in seen_keys:
            SUBS.labels(SERVICE, "duplicate").inc()
            return {"status": "duplicate"}
        seen_keys.add(b.idempotency_key)
        SUBS.labels(SERVICE, "committed").inc()
        return {"status": "committed"}

    @app.get("/profile/{student_id}")
    async def profile(student_id: str):
        await asyncio.sleep(rng.uniform(0.002, 0.01))
        return {"student_id": student_id, "level": "beginner", "history": []}

    @app.get("/admin/stats")
    async def stats():
        return {"committed": len(seen_keys)}


# --- orchestrator ---------------------------------------------------------------------------

if SERVICE == "orchestrator":
    ACTIVE = Gauge("cs_orch_active_prompts", "Tutor requests in progress", ["service"])
    LEVEL = Gauge("cs_orch_degradation_level", "0-4", ["service"])
    BREAKER = Gauge("cs_orch_breaker_state", "0 closed, 1 half-open, 2 open", ["service"])
    RESP = Counter("cs_orch_responses_total", "Answers", ["service", "level", "source"])
    ACTIVE.labels(SERVICE).set(0)
    LEVEL.labels(SERVICE).set(0)
    BREAKER.labels(SERVICE).set(0)
    BREAKER_CODE = {"closed": 0, "half_open": 1, "open": 2}

    class LocalBreaker:
        """Failsafe used when the control heartbeat is missing (and in reactive mode)."""

        def __init__(self):
            self.state, self.failures, self.opened_at = "closed", 0, 0.0

        def current(self) -> str:
            if self.state == "open" and time.time() - self.opened_at > 30:
                self.state = "half_open"
            return self.state

        def record(self, ok: bool):
            if ok:
                self.failures = 0
                if self.state == "half_open":
                    self.state = "closed"
            else:
                self.failures += 1
                if self.failures >= 5 or self.state == "half_open":
                    self.state, self.opened_at = "open", time.time()

    local = LocalBreaker()
    orch = {"source": None, "queue": 0}

    async def effective_control() -> tuple[int, str, str]:
        """(level, breaker, source). source: remote | local | none."""
        if PROTECTION_MODE == "none":
            level, breaker, source = 0, "closed", "none"
        else:
            hb, lvl, brk = await rds.mget("cs:control:heartbeat", "cs:mode:level", "cs:breaker:llm")
            if hb and PROTECTION_MODE == "cascadeshield":
                level, breaker, source = int(lvl or 0), brk or "closed", "remote"
            else:
                breaker, source = local.current(), "local"
                level = 3 if breaker == "open" else 0
        if source != orch["source"]:
            if orch["source"] is not None:
                await log_action("failsafe" if source == "local" else "platform", "control_source",
                                 source, f"control source {orch['source']} -> {source}")
            orch["source"] = source
        LEVEL.labels(SERVICE).set(level)
        BREAKER.labels(SERVICE).set(BREAKER_CODE.get(breaker, 0))
        return level, breaker, source

    class AskBody(BaseModel):
        student_id: str
        session_id: str
        course: str
        question: str

    async def no_llm_answer(level: int, b: AskBody) -> tuple[str, str, int]:
        if level <= 2:
            r = await http.post(f"{URL['curriculum_rag']}/fallback",
                                json={"question": b.question, "k": 1}, timeout=5)
            r.raise_for_status()
            d = r.json()
            return d["answer"], d["source"], 2
        if level == 3:
            return "Hint: start from the definition. What must stay true after each step?", "hint", 3
        orch["queue"] += 1
        return f"Your question is saved. You are number {orch['queue']} in the queue.", "queued", 4

    @app.post("/tutor")
    async def tutor(b: AskBody):
        ACTIVE.labels(SERVICE).inc()
        try:
            level, breaker, source = await effective_control()
            use_llm = level <= 1 and (breaker == "closed" or (breaker == "half_open" and rng.random() < 0.2))
            if use_llm:
                try:
                    try:
                        await http.get(f"{URL['student']}/profile/{b.student_id}", timeout=1)
                    except httpx.HTTPError:
                        pass  # profile has a default fallback
                    await http.post(f"{URL['curriculum_rag']}/retrieve",
                                    json={"question": b.question, "k": LEVEL_CHUNKS[level]}, timeout=5)
                    t0 = time.monotonic()
                    r = await http.post(f"{URL['llm_inference']}/generate",
                                        json={"prompt": b.question, "max_tokens": LEVEL_TOKENS[level]},
                                        timeout=LLM_TIMEOUT_S + 5)
                    r.raise_for_status()
                    local.record(time.monotonic() - t0 <= LLM_SLO_S)
                    RESP.labels(SERVICE, str(level), "llm").inc()
                    return {"answer": r.json()["text"], "level": level, "source": "llm"}
                except httpx.HTTPError:
                    local.record(False)
                    if PROTECTION_MODE == "none":
                        raise HTTPException(504, "LLM unavailable")
                    level = 2  # graceful fallback without the LLM
            answer, src, served = await no_llm_answer(level, b)
            RESP.labels(SERVICE, str(served), src).inc()
            return {"answer": answer, "level": served, "source": src}
        finally:
            ACTIVE.labels(SERVICE).dec()

    @app.get("/control/state")
    async def control_state(x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        level, breaker, source = await effective_control()
        hb, exam = await rds.mget("cs:control:heartbeat", "cs:mode:exam")
        return {"level": level, "breaker": breaker,
                "exam": json.loads(exam) if exam else {"active": False},
                "heartbeat_age_s": round(time.time() - float(hb), 2) if hb else None,
                "protection_mode": PROTECTION_MODE, "control_source": source}

    class ModeBody(BaseModel):
        level: int
        reason: str = ""
        actor: str = "operator"

    @app.post("/control/mode")
    async def control_mode(b: ModeBody, x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        if not 0 <= b.level <= 4:
            raise HTTPException(422, "level must be 0-4")
        await rds.set("cs:mode:level", b.level)
        await log_action(b.actor, "set_level", b.level, b.reason)
        return {"ok": True}

    class BreakerBody(BaseModel):
        state: str
        reason: str = ""
        actor: str = "operator"

    @app.post("/control/breaker")
    async def control_breaker(b: BreakerBody, x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        if b.state not in BREAKER_CODE:
            raise HTTPException(422, "state must be closed|half_open|open")
        await rds.set("cs:breaker:llm", b.state)
        await log_action(b.actor, "set_breaker", b.state, b.reason)
        return {"ok": True}

    class ExamBody(BaseModel):
        active: bool
        course: str | None = None
        ends_at: str | None = None
        actor: str = "operator"

    @app.post("/control/exam")
    async def control_exam(b: ExamBody, x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        await rds.set("cs:mode:exam", json.dumps(b.model_dump(exclude={"actor"})))
        await log_action(b.actor, "set_exam", b.active, f"exam {b.course or ''}")
        return {"ok": True}

    class PrewarmBody(BaseModel):
        course: str
        topics: list[str]
        actor: str = "operator"

    @app.post("/control/prewarm")
    async def control_prewarm(b: PrewarmBody, x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        await log_action(b.actor, "prewarm", ",".join(b.topics), f"prewarm {b.course}")
        return {"ok": True, "queued": len(b.topics)}

    @app.post("/admin/reset")
    async def admin_reset(x_cs_token: str | None = Header(None)):
        check_token(x_cs_token)
        global local
        local = LocalBreaker()
        orch["queue"] = 0
        await rds.mset({"cs:mode:level": 0, "cs:breaker:llm": "closed"})
        hdr = {"X-CS-Token": settings.cs_token}
        for svc in ("llm_inference", "curriculum_rag"):
            try:
                await http.post(f"{URL[svc]}/admin/reset", headers=hdr, timeout=2)
            except httpx.HTTPError:
                pass
        await log_action("operator", "reset", "all", "episode reset")
        return {"ok": True}


# --- gateway --------------------------------------------------------------------------------

if SERVICE == "gateway":
    SESSIONS = Gauge("cs_sessions_active", "Sessions seen in the last 60 s", ["service"])
    SHED = Counter("cs_shed_requests_total", "Shed by admission control", ["service", "priority"])
    SESSIONS.labels(SERVICE).set(0)
    SHED.labels(SERVICE, "tutor")
    sessions: dict[str, float] = {}
    gw = {"tutor_inflight": 0}

    def touch_session(sid: str):
        now = time.time()
        sessions[sid] = now
        for k in [k for k, t in sessions.items() if now - t > 60]:
            del sessions[k]
        SESSIONS.labels(SERVICE).set(len(sessions))

    class AskBody(BaseModel):
        student_id: str
        session_id: str
        course: str
        question: str

    @app.post("/api/tutor/ask")
    async def ask(b: AskBody):
        touch_session(b.session_id)
        if gw["tutor_inflight"] >= GATEWAY_MAX_TUTOR_INFLIGHT:
            SHED.labels(SERVICE, "tutor").inc()
            raise HTTPException(503, "busy, try again shortly")
        gw["tutor_inflight"] += 1
        t0 = time.perf_counter()
        try:
            r = await http.post(f"{URL['orchestrator']}/tutor", json=b.model_dump(),
                                timeout=LLM_TIMEOUT_S + 10)
        except httpx.HTTPError:
            raise HTTPException(504, "tutor unavailable")
        finally:
            gw["tutor_inflight"] -= 1
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return {**r.json(), "latency_ms": round((time.perf_counter() - t0) * 1000)}

    class SubmitBody(BaseModel):
        student_id: str
        quiz_id: str
        answers: dict | list
        idempotency_key: str

    @app.post("/api/quiz/submit", status_code=202)
    async def quiz(b: SubmitBody):
        touch_session(b.student_id)
        try:
            r = await http.post(f"{URL['student']}/quiz/submit", json=b.model_dump(), timeout=10)
            r.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(503, "submit failed, retry with the same idempotency_key")
        return {"status": "committed"}

    @app.get("/api/status")
    async def status():
        try:
            r = await http.get(f"{URL['orchestrator']}/control/state",
                               headers={"X-CS-Token": settings.cs_token}, timeout=2)
            level = r.json()["level"]
        except (httpx.HTTPError, KeyError, ValueError):
            level = 0
        return {"level": level, "banner": BANNERS.get(level, "")}
