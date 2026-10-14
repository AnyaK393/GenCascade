"""Contract metrics (contracts/metrics.md): HTTP middleware, /metrics, /health, and helpers
that attach the `service` label automatically."""

import time
import uuid
from functools import partial

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from cs_common.logging import request_id
from cs_common.settings import settings

SERVICE = settings.service_name
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 12, 15, 20, 30)
SKIP_ROUTES = {"/metrics", "/health"}


def metric(cls, name: str, doc: str, labels: tuple[str, ...] = (), **kw):
    """Without extra labels returns the child for this service; with labels returns a
    function taking the extra label values: RESP("0", "llm").inc()."""
    m = cls(name, doc, ["service", *labels], **kw)
    return partial(m.labels, SERVICE) if labels else m.labels(SERVICE)


REQS = metric(Counter, "cs_http_requests_total", "Requests by route and status", ("route", "status"))
DUR = metric(Histogram, "cs_http_request_duration_seconds", "Request latency", ("route",), buckets=BUCKETS)
INFLIGHT = metric(Gauge, "cs_inflight_requests", "Requests being handled")


class MetricsMiddleware:
    """Pure ASGI (BaseHTTPMiddleware costs milliseconds per request). The router writes the
    matched route into the shared scope, so its template is the `route` label."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = next((v.decode() for k, v in scope["headers"] if k == b"x-request-id"), None)
        request_id.set(rid or uuid.uuid4().hex[:12])
        if scope["path"] in SKIP_ROUTES:
            return await self.app(scope, receive, send)
        status = [500]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status[0] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.get().encode()))
            await send(message)

        INFLIGHT.inc()
        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            DUR(route).observe(time.perf_counter() - start)
            REQS(route, str(status[0])).inc()
            INFLIGHT.dec()


def instrument(app: FastAPI, ready=lambda: True) -> None:
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    async def health(response: Response):
        ok = ready()
        response.status_code = 200 if ok else 503
        return {"ok": ok, "service": SERVICE}
