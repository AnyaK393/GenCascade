# Control room image: dependencies only. The code is bind-mounted by compose, so edits need
# no rebuild; rebuild only when pyproject.toml / uv.lock change.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
WORKDIR /app/control
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/control PYTHONUNBUFFERED=1 UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=10
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group ml --no-install-project
