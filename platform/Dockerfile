# One image for all five services; compose picks the module with SERVICE_MODULE.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DEFAULT_TIMEOUT=120
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install --retries 10 -r requirements.txt
COPY cs_common cs_common
COPY mock_llm mock_llm
COPY services services
COPY data data
COPY web web
CMD uvicorn services.${SERVICE_MODULE}.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-access-log --timeout-keep-alive 30
