"""Three-mode comparison and ablations (guide 7.2-7.3).

    uv run python -m experiments.run_matrix --runs 3                       # none, reactive, cascadeshield
    uv run python -m experiments.run_matrix --runs 2 --variants threshold,no_graph,binary_ladder
    uv run python -m experiments.run_matrix --analyze results/matrix/<dir>  # -> docs/results.md

Each run: put the platform in the run's PROTECTION_MODE (restarting it locally, or asking you to
restart the Mac with --restart manual), set the core's operator settings for the variant, reset,
settle, run the fixed scenario (chaos/scenarios/comparison.yaml) with its fault, then collect the
per-request log, Prometheus series (platform signals + the core's risk), cs:actions, and the
student service's commit count. Modes are interleaved so drift spreads evenly.

The resilience core stays running in every mode: under `none` and `reactive` the platform ignores
it, but its predictions are still recorded, so lead time can be measured where nothing acts.
"""

import argparse
import json
import math
import re
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import redis
import yaml

from chaos.episode_runner import CONTROL_DIR, HDR, export, fire_fault, reset_platform, url
from experiments.labels import HOLD_S, episode_labels, onsets
from resilience_core.features import STEP_S
from resilience_core.settings import SERVICES, settings

REPO = CONTROL_DIR.parent
SCENARIO = CONTROL_DIR / "chaos" / "scenarios" / "comparison.yaml"
OUT_ROOT = CONTROL_DIR / "results" / "matrix"
RESULTS_MD = REPO / "docs" / "results.md"
RATINGS = REPO / "docs" / "answer_quality.json"
SLOW_S = 15  # a response slower than this counts as a failed interaction (guide 7.2)
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}

# variant -> (platform PROTECTION_MODE, core operator settings)
DEFAULT_OPS = {"controller": "predictive", "graph_enabled": True, "ladder": "full",
               "dry_run": False, "approval": False, "kill_switch": False}
VARIANTS = {
    "none": ("none", {}),
    "reactive": ("reactive", {}),
    "cascadeshield": ("cascadeshield", {}),
    "threshold": ("cascadeshield", {"controller": "threshold"}),  # threshold rule instead of ML
    "no_graph": ("cascadeshield", {"graph_enabled": False}),  # own risk only
    "binary_ladder": ("cascadeshield", {"ladder": "binary"}),  # L0 / L3 only
}


# --- running ------------------------------------------------------------------------------

def ensure_mode(client: httpx.Client, mode: str, restart: str) -> None:
    def current():
        try:
            return client.get(url("orchestrator", "/control/state"), headers=HDR, timeout=3).json().get("protection_mode")
        except (httpx.HTTPError, ValueError):
            return None

    if current() == mode:
        return
    if restart == "manual":
        input(f"\n>>> Restart the platform with PROTECTION_MODE={mode} CHAOS_ENABLED=1 "
              f"(Mac: make platform-up MODE={mode} CHAOS=1), then press Enter... ")
    elif restart == "ollama":
        # This machine runs the real platform (the Mac): restart it with Ollama in the next mode.
        print(f"    restarting local platform (real Ollama) in MODE={mode}", flush=True)
        subprocess.run(["make", "-s", "platform-up", f"MODE={mode}", "CHAOS=1", "BACKEND=ollama"], cwd=REPO,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print(f"    restarting local platform in MODE={mode}", flush=True)
        subprocess.run(["make", "-s", "platform-mock-up", f"MODE={mode}"], cwd=REPO, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if current() == mode:
            time.sleep(10)  # let Prometheus scrape the fresh processes
            return
        time.sleep(2)
    sys.exit(f"platform did not come back in mode {mode}")


def set_ops(client: httpx.Client, ops: dict) -> dict:
    r = client.post(f"{settings.core_url}/ops/settings", json=ops, headers=HDR, timeout=5)
    r.raise_for_status()
    return client.get(f"{settings.core_url}/state", timeout=5).json()


class CorePoller(threading.Thread):
    """Samples the core's /state every 2 s during a run (works for a native or containerized core)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.rows: list[dict] = []
        self.stop = threading.Event()

    def run(self):
        with httpx.Client(timeout=1.5) as c:
            while not self.stop.wait(STEP_S):
                try:
                    s = c.get(f"{settings.core_url}/state").json()
                except (httpx.HTTPError, ValueError):
                    continue
                if not s.get("ts"):
                    continue
                for signal, src in (("cs_core_cascade_risk", "cascade"), ("cs_core_risk", "risk")):
                    v = (s.get(src) or {}).get("llm_inference")
                    if v is not None:
                        self.rows.append({"t": float(s["ts"]), "signal": signal, "value": float(v)})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["t", "signal", "value"])


def llm_backend(client: httpx.Client) -> str:
    """The model label the platform's LLM service reports: `mock-...` for the simulator, else real Ollama."""
    try:
        text = client.get(url("llm_inference", "/metrics"), timeout=3).text
        m = re.search(r'cs_llm_model_info\{[^}]*model="([^"]+)"', text)
        return m.group(1) if m else "unknown"
    except httpx.HTTPError:
        return "unknown"


def run_one(client: httpx.Client, r: redis.Redis, variant: str, idx: int, scenario: dict,
            out_dir: Path, restart: str, settle: int) -> None:
    mode, ops = VARIANTS[variant]
    run_dir = out_dir / f"{variant}_{idx}"
    run_dir.mkdir(parents=True)
    ensure_mode(client, mode, restart)
    core = set_ops(client, {**DEFAULT_OPS, **ops})
    reset_platform(client)
    time.sleep(settle)

    env = {**os.environ, "CS_SCENARIO": str(SCENARIO), "CS_REQUEST_LOG": str(run_dir / "requests.jsonl"),
           "PYTHONPATH": str(CONTROL_DIR)}
    fault, fault_log = scenario.get("fault"), {}
    poller = CorePoller()
    poller.start()
    t0 = time.time()
    timer = threading.Timer(fault["start_s"], fire_fault, (fault, fault_log)) if fault else None
    if timer:
        timer.start()
    with open(run_dir / "locust.log", "w") as logf:
        subprocess.run([sys.executable, "-m", "locust", "-f", "chaos/locustfile.py", "--headless",
                        "--only-summary", "--csv", str(run_dir / "locust"), "--loglevel", "WARNING"],
                       cwd=CONTROL_DIR, env=env, stdout=logf, stderr=subprocess.STDOUT)
    t1 = time.time()
    poller.stop.set()
    if timer:
        timer.cancel()
    for svc in ("llm_inference", "curriculum_rag"):
        client.post(url(svc, "/chaos/clear"), headers=HDR, timeout=5)
    time.sleep(8)

    start, end = math.floor(t0 / STEP_S) * STEP_S, math.floor(t1 / STEP_S) * STEP_S
    export(client, start, end).to_parquet(run_dir / "series.parquet", index=False)
    poller.frame().to_parquet(run_dir / "core.parquet", index=False)
    actions = [{"id": i, **f} for i, f in r.xrange("cs:actions", min=f"{int(t0 * 1000)}-0", max=f"{int(t1 * 1000) + 1}-0")]
    (run_dir / "actions.json").write_text(json.dumps(actions, indent=1))
    stats = client.get(url("student", "/admin/stats"), timeout=5).json()
    meta = {"variant": variant, "mode": mode, "run": idx, "ops": {**DEFAULT_OPS, **ops},
            "t_start": t0, "t_end": t1, "export_start": start, "export_end": end, "scenario": scenario,
            "fault_log": fault_log, "student_stats": stats, "threshold": core.get("threshold"),
            "model": core.get("model"), "controller": core.get("controller"),
            "llm_backend": llm_backend(client)}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=float))


# --- analysis ------------------------------------------------------------------------------

def load_utility() -> dict[int, float] | None:
    """Mean rating per level from the joint answer-quality rating (guide 7.4), or None."""
    if not RATINGS.exists():
        return None
    return {int(k): float(v) for k, v in json.loads(RATINGS.read_text())["mean_by_level"].items()}


def held_true(mask: np.ndarray, rows: int) -> int | None:
    """First index from which mask stays true for `rows` samples."""
    run = 0
    for i, m in enumerate(mask):
        run = run + 1 if m else 0
        if run >= rows:
            return i - rows + 1
    return None


def analyze_run(run_dir: Path, utility: dict[int, float] | None) -> dict:
    meta = json.loads((run_dir / "meta.json").read_text())
    series = pd.read_parquet(run_dir / "series.parquet")
    req = pd.read_json(run_dir / "requests.jsonl", lines=True)
    t0 = meta["export_start"]

    # sessions: a student fails with any 5xx, connection error (status 0) or response over 15 s
    bad = (req["status"] >= 500) | (req["status"] == 0) | (req["latency_s"].fillna(SLOW_S + 1) > SLOW_S)
    per_student = bad.groupby(req["student"]).any()
    tutor = req[req["kind"] == "tutor"]
    quiz = req[req["kind"] == "quiz"]
    accepted = quiz.loc[quiz["status"] == 202, "key"].nunique() if len(quiz) else 0
    committed = meta["student_stats"].get("committed", 0)

    by = {s: g.set_index("t").sort_index() for s, g in series.groupby("service")}
    gw = by["gateway"]["p95_s"].fillna(0) if "gateway" in by else pd.Series(dtype=float)
    labels = episode_labels(series, SERVICES)
    failed_services = [s for s, lab in labels.items() if lab["failed"].any()]
    llm_onsets = onsets(labels["llm_inference"]["failed"].astype(bool)) if "llm_inference" in labels else []

    lead = None
    core = pd.read_parquet(run_dir / "core.parquet") if (run_dir / "core.parquet").exists() else pd.DataFrame()
    first_alarm = None
    if len(core) and meta.get("threshold") is not None:
        casc = core[core["signal"] == "cs_core_cascade_risk"].sort_values("t")
        alarms = casc[casc["value"] >= meta["threshold"]]
        if len(alarms):
            first_alarm = float(alarms["t"].iloc[0])
    if llm_onsets:
        lead = (llm_onsets[0] - first_alarm) if first_alarm is not None and first_alarm <= llm_onsets[0] else 0.0

    # recovery: from fault end until every service is under its SLO for HOLD_S
    recovery = None
    fault = meta["scenario"].get("fault")
    if fault:
        fault_end = t0 + fault["start_s"] + fault["body"].get("seconds", 0)
        grid = np.arange(t0, meta["export_end"] + STEP_S / 2, STEP_S)
        ok = np.ones(len(grid), dtype=bool)
        for s in SERVICES:
            if s in by:
                p = by[s]["p95_s"].reindex(grid).ffill(limit=7).fillna(0).to_numpy()
                ok &= p <= settings.slo_s[s]
        after = grid >= fault_end
        i = held_true(ok & after, int(HOLD_S / STEP_S) + 1)
        recovery = float(grid[i] - fault_end) if i is not None else None

    answered = tutor[tutor["status"] == 200]
    shares = answered["level"].value_counts(normalize=True).sort_index().to_dict() if len(answered) else {}
    retained = None
    if utility and len(tutor):
        per_req = tutor.apply(lambda x: utility.get(int(x["level"]), 0.0) if x["status"] == 200 and x["level"] == x["level"]
                              else 0.0, axis=1)
        retained = float(per_req.mean() / utility[0])

    return {
        "variant": meta["variant"], "run": meta["run"],
        "session_failure_rate": float(per_student.mean()) if len(per_student) else None,
        "students": int(len(per_student)),
        "quiz_accepted": int(accepted), "quiz_committed": int(committed),
        "quiz_lost": int(max(0, accepted - committed)),
        "quiz_duplicates": int(quiz["duplicate"].fillna(False).astype(bool).sum()) if len(quiz) else 0,
        "slo_violation_s": float((gw > settings.slo_s["gateway"]).sum() * STEP_S),
        "gateway_p95_s": float(np.percentile(tutor["latency_s"].dropna(), 95)) if len(tutor) else None,
        "cascade_depth": len(failed_services), "failed_services": failed_services,
        "lead_time_s": lead, "llm_onset": bool(llm_onsets), "first_alarm_s": first_alarm and first_alarm - t0,
        "recovery_s": recovery,
        "level_shares": {int(k): round(v, 3) for k, v in shares.items()},
        "learning_utility_retained": retained,
    }


METRICS = [  # (key, label, format)
    ("session_failure_rate", "Session failure rate", "pct"),
    ("quiz_lost", "Quiz submissions lost", "int"),
    ("quiz_duplicates", "Duplicate quiz retries (absorbed)", "int"),
    ("slo_violation_s", "SLO violation time (s)", "f0"),
    ("gateway_p95_s", "Tutor p95 latency (s)", "f2"),
    ("cascade_depth", "Cascade depth (services failed)", "f1"),
    ("lead_time_s", "Prediction lead time (s)", "f0"),
    ("recovery_s", "Recovery time after fault (s)", "f0"),
    ("learning_utility_retained", "Learning utility retained", "pct"),
]


def mean_ci(values: list) -> tuple[float, float, int] | None:
    v = [x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return None
    m = float(np.mean(v))
    half = T95.get(len(v) - 1, 1.96) * float(np.std(v, ddof=1)) / math.sqrt(len(v)) if len(v) > 1 else float("nan")
    return m, half, len(v)


def fmt_ci(ci, kind: str) -> str:
    if ci is None:
        return "–"
    m, h, n = ci
    scale, f = (100, ".1f") if kind == "pct" else (1, {"int": ".1f", "f0": ".0f", "f1": ".1f", "f2": ".2f"}[kind])
    unit = " %" if kind == "pct" else ""
    s = f"{m * scale:{f}}{unit}"
    if not math.isnan(h):
        s += f" ± {h * scale:{f}}"
    return s + ("" if n == 3 else f" (n={n})")


def write_results(out_dir: Path, rows: list[dict], utility) -> str:
    df = pd.DataFrame(rows)
    order = [v for v in VARIANTS if v in set(df["variant"])]
    summary = {v: {k: mean_ci(df.loc[df["variant"] == v, k].tolist()) for k, _, _ in METRICS} for v in order}
    first = next(d for d in sorted(out_dir.iterdir()) if (d / "meta.json").exists())
    peak = json.loads((first / "meta.json").read_text())["scenario"]["peak_users"]
    backends = {json.loads((d / "meta.json").read_text()).get("llm_backend") or
                ("mock-qwen2.5:0.5b" if "localhost" in json.loads((d / "meta.json").read_text()).get("platform_host", "localhost") else "unknown")
                for d in out_dir.iterdir() if (d / "meta.json").exists()}
    if all(b.startswith("mock") for b in backends):
        backend_note = ("mock LLM simulator on Fedora (calibrated to the Mac's measured 41 tok/s), not real Ollama; "
                        "real-Ollama evidence: the M3 section")
    elif not any(b.startswith("mock") or b == "unknown" for b in backends):
        backend_note = f"real Ollama ({', '.join(sorted(backends))})"
    else:
        backend_note = f"MIXED backends {sorted(backends)}: do not report these together"
    lines = ["<!-- fedora:comparison start (generated by control/experiments/run_matrix.py; edits here are overwritten) -->",
             f"## Three-mode comparison ({datetime.now():%Y-%m-%d})", "",
             f"**LLM: {backend_note}.** "
             f"Scenario `chaos/scenarios/comparison.yaml`: simulated exam ramp to {peak} "
             "simulated students (about 8x the calibrated level-0 capacity), 12 minutes, +1.5 s LLM latency fault at minute 6. "
             "Mean ± 95 % confidence interval (t distribution) over runs; data in "
             f"`control/results/matrix/{out_dir.name}/`.", "",
             "| Metric | " + " | ".join(order) + " |", "| --- |" + " --- |" * len(order)]
    for key, label, kind in METRICS:
        lines.append(f"| {label} | " + " | ".join(fmt_ci(summary[v][key], kind) for v in order) + " |")
    lines += ["", "Answer level shares (tutor requests answered, mean over runs):", "",
              "| Variant | L0 | L1 | L2 | L3 | L4 |", "| --- | --- | --- | --- | --- | --- |"]
    for v in order:
        sh = [np.mean([r["level_shares"].get(lv, 0) for r in rows if r["variant"] == v]) for lv in range(5)]
        lines.append(f"| {v} | " + " | ".join(f"{x * 100:.0f} %" for x in sh) + " |")
    notes = ["", "Notes:",
             "- Session failure: a simulated student with at least one 5xx, connection error or response over 15 s.",
             "- Lead time: first LLM failure onset minus the first time the core's cascade risk crossed its threshold "
             "(0 if no alarm came first). The core predicts in every mode; only `cascadeshield` acts on it.",
             "- Recovery: from the end of the fault until every service's p95 is under its SLO for 20 s; "
             "missing when that never happened before the run ended."]
    if utility is None:
        notes.append("- Learning utility retained: pending the joint answer-quality rating (guide 7.4, "
                     "`docs/answer_quality.json`).")
    lines += notes + ["<!-- fedora:comparison end -->"]
    block = "\n".join(lines) + "\n"
    (out_dir / "summary.json").write_text(json.dumps({"runs": rows, "summary": summary}, indent=2, default=float))
    return block


def update_results_md(block: str) -> None:
    """Replace only our marked block in docs/results.md, so the Mac's sections are untouched."""
    start, end = "<!-- fedora:comparison start", "<!-- fedora:comparison end -->"
    text = RESULTS_MD.read_text() if RESULTS_MD.exists() else "# Results\n\nNumbers in the chapter come only from this file.\n\n"
    if start in text and end in text:
        a = text.index(start)
        b = text.index(end) + len(end) + 1
        text = text[:a] + block + text[b:]
    else:
        text = text.rstrip() + "\n\n" + block
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_MD.write_text(text)


def analyze(out_dir: Path) -> None:
    utility = load_utility()
    rows = [analyze_run(d, utility) for d in sorted(out_dir.iterdir()) if (d / "meta.json").exists()]
    if not rows:
        sys.exit(f"no runs in {out_dir}")
    block = write_results(out_dir, rows, utility)
    update_results_md(block)
    print(block)
    print(f"updated {RESULTS_MD}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--variants", default="none,reactive,cascadeshield", help=f"comma list of {list(VARIANTS)}")
    ap.add_argument("--restart", choices=["local", "ollama", "manual"], default="local",
                    help="local: restart this machine's platform with the mock LLM; ollama: restart this "
                         "machine's platform with real Ollama (run on the Mac); manual: ask you to restart it")
    ap.add_argument("--settle", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--analyze", type=Path, default=None, help="analyze an existing results directory")
    args = ap.parse_args()

    if args.analyze:
        analyze(args.analyze)
        return
    variants = args.variants.split(",")
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        sys.exit(f"unknown variants {unknown}")
    scenario = yaml.safe_load(SCENARIO.read_text())
    out_dir = args.out or OUT_ROOT / f"{datetime.now():%Y%m%d-%H%M}"
    plan = [(v, i) for i in range(1, args.runs + 1) for v in variants]  # interleaved
    minutes = len(plan) * (scenario["lead_s"] + scenario["ramp_s"] + scenario["hold_s"] + scenario["taper_s"] + 60) / 60
    print(f"{len(plan)} runs, about {minutes / 60:.1f} h -> {out_dir}", flush=True)
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, password=settings.redis_password,
                    decode_responses=True)
    with httpx.Client() as client:
        try:
            for v, i in plan:
                print(f"[{v} {i}] {datetime.now():%H:%M}", flush=True)
                try:
                    run_one(client, r, v, i, scenario, out_dir, args.restart, args.settle)
                except Exception as e:  # keep the matrix going; the run directory shows what failed
                    print(f"[{v} {i}] FAILED {type(e).__name__}: {e}", flush=True)
        finally:
            set_ops(client, DEFAULT_OPS)
            ensure_mode(client, "cascadeshield", args.restart)
    analyze(out_dir)


if __name__ == "__main__":
    main()
