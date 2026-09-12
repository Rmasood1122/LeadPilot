# Stage is NAMED because docker-compose.prod.yml builds every backend service
# with `target: production`. Without the name, `docker compose -f
# docker-compose.prod.yml build` failed outright with
#   failed to solve: target stage "production" could not be found
# — so the production compose file could not build at all. `docker compose
# config` does not catch this: it validates and renders, it never resolves
# build targets.
#
# PYTHON_IMAGE defaults to the base Render and docker-compose.prod.yml have
# always used. The dev docker-compose.yml overrides it with the Debian 12
# (bookworm) variant: on a Docker Desktop whose cached Debian trixie layer is
# corrupt, every trixie-based image -- python:3.11-slim included -- dies on its
# first RUN with "exec format error", and re-pulling does not help.
ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE} AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

# System deps kept minimal; psycopg2-binary needs no build toolchain.
#
# The Pango packages are WeasyPrint's, for Feature 5's ROI proof card.
# WeasyPrint is a pure-Python wheel but binds Pango at IMPORT time and raises
# when it is missing, so without these the card silently renders through the
# Pillow fallback instead (see app/services/roi_card.py). fonts-dejavu-core is
# what the card's system font stack resolves to in a slim image -- with no font
# installed at all, every tile renders blank. Cairo is deliberately NOT here:
# WeasyPrint dropped it in v53.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Then copy the application code (source changes don't bust the deps layer).
COPY . .
RUN pip install --no-deps .

EXPOSE 8000

# Default command = API; worker/beat override it (docker-compose `command`,
# Render `dockerCommand`).
#
# ${PORT:-8000} is load-bearing, not decoration. This CMD used to hardcode
# 8000. On 2026-08-20 the Render worker service came up without its
# dockerCommand set, fell back to this line, and bound 8000 while Render was
# routing to $PORT — producing a bare 502 with nothing useful in the logs, and
# silently running the API instead of Celery so no task was ever consumed.
#
# Honouring $PORT means a service that loses its command still answers on the
# right port instead of failing invisibly. The 8000 fallback keeps
# docker-compose (which sets no PORT) working exactly as before.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
