"""
Gunicorn configuration — production process manager for the FastAPI app.

Why this file exists
---------------------
`uvicorn app.main:app` alone (what `docker-compose.yml` uses for local
dev, with `--reload`) is a single process handling every request on one
event loop. That's fine for local development, but leaves no worker-level
process supervision in production: if one worker's event loop wedges or
a worker leaks memory over days of uptime, nothing notices or recovers.
Gunicorn is a battle-tested process manager that solves exactly this: it
forks and supervises multiple worker processes, restarts any that die,
and (via `GUNICORN_MAX_REQUESTS`) proactively recycles workers before
slow leaks become a problem — while each worker still runs Uvicorn's
`UvicornWorker` class underneath, so requests are still handled by the
same ASGI/async stack as local dev, just supervised by Gunicorn instead
of run directly.

This file is Gunicorn's own config format (a plain Python module;
Gunicorn imports it and reads any of its recognized settings as
module-level variables) — see the `Dockerfile`'s production `CMD`:
    gunicorn --config gunicorn_conf.py app.main:app

How it works
------------
Every tunable here is sourced from `Settings` (`app.config.settings`) —
one source of truth for configuration, consistent with the rest of the
codebase — rather than hardcoded or read from `os.environ` directly a
second time.

- **`workers`**: if `GUNICORN_WORKERS` is set explicitly, use it —
  **strongly recommended in ECS Fargate**. Fargate allocates a specific,
  fractional vCPU quota per task (e.g. 0.5, 1, 2 vCPUs) via Linux cgroups,
  but `os.cpu_count()` inside the container reports the *host* machine's
  total core count (a well-known containerized-Python gotcha), which can
  wildly overestimate how much CPU this task actually has — leading to
  far too many workers fighting over a fraction of a core. If
  `GUNICORN_WORKERS` is left unset, `_default_worker_count()` falls back
  to a conservative formula, but explicit is genuinely better than
  computed here: set `GUNICORN_WORKERS` to match the task definition's
  `cpu` value (a common starting rule of thumb is 2 workers per vCPU for
  an I/O-bound API like this one; benchmark and adjust).
- **`worker_class`**: `uvicorn.workers.UvicornWorker` — makes each
  Gunicorn-supervised worker process run the ASGI app via Uvicorn's own
  event loop, rather than a synchronous WSGI worker.
- **`timeout`** / **`graceful_timeout`**: `timeout` kills a worker that's
  been silent (no response to the master's heartbeat — not the same as
  "a single slow request") for too long. `graceful_timeout` governs
  shutdown: how long a worker gets to finish in-flight requests after
  Gunicorn asks it to stop before being force-killed. This should stay
  comfortably under ECS's own task `stopTimeout` (default 30s, between
  ECS sending SIGTERM and escalating to SIGKILL) — see the deployment
  architecture doc for the full SIGTERM-to-SIGKILL timeline during an ECS
  deployment/scale-in.
- **`max_requests`** / **`max_requests_jitter`**: recycle each worker
  after roughly this many requests (jittered per-worker so they don't all
  restart in the same second) — cheap insurance against slow memory
  growth in long-lived worker processes.
- **`bind`**: always `0.0.0.0:<PORT>` — inside a container there's no
  "localhost-only" concern; the container boundary (and, in ECS, the
  security group) is what actually restricts access, not the bind address.
- **`accesslog`** / **`errorlog`** are set to `"-"` (stdout/stderr, not a
  file) — a container should never write logs to its own (ephemeral,
  per-task) local disk. ECS's `awslogs` log driver captures a container's
  stdout/stderr directly and ships it to CloudWatch Logs; writing to a
  file instead would mean those logs vanish the moment the Fargate task
  stops. (This governs Gunicorn's own request/error logs specifically;
  the application's own structured logs go through `app.core.
  logging_config` independently, also to stdout.)

Where future code should go
----------------------------
Additional Gunicorn-native settings (e.g. `preload_app` — not enabled
here since this app has no expensive at-import-time work worth sharing
across forked workers) can be added as more module-level variables,
following Gunicorn's own settings reference.
"""

import multiprocessing

from app.config.settings import get_settings

_settings = get_settings()


def _default_worker_count() -> int:
    """
    Fallback formula when `GUNICORN_WORKERS` isn't set explicitly — see
    module docstring for why an explicit value is preferred in Fargate.
    The classic `(2 x cores) + 1` formula, capped at 8 as a sane ceiling
    so an unexpectedly large host doesn't spin up an unreasonable number
    of workers for what is still a single container's worth of traffic.
    """
    cores = multiprocessing.cpu_count()
    return max(2, min((2 * cores) + 1, 8))


bind = f"0.0.0.0:{_settings.PORT}"
workers = _settings.GUNICORN_WORKERS or _default_worker_count()
worker_class = _settings.GUNICORN_WORKER_CLASS

timeout = _settings.GUNICORN_TIMEOUT_SECONDS
graceful_timeout = _settings.GUNICORN_GRACEFUL_TIMEOUT_SECONDS
keepalive = _settings.GUNICORN_KEEPALIVE_SECONDS

max_requests = _settings.GUNICORN_MAX_REQUESTS
max_requests_jitter = _settings.GUNICORN_MAX_REQUESTS_JITTER

accesslog = "-"
errorlog = "-"
loglevel = _settings.LOG_LEVEL.lower()

# One log line per request from Gunicorn itself (separate from, and in
# addition to, the app's own RequestLoggingMiddleware) — useful as a
# cross-check that requests are reaching workers at all, independent of
# whether the ASGI app itself is behaving.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(L)ss'
