"""Build data/train.parquet from every valid episode (guide 5.4): labels + features per
(t, service), only rows usable for training (see experiments/labels.py).

    uv run python -m experiments.build_dataset
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.labels import episode_labels
from resilience_core.features import FEATURE_COLUMNS, TARGETS, build_features

CONTROL_DIR = Path(__file__).resolve().parents[1]
EPISODES_DIR = CONTROL_DIR / "data" / "episodes"
OUT = CONTROL_DIR / "data" / "train.parquet"
META_COLUMNS = ["episode_id", "category", "scenario", "fault", "seed", "t", "service"]


def load_episodes(root: Path, include_invalid: bool = False):
    for d in sorted(p for p in root.iterdir() if (p / "meta.json").exists()):
        meta = json.loads((d / "meta.json").read_text())
        if meta.get("valid") or include_invalid:
            yield meta, pd.read_parquet(d / "series.parquet")


def episode_rows(meta: dict, series: pd.DataFrame) -> pd.DataFrame:
    feats = build_features(series)
    labs = pd.concat([lab.assign(service=s) for s, lab in episode_labels(series, TARGETS).items()])
    labs = labs.rename_axis("t").reset_index()
    df = feats.merge(labs, on=["t", "service"], how="inner")
    df = df[df.pop("keep")].drop(columns="failed")
    df.insert(0, "episode_id", meta["id"])
    df.insert(1, "category", meta["category"])
    df.insert(2, "scenario", meta["scenario"]["shape"])
    df.insert(3, "fault", meta["fault"]["kind"] if meta["fault"] else "none")
    df.insert(4, "seed", meta["seed"])
    return df


def summary(df: pd.DataFrame, metas: list[dict]) -> str:
    lines = [f"episodes: {len(metas)} valid", f"rows: {len(df)}  positive rate: {df['y'].mean():.3f}", ""]
    lines.append("positive rate by service:\n" + df.groupby("service")["y"].mean().round(3).to_string())
    ep = pd.DataFrame([{
        "scenario": m["scenario"]["shape"], "category": m["category"],
        "fault": m["fault"]["kind"] if m["fault"] else "none",
        "llm_onset": bool(m["onsets"].get("llm_inference")),
    } for m in metas])
    if not ep.empty:
        lines += ["", "episodes and llm failures by scenario:",
                  ep.groupby("scenario")["llm_onset"].agg(episodes="size", with_onset="sum").to_string(),
                  "", "by category:", ep.groupby("category")["llm_onset"].agg(episodes="size", with_onset="sum").to_string(),
                  "", "by fault:", ep.groupby("fault")["llm_onset"].agg(episodes="size", with_onset="sum").to_string()]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--episodes", type=Path, default=EPISODES_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    metas, parts = [], []
    for meta, series in load_episodes(args.episodes):
        metas.append(meta)
        parts.append(episode_rows(meta, series))
    if not parts:
        raise SystemExit(f"no valid episodes in {args.episodes}")
    df = pd.concat(parts, ignore_index=True)
    df = df[[*META_COLUMNS, *FEATURE_COLUMNS, "y", "time_to_onset_s"]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    text = summary(df, metas)
    args.out.with_name("dataset_summary.txt").write_text(text + "\n")
    print(text)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
