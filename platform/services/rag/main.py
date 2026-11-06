"""curriculum_rag_service (port 8003): TF-IDF retrieval over data/curriculum and a semantic
answer cache in Redis. Nothing here calls the LLM, which is what makes it a safe fallback."""

import asyncio
import hashlib
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from fastapi import Depends, HTTPException
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer

from cs_common import chaos, create_app, settings
from cs_common.metrics import BUCKETS, metric
from cs_common.redis_client import rds, require_token

RAGQ = metric(Histogram, "cs_rag_query_seconds", "Retrieval time", buckets=BUCKETS)
HITS = metric(Counter, "cs_cache_hits_total", "Semantic cache hits")
MISSES = metric(Counter, "cs_cache_misses_total", "Semantic cache misses")

CHUNK_CHARS = 400
CACHE_TTL_S = 6 * 3600
CACHE_MIN_SIM = 0.75
SOLUTION_TAG = "<!-- type: solution -->"
SEED_FILE = settings.data_dir / "cache_seed.yaml"  # written by tools/seed_cache.py, vetted by hand
CURRICULUM_DIR = settings.data_dir / "curriculum"
NOTES_DIR = Path(os.environ.get("NOTES_DIR", "/notes"))


@dataclass
class Chunk:
    course: str
    topic: str
    section: str
    text: str
    solution: bool


def split_chunks(course: str, topic: str, text: str) -> list[Chunk]:
    """Split one markdown file by `## ` section, then into ~400-character pieces on paragraph
    boundaries."""
    chunks = []
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        section, _, body = part.partition("\n")
        solution = SOLUTION_TAG in body
        body = body.replace(SOLUTION_TAG, "").strip()
        buf = ""
        for para in [p.strip() for p in body.split("\n\n") if p.strip()]:
            if buf and len(buf) + len(para) > CHUNK_CHARS:
                chunks.append(Chunk(course, topic, section.strip(), buf, solution))
                buf = ""
            buf = f"{buf}\n\n{para}".strip()
        if buf:
            chunks.append(Chunk(course, topic, section.strip(), buf, solution))
    return chunks


def load_chunks() -> list[Chunk]:
    """One chunk list from <COURSE>/<topic>.md under data/curriculum and the uploaded notes."""
    paths = [*sorted(CURRICULUM_DIR.glob("*/*.md")), *sorted(NOTES_DIR.glob("*/*.md"))]
    return [c for path in paths for c in split_chunks(path.parent.name, path.stem, path.read_text())]


def build_index() -> dict:
    chunks = load_chunks()
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
    matrix = vectorizer.fit_transform([f"{c.topic.replace('_', ' ')} {c.section} {c.text}" for c in chunks])
    return dict(chunks=chunks, vectorizer=vectorizer, matrix=matrix,
                courses=np.array([c.course for c in chunks]),
                solution=np.array([c.solution for c in chunks]))


index: dict = {}
cache_vecs: dict[str, tuple[str, np.ndarray, bool]] = {}  # cache key -> (course, tf-idf vector, vetted)


def cache_key(course: str, question: str) -> str:
    norm = " ".join(question.lower().split())
    return "cs:cache:" + hashlib.sha1(f"{course}|{norm}".encode()).hexdigest()[:16]


def vec(text: str) -> np.ndarray:
    return index["vectorizer"].transform([text]).toarray()[0]


async def reload_cache_vectors() -> None:
    cache_vecs.clear()
    try:
        async for key in rds.scan_iter("cs:cache:*", count=500):
            q, course, vetted = await rds.hmget(key, "question", "course", "vetted")
            if q:
                cache_vecs[key] = (course, vec(f"{q} {course}"), vetted == "1")
    except Exception:
        pass  # Redis down: start with an empty cache


@asynccontextmanager
async def lifespan(_app):
    index.update(build_index())
    await reload_cache_vectors()
    await load_seed()
    yield


app = create_app(ready=lambda: "matrix" in index, lifespan=lifespan)
chaos.install(app)


class SearchBody(BaseModel):
    query: str
    course: str | None = None
    k: int = 3
    exclude_solutions: bool = False


@app.post("/search")
async def search(b: SearchBody):
    await chaos.inject()
    t0 = time.perf_counter()
    scores = (index["matrix"] @ index["vectorizer"].transform([b.query]).T).toarray().ravel()
    if b.course:
        scores[index["courses"] != b.course] = -1
    if b.exclude_solutions:
        scores[index["solution"]] = -1
    top = [i for i in np.argsort(-scores)[: b.k] if scores[i] >= 0]
    RAGQ.observe(time.perf_counter() - t0)
    return {"chunks": [{"course": c.course, "topic": c.topic, "section": c.section, "text": c.text,
                        "solution": c.solution, "score": round(float(scores[i]), 4)}
                       for i in top for c in [index["chunks"][i]]]}


@app.get("/topics")
async def topics():
    out: dict[str, set] = {}
    for c in index["chunks"]:
        out.setdefault(c.course, set()).add(c.topic)
    return {k: sorted(v) for k, v in out.items()}


class CacheGetBody(BaseModel):
    question: str
    course: str
    vetted_only: bool = False


@app.post("/cache/get")
async def cache_get(b: CacheGetBody):
    await chaos.inject()
    t0 = time.perf_counter()
    q = vec(f"{b.question} {b.course}")
    best_key, best_sim = None, 0.0
    # vetted_only filters before choosing the best match: otherwise a closer unvetted entry hides a
    # vetted one that is also above the threshold
    for key, (course, v, vetted) in cache_vecs.items():
        if course == b.course and (vetted or not b.vetted_only):
            sim = float(q @ v)
            if sim > best_sim:
                best_key, best_sim = key, sim
    hit = None
    if best_key and best_sim >= CACHE_MIN_SIM:
        try:
            hit = await rds.hgetall(best_key)
        except Exception:
            hit = None
        if not hit:
            cache_vecs.pop(best_key, None)  # expired or evicted
        elif b.vetted_only and hit.get("vetted") != "1":
            hit = None  # flag changed in Redis since the vector was stored
    RAGQ.observe(time.perf_counter() - t0)
    if not hit:
        MISSES.inc()
        return {"hit": False, "similarity": round(best_sim, 4)}
    HITS.inc()
    return {"hit": True, "answer": hit["answer"], "topic": hit.get("topic", ""),
            "vetted": hit.get("vetted") == "1", "similarity": round(best_sim, 4)}


class CachePutBody(BaseModel):
    question: str
    course: str
    answer: str
    topic: str = ""
    vetted: bool = False


async def put(b: CachePutBody) -> str:
    key = cache_key(b.course, b.question)
    await rds.hset(key, mapping={"question": b.question, "course": b.course, "answer": b.answer,
                                 "topic": b.topic, "vetted": "1" if b.vetted else "0"})
    await rds.expire(key, CACHE_TTL_S)
    cache_vecs[key] = (b.course, vec(f"{b.question} {b.course}"), b.vetted)
    return key


@app.post("/cache/put")
async def cache_put(b: CachePutBody):
    return {"ok": True, "key": await put(b)}


async def load_seed() -> int:
    """Seeded FAQ answers are the cache's clean state: loaded at startup and on every reset."""
    if not SEED_FILE.is_file():
        return 0
    n = 0
    try:
        for course, entries in (yaml.safe_load(SEED_FILE.read_text()) or {}).items():
            for e in entries or []:
                if e.get("answer"):
                    await put(CachePutBody(course=course, question=e["question"], answer=e["answer"],
                                           topic=e.get("topic", ""), vetted=bool(e.get("vetted"))))
                    n += 1
    except Exception:
        pass  # Redis down or a bad edit to the file: start without the seed
    return n


@app.post("/cache/reload", dependencies=[Depends(require_token)])
async def cache_reload():
    return {"ok": True, "loaded": await load_seed()}


@app.post("/admin/reset", dependencies=[Depends(require_token)])
async def admin_reset():
    keys = [k async for k in rds.scan_iter("cs:cache:*", count=500)]
    if keys:
        await rds.delete(*keys)
    cache_vecs.clear()
    chaos.clear()
    return {"ok": True, "cleared": len(keys), "seeded": await load_seed()}


class NoteBody(BaseModel):
    course: str
    topic: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    markdown: str = Field(min_length=20, max_length=100_000)


notes_lock = asyncio.Lock()


@app.post("/admin/notes", dependencies=[Depends(require_token)])
async def add_note(b: NoteBody):
    # match the listing, not is_dir(): course is caller input and ends up in a path
    if b.course not in {p.name for p in CURRICULUM_DIR.iterdir() if p.is_dir()}:
        raise HTTPException(422, f"unknown course: {b.course}")
    chunks = len(split_chunks(b.course, b.topic, b.markdown))
    if not chunks:
        raise HTTPException(422, "markdown needs at least one '## ' heading with text under it")
    path = NOTES_DIR / b.course / f"{b.topic}.md"
    async with notes_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")  # a failed re-upload must not destroy the previous note
        tmp.write_text(b.markdown)
        tmp.replace(path)
        new = await asyncio.to_thread(build_index)  # searches keep running during the rebuild
        index.clear()
        index.update(new)
        await reload_cache_vectors()  # cached vectors belong to the old vocabulary
    return {"ok": True, "chunks": chunks, "total_chunks": len(index["chunks"])}


@app.get("/admin/notes", dependencies=[Depends(require_token)])
async def list_notes():
    return [{"course": p.parent.name, "topic": p.stem, "bytes": p.stat().st_size}
            for p in sorted(NOTES_DIR.glob("*/*.md"))]
