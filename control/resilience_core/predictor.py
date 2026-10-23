"""Live predictor (guide 6.3): last ~80 s of signals -> the same feature engine as training ->
calibrated failure probability, top-3 SHAP factors in plain words, and an estimated time to stall.

Refuses to start if the feature columns differ from the model's metadata.
"""

import logging

import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS, build_features
from .model import ModelBundle

log = logging.getLogger(__name__)

WINDOW_S = 80  # longest feature window (60 s) + the 30 s delta lag, with margin

BASE_LABELS = {
    "p95_s": "Latency p95", "error_rate": "Error rate", "rps": "Request rate",
    "inflight": "Requests in flight", "rss_bytes": "Memory use", "cpu_rate": "CPU use",
    "llm_queue_depth": "Inference queue", "llm_queue_wait_p95_s": "Inference queue wait",
    "llm_tokens_per_s": "Tokens per second", "llm_prompt_tokens_p95": "Prompt size",
    "llm_timeout_rate": "LLM timeouts", "error_rate_velocity": "Error rate",
    "tokens_ratio": "Tokens per second vs baseline", "p95_slo_ratio": "Latency vs SLO",
    "queue_growth_per_s": "Inference queue", "downstream_pressure": "Downstream latency",
    "sessions_active": "Active sessions", "exam_active": "Exam in progress",
    "degradation_level": "Degradation level",
}
TREND = ("_delta30", "_slope60")
DIRECTIONAL = {"error_rate_velocity", "queue_growth_per_s"}
LOW_IS_BAD = {"llm_tokens_per_s", "tokens_ratio"}


def describe(feature: str, value: float, shap_value: float) -> str:
    """Plain-language name of a feature's contribution, e.g. 'Inference queue growing'."""
    base, stat = feature, ""
    for suffix in ("_mean30", "_std30", "_mean60", "_std60", *TREND):
        if feature.endswith(suffix):
            base, stat = feature[: -len(suffix)], suffix
    name = BASE_LABELS.get(base, base.replace("_", " "))
    if stat in TREND or feature in DIRECTIONAL:
        return f"{name} {'growing' if value > 0 else 'falling' if value < 0 else 'flat'}"
    if stat.startswith("_std"):
        return f"{name} {'unstable' if value > 0 else 'steady'}"
    high = shap_value > 0
    if base in LOW_IS_BAD:
        high = not high
    window = {"_mean30": " (30 s)", "_mean60": " (60 s)"}.get(stat, "")
    return f"{name}{window} {'high' if high else 'low'}"


class Predictor:
    def __init__(self, bundle: ModelBundle):
        bundle.check_columns(FEATURE_COLUMNS)  # refuse to run on a mismatch
        self.bundle = bundle
        self.explainer = None
        try:
            import shap

            self.explainer = shap.TreeExplainer(bundle.base)  # uncalibrated base model (guide 6.3)
        except Exception as e:  # e.g. logistic regression: no tree explainer, predictions still work
            log.warning("no SHAP explainer for %s: %s", bundle.name, e)

    def _shap(self, X: pd.DataFrame) -> np.ndarray | None:
        if self.explainer is None:
            return None
        sv = self.explainer.shap_values(X)
        if isinstance(sv, list):  # older shap: one array per class
            sv = sv[1]
        sv = np.asarray(sv)
        return sv[..., 1] if sv.ndim == 3 else sv

    def factors(self, row: pd.Series, shap_row: np.ndarray, k: int = 3) -> list[dict]:
        order = np.argsort(-np.abs(shap_row))
        out = []
        for i in order:
            f = FEATURE_COLUMNS[i]
            if f.startswith("svc_"):
                continue
            label = describe(f, float(row[f]), float(shap_row[i]))
            if any(o["label"] == label for o in out):
                continue  # e.g. the 30 s and 60 s windows of one signal: show distinct reasons
            out.append({"feature": f, "label": label, "value": float(row[f]), "shap": float(shap_row[i])})
            if len(out) == k:
                break
        return out

    def predict(self, series: pd.DataFrame, exam_active: float = 0.0) -> dict[str, dict]:
        """{service: {risk, raw, threshold, factors, ttf_s}} for each target service, or
        {service: {risk: None, warming_up: True}} until the windows are full."""
        feats = build_features(series, exam_active)
        latest = feats.groupby("service").tail(1).set_index("service")
        X = latest[FEATURE_COLUMNS]
        ready = X.notna().all(axis=1)
        out: dict[str, dict] = {s: {"risk": None, "warming_up": True} for s in X.index[~ready]}
        if not ready.any():
            return out
        Xr = X[ready]
        risk = self.bundle.predict_proba(Xr)
        raw = self.bundle.raw_proba(Xr)
        ttf = self.bundle.predict_ttf(Xr)
        sv = self._shap(Xr)
        for i, svc in enumerate(Xr.index):
            out[svc] = {
                "risk": float(risk[i]), "raw": float(raw[i]), "threshold": self.bundle.threshold,
                "factors": self.factors(Xr.iloc[i], sv[i]) if sv is not None else [],
                "ttf_s": float(max(0.0, ttf[i])) if ttf is not None else None,
            }
        return out
