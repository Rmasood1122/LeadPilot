# Stage is NAMED because docker-compose.prod.yml builds every backend service
# with `target: production`. Without the name, `docker compose -f
# docker-compose.prod.yml build` failed outright with
#   failed to solve: target stage "production" could not be found
# — so the production compose file could not build at all. `docker compose
# config` does not catch this: it validates and renders, it never resolves
# build targets.
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

# System deps kept minimal; psycopg2-binary needs no build toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Then copy the application code (source changes don't bust the deps layer).
COPY . .
RUN pip install --no-deps .

EXPOSE 8000

# Default command = API; worker/beat override `command` in docker-compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
