"""
FastAPI application entrypoint.

Why this file exists
---------------------
This is the single place that assembles the whole application: it creates
the `FastAPI` instance, configures logging, wires up middlewares, global
exception handlers, CORS, and mounts the versioned API router. Every other
module plugs into the app via this file rather than the app being built
ad-hoc.

How it works
------------
- `configure_logging()` runs first so every subsequent log line (including
  startup logs) is properly formatted.
- `create_app()` is a factory function (rather than a bare module-level
  `app = FastAPI()`) so tests can create isolated app instances if needed.
- Lifespan events (`startup`/`shutdown`) are used for anything that needs
  to run once per process — currently just a startup log line; later
  modules (e.g. Redis) can add connection setup/teardown here.

Where future code should go
----------------------------
- New middlewares -> register in `create_app()` via `app.add_middleware(...)`.
- New routers -> add to `app/api/v1/router.py`, not here.
- Startup/shutdown side effects (e.g. warming a cache, verifying DB
  connectivity) -> inside the `lifespan` context manager below.

How to run locally
-------------------
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

How to test
------------
Open Swagger UI at: http://localhost:8000/docs
Try GET /api/v1/health — it should return a 200 with a JSON envelope.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config.settings import get_settings
from app.core.logging_config import configure_logging
from app.middlewares.error_handler import register_exception_handlers
from app.middlewares.logging_middleware import RequestLoggingMiddleware

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once at startup and once at shutdown (ASGI lifespan protocol)."""
    settings = get_settings()
    logger.info("Starting %s in '%s' environment", settings.APP_NAME, settings.APP_ENV)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    """Application factory — builds and configures the FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "AI Career Toolkit API — Resume ATS Analyzer, GitHub Profile Analysis, "
            "LinkedIn Optimizer, and Skill-Gap Advisor."
        ),
        version="1.0.0",
        debug=settings.APP_DEBUG,
        lifespan=lifespan,
    )

    # --- CORS: allow the configured frontend origins only ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS_LIST,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Request logging (latency + status code per request) ---
    app.add_middleware(RequestLoggingMiddleware)

    # --- Global exception handlers -> consistent JSON error envelope ---
    register_exception_handlers(app)

    # --- Versioned API routes ---
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
