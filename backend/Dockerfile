# HanRAG API. Build from the repo root:  docker build -f backend/Dockerfile .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app/backend
# Dependencies first, so code changes do not reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY eval/dataset /app/eval/dataset
COPY eval/results /app/eval/results
RUN uv sync --frozen --no-dev

# Models (about 1.2 GB) download on first start into a volume, not into the image.
ENV PATH=/app/backend/.venv/bin:$PATH \
    MODEL_CACHE_DIR=/models \
    DATA_DIR=/data
RUN useradd --create-home hanrag && mkdir -p /models /data /app/data \
    && chown -R hanrag /models /data /app/data
USER hanrag

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
