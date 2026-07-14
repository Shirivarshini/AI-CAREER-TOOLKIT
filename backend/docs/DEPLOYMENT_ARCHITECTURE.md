# Deployment Architecture — AWS ECS Fargate

This document explains how the AI Career Toolkit backend runs in production
on AWS: the components, the request path, how configuration/secrets flow
in, how health is monitored, how it scales, and how deployments happen.
It's the detailed companion to the README's "Deploying on AWS ECS"
section — read that first for the short version.

Nothing described here requires application code changes to implement.
That's by design: every environment-specific value (DB host, secrets, log
format, worker count, ...) is already read from `Settings`
(`app/config/settings.py`), which reads from environment variables. Moving
from Docker Compose to ECS is a **configuration and infrastructure**
change, not a code change.

## 1. Component map

```
                                   Internet
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   Route 53 (DNS)         │
                         │   api.yourdomain.com     │
                         └────────────┬─────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │  Application Load Balancer (ALB)  │
                    │  - HTTPS via ACM certificate      │
                    │  - Public subnets                 │
                    │  - Health check: /api/v1/health/  │
                    │    ready  (see §4)                │
                    └────────────────┬───────────────────┘
                                     │  HTTP :8000
                                     ▼
      ┌───────────────────────────────────────────────────────────┐
      │                  ECS Fargate Service                       │
      │                  (private subnets)                         │
      │                                                              │
      │   ┌────────────┐   ┌────────────┐   ┌────────────┐         │
      │   │  Task #1   │   │  Task #2   │   │  Task #N   │  ◄─ autoscaled
      │   │            │   │            │   │            │     (see §6)
      │   │ Gunicorn   │   │ Gunicorn   │   │ Gunicorn   │         │
      │   │ + N Uvicorn│   │ + N Uvicorn│   │ + N Uvicorn│         │
      │   │  workers   │   │  workers   │   │  workers   │         │
      │   │            │   │            │   │            │         │
      │   │ container  │   │ container  │   │ container  │         │
      │   │ HEALTHCHECK│   │ HEALTHCHECK│   │ HEALTHCHECK│         │
      │   │ = liveness │   │ = liveness │   │ = liveness │         │
      │   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘         │
      │         │                │                │                │
      └─────────┼────────────────┼────────────────┼────────────────┘
                │                │                │
                │   stdout/stderr (awslogs driver)  │
                ▼                ▼                ▼
      ┌───────────────────────────────────────────────┐
      │        CloudWatch Logs  (JSON lines)            │
      │        + CloudWatch Container Insights           │
      │        (CPU/memory metrics -> autoscaling, §6)   │
      └───────────────────────────────────────────────┘

                │ every task connects to:
                ▼
      ┌────────────────────┐        ┌───────────────────────┐
      │   RDS PostgreSQL     │        │  ElastiCache Redis     │
      │   (Multi-AZ, private │        │  (optional; private    │
      │    subnets, SSL)     │        │   subnets)              │
      └────────────────────┘        └───────────────────────┘

      ┌────────────────────┐        ┌───────────────────────┐
      │  AWS Secrets Manager │        │  S3 (private bucket)   │
      │  / SSM Parameter     │        │  - uploaded resumes     │
      │  Store                │        │  - LinkedIn PDF exports │
      │  -> injected as env   │        │  (Fargate has no        │
      │     vars at task      │        │   persistent local disk │
      │     launch (§3)        │        │   — see §7)             │
      └────────────────────┘        └───────────────────────┘

      ┌──────────────────────────────────────────────┐
      │  ECR (Elastic Container Registry)               │
      │  - stores the Docker image built from ./Dockerfile│
      │  - CI/CD pushes here, ECS pulls from here (§8)    │
      └──────────────────────────────────────────────┘
```

## 2. What each piece maps to today

Every AWS component above has a direct local-dev equivalent in
`docker-compose.yml`. Deploying is swapping the right-hand column in:

| Local (Docker Compose)              | Production (AWS)                          | App-code awareness       |
|--------------------------------------|--------------------------------------------|---------------------------|
| `db` container (Postgres)            | RDS PostgreSQL (Multi-AZ)                  | `POSTGRES_HOST` env var only |
| `redis` container                    | ElastiCache Redis                          | `REDIS_URL` env var only  |
| `api` container, `uvicorn --reload`  | ECS Fargate task, `gunicorn` (§5)          | none — same image        |
| host-mapped port `8000:8000`         | ALB target group -> task port 8000         | none                      |
| `uploads_data` named volume          | S3 bucket (private)                        | `ResumeFileRepository`'s swap point (see its docstring) |
| `.env` file                          | ECS task definition `environment`/`secrets`| none — `Settings` just reads env vars |
| `docker compose logs`                | CloudWatch Logs (via `awslogs` driver)     | `LOG_FORMAT=json` (§4)    |
| manual `docker compose up --build`   | GitHub Actions -> ECR -> `ecs update-service` | none (§8)              |

The app has zero knowledge of "AWS" as a concept — it only knows
`Settings`. That's what makes this swap purely infrastructural.

## 3. Configuration & secrets flow (Environment Variables / Secrets Manager)

`app/config/settings.py`'s `Settings` class is a `pydantic-settings`
`BaseSettings` subclass — every field is populated from environment
variables (or `.env` locally), case-sensitive, with `extra="ignore"` so an
unrelated env var in the container's environment doesn't break parsing.

In an ECS task definition, each container's configuration comes from two
places, and the app cannot tell (nor needs to tell) which one supplied a
given value:

- **`environment`** — plain key/value pairs, visible in the task
  definition itself (and in the ECS console/API). Use this for anything
  non-sensitive: `APP_ENV`, `LOG_FORMAT`, `LOG_LEVEL`, the `*_WEIGHT_*`
  scoring tunables, `GUNICORN_WORKERS`, `DB_POOL_SIZE`, etc.
- **`secrets`** — each entry names an environment variable and a
  `valueFrom` ARN pointing at an **AWS Secrets Manager** secret or an
  **SSM Parameter Store** parameter. ECS resolves these and injects them
  as environment variables *at task launch*, before the container's
  entrypoint runs — the container process itself never talks to Secrets
  Manager directly. Use this for: `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`,
  `GITHUB_TOKEN`, `DATABASE_URL` (if used as a single override).

This is why `Settings` needing "AWS Secrets Manager compatibility" required
no SDK, no boto3 dependency, and no code change at all: from the
container's point of view, a secret-sourced env var and a plain one are
identical. Compatibility was a property the app already had by reading
config exclusively through `Settings`/env vars (12-factor style) from
Module 1 onward — this task's job was to make sure nothing had
silently drifted from that (see the fail-fast check below), not to add
new plumbing.

**Fail-fast safety net.** `Settings._refuse_insecure_defaults_in_production`
(a Pydantic `model_validator`) raises at process startup — before the app
serves a single request — if `APP_ENV=production` and `JWT_SECRET_KEY` or
`POSTGRES_PASSWORD` still equal their insecure placeholder defaults. In
ECS terms: if a task definition's `secrets` block is misconfigured (wrong
ARN, missing entry, wrong IAM permissions resolving it), the task fails
to start and ECS reports it as a failed deployment — loud and immediate —
instead of the API silently serving production traffic signed with a
publicly-known JWT secret.

**Example task definition excerpt:**

```json
{
  "containerDefinitions": [
    {
      "name": "career-toolkit-api",
      "image": "<account>.dkr.ecr.<region>.amazonaws.com/career-toolkit-api:latest",
      "portMappings": [{ "containerPort": 8000, "protocol": "tcp" }],
      "environment": [
        { "name": "APP_ENV", "value": "production" },
        { "name": "LOG_FORMAT", "value": "json" },
        { "name": "LOG_LEVEL", "value": "INFO" },
        { "name": "POSTGRES_HOST", "value": "career-toolkit.xxxx.us-east-1.rds.amazonaws.com" },
        { "name": "POSTGRES_SSL_MODE", "value": "require" },
        { "name": "GUNICORN_WORKERS", "value": "4" }
      ],
      "secrets": [
        { "name": "POSTGRES_PASSWORD", "valueFrom": "arn:aws:secretsmanager:us-east-1:<account>:secret:career-toolkit/db-password" },
        { "name": "JWT_SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:<account>:secret:career-toolkit/jwt-secret" }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"],
        "interval": 30, "timeout": 5, "retries": 3, "startPeriod": 20
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/career-toolkit-api",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "api"
        }
      },
      "stopTimeout": 30
    }
  ]
}
```

Note the container-level `healthCheck` mirrors the Dockerfile's own
`HEALTHCHECK` (liveness, `/api/v1/health`) — ECS re-declares it in the
task definition so the ECS agent (not just `docker ps`) enforces it; the
two should always point at the same endpoint.

## 4. Health checks vs. readiness checks — two mechanisms, on purpose

This is the single most important operational distinction in this
deployment, so it's worth stating plainly:

| | `GET /api/v1/health` (**liveness**) | `GET /api/v1/health/ready` (**readiness**) |
|---|---|---|
| Checks | Nothing but "is the process serving requests" | Database connectivity (+ Redis, if `REDIS_ENABLED=true`) |
| Used by | Dockerfile `HEALTHCHECK` + ECS container-level `healthCheck` | ALB target group health check |
| On failure | ECS kills and replaces *this specific task* | ALB stops routing traffic to *this specific task* (others keep serving) |
| Appropriate response to an RDS blip | **Wrong** — restarting a healthy process doesn't fix a database outage, and mass-restarting every task at once during an RDS blip is a self-inflicted second outage | **Right** — temporarily pull the affected task(s) out of rotation, let the ALB route to (or wait for) tasks that can still reach the DB |

Mixing these up is a common and costly mistake: pointing the ECS/Docker
`HEALTHCHECK` at a DB-dependent endpoint means a transient RDS failover
(which normally causes 10–30 seconds of connection errors as it completes)
can cascade into ECS killing *every* task simultaneously, which then all
try to restart and reconnect at once — turning a brief, self-healing RDS
event into a full application outage. Keeping liveness dependency-free and
routing only the ALB at readiness avoids this entirely.

`GET /api/v1/health/ready`'s response body also reports *which* dependency
is down (`{"dependencies": [{"name": "database", "ready": false, ...}]}`),
which is useful directly in CloudWatch/ALB access logs when triaging an
incident, without needing to correlate against application logs first.

## 5. Process model inside a task (Gunicorn)

Each ECS task runs one container, and that container runs one Gunicorn
master process (PID 1, via `docker-entrypoint.sh`'s `exec "$@"` — see §9
for why `exec` matters) supervising `GUNICORN_WORKERS` `UvicornWorker`
child processes (`gunicorn_conf.py`). Requests are load-balanced across
those worker processes by the OS (they share a listening socket);
Gunicorn restarts any worker that dies, and proactively recycles workers
after `GUNICORN_MAX_REQUESTS` (± jitter) as a defense against slow memory
growth in long-lived processes.

This gives two independent scaling dimensions:

- **Vertical, within a task**: `GUNICORN_WORKERS`, matched to the task's
  vCPU allocation (`gunicorn_conf.py`'s docstring explains why an explicit
  value beats the computed fallback under Fargate's cgroup CPU quotas).
- **Horizontal, across tasks**: the ECS service's desired task count,
  driven by autoscaling (§6).

## 6. Autoscaling

ECS Service Auto Scaling (Application Auto Scaling) adjusts the service's
desired task count based on a **target tracking policy**. Two natural
metrics for this API:

- **ALB `RequestCountPerTarget`** — scale out when average requests/target
  exceeds a threshold. Good default for an API whose endpoints have very
  different costs (a resume PDF parse vs. a health check), since it
  reflects actual load rather than a CPU proxy for it.
- **ECS Service `CPUUtilization`** (from Container Insights) — simpler to
  reason about, a reasonable starting point before request-count-based
  tuning.

Either way, scaling out adds new tasks behind the same ALB target group
(no code or config changes — new tasks register themselves and start
receiving traffic once their readiness check passes); scaling in removes
tasks gracefully (§9 covers the shutdown sequence). RDS connection
capacity is the usual ceiling on how far this scales — see §7's pool-sizing
note.

## 7. AWS RDS readiness — connection pooling & resilience

Three things make this app "RDS-ready" beyond just pointing
`POSTGRES_HOST` at an RDS endpoint:

1. **TLS**: `POSTGRES_SSL_MODE=require` (via `app/core/database.py`)
   negotiates an encrypted connection — RDS accepts both plain and SSL on
   the same port, so this is opt-in via config, not a separate endpoint.
2. **Pool sizing tuned for multi-task deployments**: `DB_POOL_SIZE` /
   `DB_MAX_OVERFLOW` (per-process) matter because *every* Gunicorn worker
   in *every* ECS task holds its own pool. If you run 4 tasks × 4 workers
   × (pool_size 5 + max_overflow 5), that's up to 160 simultaneous
   connections against RDS's `max_connections` (which is capped by
   instance class — e.g. a `db.t3.medium` defaults to ~150). Two ways to
   stay under that ceiling as you scale: lower `DB_POOL_SIZE`/
   `GUNICORN_WORKERS`, or put **RDS Proxy** in front of RDS (connection
   multiplexing) — the app requires no changes for either, since it's a
   `POSTGRES_HOST` value pointing at the proxy's endpoint instead.
3. **Resilience to RDS Multi-AZ failover**: `pool_pre_ping=True` (always
   on) tests a pooled connection before handing it to a request, so a
   connection left stale by a Multi-AZ failover (RDS's primary swaps to
   the standby, typically 60–120s) gets transparently replaced instead of
   surfacing as a request-level 500. `DB_POOL_RECYCLE_SECONDS` additionally
   retires connections proactively, before RDS's own idle-connection
   timeout would silently drop them.

## 8. CI/CD

```
git push (main branch)
        │
        ▼
GitHub Actions (or CodePipeline)
        │  1. docker build -t career-toolkit-api .
        │  2. docker tag ... <ecr-repo>:<git-sha>
        │  3. docker push <ecr-repo>:<git-sha>
        │  4. aws ecs update-service --cluster ... --service ... \
        │       --force-new-deployment
        ▼
ECS rolls out new tasks (new image), old tasks drain (§9),
ALB shifts traffic once new tasks pass readiness
```

Tag images by commit SHA (not just `:latest`) so a specific deployed image
is always identifiable from the running task definition, and rollback is
"redeploy the previous task definition revision," not "rebuild."

## 9. Graceful shutdown (deploys & scale-in)

Every ECS task stop (a deployment rolling out, scale-in, or a manual
`StopTask`) follows the same sequence:

1. The task is deregistered from the ALB target group (stops receiving
   *new* requests; in-flight ones continue).
2. ECS sends `SIGTERM` to the container's PID 1.
3. `docker-entrypoint.sh` runs `exec "$@"` — replacing the shell process
   with Gunicorn *as PID 1*, rather than leaving Gunicorn as a child of a
   shell that would swallow the signal. This is why `exec` matters:
   without it, `SIGTERM` would hit the wrapper shell, not Gunicorn, and
   workers would only die on the harder `SIGKILL` a few steps later,
   aborting in-flight requests instead of finishing them.
4. Gunicorn's master forwards the shutdown to its workers, which stop
   accepting new requests but finish in-flight ones, for up to
   `GUNICORN_GRACEFUL_TIMEOUT_SECONDS` (25s by default).
5. If the task hasn't exited by ECS's own `stopTimeout` (30s default, set
   explicitly in the task definition — see §3's example), ECS sends
   `SIGKILL`. `GUNICORN_GRACEFUL_TIMEOUT_SECONDS` is deliberately kept a
   few seconds under this so Gunicorn's own graceful shutdown always wins
   the race, rather than requests being hard-killed mid-response.

## 10. Storage: why S3, not the container's local disk

Fargate tasks have no persistent local disk — anything written inside the
container (including `uploads/`, the local dev bind mount's target) is
gone the moment that task stops, and isn't shared across the other tasks
behind the same ALB. `ResumeFileRepository`'s docstring already documents
its local-disk implementation as a swap point for a future S3-backed one
(per the PRD's own S3 target for uploaded resumes) — that swap is exactly
what's required before relying on file persistence in production; nothing
in this deployment-readiness pass changes that storage layer itself.

## 11. Summary — what's now true about this codebase

- **Environment Variables**: every deployment-relevant knob (DB pool/SSL,
  log format, Gunicorn tuning, readiness timeout) is a typed `Settings`
  field with a safe local-dev default, documented in `.env.example`.
- **Production Logging**: `LOG_FORMAT=json` emits one structured JSON
  object per log line (`app/core/logging_config.py`), queryable in
  CloudWatch Logs Insights.
- **Gunicorn**: supervises multiple `UvicornWorker` processes
  (`gunicorn_conf.py`), replacing the single bare Uvicorn process used
  only for local `--reload` dev.
- **Docker Optimizations**: multi-stage build, non-root runtime user,
  `.dockerignore` keeps tests/docs/`.env` out of the image and build
  context.
- **Health Checks / Readiness Checks**: `/api/v1/health` (liveness) and
  `/api/v1/health/ready` (readiness, DB + optional Redis), wired to two
  different AWS mechanisms on purpose (§4).
- **AWS ECS Ready**: stateless containers, `SIGTERM`-safe shutdown via
  `exec`, stdout/stderr-only logging, config entirely via environment.
- **AWS RDS Ready**: SSL support, tuned/documented connection pooling,
  `pool_pre_ping` + recycle for Multi-AZ failover resilience.
- **AWS Secrets Manager Compatible**: config is 100% environment-variable
  driven with no code-level distinction between a plain value and a
  resolved secret, plus a fail-fast check against misconfigured secrets
  in production.
