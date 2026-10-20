"""Failure labels (contracts/features.md, guide 5.1).

Failed state of a service at t: p95 > SLO held >= 20 s, or error rate > 5 % held >= 20 s, or
(llm_inference only) queue depth > 30. Failed runs closer than 20 s are merged, so one stall
with a brief dip counts once. Onset is the first timestamp of a failed run.
y(t) = 1 if an onset falls in (t, t + 90 s]. Rows inside a failed state are excluded, and so are
rows whose 90 s look-ahead runs past the end of the episode without an onset (unknown outcome).
"""

import numpy as np
import pandas as pd

from resilience_core.features import SPARSE_FILL_ROWS, STEP_S, WARMUP_S
from resilience_core.settings import settings

HOLD_S = 20
HORIZON_S = 90
MERGE_GAP_S = 20
ERROR_LIMIT = 0.05
QUEUE_LIMIT = 30


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of consecutive True values."""
    padded = np.concatenate([[False], mask, [False]]).astype(int)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2], edges[1::2]))


def _held(mask: np.ndarray, hold_s: float) -> np.ndarray:
    """Keep only runs lasting at least hold_s (n samples span (n - 1) * STEP_S seconds)."""
    out = np.zeros_like(mask, dtype=bool)
    for a, b in _runs(mask):
        if (b - a - 1) * STEP_S >= hold_s:
            out[a:b] = True
    return out


def _merge(mask: np.ndarray, gap_s: float) -> np.ndarray:
    out = mask.copy()
    runs = _runs(mask)
    for (_, b), (a2, _) in zip(runs, runs[1:]):
        if (a2 - b) * STEP_S < gap_s:
            out[b:a2] = True
    return out


def failed_state(own: pd.DataFrame, slo_s: float, queue: pd.Series | None = None) -> pd.Series:
    """own: one service's signals on the time grid (index t). queue: llm queue depth, if it applies."""
    p95 = own["p95_s"].ffill(limit=SPARSE_FILL_ROWS).fillna(0).to_numpy()
    err = own["error_rate"].fillna(0).to_numpy()
    failed = _held(p95 > slo_s, HOLD_S) | _held(err > ERROR_LIMIT, HOLD_S)
    if queue is not None:
        failed |= queue.fillna(0).to_numpy() > QUEUE_LIMIT
    return pd.Series(_merge(failed, MERGE_GAP_S), index=own.index)


def onsets(failed: pd.Series) -> list[float]:
    """Start times of failed runs. A run already under way at the first row has no observed onset."""
    return [failed.index[a] for a, _ in _runs(failed.to_numpy()) if a > 0]


def label(failed: pd.Series, t_end: float | None = None) -> pd.DataFrame:
    """Per t: y, keep (row is usable for training) and time_to_onset_s (NaN if none ahead)."""
    t = failed.index.to_numpy(dtype=float)
    t_end = t[-1] if t_end is None else t_end
    on = np.array(onsets(failed), dtype=float)
    nxt_idx = np.searchsorted(on, t, side="right")  # first onset strictly after t
    nxt = np.full(len(t), np.nan)
    ahead = nxt_idx < len(on)
    nxt[ahead] = on[nxt_idx[ahead]]
    tto = nxt - t
    y = (tto > 0) & (tto <= HORIZON_S)
    keep = (~failed.to_numpy()) & (t >= t[0] + WARMUP_S) & ((t + HORIZON_S <= t_end) | y)
    return pd.DataFrame({"y": y.astype(int), "keep": keep, "time_to_onset_s": tto}, index=failed.index)


def episode_labels(series: pd.DataFrame, services: list[str], slo_s: dict[str, float] | None = None
                   ) -> dict[str, pd.DataFrame]:
    """Labels for each service of one episode's long-format export (columns t, service, signals)."""
    slo_s = slo_s or settings.slo_s
    grid = np.arange(series["t"].min(), series["t"].max() + STEP_S / 2, STEP_S)
    by = {s: g.set_index("t").reindex(grid) for s, g in series.groupby("service")}
    queue = by["llm_inference"]["queue_depth"] if "llm_inference" in by else None
    out = {}
    for s in services:
        if s not in by:
            continue
        failed = failed_state(by[s], slo_s[s], queue if s == "llm_inference" else None)
        lab = label(failed)
        lab["failed"] = failed.astype(int)
        out[s] = lab
    return out
