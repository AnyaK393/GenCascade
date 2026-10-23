"""gateway_service (port 8000): public API and student page. Quiz submits (P0) go straight to
student_service on their own small pool, never through the orchestrator (session preservation).
During an exam, tutoring (P1) passes an AIMD concurrency limiter (guide 6.1)."""

import asyncio
import json
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import Counter, Gauge
from pydantic import BaseModel

from cs_common import create_app, settings
from cs_common.logging import make_client
from cs_common.metrics import metric
from cs_common.redis_client import ADMISSION, EXAM, active_exam, log_action, rds
from cs_common.settings import PLATFORM_DIR

SESSIONS = metric(Gauge, "cs_sessions_active", "Distinct sessions seen in the last 60 s")
SHED = metric(Counter, "cs_shed_requests_total", "Requests rejected or queued by admission control", ("priority",))
for p in ("P0", "P1"):
    SHED(p)
LIMIT = metric(Gauge, "cs_admission_limit", "Current adaptive concurrency limit for tutoring requests")

BANNERS = {
    0: ("green", "Tutor running normally"),
    1: ("amber", "Tutor in light mode: answers are shorter"),
    2: ("blue", "High demand: showing course notes and hints. Your quiz is safe."),
    3: ("blue", "High demand: showing course notes and hints. Your quiz is safe."),
    4: ("blue", "Very high demand: your question is saved in a queue. Your quiz is safe."),
}

class AIMD:
    """Additive increase, multiplicative decrease, like TCP: every 5 s +1 while tutor p95 is under
    target; halve on an LLM timeout (at most once per 2 s, so one burst of timeouts halves once)."""

    def __init__(self):
        self.limit, self.inflight, self.halved_at = settings.admission_start, 0, 0.0
        self.lat: deque[tuple[float, float]] = deque()  # (finished_at, seconds) of admitted requests
        self.cond = asyncio.Condition()
        LIMIT.set(self.limit)

    async def acquire(self) -> bool:
        async with self.cond:
            try:
                await asyncio.wait_for(self.cond.wait_for(lambda: self.inflight < self.limit),
                                       settings.admission_wait_s)
            except TimeoutError:
                return False
            self.inflight += 1
            return True

    async def release(self, seconds: float, llm_timeout: bool) -> None:
        now = time.time()
        self.lat.append((now, seconds))
        if llm_timeout and now - self.halved_at > 2:
            self.halved_at = now
            await self.set(max(1, self.limit // 2), "LLM timeout")
        async with self.cond:
            self.inflight -= 1
            self.cond.notify_all()

    def p95(self) -> float | None:
        cutoff = time.time() - 5
        while self.lat and self.lat[0][0] < cutoff:
            self.lat.popleft()
        xs = sorted(x for _, x in self.lat)
        return xs[int(0.95 * (len(xs) - 1))] if xs else None

    async def tick(self) -> None:
        p95 = self.p95()
        if p95 is not None and p95 < settings.admission_target_s and self.limit < settings.admission_max:
            await self.set(self.limit + 1, f"tutor p95 {p95:.1f} s < {settings.admission_target_s:.0f} s")
        try:
            await rds.set(ADMISSION, self.limit, ex=30)
        except Exception:
            pass

    async def set(self, limit: int, reason: str) -> None:
        self.limit = limit
        LIMIT.set(limit)
        async with self.cond:
            self.cond.notify_all()
        await log_action("platform", "admission_limit", limit, reason)

    def reset(self) -> None:
        self.limit, self.halved_at = settings.admission_start, 0.0
        self.lat.clear()
        LIMIT.set(self.limit)


admission = AIMD()
exam_cache = {"at": 0.0, "exam": None}


async def current_exam() -> dict | None:
    """cs:mode:exam, read at most once a second (it changes rarely; every request needs it)."""
    if settings.protection_mode == "none":
        return None
    now = time.time()
    if now - exam_cache["at"] > 1:
        try:
            raw = await rds.get(EXAM)
            exam_cache["exam"] = json.loads(raw) if raw else None
        except Exception:
            pass
        exam_cache["at"] = now
    return active_exam(exam_cache["exam"])


async def aimd_loop() -> None:
    while True:
        await asyncio.sleep(5)
        try:
            if await current_exam():
                await admission.tick()
            elif admission.limit != settings.admission_start:
                admission.reset()  # each exam starts from the same limit
        except Exception:
            pass


async def sessions_loop() -> None:
    """Expire idle sessions even when no request arrives, so the gauge falls to 0 within 60 s of the
    last request (contracts/metrics.md); touch_session alone left it stuck after a rush."""
    while True:
        await asyncio.sleep(5)
        prune_sessions(time.time())


@asynccontextmanager
async def lifespan(_app):
    tasks = [asyncio.create_task(aimd_loop()), asyncio.create_task(sessions_loop())]
    yield
    for task in tasks:
        task.cancel()


app = create_app(lifespan=lifespan)
tutor_http = make_client(settings.llm_timeout_s + 5, max_connections=200)
quiz_http = make_client(settings.quiz_timeout_s, max_connections=20)  # separate pool (guide 5.4)
sessions: dict[str, float] = {}


def prune_sessions(now: float) -> None:
    for k in [k for k, t in sessions.items() if now - t > 60]:
        del sessions[k]
    SESSIONS.set(len(sessions))


def touch_session(sid: str) -> None:
    sessions[sid] = time.time()
    SESSIONS.set(len(sessions))  # sessions_loop expires the idle ones every 5 s


async def allow(student_id: str) -> bool:
    """Per-student limit of rate_limit_per_min tutor questions per minute (cs:rl:<id>, TTL 60 s).
    If Redis is unavailable, let the request through."""
    try:
        key = f"cs:rl:{student_id}"
        async with rds.pipeline(transaction=True) as p:
            n, _ = await p.incr(key).expire(key, 60, nx=True).execute()
        return n <= settings.rate_limit_per_min
    except Exception:
        return True


class AskBody(BaseModel):
    student_id: str
    session_id: str | None = None
    course: str
    question: str


@app.post("/api/tutor/ask")
async def ask(b: AskBody):
    b.session_id = b.session_id or uuid.uuid4().hex
    touch_session(b.session_id)
    if not await allow(b.student_id):
        SHED("P1").inc()
        raise HTTPException(429, "Too many questions this minute, try again shortly")
    t0 = time.perf_counter()
    body = b.model_dump()
    admitted = False
    if await current_exam():
        admitted = await admission.acquire()
        if not admitted:  # over the limit for 3 s: level 4, the question is queued
            SHED("P1").inc()
            body["shed"] = True
    llm_timeout = False
    try:
        r = await tutor_http.post(f"{settings.orchestrator_url}/tutor/ask", json=body)
        llm_timeout = r.status_code < 400 and r.json().get("llm_error") == "timeout"
    except httpx.HTTPError as e:
        llm_timeout = isinstance(e, httpx.TimeoutException)
        raise HTTPException(504, "tutor unavailable")
    finally:
        if admitted:
            await admission.release(time.perf_counter() - t0, llm_timeout)
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("detail", r.text) if r.content else "")
    d = r.json()
    out = {"answer": d["answer"], "level": d["level"], "source": d["source"],
           "latency_ms": round((time.perf_counter() - t0) * 1000), "session_id": b.session_id}
    if "queue_id" in d:  # level 4: the page polls /api/tutor/queued/<id> for the real answer
        out.update(queue_id=d["queue_id"], position=d["position"])
    return out


@app.get("/api/tutor/queued/{qid}")
async def queued(qid: str):
    try:
        r = await tutor_http.get(f"{settings.orchestrator_url}/tutor/queued/{qid}", timeout=2)
    except httpx.HTTPError:
        raise HTTPException(504, "tutor unavailable")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("detail", "") if r.content else "")
    return r.json()


class SubmitBody(BaseModel):
    student_id: str
    quiz_id: str
    answers: dict | list
    idempotency_key: str


@app.post("/api/quiz/submit", status_code=202)
async def quiz_submit(b: SubmitBody):
    touch_session(b.student_id)
    try:
        r = await quiz_http.post(f"{settings.student_url}/submissions", json=b.model_dump())
        r.raise_for_status()
    except httpx.HTTPError:
        return JSONResponse({"status": "failed", "detail": "retry with the same idempotency_key"}, 503)
    return {"status": "committed", "duplicate": r.json()["status"] == "duplicate"}


@app.get("/api/status")
async def status():
    try:
        r = await tutor_http.get(f"{settings.orchestrator_url}/control/state",
                                 headers={"X-CS-Token": settings.cs_token}, timeout=1)
        level = int(r.json()["level"])
    except (httpx.HTTPError, KeyError, ValueError):
        level = 0
    color, banner = BANNERS.get(level, BANNERS[4])
    exam = await current_exam()
    return {"level": level, "banner": banner, "color": color,
            "exam": {"active": True, "course": exam["course"], "ends_at": exam.get("ends_at")} if exam else {"active": False}}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(PLATFORM_DIR / "web" / "index.html")
