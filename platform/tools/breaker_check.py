#!/usr/bin/env python3
"""Phase 2 check in reactive mode with chaos hooks on (M2 exit check 2, guide 5.5): LLM errors
open the local breaker, it goes half-open after 20 s and closes after 5 good probes; RAG latency
pushes level 2 down to hints; the leak holds memory until cleared; reset takes under 5 s.

    make platform-up MODE=reactive CHAOS=1 BACKEND=mock && make platform-breaker
"""

import argparse
import asyncio
import re
import time
import uuid

import httpx

from smoke import env


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    a = ap.parse_args()
    tok = {"X-CS-Token": env("CS_TOKEN", "dev-token")}
    gw, orch, rag, llm = (f"http://{a.host}:{p}" for p in (8000, 8002, 8003, 8004))
    results = []

    def check(name, cond, detail=""):
        results.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    async with httpx.AsyncClient(timeout=60) as c:
        async def ask(q="Why does inserting sorted keys make a BST slow?"):
            body = {"student_id": f"brk-{uuid.uuid4().hex[:6]}", "course": "DSA101", "question": q}
            return (await c.post(f"{gw}/api/tutor/ask", json=body)).json()

        async def state():
            return (await c.get(f"{orch}/control/state", headers=tok)).json()

        async def rss_mb(url):
            m = re.search(r"^process_resident_memory_bytes (\S+)", (await c.get(f"{url}/metrics")).text, re.M)
            return float(m.group(1)) / 2**20

        await c.post(f"{orch}/admin/reset", headers=tok)
        st = await state()
        if st["protection_mode"] != "reactive":
            raise SystemExit(f"needs PROTECTION_MODE=reactive, platform runs {st['protection_mode']}")
        if (await c.post(f"{llm}/chaos/clear", headers=tok)).status_code == 404:
            raise SystemExit("chaos hooks are off: start with CHAOS=1")
        check("chaos needs the token", (await c.post(f"{llm}/chaos/clear")).status_code == 401)

        d = await ask()
        check("healthy: LLM answers", d["source"] == "llm", f"level {d['level']}")

        await c.post(f"{llm}/chaos/errors", headers=tok, json={"rate": 1.0, "seconds": 60})
        served = [await ask() for _ in range(5)]
        check("LLM errors degrade answers instead of failing them",
              all(s["level"] >= 2 and s["answer"] for s in served), [s["source"] for s in served])
        st = await state()
        check("5 failures in 10 s open the local breaker", st["local_breaker"] == "open" and st["breaker"] == "open")
        await c.post(f"{llm}/chaos/clear", headers=tok)

        opened = time.time()
        while time.time() - opened < 25 and (await state())["local_breaker"] == "open":
            await asyncio.sleep(1)
        check("half-open after 20 s", (await state())["local_breaker"] == "half_open", f"{time.time() - opened:.0f} s")

        sources = []
        for _ in range(200):
            sources.append((await ask())["source"])
            if (await state())["local_breaker"] == "closed":
                break
        probes = sources.count("llm")
        check("5 good probes close it", (await state())["local_breaker"] == "closed",
              f"{probes} probes in {len(sources)} requests ({probes / len(sources):.0%}, target 10%)")

        await c.post(f"{rag}/chaos/latency", headers=tok, json={"extra_ms": 1500, "seconds": 30})
        st_src = (await ask())["source"]
        check("slow RAG: LLM path still answers", st_src in ("llm", "hint"), st_src)
        await c.post(f"{rag}/chaos/clear", headers=tok)

        base = await rss_mb(llm)
        await c.post(f"{llm}/chaos/leak", headers=tok, json={"mb_per_s": 10, "seconds": 4})
        await asyncio.sleep(5)
        leaked = (await c.get(f"{llm}/chaos/state", headers=tok)).json()["leaked_mb"]
        grown = await rss_mb(llm)
        check("leak holds memory", leaked >= 30 and grown - base >= 25, f"{leaked} MB held, RSS {base:.0f} -> {grown:.0f} MB")
        await c.post(f"{llm}/chaos/leak", headers=tok, json={"mb_per_s": 50, "seconds": 10})
        await asyncio.sleep(4)
        cs = (await c.get(f"{llm}/chaos/state", headers=tok)).json()
        check("leak capped below the 160 MB limit", cs["leaked_mb"] <= 120 and cs["rss_mb"] < 150,
              f"{cs['leaked_mb']} MB held, RSS {cs['rss_mb']} MB")

        await c.post(f"{llm}/chaos/latency", headers=tok, json={"extra_ms": 800, "seconds": 30})
        t = time.perf_counter()
        d = await ask()
        check("LLM latency adds to answers", (time.perf_counter() - t) > 0.8 and d["source"] == "llm",
              f"{(time.perf_counter() - t):.1f} s")

        t = time.perf_counter()
        await c.post(f"{orch}/admin/reset", headers=tok)
        reset_s = time.perf_counter() - t
        cs = (await c.get(f"{llm}/chaos/state", headers=tok)).json()
        check("reset clears faults in under 5 s", reset_s < 5 and cs["leaked_mb"] == 0 and not cs["latency_ms"] and not cs["error_rate"],
              f"{reset_s:.2f} s {cs}")
    print(f"\n{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
