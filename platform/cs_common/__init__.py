"""Shared platform library: settings, JSON logging, contract metrics, Redis helpers."""

from fastapi import FastAPI

from cs_common.logging import setup_logging
from cs_common.metrics import instrument
from cs_common.settings import settings


def create_app(ready=lambda: True, **kw) -> FastAPI:
    setup_logging()
    app = FastAPI(title=settings.service_name, **kw)
    instrument(app, ready)
    return app
