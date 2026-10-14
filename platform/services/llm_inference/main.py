"""llm_inference_service (port 8004): the single GPU bottleneck. A semaphore models Ollama's
OLLAMA_NUM_PARALLEL slots; waiters are the queue. Real token telemetry from Ollama's response."""

import asyncio
import time
from collections import deque

import httpx
from fastapi import HTTPException
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel

from cs_common import create_app, settings
from cs_common.logging import make_client
from cs_common.metrics import BUCKETS, metric
from mock_llm import sim

QDEPTH = metric(Gauge, "cs_llm_queue_depth", "Requests waiting for a generation slot")
QWAIT = metric(Histogram, "cs_llm_queue_wait_seconds", "Time waiting for a slot", buckets=BUCKETS)
TOKENS = metric(Counter, "cs_llm_tokens_generated_total", "Tokens generated (eval_count)")
TPS = metric(Gauge, "cs_llm_tokens_per_second", "eval_count / eval_duration, last 10 s")
PROMPT = metric(Histogram, "cs_llm_prompt_tokens", "Prompt tokens (prompt_eval_count)",
                buckets=(32, 64, 128, 256, 512, 1024, 2048))
TIMEOUTS = metric(Counter, "cs_llm_timeouts_total", "Generations that exceeded the timeout")
MODEL = metric(Gauge, "cs_llm_model_info", "1 for the model in use", ("model",))

MOCK = settings.llm_backend == "mock"
MODEL_NAME = f"mock-{settings.llm_model}" if MOCK else settings.llm_model
MODEL(MODEL_NAME).set(1)
MAX_QUEUE = 1000 if settings.protection_mode == "none" else settings.max_queue

app = create_app()
slots = asyncio.Semaphore(settings.max_inflight)
state = {"waiting": 0}
recent: deque[tuple[float, int, float]] = deque()  # (finished_at, eval_count, eval_seconds)
ollama = make_client(settings.llm_timeout_s, max_connections=settings.max_inflight + 2)


class GenerateBody(BaseModel):
    prompt: str
    max_tokens: int = 256
    system: str | None = None
    model: str | None = None


def record(out: dict) -> None:
    tokens, secs = int(out.get("eval_count", 0)), out.get("eval_duration", 0) / 1e9
    TOKENS.inc(tokens)
    PROMPT.observe(out.get("prompt_eval_count", 0))
    now = time.time()
    recent.append((now, tokens, secs))
    while recent and recent[0][0] < now - 10:
        recent.popleft()
    total_s = sum(r[2] for r in recent)
    if total_s > 0:
        TPS.set(sum(r[1] for r in recent) / total_s)


async def call_backend(b: GenerateBody) -> dict:
    if MOCK:
        return await sim.generate(f"{b.system or ''} {b.prompt}", b.max_tokens, settings.mock_tokens_per_s)
    body = {"model": b.model or settings.llm_model, "prompt": b.prompt, "stream": False,
            "options": {"num_predict": b.max_tokens}}
    if b.system:
        body["system"] = b.system
    r = await ollama.post(f"{settings.ollama_url}/api/generate", json=body)
    r.raise_for_status()
    return r.json()


@app.post("/generate")
async def generate(b: GenerateBody):
    if state["waiting"] >= MAX_QUEUE:
        raise HTTPException(503, "LLM queue full")
    start = time.monotonic()
    state["waiting"] += 1
    QDEPTH.set(state["waiting"])
    try:
        await asyncio.wait_for(slots.acquire(), timeout=settings.llm_timeout_s)
    except TimeoutError:
        TIMEOUTS.inc()
        raise HTTPException(504, "timed out waiting for a generation slot")
    finally:
        state["waiting"] -= 1
        QDEPTH.set(state["waiting"])
    QWAIT.observe(time.monotonic() - start)
    try:
        remaining = max(0.1, settings.llm_timeout_s - (time.monotonic() - start))
        out = await asyncio.wait_for(call_backend(b), timeout=remaining)
    except (TimeoutError, httpx.TimeoutException):
        TIMEOUTS.inc()
        raise HTTPException(504, "generation timed out")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"LLM backend error: {e}")
    finally:
        slots.release()
    record(out)
    return {"text": out.get("response", "").strip(), "model": MODEL_NAME,
            "eval_count": out.get("eval_count", 0), "prompt_eval_count": out.get("prompt_eval_count", 0),
            "latency_s": round(time.monotonic() - start, 3)}
