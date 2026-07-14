"""
Request/response logging middleware.

Why this file exists
---------------------
Production services need visibility into every request: method, path,
status code, and latency — useful for debugging and for verifying the
PRD's NFR: "Resume analysis P95 latency < 5 seconds."

How it works
------------
A plain ASGI-style `BaseHTTPMiddleware` subclass that times each request
and logs a single structured line after it completes. Registered on the
FastAPI app in `app/main.py` via `app.add_middleware(...)`.

Where future code should go
----------------------------
If per-request tracing (e.g. a request ID for correlating logs) is later
needed, generate/attach it here and expose it via a response header.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        return response
