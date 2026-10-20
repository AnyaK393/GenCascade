"""Event-level evaluation (guide 6.2). Rows come from data/train.parquet plus a `score` column.

- Recall: fraction of failure onsets with at least one alarm (score >= threshold) in the 90 s before them.
- Lead time: onset minus the first alarm in that window (median and 10th percentile).
- False alarms per hour: alarm episodes (runs of consecutive alarming rows) among rows whose window
  has no onset (y = 0), per hour of such time.
- PR-AUC: average precision over rows.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from resilience_core.features import STEP_S

THRESHOLDS = np.round(np.arange(0.05, 0.96, 0.01), 2)


def onset_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (episode, service, onset) that has at least one usable row before it."""
    pos = df[df["y"] == 1].copy()
    pos["onset"] = (pos["t"] + pos["time_to_onset_s"]).round(3)
    return pos


def false_alarms(df: pd.DataFrame, alarm: np.ndarray) -> tuple[int, float]:
    """(alarm runs, hours) over y = 0 rows. A run breaks at gaps between usable rows."""
    neg = df.assign(alarm=alarm)[df["y"] == 0].sort_values(["episode_id", "service", "t"])
    if neg.empty:
        return 0, 0.0
    same = (neg["episode_id"] == neg["episode_id"].shift()) & (neg["service"] == neg["service"].shift())
    contiguous = same & (neg["t"] - neg["t"].shift() <= STEP_S + 1e-6)
    starts = neg["alarm"] & ~(contiguous & neg["alarm"].shift(fill_value=False))
    return int(starts.sum()), len(neg) * STEP_S / 3600


def event_metrics(df: pd.DataFrame, score: np.ndarray, threshold: float) -> dict:
    alarm = np.asarray(score) >= threshold
    pos = onset_table(df.assign(alarm=alarm))
    events = pos.groupby(["episode_id", "service", "onset"])
    caught = events["alarm"].any()
    first_alarm = pos[pos["alarm"]].groupby(["episode_id", "service", "onset"])["t"].min()
    lead = (first_alarm.index.get_level_values("onset") - first_alarm.to_numpy()) if len(first_alarm) else np.array([])
    fa, hours = false_alarms(df, alarm)
    y = df["y"].to_numpy()
    return {
        "threshold": float(threshold),
        "onsets": int(len(caught)),
        "recall": float(caught.mean()) if len(caught) else float("nan"),
        "false_alarms": fa,
        "safe_hours": round(hours, 3),
        "false_alarms_per_hour": fa / hours if hours else float("nan"),
        "lead_median_s": float(np.median(lead)) if len(lead) else float("nan"),
        "lead_p10_s": float(np.percentile(lead, 10)) if len(lead) else float("nan"),
        "pr_auc": float(average_precision_score(y, score)) if 0 < y.sum() < len(y) else float("nan"),
        "rows": int(len(df)),
        "positive_rate": float(y.mean()) if len(y) else float("nan"),
    }


def choose_threshold(df: pd.DataFrame, score: np.ndarray, max_fa_per_hour: float = 1.0) -> float:
    """Lowest threshold with at most max_fa_per_hour false alarms on these rows (guide 6.1 step 5).
    If none qualifies, the one with the fewest false alarms per hour."""
    best, best_fa = THRESHOLDS[-1], float("inf")
    for thr in THRESHOLDS:
        fa, hours = false_alarms(df, np.asarray(score) >= thr)
        rate = fa / hours if hours else 0.0
        if rate <= max_fa_per_hour:
            return float(thr)
        if rate < best_fa:
            best, best_fa = thr, rate
    return float(best)


def threshold_rule_score(df: pd.DataFrame) -> np.ndarray:
    """The Phase 1 rule as a score: clip((p95 / SLO - 0.5) / 0.5, 0, 1); it alarms at 0.8."""
    return np.clip((df["p95_slo_ratio"].to_numpy() - 0.5) / 0.5, 0, 1)
