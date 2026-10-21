"""Chapter figures (guide 7.5), saved to docs/figures/ as PNG (2x) and SVG.

    uv run python -m experiments.figures all [--matrix results/matrix/<dir>]
    uv run python -m experiments.figures screenshot healthy      # dashboard via headless Chrome
    uv run python -m experiments.figures screenshot contained    # take it while a ramp is contained

1 architecture · 2/3 dashboard (screenshots) · 4 prediction vs reality timeline ·
5 three-mode comparison with 95 % CIs · 6 SHAP summary (held-out episodes) · 7 degradation ladder
with learning utility (needs docs/answer_quality.json).

Style: light surface, recessive grid, one y-axis per panel (stacked panels share time instead of
dual axes), modes in the first three validated categorical slots, direct value labels.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from resilience_core.settings import settings  # noqa: E402

CONTROL = Path(__file__).resolve().parents[1]
REPO = CONTROL.parent
FIG_DIR = REPO / "docs" / "figures"
MATRIX_ROOT = CONTROL / "results" / "matrix"

# reference palette (dataviz skill), light mode
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
MODE_COLOUR = {"none": SERIES[0], "reactive": SERIES[1], "cascadeshield": SERIES[2],
               "threshold": SERIES[3], "no_graph": SERIES[4], "binary_ladder": SERIES[5]}
CRITICAL, GOOD = "#d03b3b", "#0ca30c"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.sans-serif": ["Inter", "Segoe UI", "DejaVu Sans"], "font.size": 10,
    "text.color": INK, "axes.labelcolor": INK2, "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlelocation": "left",
    "axes.titlesize": 11, "axes.titleweight": "bold", "legend.frameon": False, "lines.linewidth": 1.6,
})


def save(fig, name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote docs/figures/{name}.png / .svg")


# --- 1 architecture -------------------------------------------------------------------------

def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(11, 5.4))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.4)
    ax.axis("off")

    def box(x, y, w, h, text, fc="#ffffff", ec=AXIS, bold=False, size=9):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
                fontweight="bold" if bold else "normal", color=INK)

    def arrow(a, b, colour=INK2, ls="-", rad=0.0):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11, color=colour, lw=1.1,
                                     linestyle=ls, connectionstyle=f"arc3,rad={rad}"))

    def label(x, y, text, colour=INK2, ha="center"):
        ax.text(x, y, text, ha=ha, va="center", fontsize=8, color=colour, linespacing=1.2)

    # machines
    box(0.2, 0.3, 4.6, 4.8, "", fc="#f3f6fb", ec="#b7d3f6")
    ax.text(0.35, 4.85, "Fedora · control room (advises)", fontsize=10, fontweight="bold", color="#1c5cab")
    box(6.0, 0.3, 4.8, 4.8, "", fc="#f6f4ee", ec=AXIS)
    ax.text(6.15, 4.85, "Mac · campus GenAI platform", fontsize=10, fontweight="bold", color=INK2)

    # Fedora: Prometheus left, Locust right (next to the gateway it loads)
    box(0.45, 3.85, 1.9, 0.6, "Prometheus\nscrape every 2 s")
    box(2.65, 3.85, 1.9, 0.6, "Locust\nsimulated students")
    box(0.45, 1.2, 4.1, 2.15, "", fc="#ffffff")
    ax.text(0.6, 3.1, "Resilience core (:8600), every 2 s", fontsize=9, fontweight="bold")
    for i, t in enumerate(["features (same code as training)", "calibrated RF + SHAP",
                           "dependency graph → cascade risk", "containment engine + guardrails", "exam calendar"]):
        ax.text(0.7, 2.77 - i * 0.32, f"• {t}", fontsize=8.5, color=INK2)
    box(0.45, 0.5, 4.1, 0.5, "Dashboard (:8501): topology · risk · SHAP · log")
    arrow((1.4, 3.85), (1.4, 3.35), colour=MUTED)  # Prometheus -> core
    arrow((2.5, 1.2), (2.5, 1.0), colour=MUTED)  # core -> dashboard

    # Mac: two columns
    for (x, y), name in [((6.3, 3.85), "gateway"), ((6.3, 2.6), "orchestrator"), ((6.3, 1.4), "curriculum_rag"),
                         ((8.6, 3.85), "student"), ((8.6, 2.6), "llm_inference")]:
        box(x, y, 1.95, 0.6, name, bold=True)
    box(6.3, 0.5, 1.95, 0.6, "Redis\ncontrol keys · cache")
    box(8.6, 1.4, 1.95, 0.6, "Ollama\nqwen2.5:0.5b")
    arrow((8.25, 4.15), (8.6, 4.15))  # gateway -> student
    arrow((7.27, 3.85), (7.27, 3.2))  # gateway -> orchestrator
    arrow((8.25, 2.9), (8.6, 2.9))  # orchestrator -> llm
    arrow((8.25, 3.1), (8.6, 3.95))  # orchestrator -> student
    arrow((7.27, 2.6), (7.27, 2.0))  # orchestrator -> rag
    arrow((9.57, 2.6), (9.57, 2.0), ls=":")  # llm -> ollama

    # between machines
    arrow((4.55, 4.15), (6.3, 4.15), colour=SERIES[0])
    label(5.4, 4.35, "exam-day load", SERIES[0])
    arrow((6.3, 3.95), (2.0, 3.85), colour=MUTED, rad=-0.12)
    label(5.4, 3.62, "/metrics pull", MUTED)
    arrow((4.55, 2.6), (6.3, 2.85), colour=SERIES[2])
    label(5.4, 2.42, "control API:\nlevel · breaker · exam", SERIES[2])
    arrow((4.55, 1.45), (6.3, 0.8), colour=SERIES[2])
    label(5.4, 1.52, "heartbeat\nrisk · SHAP", SERIES[2])
    save(fig, "1_architecture")


# --- 4 timeline -------------------------------------------------------------------------------

def pick_run(matrix: Path, variant: str = "cascadeshield") -> Path:
    runs = sorted(d for d in matrix.iterdir() if d.name.startswith(f"{variant}_") and (d / "meta.json").exists())
    if not runs:
        sys.exit(f"no {variant} runs in {matrix}")
    return runs[0]


def fig_timeline(run_dir: Path) -> None:
    from experiments.labels import episode_labels, onsets

    meta = json.loads((run_dir / "meta.json").read_text())
    series = pd.read_parquet(run_dir / "series.parquet")
    core = pd.read_parquet(run_dir / "core.parquet")
    t0, thr = meta["export_start"], meta.get("threshold") or 0.8
    rel = lambda t: (np.asarray(t) - t0) / 60  # noqa: E731
    llm = series[series["service"] == "llm_inference"].sort_values("t")
    orch = series[series["service"] == "orchestrator"].sort_values("t")
    casc = core[core["signal"] == "cs_core_cascade_risk"].sort_values("t")
    lab = episode_labels(series, ["llm_inference"])["llm_inference"]
    on = onsets(lab["failed"].astype(bool))
    alarm = casc[casc["value"] >= thr]["t"].min() if len(casc) else np.nan
    fault = meta["scenario"].get("fault")

    fig, axes = plt.subplots(3, 1, figsize=(10, 6.4), sharex=True, gridspec_kw={"height_ratios": [1.2, 1.2, 0.7]})
    for ax in axes:
        if fault:
            a = fault["start_s"] / 60
            ax.axvspan(a, a + fault["body"]["seconds"] / 60, color="#ede9f9", lw=0, zorder=0)
        if not np.isnan(alarm):
            ax.axvline(rel(alarm), color=SERIES[2], lw=1.2, ls="--")
        for o in on:
            ax.axvline(rel(o), color=CRITICAL, lw=1.2)

    ax = axes[0]
    ax.plot(rel(casc["t"]), casc["value"], color=SERIES[2], lw=2)
    ax.axhline(thr, color=INK2, lw=1, ls=":")
    ax.text(rel(casc["t"]).max(), thr + 0.03, f"threshold {thr:.2f}", ha="right", fontsize=8, color=INK2)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("predicted risk")
    ax.set_title(f"Prediction versus reality · {meta['variant']} run {meta['run']} (simulated students)")
    if not np.isnan(alarm):
        ax.text(rel(alarm) + 0.08, 0.06, "first alarm", fontsize=8, color=SERIES[2])

    ax = axes[1]
    ratio = llm["p95_s"].ffill(limit=7) / settings.slo_s["llm_inference"]
    ax.plot(rel(llm["t"]), ratio, color=SERIES[0], lw=2)
    ax.axhline(1, color=INK2, lw=1, ls=":")
    ax.text(rel(llm["t"]).max(), 1.04, "SLO", ha="right", fontsize=8, color=INK2)
    ax.set_ylabel("LLM p95 ÷ SLO")
    ax.set_ylim(0, max(2.0, float(np.nanmax(ratio)) * 1.05) if ratio.notna().any() else 2)
    if on:
        ax.text(rel(on[0]) + 0.08, ax.get_ylim()[1] * 0.88, "failure onset", fontsize=8, color=CRITICAL)
    if fault:
        ax.text(fault["start_s"] / 60 + 0.08, ax.get_ylim()[1] * 0.75, f"+{fault['body']['extra_ms']} ms fault",
                fontsize=8, color="#6250d6")

    ax = axes[2]
    ax.step(rel(orch["t"]), orch["degradation_level"], where="post", color=SERIES[1], lw=2)
    ax.set_yticks(range(5))
    ax.set_yticklabels(["L0", "L1", "L2", "L3", "L4"])
    ax.set_ylim(-0.3, 4.3)
    ax.set_ylabel("level set")  # while half-open, ~90 % of answers are still served at L2
    ax.set_xlabel("minutes since load start")
    fig.tight_layout()
    save(fig, "4_timeline")


# --- 5 comparison -------------------------------------------------------------------------------

COMPARE = [("session_failure_rate", "Session failure rate", 100, "%"),
           ("slo_violation_s", "SLO violation time", 1, "s"),
           ("cascade_depth", "Cascade depth", 1, "services"),
           ("recovery_s", "Recovery after fault", 1, "s")]


def fig_comparison(matrix: Path, variants=("none", "reactive", "cascadeshield"), name="5_comparison") -> None:
    summary = json.loads((matrix / "summary.json").read_text())["summary"]
    variants = [v for v in variants if v in summary]
    fig, axes = plt.subplots(1, len(COMPARE), figsize=(3.0 * len(COMPARE), 3.4))
    for ax, (key, title, scale, unit) in zip(axes, COMPARE):
        x = np.arange(len(variants))
        missing = []
        for i, v in enumerate(variants):
            ci = summary[v].get(key)
            if not ci:
                missing.append(i)
                continue
            m, h, _ = ci
            h = 0 if h is None or (isinstance(h, float) and np.isnan(h)) else h
            ax.bar(i, m * scale, width=0.62, color=MODE_COLOUR[v], edgecolor=SURFACE, linewidth=2, zorder=2)
            ax.errorbar(i, m * scale, yerr=h * scale, color=INK, capsize=4, lw=1, zorder=3)
            ax.text(i, (m + h) * scale, f"{m * scale:.0f}" if m * scale >= 10 else f"{m * scale:.1f}",
                    ha="center", va="bottom", fontsize=9, color=INK, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(variants, rotation=0, fontsize=8.5)
        ax.set_title(f"{title} ({unit})", fontsize=10)
        ax.grid(axis="x", visible=False)
        ax.set_ylim(bottom=0)
        ax.margins(y=0.18)
        for i in missing:  # e.g. recovery never happened before the run ended
            ax.text(i, ax.get_ylim()[1] * 0.04, "not\nreached", ha="center", va="bottom", fontsize=8, color=MUTED)
    fig.suptitle("Three protection modes, mean ± 95 % CI over runs (simulated students)", x=0.01, ha="left",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, name)


# --- 6 SHAP summary -----------------------------------------------------------------------------

def fig_shap(max_rows: int = 2000) -> None:
    import shap

    from experiments.build_dataset import OUT as TRAIN
    from resilience_core.features import FEATURE_COLUMNS
    from resilience_core.model import load_active
    from resilience_core.predictor import BASE_LABELS

    bundle = load_active()
    if bundle is None:
        sys.exit("no active model; run make train")
    df = pd.read_parquet(TRAIN)
    res = CONTROL / "results" / "model_results.json"
    test_eps = json.loads(res.read_text()).get("test_episodes") if res.exists() else None
    if test_eps:
        df = df[df["episode_id"].isin(test_eps)]
    df = df[df["service"] == "llm_inference"]
    X = df[FEATURE_COLUMNS].fillna(0).sample(min(max_rows, len(df)), random_state=0)
    sv = shap.TreeExplainer(bundle.base).shap_values(X)
    sv = np.asarray(sv[1] if isinstance(sv, list) else sv)
    sv = sv[..., 1] if sv.ndim == 3 else sv

    def nice(f):
        for suf, word in [("_slope60", " · slope 60 s"), ("_delta30", " · Δ 30 s"), ("_mean30", " · mean 30 s"),
                          ("_mean60", " · mean 60 s"), ("_std30", " · std 30 s"), ("_std60", " · std 60 s")]:
            if f.endswith(suf):
                return BASE_LABELS.get(f[: -len(suf)], f[: -len(suf)]) + word
        return BASE_LABELS.get(f, f)

    keep = [i for i, f in enumerate(FEATURE_COLUMNS) if not f.startswith("svc_")]
    plt.figure()
    shap.summary_plot(sv[:, keep], X.iloc[:, keep], feature_names=[nice(FEATURE_COLUMNS[i]) for i in keep],
                      max_display=12, show=False, plot_size=(9, 5.5))
    fig = plt.gcf()
    fig.axes[0].set_title("What drives the failure prediction (SHAP, held-out episodes, llm_inference)", loc="left",
                          fontsize=11, fontweight="bold")
    save(fig, "6_shap_summary")


# --- 7 degradation ladder -------------------------------------------------------------------------

def fig_ladder() -> None:
    path = REPO / "docs" / "answer_quality.json"
    if not path.exists():
        print("skip 7_ladder: docs/answer_quality.json missing (run experiments.answer_quality first)")
        return
    aq = json.loads(path.read_text())
    names = {0: "L0 Full", 1: "L1 Lean", 2: "L2 Cache + RAG", 3: "L3 Hints"}
    levels = sorted(int(k) for k in aq["mean_by_level"])
    vals = [aq["mean_by_level"][str(k)] for k in levels]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ramp = ["#1c5cab", "#2a78d6", "#5598e7", "#86b6ef"]  # one hue: more LLM -> darker
    ax.bar(range(len(levels)), vals, color=[ramp[min(k, 3)] for k in levels], width=0.6, edgecolor=SURFACE, lw=2)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.05, f"{v:.2f}", ha="center", fontsize=9, fontweight="bold")
    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels([f"{names.get(k, k)}\n{'uses LLM' if k <= 1 else 'no LLM'}" for k in levels], fontsize=9)
    ax.set_ylim(0, 5.3)
    ax.set_ylabel("mean rating (1–5)")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Learning utility per level · {aq['answers_rated']} answers, two blind raters, "
                 f"{aq['agreement_within_1'] * 100:.0f} % within 1 point")
    save(fig, "7_ladder")


# --- 2/3 dashboard screenshots ---------------------------------------------------------------------

def screenshot(name: str, wait_s: int = 20) -> None:
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        sys.exit("no Chrome/Chromium found; take the screenshot by hand at 1280x720")
    fname = {"healthy": "2_dashboard_healthy", "contained": "3_dashboard_contained"}[name]
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        "--window-size=1280,720", "--force-device-scale-factor=2", f"--virtual-time-budget={wait_s * 1000}",
                        f"--screenshot={FIG_DIR / (fname + '.png')}", "http://localhost:8501"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=wait_s + 60)
    print(f"wrote docs/figures/{fname}.png (check it: Streamlit may need a longer --wait)")


def latest_matrix() -> Path | None:
    dirs = sorted(d for d in MATRIX_ROOT.glob("*") if (d / "summary.json").exists()) if MATRIX_ROOT.exists() else []
    return dirs[-1] if dirs else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=["all", "architecture", "timeline", "comparison", "ablation", "shap", "ladder",
                                     "screenshot"])
    ap.add_argument("shot", nargs="?", choices=["healthy", "contained"])
    ap.add_argument("--matrix", type=Path, default=None)
    ap.add_argument("--run", type=Path, default=None, help="run directory for the timeline")
    ap.add_argument("--wait", type=int, default=20)
    args = ap.parse_args()
    if args.what == "screenshot":
        screenshot(args.shot or "healthy", args.wait)
        return
    matrix = args.matrix or latest_matrix()
    jobs = ["architecture", "timeline", "comparison", "shap", "ladder"] if args.what == "all" else [args.what]
    for job in jobs:
        if job == "architecture":
            fig_architecture()
        elif job == "shap":
            fig_shap()
        elif job == "ladder":
            fig_ladder()
        elif matrix is None and args.run is None:
            print(f"skip {job}: no results/matrix/<dir>/summary.json yet (run experiments.run_matrix)")
        elif job == "timeline":
            fig_timeline(args.run or pick_run(matrix))
        elif job == "comparison":
            fig_comparison(matrix)
        elif job == "ablation":
            fig_comparison(matrix, ("cascadeshield", "threshold", "no_graph", "binary_ladder"), "5b_ablation")


if __name__ == "__main__":
    main()
