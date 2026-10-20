import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.isotonic import IsotonicRegression

from resilience_core.features import FEATURE_COLUMNS, build_features
from resilience_core.model import FeatureMismatch, ModelBundle, activate, load_active
from resilience_core.predictor import Predictor, describe
from tests.test_labels_features import synthetic_series


@pytest.fixture
def bundle():
    feats = build_features(synthetic_series(120)).dropna()
    X = feats[FEATURE_COLUMNS]
    y = (feats["llm_queue_depth"] > 60).astype(int)  # learnable: queue length
    base = RandomForestClassifier(n_estimators=20, random_state=0).fit(X, y)
    iso = IsotonicRegression(out_of_bounds="clip").fit(base.predict_proba(X)[:, 1], y)
    ttf = RandomForestRegressor(n_estimators=10, random_state=0).fit(X, np.linspace(90, 0, len(X)))
    return ModelBundle(base=base, calibrator=iso, feature_columns=list(FEATURE_COLUMNS), threshold=0.7,
                       name="test_rf", ttf=ttf)


def test_live_prediction_with_factors(bundle):
    out = Predictor(bundle).predict(synthetic_series(120))
    llm = out["llm_inference"]
    assert 0 <= llm["risk"] <= 1 and llm["threshold"] == 0.7 and llm["ttf_s"] >= 0
    assert len(llm["factors"]) == 3 and all(not f["feature"].startswith("svc_") for f in llm["factors"])
    assert all(isinstance(f["label"], str) and f["label"] for f in llm["factors"])


def test_warming_up_until_windows_are_full(bundle):
    out = Predictor(bundle).predict(synthetic_series(20))  # 40 s of data < 60 s window
    assert out["llm_inference"] == {"risk": None, "warming_up": True}


def test_refuses_mismatched_columns(bundle):
    bundle.feature_columns = list(reversed(FEATURE_COLUMNS))
    with pytest.raises(FeatureMismatch):
        Predictor(bundle)


def test_save_activate_load(bundle, tmp_path):
    bundle.save(tmp_path)
    activate(bundle, tmp_path)
    loaded = load_active(tmp_path)
    assert loaded.name == "test_rf" and loaded.threshold == 0.7
    assert load_active(tmp_path / "empty") is None


def test_describe():
    assert describe("llm_queue_depth_slope60", 0.4, 0.2) == "Inference queue growing"
    assert describe("llm_tokens_per_s_delta30", -5, 0.1) == "Tokens per second falling"
    assert describe("llm_tokens_per_s", 12, 0.1) == "Tokens per second low"
    assert describe("p95_s_std30", 3, 0.1) == "Latency p95 unstable"
    assert describe("p95_s_std30", 0, 0.1) == "Latency p95 steady"
    assert describe("sessions_active", 40, 0.3) == "Active sessions high"
