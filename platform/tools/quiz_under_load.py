#!/usr/bin/env python3
"""Guide 5.4 test: saturate the LLM with tutor questions, then fire concurrent quiz submits
(each retried once with the same key). Every submit must commit, with zero duplicates stored.

    platform/.venv/bin/python platform/tools/quiz_under_load.py [--tutors 40] [--submits 200]
"""

import argparse
import asyncio
import time
import uuid

import httpx


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--tutors", type=int, default=40)
    ap.add_argument("--submits", type=int, default=200)
    a = ap.parse_args()
    gw = f"http://{a.host}:8000"
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=500)) as c:
        before = (await c.get(f"http://{a.host}:8001/admin/stats")).json()["committed"]
        tutors = [asyncio.create_task(c.post(f"{gw}/api/tutor/ask", json={
            "student_id": f"load{i}", "course": "DSA101", "question": "Explain heaps step by step"}))
            for i in range(a.tutors)]
        await asyncio.sleep(3)
        depth = [l for l in (await c.get(f"http://{a.host}:8004/metrics")).text.splitlines()
                 if l.startswith("cs_llm_queue_depth")]
        print("LLM saturated:", depth[0] if depth else "?")

        async def submit(i):
            body = {"student_id": f"q{i}", "quiz_id": "quiz1", "answers": {"q1": "a"},
                    "idempotency_key": str(uuid.uuid4())}
            async def post():  # like the page and Locust: up to 3 retries with the same key
                for attempt in range(4):
                    try:
                        r = await c.post(f"{gw}/api/quiz/submit", json=body)
                        if r.status_code == 202:
                            return r.status_code
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.2 * (attempt + 1))
                return 0

            t0 = time.perf_counter()
            s1 = await post()
            ms = (time.perf_counter() - t0) * 1000
            s2 = await post()  # deliberate duplicate submit with the same key
            return s1, s2, ms

        res = await asyncio.gather(*(submit(i) for i in range(a.submits)))
        lat = sorted(r[2] for r in res)
        after = (await c.get(f"http://{a.host}:8001/admin/stats")).json()["committed"]
        ok = sum(r[0] == 202 and r[1] == 202 for r in res)
        print(f"submits: {ok}/{a.submits} accepted (both tries), stored rows +{after - before} "
              f"(expected {a.submits}), p95 {lat[int(0.95 * (len(lat) - 1))]:.0f} ms")
        for t in tutors:
            t.cancel()
        passed = ok == a.submits and after - before == a.submits
        print("PASS" if passed else "FAIL")
        raise SystemExit(0 if passed else 1)


asyncio.run(main())
