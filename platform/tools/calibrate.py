#!/usr/bin/env python3
"""Baseline calibration against native Ollama (guide 3.2). Standard library only.

    python3 platform/tools/calibrate.py [--n 30] [--levels 1,2,4,8] [--out docs/calibration_run.md]

Sends tutor-style prompts (~60 prompt tokens, 200 output tokens): N sequential, then batches at
each concurrency level. Reports p50/p95 latency and tokens/s, finds the knee (first concurrency
where p95 > 3x unloaded p95) and proposes the llm_inference SLO = 3x unloaded p95.
Close other apps and watch Activity Monitor -> Memory pressure while it runs.
"""

import argparse
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

QUESTIONS = [
    "I am confused about binary search trees. Why does inserting keys in sorted order make searching slow, "
    "and how is that different from a balanced tree? Please explain with a small example of five keys.",
    "In operating systems, how does round robin scheduling decide which process runs next, and what happens "
    "to the average waiting time when the time quantum is made very large or very small?",
    "For database normalization, what is the difference between second normal form and third normal form? "
    "I keep mixing up partial dependency and transitive dependency in my assignment questions.",
]


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def one(url: str, model: str, prompt: str, num_predict: int) -> dict:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": num_predict}}).encode()
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{url}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    return {"latency": time.perf_counter() - t0, "eval_count": d.get("eval_count", 0),
            "tps": d.get("eval_count", 0) / max(1e-9, d.get("eval_duration", 1) / 1e9),
            "prompt_tokens": d.get("prompt_eval_count", 0)}


def run(url, model, n, concurrency, num_predict) -> dict:
    prompts = [QUESTIONS[i % len(QUESTIONS)] + f" (variant {i})" for i in range(n)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(concurrency) as ex:
        res = list(ex.map(lambda p: one(url, model, p, num_predict), prompts))
    wall = time.perf_counter() - t0
    lat = [r["latency"] for r in res]
    return {"concurrency": concurrency, "n": n, "p50": pct(lat, 50), "p95": pct(lat, 95),
            "tps_per_req": statistics.mean(r["tps"] for r in res),
            "tps_total": sum(r["eval_count"] for r in res) / wall,
            "prompt_tokens": statistics.mean(r["prompt_tokens"] for r in res),
            "out_tokens": statistics.mean(r["eval_count"] for r in res)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--model", default="qwen2.5:0.5b")
    ap.add_argument("--n", type=int, default=30, help="sequential requests")
    ap.add_argument("--levels", default="2,4,8", help="concurrency levels after the sequential run")
    ap.add_argument("--per-level", type=int, default=4, help="requests per worker at each level")
    ap.add_argument("--num-predict", type=int, default=200)
    ap.add_argument("--out", help="also write the markdown table to this file")
    a = ap.parse_args()

    one(a.url, a.model, "Say hi.", 5)  # warm the model
    rows = [run(a.url, a.model, a.n, 1, a.num_predict)]
    print(f"c=1   p50 {rows[0]['p50']:.2f}s  p95 {rows[0]['p95']:.2f}s", flush=True)
    for c in [int(x) for x in a.levels.split(",") if x]:
        rows.append(run(a.url, a.model, c * a.per_level, c, a.num_predict))
        print(f"c={c:<3} p50 {rows[-1]['p50']:.2f}s  p95 {rows[-1]['p95']:.2f}s", flush=True)

    base = rows[0]["p95"]
    knee = next((r["concurrency"] for r in rows[1:] if r["p95"] > 3 * base), None)
    lines = ["| Concurrency | Requests | p50 (s) | p95 (s) | tok/s per request | tok/s total | prompt tok | output tok |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r['concurrency']} | {r['n']} | {r['p50']:.2f} | {r['p95']:.2f} | {r['tps_per_req']:.1f} | "
              f"{r['tps_total']:.1f} | {r['prompt_tokens']:.0f} | {r['out_tokens']:.0f} |" for r in rows]
    lines += ["", f"- Unloaded p95: **{base:.2f} s**; unloaded tokens/s per request: **{rows[0]['tps_per_req']:.1f}**",
              f"- Knee (first concurrency with p95 > 3x unloaded p95): **{knee or 'not reached'}**",
              f"- Proposed `llm_inference` SLO (3x unloaded p95): **{3 * base:.1f} s**"]
    md = "\n".join(lines)
    print("\n" + md)
    if a.out:
        with open(a.out, "w") as f:
            f.write(md + "\n")


if __name__ == "__main__":
    main()
