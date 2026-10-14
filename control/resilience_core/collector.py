"""Telemetry collector: one Prometheus instant query per signal, grouped by service."""

import asyncio
import logging
import math

import httpx

log = logging.getLogger(__name__)

# snapshot key -> PromQL. Recording rules keep definitions identical for every consumer.
QUERIES = {
    "p95_s": "cs:latency_p95:15s",
    "error_rate": "cs:error_rate:15s",
    "rps": "cs:rps:15s",
    "inflight": "cs_inflight_requests",
    "rss_bytes": "process_resident_memory_bytes",
    "cpu_rate": "rate(process_cpu_seconds_total[15s])",
    "queue_depth": "cs_llm_queue_depth",
    "tokens_per_s": "cs_llm_tokens_per_second",
    "sessions_active": "cs_sessions_active",
    "degradation_level": "cs_orch_degradation_level",
    "breaker_state": "cs_orch_breaker_state",
}


class TelemetryError(RuntimeError):
    """Prometheus could not be queried; the cycle has no fresh data."""


def _value(raw: str) -> float | None:
    v = float(raw)
    return None if math.isnan(v) or math.isinf(v) else v


class Collector:
    def __init__(self, prometheus_url: str, client: httpx.AsyncClient):
        self.url = prometheus_url.rstrip("/") + "/api/v1/query"
        self.client = client

    async def _query(self, promql: str) -> list[dict]:
        r = await self.client.get(self.url, params={"query": promql}, timeout=1.5)
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "success":
            raise TelemetryError(body.get("error", "query failed"))
        return body["data"]["result"]

    async def collect(self) -> dict[str, dict[str, float | None]]:
        """Return {service: {signal: value}}. Raises TelemetryError if Prometheus is unreachable."""
        try:
            results = await asyncio.gather(*(self._query(q) for q in QUERIES.values()))
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise TelemetryError(str(e)) from e

        by_service: dict[str, dict[str, float | None]] = {}
        for key, series in zip(QUERIES, results):
            for s in series:
                svc = s["metric"].get("service")
                if svc:
                    by_service.setdefault(svc, {})[key] = _value(s["value"][1])
        return by_service

    async def targets_up(self) -> dict[str, bool]:
        series = await self._query('up{job="platform"}')
        return {s["metric"].get("service", "?"): s["value"][1] == "1" for s in series}
