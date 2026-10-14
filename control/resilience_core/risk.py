"""Phase 1 placeholder risk: how close p95 latency is to the SLO. Replaced by the ML predictor in Phase 3."""


def threshold_risk(p95_s: float | None, slo_s: float) -> float:
    """risk = clip((p95 / SLO - 0.5) / 0.5, 0, 1): 0 at half the SLO, 1 at the SLO."""
    if p95_s is None or slo_s <= 0:
        return 0.0
    return min(1.0, max(0.0, (p95_s / slo_s - 0.5) / 0.5))
