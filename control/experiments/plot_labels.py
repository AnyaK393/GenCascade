"""Plot random failing episodes to check by eye that labels sit where expected (guide 5.4):
p95 against time, SLO line, failed state (red), label window y=1 (orange), excluded rows (grey).

    uv run python -m experiments.plot_labels [--n 5] [--service llm_inference]
"""

import argparse
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from experiments.build_dataset import EPISODES_DIR, load_episodes  # noqa: E402
from experiments.labels import episode_labels  # noqa: E402
from resilience_core.settings import settings  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "results" / "label_check"


def shade(ax, t, mask, **kw):
    """Shade each run of True in mask."""
    start = None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = t[i]
        elif not m and start is not None:
            ax.axvspan(start, t[i - 1] + 2, lw=0, **kw)
            start = None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--service", default="llm_inference")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    failing = [(m, s) for m, s in load_episodes(EPISODES_DIR) if m["onsets"].get(args.service)]
    if not failing:
        raise SystemExit(f"no episodes with a {args.service} onset yet")
    picks = random.Random(args.seed).sample(failing, min(args.n, len(failing)))
    slo = settings.slo_s[args.service]

    fig, axes = plt.subplots(len(picks), 1, figsize=(11, 2.6 * len(picks)), squeeze=False)
    for ax, (meta, series) in zip(axes[:, 0], picks):
        lab = episode_labels(series, [args.service])[args.service]
        own = series[series["service"] == args.service].set_index("t").reindex(lab.index)
        t = (lab.index - lab.index[0]).to_numpy()
        ax.plot(t, own["p95_s"], color="black", lw=1.2, label="p95 (s)")
        ax.axhline(slo, color="tab:blue", ls="--", lw=1, label=f"SLO {slo:g} s")
        shade(ax, t, lab["failed"].astype(bool), color="tab:red", alpha=0.25, label="failed")
        shade(ax, t, (lab["y"] == 1) & lab["keep"], color="tab:orange", alpha=0.35, label="y = 1")
        shade(ax, t, ~lab["keep"] & ~lab["failed"].astype(bool), color="grey", alpha=0.15, label="excluded")
        for on in meta["onsets"][args.service]:
            ax.axvline(on - lab.index[0], color="tab:red", lw=1.5)
        if meta["fault"]:
            ax.axvline(meta["fault"]["start_s"], color="tab:purple", ls=":", lw=1.5, label="fault start (kind in title)")
        ax.set_title(f"{meta['id']}  (peak {meta['peak_users']} users)", fontsize=9, loc="left")
        ax.set_ylabel("s")
        ax.set_xlim(0, t[-1])
    axes[-1, 0].set_xlabel("seconds since load start")
    seen = {}
    for ax in axes[:, 0]:
        for h, lbl in zip(*ax.get_legend_handles_labels()):
            seen.setdefault(lbl, h)
    fig.legend(seen.values(), seen.keys(), loc="upper right", ncol=6, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.service}.png"
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
