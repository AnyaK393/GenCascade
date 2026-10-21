#!/usr/bin/env python3
"""Phase 3 check in cascadeshield mode (M3 exit checks 1-4). Plays Fedora's heartbeat, pre-warms
DSA101, turns exam mode on, checks the floor and the integrity filter, measures the exam cache hit
rate on Locust's question bank, then loads the platform and measures quiz p95 and the banner.

    make platform-up && make platform-exam        (real Ollama; BACKEND=mock is faster)
"""

import argparse
import asyncio
import random
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import redis.asyncio as aioredis

from smoke import env

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control"))
from chaos.questions import bank  # noqa: E402  (Fedora's Locust question bank, read only)

COURSE = "DSA101"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--load-s", type=int, default=40)
    ap.add_argument("--tutors", type=int, default=30)
    ap.add_argument("--skip-prewarm", action="store_true")
    a = ap.parse_args()
    tok = {"X-CS-Token": env("CS_TOKEN", "dev-token")}
    gw, orch, rag, stu = (f"http://{a.host}:{p}" for p in (8000, 8002, 8003, 8001))
    r = aioredis.Redis(host=a.host, password=env("REDIS_PASSWORD", "dev-redis"), decode_responses=True)
    results = []

    def check(name, cond, detail=""):
        results.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=400)) as c:
        async def state():
            return (await c.get(f"{orch}/control/state", headers=tok)).json()

        async def mode(level):
            await c.post(f"{orch}/control/mode", headers=tok, json={"level": level, "reason": "exam check"})

        async def ask(q, course=COURSE):
            body = {"student_id": f"ex-{uuid.uuid4().hex[:6]}", "course": course, "question": q}
            return (await c.post(f"{gw}/api/tutor/ask", json=body)).json()

        async def cache_counts():
            text = (await c.get(f"{rag}/metrics")).text
            return [float(re.search(rf"^{n}{{[^}}]*}} (\S+)", text, re.M).group(1))
                    for n in ("cs_cache_hits_total", "cs_cache_misses_total")]

        await c.post(f"{orch}/admin/reset", headers=tok)
        if (await state())["protection_mode"] != "cascadeshield":
            raise SystemExit("needs PROTECTION_MODE=cascadeshield")
        stop = asyncio.Event()

        async def heartbeat():
            while not stop.is_set():
                await r.set("cs:control:heartbeat", f"{time.time():.3f}", ex=10)
                await asyncio.sleep(2)

        hb = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.3)

        # 1. Pre-warm (guide 6.2), before the exam starts
        if not a.skip_prewarm:
            p = (await c.post(f"{orch}/control/prewarm", headers=tok, json={"course": COURSE, "topics": []})).json()
            print(f"      pre-warming {len(p['topics'])} topics ...")
            while (p := (await c.get(f"{orch}/control/prewarm", headers=tok)).json())["running"]:
                await asyncio.sleep(3)
            check("pre-warm of 10 topics finishes", p["done"] == p["total"] and not p["failed"],
                  f"{p['total']} answers ({p['from_seed']} vetted from seed, {p['generated']} generated) "
                  f"in {p['elapsed_s']:.0f} s, {p['failed']} failed")

        # 2. Exam on, floor 1
        ends = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        await c.post(f"{orch}/control/exam", headers=tok,
                     json={"active": True, "course": COURSE, "ends_at": ends, "floor": 1, "reason": "exam check"})
        st = await state()
        check("exam active in /control/state", st["exam"].get("active") and st["exam"].get("remaining_s", 0) > 1000,
              f"{st['exam'].get('course')} floor {st['exam'].get('floor')} {st['exam'].get('remaining_s')} s left")
        await asyncio.sleep(1.1)  # the gateway reads the exam key once a second
        s = (await c.get(f"{gw}/api/status")).json()
        check("student page sees the exam", s["exam"]["active"] and s["exam"]["course"] == COURSE)
        await mode(0)
        d = await ask("Why does inserting sorted keys make a BST slow?")
        check("exam floor 1: level 0 request answered lean", d["level"] == 1 and d["source"] == "llm",
              f"-> level {d['level']} {d['source']}")

        # 3. Integrity filter at level 2
        await mode(2)
        planted_q = f"zebra quantum lattice question {uuid.uuid4().hex[:6]}"
        for course in (COURSE, "DBMS201"):
            await c.post(f"{rag}/cache/put", json={"question": planted_q, "course": course, "topic": "x",
                                                   "answer": "PLANTED-UNVETTED", "vetted": False})
        d_exam, d_other = await ask(planted_q), await ask(planted_q, "DBMS201")
        check("unvetted cache entry not served to the exam course", "PLANTED" not in d_exam["answer"], d_exam["source"])
        check("...but still served to other courses", d_other["answer"] == "PLANTED-UNVETTED", d_other["source"])
        sols = [ch for ch in (await c.post(f"{rag}/search", json={"query": "worked solution", "course": COURSE,
                                                                   "k": 60})).json()["chunks"] if ch["solution"]]
        leaked = 0
        for ch in sols[:12]:
            d = await ask(ch["text"][:160])  # the question most likely to retrieve that solution chunk
            leaked += any(s2["text"][:80] in d["answer"] for s2 in sols)
        check("no solution chunk served during the exam", sols and leaked == 0, f"{leaked}/{min(12, len(sols))} leaked")

        # 4. Cache hit rate on Locust's question bank during the exam (vetted only)
        sample = random.Random(7).sample(bank(COURSE, "short"), 60)
        h0, m0 = await cache_counts()
        for _, q in sample:
            await ask(q)
        h1, m1 = await cache_counts()
        rate = (h1 - h0) / max(1, (h1 - h0) + (m1 - m0))
        sims = [(await c.post(f"{rag}/cache/get", json={"question": q, "course": COURSE})).json()["hit"] for _, q in sample]
        check("exam cache hit rate above 40%", rate > 0.40,
              f"{rate:.0%} with vetted answers only; {sum(sims) / len(sims):.0%} if every cached answer were vetted")

        # 5. Load: tutors flood the platform while quiz submits arrive at 5 per second
        await mode(0)
        lat, shed, limits, done = [], [], [], asyncio.Event()

        async def tutor():
            qs = bank(COURSE, "short")
            while not done.is_set():
                try:
                    d = await ask(random.choice(qs)[1])
                    shed.append(d.get("source") == "queued")
                except httpx.HTTPError:
                    pass

        async def submit(i):
            body = {"student_id": f"s{i % 1500:04d}", "quiz_id": "exam-quiz", "answers": {"q1": "a"},
                    "idempotency_key": str(uuid.uuid4())}
            t = time.perf_counter()
            for attempt in range(4):
                try:
                    if (await c.post(f"{gw}/api/quiz/submit", json=body)).status_code == 202:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2 * (attempt + 1))
            lat.append((time.perf_counter() - t) * 1000)

        async def sample_limit():
            while not done.is_set():
                m = re.search(r"^cs_admission_limit{[^}]*} (\S+)", (await c.get(f"{gw}/metrics")).text, re.M)
                limits.append(int(float(m.group(1))))
                await asyncio.sleep(5)

        before = (await c.get(f"{stu}/admin/stats")).json()["committed"]
        tutors = [asyncio.create_task(tutor()) for _ in range(a.tutors)]
        sampler = asyncio.create_task(sample_limit())
        await asyncio.sleep(5)  # let the tutor load build
        subs = []
        for i in range(a.load_s * 5):
            subs.append(asyncio.create_task(submit(i)))
            await asyncio.sleep(0.2)
        await asyncio.gather(*subs)
        done.set()
        await asyncio.gather(*tutors, sampler, return_exceptions=True)
        after = (await c.get(f"{stu}/admin/stats")).json()["committed"]
        lat.sort()
        p95 = lat[int(0.95 * (len(lat) - 1))]
        check("quiz p95 under 500 ms during the exam", p95 < 500,
              f"p95 {p95:.0f} ms, p50 {lat[len(lat) // 2]:.0f} ms over {len(lat)} submits")
        check("every submit committed", after - before == len(lat), f"+{after - before} rows")
        print(f"      tutoring: {len(shed)} answers, {sum(shed)} shed to the queue; admission limit over time {limits}")

        # 6. Banner
        await mode(2)
        t = time.perf_counter()
        while (await c.get(f"{gw}/api/status")).json()["level"] != 2 and time.perf_counter() - t < 5:
            await asyncio.sleep(0.05)
        lag = time.perf_counter() - t
        check("banner changes within 3 s (page polls every 3 s)", lag + 3 <= 3.5, f"server side {lag * 1000:.0f} ms + up to 3 s poll")

        stop.set()
        await hb
        await c.post(f"{orch}/control/exam", headers=tok, json={"active": False, "reason": "exam check done"})
        await c.post(f"{orch}/admin/reset", headers=tok)
    print(f"\n{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
