"""Episode runner (guide 5.2): reset -> settle -> seeded Locust load (+ an optional fault) ->
export every signal at 2 s -> validate. One episode per directory under data/episodes/.

    uv run python -m chaos.episode_runner --n 60 --seed 2026
    uv run python -m chaos.episode_runner --n 5 --dry-run       # print the plan only

Run with the platform in PROTECTION_MODE=none and CHAOS_ENABLED=1, and the resilience core
stopped, so failures happen naturally and nothing else writes control keys.
"""

import argparse
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from experiments.labels import episode_labels, onsets
from resilience_core.features import TARGETS
from resilience_core.settings import SERVICE_PORTS, settings
from resilience_core.signals import SIGNALS, to_frame

CONTROL_DIR = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).with_name("episodes.yaml")
EPISODES_DIR = CONTROL_DIR / "data" / "episodes"
STEP_S = 2
MAX_GAP_S = 10
HDR = {"X-CS-Token": settings.cs_token}


# --- planning ------------------------------------------------------------------------------

def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _uniform(rng: random.Random, lo_hi, ndigits: int = 0) -> float:
    v = rng.uniform(*lo_hi)
    return round(v, ndigits) if ndigits else round(v)


def _loguniform(rng: random.Random, lo: float, hi: float) -> float:
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def _shape_params(rng: random.Random, shape: str, peak: int, duration: int, ramp: int) -> dict:
    if shape == "exam_ramp":
        taper = 30
        ramp = min(ramp, duration - taper - 60)
        return {"peak_users": peak, "ramp_s": ramp, "hold_s": duration - ramp - taper, "taper_s": taper}
    if shape == "deadline_wave":
        waves, rise, hold, gap = rng.choice([2, 3]), rng.randint(20, 40), rng.randint(40, 90), 120
        return {"waves": waves, "wave_users": peak, "wave_rise_s": rise, "wave_hold_s": hold,
                "wave_gap_s": gap, "base_users": rng.randint(1, 3)}
    if shape == "flash_burst":
        base_s = rng.randint(60, 150)
        return {"base_users": rng.randint(1, 3), "base_s": base_s, "peak_users": peak, "burst_s": 5,
                "hold_s": duration - base_s - 5}
    if shape == "steady_safe":
        return {"users": peak, "ramp_s": 60, "hold_s": duration - 60}
    raise ValueError(shape)


def shape_length(shape: str, p: dict) -> int:
    if shape == "exam_ramp":
        return p["ramp_s"] + p["hold_s"] + p["taper_s"]
    if shape == "deadline_wave":
        return 60 + p["waves"] * (2 * p["wave_rise_s"] + p["wave_hold_s"] + p["wave_gap_s"])
    if shape == "flash_burst":
        return p["base_s"] + p["burst_s"] + p["hold_s"]
    return p["ramp_s"] + p["hold_s"]


def plan_episode(cfg: dict, seed: int) -> dict:
    """Draw one episode's parameters. Deterministic for a given seed."""
    rng = random.Random(seed)
    cap, category = cfg["capacity_users"], _pick(rng, cfg["mix"])
    duration = _uniform(rng, cfg["duration_s"])
    fault = None

    if category == "fail":
        c = cfg["fail"]
        shape = _pick(rng, c["shapes"])
        peak = min(cfg["max_users"], round(cap * _loguniform(rng, *c["peak_x_capacity"])))
        ramp = _uniform(rng, c["ramp_s"])
        with_fault = rng.random() < c["fault_prob"]
    elif category == "safe":
        c = cfg["safe"]
        shape = _pick(rng, c["shapes"])
        peak = max(1, round(cap * rng.uniform(*c["users_x_capacity"])))
        ramp, with_fault = _uniform(rng, [60, 240]), False
    else:
        shape, ramp, with_fault = "steady_safe", 60, True
        peak = max(1, round(cap * rng.uniform(*cfg["fault_only"]["users_x_capacity"])))

    params = _shape_params(rng, shape, peak, duration, ramp)
    length = shape_length(shape, params)
    lead_s = _uniform(rng, cfg["lead_s"])
    lead_users = max(1, round(cap * rng.uniform(*cfg["lead_users_x_capacity"])))
    if with_fault:
        kind = rng.choice(list(cfg["faults"]))
        spec = cfg["faults"][kind]
        lo, hi = cfg["fault_start_s"]
        body = {k: _uniform(rng, v, 2 if isinstance(v[0], float) else 0)
                for k, v in spec.items() if isinstance(v, list)}
        fault = {"kind": kind, "service": spec["service"], "hook": spec["hook"], "body": body,
                 "start_s": lead_s + rng.randint(lo, max(lo, length + hi))}

    scenario = {"shape": shape, "seed": seed, "lead_s": lead_s, "lead_users": lead_users, **params,
                "tutor_weight": 7, "quiz_weight": 3,
                "question_length": _pick(rng, cfg["question_length"]), "course": "mixed"}
    return {"seed": seed, "category": category, "scenario": scenario, "fault": fault,
            "load_s": lead_s + length, "peak_users": peak}


def episode_id(plan: dict) -> str:
    fault = plan["fault"]["kind"] if plan["fault"] else "nofault"
    return f"{datetime.now():%Y%m%d-%H%M%S}_{plan['scenario']['shape']}_{fault}_s{plan['seed']}"


# --- running -------------------------------------------------------------------------------

def url(service: str, path: str) -> str:
    return f"{settings.service_url(service)}{path}"


def preflight(client: httpx.Client, need_chaos: bool, allow_protection: bool) -> dict:
    state = client.get(url("orchestrator", "/control/state"), headers=HDR, timeout=3).json()
    if state.get("protection_mode") != "none" and not allow_protection:
        sys.exit(f"platform PROTECTION_MODE={state.get('protection_mode')}; dataset runs need 'none' "
                 "(make platform-mock-up MODE=none) or pass --allow-protection")
    if need_chaos and client.get(url("llm_inference", "/chaos/state"), headers=HDR, timeout=3).status_code != 200:
        sys.exit("chaos hooks are off on the platform; start it with CHAOS_ENABLED=1")
    client.get(f"{settings.prometheus_url}/-/ready", timeout=3).raise_for_status()
    return state


def reset_platform(client: httpx.Client) -> None:
    client.post(url("orchestrator", "/admin/reset"), headers=HDR, timeout=10).raise_for_status()
    for svc in ("llm_inference", "curriculum_rag"):
        client.post(url(svc, "/chaos/clear"), headers=HDR, timeout=5)  # 404 when chaos is off: fine
    # fresh submissions table, so quiz loss can be counted per episode
    client.post(url("student", "/admin/reset"), headers=HDR, timeout=5)


def fire_fault(fault: dict, log: dict) -> None:
    try:
        r = httpx.post(url(fault["service"], f"/chaos/{fault['hook']}"), json=fault["body"],
                       headers=HDR, timeout=5)
        log.update(fired_at=time.time(), status=r.status_code)
    except httpx.HTTPError as e:
        log.update(fired_at=time.time(), error=str(e))


def export(client: httpx.Client, start: float, end: float):
    results = {}
    for name, promql in SIGNALS.items():
        r = client.get(f"{settings.prometheus_url}/api/v1/query_range",
                       params={"query": promql, "start": start, "end": end, "step": STEP_S}, timeout=30)
        r.raise_for_status()
        results[name] = r.json()["data"]["result"]
    return to_frame(results)


def validate(series, start: float, end: float) -> list[str]:
    problems = []
    expected = set(SERVICE_PORTS)
    for svc in sorted(expected - set(series["service"])):
        problems.append(f"no data for {svc}")
    for svc, g in series.groupby("service"):
        if svc not in expected:
            continue
        starts = g["process_start"].dropna()
        if starts.nunique() > 1:
            problems.append(f"{svc} restarted")
        if "sample_ts" in g:
            gap = (g["t"] - g["sample_ts"]).max()
            if gap > MAX_GAP_S:
                problems.append(f"{svc} scrape gap {gap:.0f}s")
        steps = g["t"].sort_values().diff().max()
        if steps and steps > MAX_GAP_S:
            problems.append(f"{svc} missing rows ({steps:.0f}s)")
        if len(g) < 0.9 * (end - start) / STEP_S:
            problems.append(f"{svc} only {len(g)} rows")
    return problems


def run_episode(client: httpx.Client, cfg: dict, plan: dict, out_root: Path) -> dict:
    ep_id = episode_id(plan)
    ep_dir = out_root / ep_id
    ep_dir.mkdir(parents=True)
    (ep_dir / "scenario.yaml").write_text(yaml.safe_dump(plan["scenario"], sort_keys=False))
    meta = {"id": ep_id, **plan, "platform_host": settings.platform_host, "step_s": STEP_S}

    reset_platform(client)
    time.sleep(cfg["settle_s"])
    platform_state = client.get(url("orchestrator", "/control/state"), headers=HDR, timeout=3).json()

    env = {**os.environ, "CS_SCENARIO": str(ep_dir / "scenario.yaml"), "PYTHONPATH": str(CONTROL_DIR)}
    cmd = [sys.executable, "-m", "locust", "-f", "chaos/locustfile.py", "--headless", "--only-summary",
           "--csv", str(ep_dir / "locust"), "--run-time", f"{plan['load_s'] + 60}s",
           "--stop-timeout", "5", "--loglevel", "WARNING"]
    fault_log: dict = {}
    t_start = time.time()
    timer = None
    if plan["fault"]:
        timer = threading.Timer(plan["fault"]["start_s"], fire_fault, (plan["fault"], fault_log))
        timer.start()
    with open(ep_dir / "locust.log", "w") as logf:
        rc = subprocess.run(cmd, cwd=CONTROL_DIR, env=env, stdout=logf, stderr=subprocess.STDOUT).returncode
    t_end = time.time()
    if timer:
        timer.cancel()
    for svc in ("llm_inference", "curriculum_rag"):
        client.post(url(svc, "/chaos/clear"), headers=HDR, timeout=5)
    time.sleep(cfg["tail_s"])

    start = math.floor(t_start / STEP_S) * STEP_S
    end = math.floor(t_end / STEP_S) * STEP_S
    series = export(client, start, end)
    series.to_parquet(ep_dir / "series.parquet", index=False)

    problems = validate(series, start, end)
    if plan["fault"] and "fired_at" not in fault_log:
        problems.append("fault did not fire")
    if plan["fault"] and fault_log.get("status") not in (None, 200):
        problems.append(f"fault hook returned {fault_log.get('status')}")
    labels = episode_labels(series, TARGETS) if not series.empty else {}
    meta.update(
        t_start=t_start, t_end=t_end, export_start=start, export_end=end, locust_rc=rc,
        fault_log=fault_log, platform_state=platform_state,
        onsets={s: onsets(lab["failed"].astype(bool)) for s, lab in labels.items()},
        valid=not problems, problems=problems,
    )
    (ep_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=float))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=1, help="episodes to run")
    ap.add_argument("--seed", type=int, default=2026, help="master seed; episode i uses seed*1000+i")
    ap.add_argument("--start", type=int, default=None, help="first episode index (default: continue)")
    ap.add_argument("--out", type=Path, default=EPISODES_DIR)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--dry-run", action="store_true", help="print the plans, run nothing")
    ap.add_argument("--allow-protection", action="store_true", help="allow a protection mode other than none")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    start = args.start if args.start is not None else len([p for p in args.out.iterdir() if p.is_dir()])
    plans = [plan_episode(cfg, args.seed * 1000 + i) for i in range(start, start + args.n)]

    for i, p in enumerate(plans, start):
        f = p["fault"]
        print(f"[{i}] {p['category']:<10} {p['scenario']['shape']:<13} peak {p['peak_users']:>3}  "
              f"{p['load_s']:>3}s  fault {f['kind'] + '@' + str(f['start_s']) + 's' if f else '-'}", flush=True)
    if args.dry_run:
        return

    total_s = sum(p["load_s"] + cfg["settle_s"] + cfg["tail_s"] + 15 for p in plans)
    print(f"\n{len(plans)} episodes, about {total_s / 3600:.1f} h -> {args.out}\n", flush=True)
    with httpx.Client() as client:
        preflight(client, any(p["fault"] for p in plans), args.allow_protection)
        for i, plan in enumerate(plans, start):
            meta = run_episode(client, cfg, plan, args.out)
            on = meta["onsets"].get("llm_inference", [])
            status = "ok" if meta["valid"] else "INVALID " + "; ".join(meta["problems"])
            first = f"first llm onset +{on[0] - meta['export_start']:.0f}s" if on else "no llm onset"
            print(f"[{i}] {meta['id']}  {first}  {status}", flush=True)


if __name__ == "__main__":
    main()
