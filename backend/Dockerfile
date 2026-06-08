# Kasa backend image — serves the FastAPI app AND the chain worker (one image, two commands:
# `uvicorn ...` for the API, `python -m worker.main` for the watcher/withdrawer).
#
# Build context MUST be the repo root (`docker build -f backend/Dockerfile .`) because the backend
# needs the shared Python lib + registry data at runtime:
#   packages/shared/python  → kasa_shared (typed registry mirror, on PYTHONPATH)
#   packages/shared/data     → chain/token JSON the asset-seed + boot hash read
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app/backend

# Dependency layer (cached unless pyproject/uv.lock change): install prod deps into /app/backend/.venv.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code + the shared trees the backend imports/reads at runtime.
COPY backend ./
COPY packages/shared/python /app/packages/shared/python
COPY packages/shared/data /app/packages/shared/data

ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONPATH="/app/backend:/app/packages/shared/python"

EXPOSE 8000

# Default: the API. The compose `worker` service overrides this with `python -m worker.main`,
# and the `migrate` service with `alembic upgrade head`.
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
