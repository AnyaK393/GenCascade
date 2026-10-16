"""orchestrator_service (port 8002): builds Socratic tutor answers and serves the control API.

Control: in `cascadeshield` mode it follows Fedora's Redis keys while the heartbeat is fresh,
otherwise (and always in `reactive` mode) its own local breaker. `none` ignores all control.
Ladder (contracts/control_api.md): 0 full, 1 lean (LLM); 2 cache + RAG, 3 hint, 4 shed (no LLM).
"""

import asyncio
import logging
import random
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import yaml
from fastapi import Depends, HTTPException
from prometheus_client import Counter, Gauge
from pydantic import BaseModel

from cs_common import create_app, settings
from cs_common.logging import make_client
from cs_common.metrics import metric
from cs_common.redis_client import BREAKER, LEVEL, control_keys, log_action, rds, require_token

ACTIVE = metric(Gauge, "cs_orch_active_prompts", "Tutor requests in progress")
LEVEL_G = metric(Gauge, "cs_orch_degradation_level", "Effective degradation level 0-4")
BREAKER_G = metric(Gauge, "cs_orch_breaker_state", "0 closed, 1 half-open, 2 open")
RESP = metric(Counter, "cs_orch_responses_total", "Answers by level and source", ("level", "source"))
BREAKER_CODE = {"closed": 0, "half_open": 1, "open": 2}
LEVEL_TOKENS, LEVEL_CHUNKS = {0: 256, 1: 80}, {0: 3, 1: 1}
PM = settings.protection_mode
SHED_TTL_S = 6 * 3600

log = logging.getLogger("orchestrator")
http = make_client(settings.llm_timeout_s + 2, max_connections=200)
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "socratic.txt").read_text()
HINTS: dict = yaml.safe_load((settings.data_dir / "hints.yaml").read_text())
COURSES = [c for c in HINTS if not c.startswith("_")]
history: dict[str, deque] = defaultdict(lambda: deque(maxlen=4))


class LocalBreaker:
    """Opens after 5 LLM failures within 10 s; half-open after 20 s, where 5 good probes close
    it and 1 failure reopens it (guide 5.2)."""

    def __init__(self):
        self.state, self.opened_at, self.probes_ok = "closed", 0.0, 0
        self.failures: deque[float] = deque()

    def current(self) -> str:
        if self.state == "open" and time.time() - self.opened_at >= 20:
            self.state, self.probes_ok = "half_open", 0
        return self.state

    def record(self, ok: bool) -> None:
        now = time.time()
        if self.current() == "half_open":
            if not ok:
                self.state, self.opened_at = "open", now
            else:
                self.probes_ok += 1
                if self.probes_ok >= 5:
                    self.state = "closed"
                    self.failures.clear()
            return
        if ok:
            return
        self.failures.append(now)
        while self.failures and self.failures[0] < now - 10:
            self.failures.popleft()
        if len(self.failures) >= 5 and self.state == "closed":
            self.state, self.opened_at = "open", now


local = LocalBreaker()
ctl = {"source": None}


def exam_floor(_keys: dict) -> int:
    return 0  # Phase 3: minimum level during the exam window


async def control() -> dict:
    """Effective level = max(redis_level, local_level, exam_floor) and the effective breaker,
    plus where they came from (guide 5.1)."""
    keys = await control_keys()
    if PM == "none":
        level, breaker, source = 0, "closed", "none"
    else:
        breaker, source = local.current(), "local"
        level = 0
        age = keys["heartbeat_age"]
        if PM == "cascadeshield" and age is not None and age <= settings.heartbeat_stale_s:
            # Follow Fedora; the local breaker stays as a backup, so take the safer of the two.
            source = "remote"
            level = min(4, max(0, keys["level"] or 0))
            remote = keys["breaker"] if keys["breaker"] in BREAKER_CODE else "closed"
            breaker = max(breaker, remote, key=BREAKER_CODE.get)
        level = max(level, exam_floor(keys))
        if breaker == "open":
            level = max(level, 2)  # no LLM calls while open
    if source != ctl["source"]:
        if ctl["source"] is not None:
            actor = "failsafe" if source == "local" else "platform"
            await log_action(actor, "control_source", source, f"control source {ctl['source']} -> {source}")
            log.warning("control source %s -> %s", ctl["source"], source)
        ctl["source"] = source
    LEVEL_G.set(level)
    BREAKER_G.set(BREAKER_CODE[breaker])
    return {"level": level, "breaker": breaker, "source": source, "keys": keys}


# --- answer paths, one per level --------------------------------------------------------------

class AskBody(BaseModel):
    student_id: str
    session_id: str = ""
    course: str
    question: str


async def get_profile(student_id: str) -> dict:
    try:
        r = await http.get(f"{settings.student_url}/profile/{student_id}", timeout=settings.profile_timeout_s)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        return {"level": "intermediate", "mastery": {}}


async def search(question: str, course: str, k: int, timeout: float | None = None,
                 exclude_solutions: bool = False) -> list[dict]:
    try:
        r = await http.post(f"{settings.rag_url}/search", timeout=timeout or settings.rag_timeout_s,
                            json={"query": question, "course": course, "k": k, "exclude_solutions": exclude_solutions})
        r.raise_for_status()
        return r.json()["chunks"]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


async def answer_llm(b: AskBody, level: int) -> dict:
    profile = await get_profile(b.student_id)
    chunks = await search(b.question, b.course, LEVEL_CHUNKS[level])
    notes = "\n\n".join(c["text"] for c in chunks) or "(no notes found)"
    turns = history[b.session_id] if level == 0 and b.session_id else ()
    past = "\n".join(f"Student: {q}\nTutor: {a}" for q, a in turns)
    prompt = f"Course notes:\n{notes}\n\n" + (f"Conversation so far:\n{past}\n\n" if past else "") + \
             f"Student question: {b.question}"
    system = SYSTEM_PROMPT.format(course=b.course, level=profile.get("level", "intermediate"))
    r = await http.post(f"{settings.llm_url}/generate",
                        json={"prompt": prompt, "system": system, "max_tokens": LEVEL_TOKENS[level]})
    r.raise_for_status()
    answer = r.json()["text"]
    if level == 0 and b.session_id:
        history[b.session_id].append((b.question, answer))
    return {"answer": answer, "level": level, "source": "llm", "topic": chunks[0]["topic"] if chunks else ""}


async def answer_full(b: AskBody) -> dict:
    """Level 0: up to 256 tokens, 3 chunks, last 4 turns."""
    return await answer_llm(b, 0)


async def answer_lean(b: AskBody) -> dict:
    """Level 1: up to 80 tokens, 1 chunk, no history."""
    return await answer_llm(b, 1)


def topic_hints(course: str, topic: str | None) -> list[str]:
    entry = HINTS.get(course, {}).get(topic) if topic else None
    return entry["hints"] if entry else HINTS["_generic"]["hints"]


def detect_topic_by_keywords(course: str, question: str) -> str | None:
    q = question.lower()
    for topic, entry in HINTS.get(course, {}).items():
        if any(k in q for k in entry.get("keywords", [])):
            return topic
    return None


async def answer_cache_rag(b: AskBody) -> dict:
    """Level 2: cached answer if similarity >= 0.75, else the best syllabus passage plus a
    guiding question. Never calls the LLM; if the RAG service is down, falls to level 3."""
    try:
        r = await http.post(f"{settings.rag_url}/cache/get", timeout=settings.rag_timeout_s,
                            json={"question": b.question, "course": b.course})
        r.raise_for_status()
        hit = r.json()
        if hit.get("hit"):
            return {"answer": hit["answer"], "level": 2, "source": "cache", "topic": hit.get("topic", "")}
    except (httpx.HTTPError, ValueError):
        return await answer_hint(b)
    chunks = await search(b.question, b.course, 1, exclude_solutions=True)
    if not chunks or chunks[0]["score"] <= 0:
        return await answer_hint(b)
    c = chunks[0]
    title = HINTS.get(b.course, {}).get(c["topic"], {}).get("title", c["topic"].replace("_", " "))
    answer = (f"From the course notes ({title}, {c['section']}):\n\n{c['text']}\n\n"
              f"Think about it: {random.choice(topic_hints(b.course, c['topic']))}")
    return {"answer": answer, "level": 2, "source": "rag", "topic": c["topic"]}


async def answer_hint(b: AskBody) -> dict:
    """Level 3: rule-based Socratic hint from hints.yaml. Never calls the LLM."""
    top = await search(b.question, b.course, 1, timeout=0.3)  # TF-IDF, falls back to keywords
    topic = top[0]["topic"] if top and top[0]["score"] > 0 else detect_topic_by_keywords(b.course, b.question)
    if topic not in HINTS.get(b.course, {}):
        topic = None
    return {"answer": random.choice(topic_hints(b.course, topic)), "level": 3, "source": "hint", "topic": topic or ""}


# --- level 4: shed queue (cs:shed:<course> list of ids, cs:shed:q:<id> hash) -------------------

def shed_list(course: str) -> str:
    return f"cs:shed:{course}"


async def answer_shed(b: AskBody) -> dict:
    """Level 4: save the question and tell the student their place in the queue, with a hint
    so they are not left empty-handed. The drain task answers it once the level drops to 0-1."""
    hint = await answer_hint(b)
    if b.course not in COURSES:
        return hint
    qid = f"{b.course}-{uuid.uuid4().hex[:10]}"
    try:
        if await rds.llen(shed_list(b.course)) >= settings.shed_max_per_course:
            return hint
        key = f"cs:shed:q:{qid}"
        async with rds.pipeline(transaction=True) as p:
            p.hset(key, mapping={"status": "queued", "student_id": b.student_id, "session_id": b.session_id,
                                 "course": b.course, "question": b.question, "queued_at": f"{time.time():.3f}"})
            p.expire(key, SHED_TTL_S)
            p.rpush(shed_list(b.course), qid)
            p.expire(shed_list(b.course), SHED_TTL_S)
            position = (await p.execute())[2]
    except Exception:
        return hint  # Redis down: a hint is still useful, a lost question is not
    answer = (f"The tutor is very busy right now. Your question is saved: you are number {position} "
              f"in the {b.course} queue and will get a full answer as soon as demand drops. "
              f"Your quiz is safe.\n\nWhile you wait: {hint['answer']}")
    return {"answer": answer, "level": 4, "source": "queued", "topic": hint["topic"],
            "queue_id": qid, "position": position}


async def drain_once() -> bool:
    """Answer one queued question if the platform is back at level 0-1 with the breaker closed.
    Courses take turns so no course's queue starves. Returns True if it answered one."""
    c = await control()
    if c["level"] > 1 or c["breaker"] != "closed":
        return False
    courses = random.sample(COURSES, len(COURSES))
    for course in courses:
        qid = await rds.lpop(shed_list(course))
        if not qid:
            continue
        q = await rds.hgetall(f"cs:shed:q:{qid}")
        if not q:
            continue  # expired
        b = AskBody(student_id=q["student_id"], session_id=q.get("session_id", ""), course=course,
                    question=q["question"])
        try:
            out = await answer_llm(b, c["level"])
            local.record(True)
        except (httpx.HTTPError, KeyError, ValueError):
            local.record(False)
            await rds.lpush(shed_list(course), qid)  # keep its place
            return False
        await rds.hset(f"cs:shed:q:{qid}", mapping={"status": "answered", "answer": out["answer"],
                                                    "level": out["level"], "answered_at": f"{time.time():.3f}"})
        try:
            await http.post(f"{settings.rag_url}/cache/put", timeout=settings.rag_timeout_s,
                            json={"question": b.question, "course": course, "answer": out["answer"],
                                  "topic": out["topic"], "vetted": False})
        except httpx.HTTPError:
            pass
        return True
    return False


async def drain_loop() -> None:
    while True:
        try:
            answered = await drain_once()
        except Exception:
            log.exception("shed drain failed")
            answered = False
        await asyncio.sleep(0.2 if answered else 1.0)  # one at a time, so recovery is not stampeded


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(drain_loop()) if PM != "none" else None
    yield
    if task:
        task.cancel()


app = create_app(lifespan=lifespan)
LADDER = {0: answer_full, 1: answer_lean, 2: answer_cache_rag, 3: answer_hint, 4: answer_shed}


@app.post("/tutor/ask")
async def tutor_ask(b: AskBody):
    ACTIVE.inc()
    try:
        c = await control()
        level, breaker = c["level"], c["breaker"]
        if level <= 1 and breaker == "half_open" and random.random() >= 0.1:
            level = 2  # only 10% of requests probe the LLM while half-open
        out = None
        if level <= 1:
            try:
                out = await LADDER[level](b)
                local.record(True)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                local.record(False)
                if PM == "none":
                    raise HTTPException(504, f"LLM unavailable: {type(e).__name__}")
                level = 2  # degrade this answer instead of failing it
        if out is None:
            out = await LADDER[level](b)
        RESP(str(out["level"]), out["source"]).inc()
        return out
    finally:
        ACTIVE.dec()


@app.get("/tutor/queued/{qid}")
async def tutor_queued(qid: str):
    q = await rds.hgetall(f"cs:shed:q:{qid}")
    if not q:
        raise HTTPException(404, "unknown or expired queue id")
    if q["status"] == "answered":
        return {"status": "answered", "answer": q["answer"], "level": int(q["level"]), "source": "llm"}
    course = qid.rsplit("-", 1)[0]
    pos = await rds.lpos(shed_list(course), qid)
    return {"status": "queued", "position": pos + 1 if pos is not None else None}


# --- control API (contracts/control_api.md) ---------------------------------------------------

@app.get("/control/state", dependencies=[Depends(require_token)])
async def control_state():
    c = await control()
    k = c["keys"]
    try:
        async with rds.pipeline(transaction=False) as p:
            for course in COURSES:
                p.llen(shed_list(course))
            queued = dict(zip(COURSES, await p.execute()))
    except Exception:
        queued = {}
    return {"level": c["level"], "breaker": c["breaker"], "exam": k["exam"] or {"active": False},
            "heartbeat_age_s": k["heartbeat_age"], "protection_mode": PM, "control_source": c["source"],
            "requested": {"level": k["level"], "breaker": k["breaker"]}, "local_breaker": local.current(),
            "shed_queue": queued}


class ModeBody(BaseModel):
    level: int
    reason: str = ""
    actor: str = "operator"


@app.post("/control/mode", dependencies=[Depends(require_token)])
async def control_mode(b: ModeBody):
    if not 0 <= b.level <= 4:
        raise HTTPException(422, "level must be 0-4")
    await rds.set(LEVEL, b.level)
    await log_action(b.actor, "set_level", b.level, b.reason)
    return {"ok": True}


class BreakerBody(BaseModel):
    state: str
    reason: str = ""
    actor: str = "operator"


@app.post("/control/breaker", dependencies=[Depends(require_token)])
async def control_breaker(b: BreakerBody):
    if b.state not in BREAKER_CODE:
        raise HTTPException(422, "state must be closed|half_open|open")
    await rds.set(BREAKER, b.state)
    await log_action(b.actor, "set_breaker", b.state, b.reason)
    return {"ok": True}


@app.post("/control/exam", dependencies=[Depends(require_token)])
async def control_exam():
    raise HTTPException(501, "exam mode arrives in Phase 3")


@app.post("/control/prewarm", dependencies=[Depends(require_token)])
async def control_prewarm():
    raise HTTPException(501, "pre-warm arrives in Phase 3")


class AnswerBody(BaseModel):
    course: str
    question: str
    level: int = 0


@app.post("/admin/answer", dependencies=[Depends(require_token)])
async def admin_answer(b: AnswerBody):
    """An LLM answer at level 0 or 1 regardless of control state (tools/seed_cache.py)."""
    if b.level not in LEVEL_TOKENS:
        raise HTTPException(422, "level must be 0 or 1")
    try:
        return await answer_llm(AskBody(student_id="seed", course=b.course, question=b.question), b.level)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"LLM unavailable: {type(e).__name__}")


@app.post("/admin/reset", dependencies=[Depends(require_token)])
async def admin_reset():
    global local
    local = LocalBreaker()
    history.clear()
    shed = [k async for k in rds.scan_iter("cs:shed:*", count=500)]
    await rds.mset({LEVEL: 0, BREAKER: "closed"})
    if shed:
        await rds.delete(*shed)
    hdr = {"X-CS-Token": settings.cs_token}
    for url in (settings.rag_url, settings.llm_url):
        try:
            await http.post(f"{url}/admin/reset", headers=hdr, timeout=3)
        except httpx.HTTPError:
            pass
    await log_action("operator", "reset", "all", "episode reset")
    return {"ok": True, "shed_cleared": len(shed)}
