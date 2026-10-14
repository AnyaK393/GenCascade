"""orchestrator_service (port 8002): builds Socratic tutor answers and serves the control API.

Control: in `cascadeshield` mode it follows Fedora's Redis keys while the heartbeat is fresh,
otherwise (and always in `reactive` mode) its own local breaker. `none` ignores all control.
Phase 1 ladder: levels 0-1 use the LLM; any higher level, or an open breaker, serves a hint.
"""

import logging
import random
import time
from collections import defaultdict, deque
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

log = logging.getLogger("orchestrator")
app = create_app()
http = make_client(settings.llm_timeout_s + 2, max_connections=200)
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "socratic.txt").read_text()
HINTS: dict = yaml.safe_load((settings.data_dir / "hints.yaml").read_text())
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


async def control() -> dict:
    """Effective level and breaker for this request, plus where they came from."""
    keys = await control_keys()
    if PM == "none":
        level, breaker, source = 0, "closed", "none"
    else:
        lb = local.current()
        level, breaker, source = (3 if lb == "open" else 0), lb, "local"
        age = keys["heartbeat_age"]
        if PM == "cascadeshield" and age is not None and age <= settings.heartbeat_stale_s:
            # Follow Fedora; the local breaker stays as a backup, so take the safer of the two.
            source = "remote"
            level = max(level, keys["level"] or 0)
            remote = keys["breaker"] if keys["breaker"] in BREAKER_CODE else "closed"
            breaker = max(breaker, remote, key=BREAKER_CODE.get)
        if breaker == "open":
            level = max(level, 3)  # no LLM calls while open (Phase 2: level 2, cache + RAG)
    if source != ctl["source"]:
        if ctl["source"] is not None:
            actor = "failsafe" if source == "local" else "platform"
            await log_action(actor, "control_source", source, f"control source {ctl['source']} -> {source}")
            log.warning("control source %s -> %s", ctl["source"], source)
        ctl["source"] = source
    LEVEL_G.set(level)
    BREAKER_G.set(BREAKER_CODE[breaker])
    return {"level": level, "breaker": breaker, "source": source, "keys": keys}


# --- answer paths -----------------------------------------------------------------------------

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


async def search(question: str, course: str, k: int, timeout: float | None = None) -> list[dict]:
    try:
        r = await http.post(f"{settings.rag_url}/search", json={"query": question, "course": course, "k": k},
                            timeout=timeout or settings.rag_timeout_s)
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


def detect_topic_by_keywords(course: str, question: str) -> str | None:
    q = question.lower()
    for topic, entry in HINTS.get(course, {}).items():
        if any(k in q for k in entry.get("keywords", [])):
            return topic
    return None


async def answer_hint(b: AskBody) -> dict:
    """Level 3: rule-based Socratic hint from hints.yaml. Never calls the LLM."""
    top = await search(b.question, b.course, 1, timeout=0.3)  # TF-IDF, falls back to keywords
    topic = top[0]["topic"] if top and top[0]["score"] > 0 else detect_topic_by_keywords(b.course, b.question)
    entry = HINTS.get(b.course, {}).get(topic) if topic else None
    hints = entry["hints"] if entry else HINTS["_generic"]["hints"]
    return {"answer": random.choice(hints), "level": 3, "source": "hint", "topic": topic or ""}


@app.post("/tutor/ask")
async def tutor_ask(b: AskBody):
    ACTIVE.inc()
    try:
        c = await control()
        level, breaker = c["level"], c["breaker"]
        use_llm = level <= 1 and (breaker == "closed" or (breaker == "half_open" and random.random() < 0.1))
        out = None
        if use_llm:
            try:
                out = await answer_llm(b, level)
                local.record(True)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                local.record(False)
                if PM == "none":
                    raise HTTPException(504, f"LLM unavailable: {type(e).__name__}")
        if out is None:
            out = await answer_hint(b)
        RESP(str(out["level"]), out["source"]).inc()
        return out
    finally:
        ACTIVE.dec()


# --- control API (contracts/control_api.md) ---------------------------------------------------

@app.get("/control/state", dependencies=[Depends(require_token)])
async def control_state():
    c = await control()
    k = c["keys"]
    return {"level": c["level"], "breaker": c["breaker"], "exam": k["exam"] or {"active": False},
            "heartbeat_age_s": k["heartbeat_age"], "protection_mode": PM, "control_source": c["source"],
            "requested": {"level": k["level"], "breaker": k["breaker"]}, "local_breaker": local.current()}


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


@app.post("/admin/reset", dependencies=[Depends(require_token)])
async def admin_reset():
    global local
    local = LocalBreaker()
    history.clear()
    await rds.mset({LEVEL: 0, BREAKER: "closed"})
    hdr = {"X-CS-Token": settings.cs_token}
    for url in (settings.rag_url, settings.llm_url):
        try:
            await http.post(f"{url}/admin/reset", headers=hdr, timeout=2)
        except httpx.HTTPError:
            pass
    await log_action("operator", "reset", "all", "episode reset")
    return {"ok": True}
