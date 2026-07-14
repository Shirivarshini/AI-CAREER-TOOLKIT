# =============================================================================
# AI Career Toolkit Backend — Production Dockerfile
#
# Two stages:
#   1. "builder" — has compilers (gcc, libpq-dev) needed to build Python wheels
#      (e.g. psycopg2, cryptography have C extensions). Discarded after use.
#   2. final image — slim, no compilers, runs as a non-root user. Only the
#      installed Python packages and application code are copied in from the
#      builder stage, keeping the final image small and reducing attack
#      surface (no gcc/build tools available to an attacker inside a
#      compromised container).
# =============================================================================

# ---- Stage 1: builder ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build-time system deps: gcc + libpq-dev are needed to compile psycopg2 and
# cryptography's C extensions; discarded when this stage is discarded.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a venv (not system site-packages) so the
# final stage can copy just this one self-contained directory.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ---- Stage 2: final runtime image ----
FROM python:3.12-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime-only system deps: libpq5 (the psycopg2 *runtime* library, not
# libpq-dev's headers/compiler) and curl (used by the HEALTHCHECK below).
# No gcc here — nothing in the final image needs to compile anything.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home-dir /app app

# Bring in the pre-built dependency venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Application code.
COPY . .

# Temporary resume-upload storage (S3 in production — see PRD section 12).
RUN mkdir -p /app/uploads \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Hits our own /api/v1/health endpoint (Module 1) — used by both
# `docker ps` and, in ECS, can back the task/service health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]

# Plain uvicorn (no --reload — that's a docker-compose dev-only override).
# For higher-throughput production traffic, swap for gunicorn with uvicorn
# workers, e.g.:
#   CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
