#!/usr/bin/env python3
"""Phase 2 check in cascadeshield mode (M2 exit checks 1 and 3). Plays Fedora by writing the
heartbeat itself, then drives /control/mode through levels 0-4, opens the breaker, drains the
shed queue, and finally lets the heartbeat go stale to show the failsafe.

    make platform-up BACKEND=mock && make platform-ladder      (works with Ollama too, slower)
"""

import argparse
import asyncio
import re
import time
import uuid

import httpx
import redis.asyncio as aioredis

from smoke import env

EXPECT = {0: ({0}, {"llm"}), 1: ({1}, {"llm"}), 2: ({2, 3}, {"cache", "rag", "hint"}),
          3: ({3}, {"hint"}), 4: ({4}, {"queued"})}
QUESTIONS = [("DSA101", "Why does inserting sorted keys make a BST slow?"),
             ("DBMS201", "What is the difference between 2NF and 3NF?"),
             ("OS202", "What are the four conditions for deadlock?")]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--redis-password", default=None)
    a = ap.parse_args()
    tok = {"X-CS-Token": env("CS_TOKEN", "dev-token")}
    gw, orch, llm = (f"http://{a.host}:{p}" for p in (8000, 8002, 8004))
    r = aioredis.Redis(host=a.host, password=a.redis_password or env("REDIS_PASSWORD", "dev-redis"),
                       decode_responses=True)
    results = []

    def check(name, cond, detail=""):
        results.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    async with httpx.AsyncClient(timeout=60) as c:
        async def llm_calls() -> float:
            text = (await c.get(f"{llm}/metrics")).text
            return sum(float(m) for m in re.findall(r'cs_http_requests_total\{[^}]*route="/generate"[^}]*\} (\S+)', text))

        async def ask(course, q):
            body = {"student_id": f"chk-{uuid.uuid4().hex[:6]}", "course": course, "question": q}
            return (await c.post(f"{gw}/api/tutor/ask", json=body)).json()

        async def state():
            return (await c.get(f"{orch}/control/state", headers=tok)).json()

        t0 = time.perf_counter()
        await c.post(f"{orch}/admin/reset", headers=tok)
        reset_s = time.perf_counter() - t0
        check("reset under 5 s", reset_s < 5, f"{reset_s:.2f} s")
        st = await state()
        if st["protection_mode"] != "cascadeshield":
            raise SystemExit(f"needs PROTECTION_MODE=cascadeshield, platform runs {st['protection_mode']}")

        stop = asyncio.Event()

        async def heartbeat():  # what Fedora's actuator does
            while not stop.is_set():
                await r.set("cs:control:heartbeat", f"{time.time():.3f}", ex=10)
                await asyncio.sleep(2)

        hb = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.3)
        check("follows Fedora while heartbeat is fresh", (await state())["control_source"] == "remote")

        queue_ids = []
        for level in range(5):
            await c.post(f"{orch}/control/mode", headers=tok, json={"level": level, "reason": "ladder check"})
            check(f"state reports level {level}", (await state())["level"] == level)
            for course, q in QUESTIONS:
                before = await llm_calls()
                t = time.perf_counter()
                d = await ask(course, q)
                used_llm = await llm_calls() > before
                levels, sources = EXPECT[level]
                ok = d.get("level") in levels and d.get("source") in sources and d.get("answer")
                if level >= 2:
                    ok = ok and not used_llm
                if level == 4:
                    ok = ok and d.get("queue_id") and d.get("position", 0) >= 1
                    queue_ids.append(d.get("queue_id"))
                check(f"L{level} {course}", ok, f"-> level {d.get('level')} {d.get('source')} "
                      f"{(time.perf_counter() - t) * 1000:.0f} ms llm_call={used_llm} | {d.get('answer', '')[:70]!r}")

        st = await state()
        check("shed queue holds the L4 questions", sum(st["shed_queue"].values()) >= len(queue_ids), st["shed_queue"])
        await c.post(f"{orch}/control/mode", headers=tok, json={"level": 0, "reason": "ladder check: drain"})
        deadline, answered = time.time() + 90, set()
        while time.time() < deadline and len(answered) < len(queue_ids):
            for qid in queue_ids:
                if qid not in answered and (await c.get(f"{gw}/api/tutor/queued/{qid}")).json().get("status") == "answered":
                    answered.add(qid)
            await asyncio.sleep(1)
        check("queued questions answered after level drops to 0", len(answered) == len(queue_ids),
              f"{len(answered)}/{len(queue_ids)}")

        await c.post(f"{orch}/control/breaker", headers=tok, json={"state": "open", "reason": "ladder check"})
        before = await llm_calls()
        d = await ask(*QUESTIONS[0])
        check("breaker open -> level >= 2, no LLM call", d["level"] >= 2 and await llm_calls() == before,
              f"-> level {d['level']} {d['source']}")
        st = await state()
        check("state shows breaker open", st["breaker"] == "open" and st["level"] >= 2, f"level {st['level']}")

        # Failsafe: Fedora goes silent while its last advice still says "open".
        stop.set()
        await hb
        await r.delete("cs:control:heartbeat")
        await asyncio.sleep(0.5)
        st = await state()
        check("failsafe: stale heartbeat -> local control", st["control_source"] == "local" and st["breaker"] == "closed",
              f"source {st['control_source']}, breaker {st['breaker']}, Fedora still asks {st['requested']}")
        d = await ask(*QUESTIONS[1])
        check("failsafe answers from the LLM again", d["source"] == "llm", f"-> level {d['level']} {d['source']}")
        actions = await r.xrevrange("cs:actions", count=20)
        check("switch logged to cs:actions", any(f.get("actor") == "failsafe" for _, f in actions))

        await c.post(f"{orch}/admin/reset", headers=tok)
    print(f"\n{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
