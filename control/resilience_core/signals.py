"""The one list of Prometheus signals the control room reads, by service.

The episode runner exports these with query_range and the live collector reads the same
expressions, so training data and live inference see identical definitions.
"""


def _p95(metric: str) -> str:
    return f"histogram_quantile(0.95, sum by (service, le) (rate({metric}_bucket[15s])))"


def _rate(metric: str) -> str:
    return f"sum by (service) (rate({metric}[15s]))"


SIGNALS: dict[str, str] = {
    # every service
    "p95_s": "cs:latency_p95:15s",
    "error_rate": "cs:error_rate:15s",
    "rps": "cs:rps:15s",
    "inflight": "cs_inflight_requests",
    "rss_bytes": "process_resident_memory_bytes",
    "cpu_rate": "rate(process_cpu_seconds_total[15s])",
    # llm_inference
    "queue_depth": "cs_llm_queue_depth",
    "queue_wait_p95_s": _p95("cs_llm_queue_wait_seconds"),
    "tokens_per_s": "cs_llm_tokens_per_second",
    "tokens_rate": _rate("cs_llm_tokens_generated_total"),
    "prompt_tokens_p95": _p95("cs_llm_prompt_tokens"),
    "timeout_rate": _rate("cs_llm_timeouts_total"),
    # orchestrator
    "active_prompts": "cs_orch_active_prompts",
    "degradation_level": "cs_orch_degradation_level",
    "breaker_state": "cs_orch_breaker_state",
    # gateway
    "sessions_active": "cs_sessions_active",
    "shed_rate": _rate("cs_shed_requests_total"),
    # data-quality checks, not features
    "process_start": "process_start_time_seconds",
    "up": 'up{job="platform"}',
    "sample_ts": 'timestamp(up{job="platform"})',
}

QUALITY_SIGNALS = {"process_start", "up", "sample_ts"}


def to_frame(results: dict[str, list[dict]]):
    """Prometheus query_range results per signal -> long DataFrame (t, service, *signals).

    Used for episode exports and by the live predictor, so both build features from the same shape.
    """
    import pandas as pd

    parts = []
    for name, series in results.items():
        for s in series:
            svc = s["metric"].get("service")
            if not svc:
                continue
            vals = s.get("values") or [s["value"]]
            df = pd.DataFrame(vals, columns=["t", name])
            df["t"] = df["t"].astype(float)
            df[name] = pd.to_numeric(df[name], errors="coerce").replace([float("inf"), float("-inf")], float("nan"))
            df["service"] = svc
            parts.append(df.set_index(["t", "service"]))
    if not parts:
        return pd.DataFrame(columns=["t", "service"])
    wide = pd.concat(parts, axis=1)
    wide = wide.T.groupby(level=0).first().T  # a signal split over several series per service
    return wide.reset_index().sort_values(["service", "t"], ignore_index=True)
