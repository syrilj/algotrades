# Market-runtime backend — Render / Cloud Run / any container host
# Build from monorepo root:
#   docker build -t market-runtime .
# Run:
#   docker run --rm -p 8000:8000 -e LSE_API_KEY=... market-runtime
#
# Health: GET  /health
# Plan:   POST /plan    {"symbol":"SPY","account":1000,"no_model":true}
# Analyze: POST /analyze {"symbol":"SPY","account":1000}

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/tools:/app/services \
    MARKET_RUNTIME_ENV=production \
    PORT=8000

COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-runtime.txt \
    && groupadd --system runtime \
    && useradd --system --gid runtime --home-dir /app --no-create-home runtime

COPY --chown=runtime:runtime services ./services
COPY --chown=runtime:runtime tools ./tools
COPY --chown=runtime:runtime models ./models

# Optional local cache mount at runtime: -v $(pwd)/data_cache:/app/data_cache
RUN mkdir -p /app/data /app/data_cache /app/runs \
    && chown -R runtime:runtime /app/data /app/data_cache /app/runs

USER runtime

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4).read()"

CMD ["sh", "-c", "uvicorn services.market_runtime.server:app --host 0.0.0.0 --port ${PORT}"]
