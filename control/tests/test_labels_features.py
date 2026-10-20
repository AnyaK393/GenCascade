import numpy as np
import pandas as pd

from experiments.labels import episode_labels, failed_state, label, onsets
from resilience_core.features import FEATURE_COLUMNS, STEP_S, build_features

SLO = 16.0


def frame(p95, err=None):
    t = np.arange(len(p95)) * STEP_S + 1000.0
    return pd.DataFrame({"p95_s": p95, "error_rate": err if err is not None else np.zeros(len(p95))},
                        index=pd.Index(t, name="t"))


def test_short_breach_is_not_a_failure():
    p95 = [5.0] * 50 + [20.0] * 10 + [5.0] * 50  # 10 samples = 18 s above SLO
    assert not failed_state(frame(p95), SLO).any()


def test_held_breach_has_one_onset_at_its_start():
    p95 = [5.0] * 50 + [20.0] * 11 + [5.0] * 5 + [20.0] * 20 + [5.0] * 50  # 10 s dip is merged
    failed = failed_state(frame(p95), SLO)
    assert onsets(failed) == [1000.0 + 50 * STEP_S]
    assert failed.iloc[50:86].all()


def test_queue_depth_fails_instantly():
    q = pd.Series([0.0] * 40 + [31.0] + [0.0] * 40, index=frame([1.0] * 81).index)
    assert failed_state(frame([1.0] * 81), SLO, queue=q).sum() == 1


def test_label_window_and_exclusions():
    p95 = [5.0] * 150 + [20.0] * 30 + [5.0] * 30
    lab = label(failed_state(frame(p95), SLO))
    onset_t = 1000.0 + 150 * STEP_S
    t = lab.index.to_numpy()
    pos = t[lab["y"] == 1]
    assert pos.min() == onset_t - 90 and pos.max() == onset_t - STEP_S
    assert not lab.loc[onset_t:onset_t + 29 * STEP_S, "keep"].any()  # inside the failure
    assert not lab.loc[: 1000.0 + 58, "keep"].any()  # warm-up
    assert not lab["keep"].iloc[-10:].any()  # look-ahead runs past the end, no onset
    assert lab.loc[onset_t - 10, "time_to_onset_s"] == 10


def synthetic_series(n=120):
    t = np.arange(n) * STEP_S + 5000.0
    rows = []
    for svc in ["gateway", "orchestrator", "llm_inference", "curriculum_rag", "student"]:
        for i, ti in enumerate(t):
            rows.append({"t": ti, "service": svc, "p95_s": 2 + i * 0.2, "error_rate": 0.0, "rps": 3.0,
                         "inflight": 1.0, "rss_bytes": 1e8 + i * 1e6, "cpu_rate": 0.1,
                         "queue_depth": float(i) if svc == "llm_inference" else np.nan,
                         "tokens_per_s": 40.0, "sessions_active": 10.0})
    return pd.DataFrame(rows)


def test_features_shape_and_trends():
    f = build_features(synthetic_series())
    assert list(f.columns) == ["t", "service", *FEATURE_COLUMNS]
    assert set(f["service"]) == {"llm_inference", "orchestrator", "gateway"}
    llm = f[f["service"] == "llm_inference"].set_index("t")
    late = llm.iloc[-1]
    assert abs(late["p95_s_slope60"] - 0.1) < 1e-9  # +0.2 s per 2 s step
    assert abs(late["llm_queue_depth_delta30"] - 15) < 1e-9
    assert abs(late["queue_growth_per_s"] - 0.5) < 1e-9
    assert late["svc_llm_inference"] == 1 and late["svc_gateway"] == 0
    assert llm.iloc[:29]["p95_s_slope60"].isna().all() and llm.iloc[30:].notna().all().all()
    gw = f[f["service"] == "gateway"].iloc[-1]
    # max over orchestrator (SLO 18 s) and student (SLO 0.3 s); every service has the same p95 here
    assert gw["downstream_pressure"] == max(gw["p95_s"] / 18.0, gw["p95_s"] / 0.3)


def test_live_window_matches_offline_row():
    """The live predictor computes features from the last 70 s only; the final row must match."""
    s = synthetic_series()
    full = build_features(s).groupby("service").tail(1).set_index("service")
    recent = build_features(s[s["t"] >= s["t"].max() - 70]).groupby("service").tail(1).set_index("service")
    pd.testing.assert_frame_equal(full[FEATURE_COLUMNS], recent[FEATURE_COLUMNS])


def test_episode_labels_per_service():
    s = synthetic_series(200)
    labs = episode_labels(s, ["llm_inference", "gateway"])
    assert labs["llm_inference"]["failed"].any()  # queue_depth passes 30
    assert set(labs) == {"llm_inference", "gateway"}


def test_labels_tolerate_missing_signal_columns():
    s = synthetic_series(80).drop(columns=["error_rate"])
    labs = episode_labels(s, ["gateway"])
    assert "y" in labs["gateway"]
