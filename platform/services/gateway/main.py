"""gateway_service (port 8000): public API and student page. Quiz submits go straight to
student_service on their own small pool, never through the orchestrator (session preservation)."""

import time
import uuid

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import Counter, Gauge
from pydantic import BaseModel

from cs_common import create_app, settings
from cs_common.logging import make_client
from cs_common.metrics import metric
from cs_common.redis_client import rds
from cs_common.settings import PLATFORM_DIR

SESSIONS = metric(Gauge, "cs_sessions_active", "Distinct sessions seen in the last 60 s")
SHED = metric(Counter, "cs_shed_requests_total", "Requests rejected or queued by admission control", ("priority",))
for p in ("P0", "P1"):
    SHED(p)

BANNERS = {
    0: ("green", "Tutor running normally"),
    1: ("amber", "Tutor in light mode: answers are shorter"),
    2: ("blue", "High demand: showing course notes and hints. Your quiz is safe."),
    3: ("blue", "High demand: showing course notes and hints. Your quiz is safe."),
    4: ("blue", "Very high demand: your question is saved in a queue. Your quiz is safe."),
}

app = create_app()
tutor_http = make_client(settings.llm_timeout_s + 5, max_connections=200)
quiz_http = make_client(settings.quiz_timeout_s, max_connections=20)  # separate pool (guide 5.4)
sessions: dict[str, float] = {}


def touch_session(sid: str) -> None:
    now = time.time()
    sessions[sid] = now
    if len(sessions) % 50 == 0 or now - min(sessions.values(), default=now) > 60:
        for k in [k for k, t in sessions.items() if now - t > 60]:
            del sessions[k]
    SESSIONS.set(len(sessions))


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
    try:
        r = await tutor_http.post(f"{settings.orchestrator_url}/tutor/ask", json=b.model_dump())
    except httpx.HTTPError:
        raise HTTPException(504, "tutor unavailable")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("detail", r.text) if r.content else "")
    d = r.json()
    return {"answer": d["answer"], "level": d["level"], "source": d["source"],
            "latency_ms": round((time.perf_counter() - t0) * 1000), "session_id": b.session_id}


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
    return {"level": level, "banner": banner, "color": color}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(PLATFORM_DIR / "web" / "index.html")
