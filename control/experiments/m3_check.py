"""M3 exit check (guide 6, milestone M3): on exam_ramp, does the breaker open before the LLM p95
crosses the SLO? Runs the scenario N times against a platform in PROTECTION_MODE=cascadeshield
with the resilience core running live (not dry-run).

    uv run python -m experiments.m3_check --runs 5 [--scenario exam_ramp]

Per run: reset, settle, Locust headless, then read cs:actions (first breaker open by the control
room) and Prometheus (first time llm p95 > SLO). A run passes if the breaker opened and the p95
either never crossed or crossed later. If containment works, p95 may never cross at all.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import redis
import yaml

from chaos.episode_runner import CONTROL_DIR, HDR, reset_platform, url
from resilience_core.settings import settings

RESULTS = CONTROL_DIR / "results" / "m3_check.json"
CONTROL_ACTORS = ("cascadeshield", "cascadeshield+operator")


def first_breaker_open(r: redis.Redis, since: float) -> float | None:
    for _, f in r.xrange("cs:actions", min=f"{int(since * 1000)}-0"):
        if f.get("action") == "set_breaker" and f.get("value") == "open" and f.get("actor") in CONTROL_ACTORS:
            return float(f["ts"])
    return None


def first_slo_cross(client: httpx.Client, start: float, end: float) -> float | None:
    slo = settings.slo_s["llm_inference"]
    resp = client.get(f"{settings.prometheus_url}/api/v1/query_range", params={
        "query": 'cs:latency_p95:15s{service="llm_inference"}', "start": start, "end": end, "step": 2}, timeout=30)
    for series in resp.json()["data"]["result"]:
        for t, v in series["values"]:
            if v not in ("NaN", "+Inf") and float(v) > slo:
                return float(t)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--scenario", default="exam_ramp")
    ap.add_argument("--settle", type=int, default=20)
    args = ap.parse_args()

    path = Path(args.scenario) if Path(args.scenario).exists() else CONTROL_DIR / "chaos" / "scenarios" / f"{args.scenario}.yaml"
    scenario = yaml.safe_load(path.read_text())
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, password=settings.redis_password,
                    decode_responses=True)
    results = []
    with httpx.Client() as client:
        state = client.get(url("orchestrator", "/control/state"), headers=HDR, timeout=3).json()
        core = client.get(f"{settings.core_url}/state", timeout=3).json()
        if state.get("protection_mode") != "cascadeshield":
            sys.exit(f"platform PROTECTION_MODE={state.get('protection_mode')}; needs cascadeshield")
        if not core.get("healthy") or (core.get("ops") or {}).get("dry_run") or (core.get("ops") or {}).get("kill_switch"):
            sys.exit("the resilience core must be running live (healthy, not dry-run, no kill switch)")
        print(f"controller {core.get('controller')}, model {core.get('model')}, threshold {core.get('threshold')}")

        for i in range(args.runs):
            reset_platform(client)
            time.sleep(args.settle)
            t0 = time.time()
            env = {**os.environ, "CS_SCENARIO": args.scenario, "PYTHONPATH": str(CONTROL_DIR)}
            subprocess.run([sys.executable, "-m", "locust", "-f", "chaos/locustfile.py", "--headless",
                            "--only-summary", "--loglevel", "WARNING"], cwd=CONTROL_DIR, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            t1 = time.time()
            time.sleep(4)
            t_open, t_cross = first_breaker_open(r, t0), first_slo_cross(client, t0, t1)
            passed = t_open is not None and (t_cross is None or t_open < t_cross)
            row = {"run": i + 1, "breaker_open_s": t_open and round(t_open - t0, 1),
                   "slo_cross_s": t_cross and round(t_cross - t0, 1),
                   "lead_s": round(t_cross - t_open, 1) if t_open and t_cross else None, "passed": passed}
            results.append(row)
            print(f"run {i + 1}: breaker open at {row['breaker_open_s']} s, p95 > SLO at {row['slo_cross_s']} s "
                  f"-> {'PASS' if passed else 'FAIL'}", flush=True)
        reset_platform(client)

    n_pass = sum(r_["passed"] for r_ in results)
    print(f"\n{n_pass}/{len(results)} runs opened the breaker before the SLO crossing (M3 needs 4 of 5)")
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"scenario": scenario, "controller": core.get("controller"),
                                   "model": core.get("model"), "runs": results, "passed": n_pass}, indent=2))


if __name__ == "__main__":
    main()
