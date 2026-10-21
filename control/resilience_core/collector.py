"""Telemetry collector: one Prometheus instant query per signal, grouped by service."""

import asyncio
import logging
import math

import httpx

from .signals import QUALITY_SIGNALS, SIGNALS

log = logging.getLogger(__name__)

QUERIES = {k: v for k, v in SIGNALS.items() if k not in QUALITY_SIGNALS}


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

    async def range_frame(self, window_s: float, step_s: int = 2):
        """Every signal over the last window_s on the step grid, as the feature engine's long frame."""
        import time

        from .signals import to_frame

        end = time.time() // step_s * step_s
        url = self.url.replace("/query", "/query_range")

        async def one(promql: str):
            r = await self.client.get(url, params={"query": promql, "start": end - window_s, "end": end,
                                                   "step": step_s}, timeout=1.5)
            r.raise_for_status()
            return r.json()["data"]["result"]

        try:
            results = await asyncio.gather(*(one(q) for q in SIGNALS.values()))
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise TelemetryError(str(e)) from e
        frame = to_frame(dict(zip(SIGNALS, results)))
        if frame.empty or "up" not in frame or frame.groupby("service")["t"].max().max() < end - 10:
            raise TelemetryError("no recent samples from the platform")
        return frame
