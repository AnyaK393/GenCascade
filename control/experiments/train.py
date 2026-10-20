"""Train, calibrate and evaluate the failure predictor (guide 6.1-6.2).

    uv run python -m experiments.train            # evaluate all models, save them, activate rf_v1

- Splits are by episode, never by row: 20 % of episodes (stratified by category) are held out;
  GroupKFold over the rest gives out-of-fold scores for calibration and the threshold.
- Isotonic calibration is fitted on out-of-fold raw scores, so it never sees its own training rows.
- Threshold: the lowest with at most 1 false alarm per hour of non-failing time (out-of-fold).
- Unseen-fault test: train on every episode without a `leak` fault, test on the leak episodes.
- The saved models are refitted on every episode; the holdout numbers go in their metadata.
Results: results/model_results.md, results/model_results.json, results/reliability.png.
"""

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from experiments.build_dataset import OUT as TRAIN_PATH  # noqa: E402
from experiments.evaluate import choose_threshold, event_metrics, threshold_rule_score  # noqa: E402
from resilience_core.features import FEATURE_COLUMNS  # noqa: E402
from resilience_core.model import MODELS_DIR, ModelBundle, activate  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
EVAL_SERVICE = "llm_inference"  # the contained service; metrics are reported on its rows
SEED = 0


def model_specs() -> dict:
    specs = {
        "lr_v1": lambda: make_pipeline(StandardScaler(), LogisticRegression(
            class_weight="balanced", max_iter=2000, C=0.5)),
        "rf_v1": lambda: RandomForestClassifier(
            n_estimators=300, max_depth=12, min_samples_leaf=5, class_weight="balanced",
            n_jobs=-1, random_state=SEED),
    }
    try:
        from xgboost import XGBClassifier

        specs["xgb_v1"] = lambda: XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            eval_metric="logloss", tree_method="hist", n_jobs=4, random_state=SEED)
    except ImportError:
        pass
    return specs


def split_episodes(df: pd.DataFrame, test_frac: float = 0.2) -> tuple[list[str], list[str]]:
    """Hold out test_frac of episodes per category (at least one per category with 3+ episodes)."""
    rng = random.Random(SEED)
    train, test = [], []
    eps = df.groupby("episode_id")["category"].first()
    for _, ids in eps.groupby(eps):
        ids = sorted(ids.index)
        rng.shuffle(ids)
        n_test = round(len(ids) * test_frac) or (1 if len(ids) >= 3 else 0)
        test += ids[:n_test]
        train += ids[n_test:]
    return train, test


def X_of(df: pd.DataFrame) -> pd.DataFrame:
    return df[FEATURE_COLUMNS].fillna(0.0)


def oof_raw(make, df: pd.DataFrame) -> np.ndarray:
    """Out-of-fold raw scores with GroupKFold by episode."""
    groups = df["episode_id"].to_numpy()
    n_splits = min(5, len(set(groups)))
    out = np.full(len(df), np.nan)
    for tr, va in GroupKFold(n_splits=n_splits).split(df, df["y"], groups):
        if df["y"].iloc[tr].nunique() < 2:  # a fold without positives: no signal, predict the base rate
            out[va] = df["y"].iloc[tr].mean()
            continue
        m = make().fit(X_of(df.iloc[tr]), df["y"].iloc[tr])
        out[va] = m.predict_proba(X_of(df.iloc[va]))[:, 1]
    return out


def fit_bundle(name: str, make, df: pd.DataFrame) -> tuple[ModelBundle, np.ndarray]:
    """Calibrator and threshold from out-of-fold scores; base model refitted on all of df."""
    raw = oof_raw(make, df)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(raw, df["y"])
    cal = iso.predict(raw)
    svc = (df["service"] == EVAL_SERVICE).to_numpy()
    threshold = choose_threshold(df[svc], cal[svc])
    base = make().fit(X_of(df), df["y"])
    return ModelBundle(base=base, calibrator=iso, feature_columns=list(FEATURE_COLUMNS),
                       threshold=threshold, name=name), cal


def fit_ttf(df: pd.DataFrame) -> RandomForestRegressor | None:
    pos = df[df["y"] == 1]
    if len(pos) < 20:
        return None
    return RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=5, n_jobs=-1,
                                 random_state=SEED).fit(X_of(pos), pos["time_to_onset_s"])


def evaluate_split(make, name: str, train: pd.DataFrame, test: pd.DataFrame) -> tuple[dict, np.ndarray]:
    bundle, oof_cal = fit_bundle(name, make, train)
    t = test[test["service"] == EVAL_SERVICE]
    m = event_metrics(t, bundle.predict_proba(X_of(t)), bundle.threshold) if len(t) else {}
    return m, oof_cal


def reliability_plot(curves: dict[str, tuple[np.ndarray, np.ndarray]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], ls="--", color="grey", lw=1, label="perfect")
    for name, (y, p) in curves.items():
        frac, mean = calibration_curve(y, p, n_bins=10, strategy="quantile")
        ax.plot(mean, frac, marker="o", lw=1.2, label=name)
    ax.set_xlabel("predicted probability (out-of-fold, calibrated)")
    ax.set_ylabel("observed failure rate")
    ax.set_title("Reliability", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def fmt(v, digits=2):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{digits}f}"


def results_markdown(rows: list[dict], unseen: dict, info: dict) -> str:
    lines = [f"# Predictor results ({info['date']})", "",
             f"Episodes: {info['episodes']} ({info['train_episodes']} train / {info['test_episodes']} held out). "
             f"Metrics on `{EVAL_SERVICE}` rows of the held-out episodes. "
             "Threshold chosen on out-of-fold training scores (≤ 1 false alarm per hour).", "",
             "| Model | Threshold | PR-AUC | Recall | False alarms / h | Lead median (s) | Lead p10 (s) | Onsets |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['model']} | {fmt(r.get('threshold'))} | {fmt(r.get('pr_auc'))} | {fmt(r.get('recall'))} | "
                     f"{fmt(r.get('false_alarms_per_hour'))} | {fmt(r.get('lead_median_s'), 0)} | "
                     f"{fmt(r.get('lead_p10_s'), 0)} | {r.get('onsets', '–')} |")
    lines += ["", "## Unseen-fault test (trained without `leak`, tested on `leak` episodes)", ""]
    if unseen:
        lines.append(f"Episodes: {unseen['train_episodes']} train / {unseen['test_episodes']} leak. "
                     f"Recall {fmt(unseen.get('recall'))} over {unseen.get('onsets', 0)} onsets, "
                     f"{fmt(unseen.get('false_alarms_per_hour'))} false alarms per hour, "
                     f"PR-AUC {fmt(unseen.get('pr_auc'))}.")
    else:
        lines.append("Not run: no `leak` episodes, or none without it.")
    if info.get("ttf_mae_s") is not None:
        lines += ["", f"Time-to-failure regressor (estimate): MAE {info['ttf_mae_s']:.0f} s on held-out rows with y = 1."]
    lines += ["", f"*Small dataset warning*: {info['episodes']} episodes. Re-run after the full 50+ episode dataset."
              if info["episodes"] < 50 else ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=TRAIN_PATH)
    ap.add_argument("--activate", default="rf_v1", help="model the live predictor loads (models/metadata.json)")
    args = ap.parse_args()

    df = pd.read_parquet(args.data)
    train_ids, test_ids = split_episodes(df)
    train, test = df[df["episode_id"].isin(train_ids)], df[df["episode_id"].isin(test_ids)]
    if train["episode_id"].nunique() < 2 or train["y"].nunique() < 2:
        raise SystemExit("need at least 2 training episodes with both labels; record more episodes")

    rows, curves = [], {}
    for name, make in model_specs().items():
        m, oof_cal = evaluate_split(make, name, train, test)
        svc = (train["service"] == EVAL_SERVICE).to_numpy()
        curves[name] = (train["y"].to_numpy()[svc], oof_cal[svc])
        rows.append({"model": name, **m})
        print(f"{name:<8} " + "  ".join(f"{k}={fmt(v) if isinstance(v, float) else v}" for k, v in m.items()), flush=True)
    t = test[test["service"] == EVAL_SERVICE]
    if len(t):
        rows.append({"model": "threshold rule (Phase 1)", **event_metrics(t, threshold_rule_score(t), 0.8)})

    leak = df["fault"] == "leak"
    unseen = {}
    if leak.any() and (~leak).any() and df[~leak]["y"].nunique() == 2:
        m, _ = evaluate_split(model_specs()["rf_v1"], "rf_unseen", df[~leak], df[leak])
        unseen = {**m, "train_episodes": df[~leak]["episode_id"].nunique(),
                  "test_episodes": df[leak]["episode_id"].nunique()}

    ttf = fit_ttf(train)
    ttf_mae = None
    tp = test[test["y"] == 1]
    if ttf is not None and len(tp):
        ttf_mae = float(np.mean(np.abs(ttf.predict(X_of(tp)) - tp["time_to_onset_s"])))

    info = {"date": f"{datetime.now():%Y-%m-%d %H:%M}", "episodes": df["episode_id"].nunique(),
            "train_episodes": len(train_ids), "test_episodes": len(test_ids), "ttf_mae_s": ttf_mae}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    reliability_plot(curves, RESULTS_DIR / "reliability.png")
    (RESULTS_DIR / "model_results.json").write_text(json.dumps(
        {"info": info, "holdout": rows, "unseen_fault": unseen, "test_episodes": test_ids}, indent=2, default=float))
    text = results_markdown(rows, unseen, info)
    (RESULTS_DIR / "model_results.md").write_text(text)
    print("\n" + text)

    # Deployable models: refitted on every episode; holdout numbers recorded alongside.
    holdout = {r["model"]: r for r in rows}
    for name, make in model_specs().items():
        bundle, _ = fit_bundle(name, make, df)
        if name == "rf_v1":
            bundle.ttf = fit_ttf(df)
        bundle.metadata = {
            "trained_at": info["date"], "episodes": sorted(df["episode_id"].unique()),
            "label_horizon_s": 90, "eval_service": EVAL_SERVICE,
            "holdout_metrics": holdout.get(name), "unseen_fault": unseen if name == "rf_v1" else None,
            "threshold_rule": "lowest threshold with <= 1 false alarm per hour, out-of-fold on all episodes",
        }
        bundle.save()
        if name == args.activate:
            activate(bundle)
            print(f"activated {name} (threshold {bundle.threshold:.2f}) -> {MODELS_DIR / 'metadata.json'}")


if __name__ == "__main__":
    main()
