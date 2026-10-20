"""Feature engine (contracts/features.md). The same function builds training rows from
episode exports and the live row from the last ~70 s of Prometheus data, so the two cannot drift.

Input: a long frame with one row per (t, service) and one column per signal in
`signals.SIGNALS`. Output: one row per (t, target service) with FEATURE_COLUMNS.
"""

import numpy as np
import pandas as pd

from .settings import TOKENS_PER_S_BASELINE, settings

STEP_S = 2
WARMUP_S = 60  # the longest window; rows before t0 + WARMUP_S have incomplete features
TARGETS = ["llm_inference", "orchestrator", "gateway"]  # services with failure labels
# What each service calls synchronously (the dependency graph, guide 6.4).
DOWNSTREAM = {
    "gateway": ["orchestrator", "student"],
    "orchestrator": ["llm_inference", "curriculum_rag", "student"],
    "llm_inference": [],
}

INSTANT = ["p95_s", "error_rate", "rps", "inflight", "rss_bytes", "cpu_rate"]  # own service
LLM = ["queue_depth", "queue_wait_p95_s", "tokens_per_s", "prompt_tokens_p95", "timeout_rate"]
# (column, window s, statistic); trend inputs are own-service or llm_ signals
TREND_INPUTS = ["p95_s", "rps", "inflight", "rss_bytes",
                "llm_queue_depth", "llm_tokens_per_s", "llm_queue_wait_p95_s"]
TREND_STATS = ["mean30", "std30", "mean60", "std60", "delta30", "slope60"]
# Latency-like signals are missing when a window has no requests; carry the last value briefly.
SPARSE = {"p95_s", "queue_wait_p95_s", "prompt_tokens_p95", "tokens_per_s"}
SPARSE_FILL_ROWS = 7  # ~15 s, one rate window

FEATURE_COLUMNS: list[str] = (
    INSTANT
    + [f"llm_{s}" for s in LLM]
    + [f"{c}_{st}" for c in TREND_INPUTS for st in TREND_STATS]
    + ["error_rate_velocity", "tokens_ratio", "p95_slo_ratio", "queue_growth_per_s"]
    + ["downstream_pressure"]
    + ["sessions_active", "exam_active", "degradation_level"]
    + [f"svc_{s}" for s in TARGETS]
)


def _grid(series: pd.DataFrame) -> pd.Index:
    t = series["t"]
    return pd.Index(np.arange(t.min(), t.max() + STEP_S / 2, STEP_S), name="t")


def _service_frame(series: pd.DataFrame, service: str, grid: pd.Index) -> pd.DataFrame:
    """All signals of one service on the full time grid, with gaps filled."""
    df = series[series["service"] == service].set_index("t").drop(columns="service")
    df = df[~df.index.duplicated()].reindex(grid)
    for col in df.columns:
        if col in SPARSE:
            df[col] = df[col].ffill(limit=SPARSE_FILL_ROWS)
    if "tokens_per_s" in df:
        # 0 or missing means nothing was generated recently (e.g. a fresh platform), not a slow
        # model: use the calibrated baseline so "no evidence" never reads as "extremely slow".
        df["tokens_per_s"] = df["tokens_per_s"].where(df["tokens_per_s"] > 0, TOKENS_PER_S_BASELINE)
    return df.fillna(0.0)


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name] if name in df else pd.Series(0.0, index=df.index)


def _slope(x: pd.Series, rows: int) -> pd.Series:
    """Least-squares slope per second over a rolling window."""
    t = pd.Series(x.index.to_numpy(dtype=float), index=x.index)
    return x.rolling(rows, min_periods=rows).cov(t) / t.rolling(rows, min_periods=rows).var()


def _trend(x: pd.Series) -> dict[str, pd.Series]:
    r30, r60 = 30 // STEP_S, 60 // STEP_S
    return {
        "mean30": x.rolling(r30, min_periods=r30).mean(),
        "std30": x.rolling(r30, min_periods=r30).std(),
        "mean60": x.rolling(r60, min_periods=r60).mean(),
        "std60": x.rolling(r60, min_periods=r60).std(),
        "delta30": x - x.shift(r30),
        "slope60": _slope(x, r60),
    }


def build_features(series: pd.DataFrame, exam_active: float | pd.Series = 0.0,
                   slo_s: dict[str, float] | None = None) -> pd.DataFrame:
    """Return one row per (t, target service): columns t, service, *FEATURE_COLUMNS.

    `series` needs columns t (unix seconds on a STEP_S grid), service, and signal columns.
    Rows inside the first WARMUP_S seconds contain NaN trend features.
    """
    slo_s = slo_s or settings.slo_s
    grid = _grid(series)
    frames = {s: _service_frame(series, s, grid) for s in series["service"].unique()}
    empty = pd.DataFrame(index=grid)
    llm = frames.get("llm_inference", empty)
    gateway = frames.get("gateway", empty)
    orch = frames.get("orchestrator", empty)

    out = []
    for target in TARGETS:
        own = frames.get(target, empty)
        f = pd.DataFrame(index=grid)
        for s in INSTANT:
            f[s] = _col(own, s)
        for s in LLM:
            f[f"llm_{s}"] = _col(llm, s)
        for c in TREND_INPUTS:
            for st, v in _trend(f[c]).items():
                f[f"{c}_{st}"] = v
        f["error_rate_velocity"] = (f["error_rate"] - f["error_rate"].shift(10 // STEP_S)) / 10
        f["tokens_ratio"] = f["llm_tokens_per_s"] / TOKENS_PER_S_BASELINE
        f["p95_slo_ratio"] = f["p95_s"] / slo_s[target]
        f["queue_growth_per_s"] = f["llm_queue_depth_delta30"] / 30
        pressure = [_col(frames.get(d, empty), "p95_s") / slo_s[d] for d in DOWNSTREAM[target]]
        f["downstream_pressure"] = pd.concat(pressure, axis=1).max(axis=1) if pressure else 0.0
        f["sessions_active"] = _col(gateway, "sessions_active")
        f["exam_active"] = exam_active.reindex(grid).fillna(0.0) if isinstance(exam_active, pd.Series) else exam_active
        f["degradation_level"] = _col(orch, "degradation_level")
        for s in TARGETS:
            f[f"svc_{s}"] = float(s == target)
        f["service"] = target
        out.append(f.reset_index())

    return pd.concat(out, ignore_index=True)[["t", "service", *FEATURE_COLUMNS]]
