"""JSON logs carrying a request_id that travels between services in X-Request-ID."""

import json
import logging
import sys
import time
from contextvars import ContextVar

import httpx

from cs_common.settings import settings

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": round(time.time(), 3), "level": record.levelname, "service": settings.service_name,
               "request_id": request_id.get(), "msg": record.getMessage()}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(settings.service_name)


async def _add_request_id(request: httpx.Request) -> None:
    request.headers["X-Request-ID"] = request_id.get()


def make_client(timeout: float, max_connections: int = 100) -> httpx.AsyncClient:
    """One client per pool, always with an explicit timeout (a default one causes cascades)."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=1.0),
        limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections),
        event_hooks={"request": [_add_request_id]},
    )
