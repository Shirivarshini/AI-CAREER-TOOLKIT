# AI Career Toolkit — Backend

FastAPI backend for the AI Career Toolkit (Resume ATS Analyzer, GitHub
Profile Analysis, LinkedIn Optimizer, Skill-Gap Advisor). See the PRD for
full product scope.

## Current status

**Module 1 — Project Setup & Core Infrastructure** ✅
**Module 2 — Resume Upload API (validation + text extraction)** ✅
**Module 3 — ATS Scoring Engine** ✅
**Module 4 — GitHub Profile Analysis** ✅
**Module 5 — Skill-Gap Advisor** ✅
**Module 6 — Authentication (signup/login/JWT/refresh/logout)** ✅
**Module 7 — Dockerization** ✅
**Module 8 — LinkedIn Optimizer (parsing, heuristics, and scoring engine)** ✅

`POST /api/v1/resume/analyze` accepts a resume (+ optional job description)
and returns extracted text plus a full ATS score. `POST /api/v1/github/analyze`
scores a public GitHub profile. `POST /api/v1/skills/gap` compares a resume
against a target role's skill taxonomy. `POST /api/v1/auth/{signup,login,refresh,logout}`
and `GET /api/v1/auth/me` handle account creation and JWT-based auth.
`POST /api/v1/linkedin/analyze` accepts pasted profile sections or a
LinkedIn PDF export and returns a full profile analysis (see
"LinkedIn Optimizer scoring engine" below).

The scoring engines (`app/services/ats_scoring/`, `app/services/github_analysis/`,
`app/services/skill_gap/`, `app/services/linkedin_analysis/`) are standalone,
framework-agnostic packages — usable outside the API since they have no
FastAPI/Pydantic/DB dependency.

Remaining PRD scope (Reports, Dashboard/history) is layered on top of this.

## Project structure

```
backend/
├── app/                    # config/, core/, api/v1/, services/, repositories/, models/, schemas/, utils/, middlewares/
├── alembic/                # DB migrations
├── tests/                  # Pytest suite
├── uploads/                # Local dev file storage (S3 in prod)
├── requirements.txt
├── Dockerfile              # Multi-stage build, non-root runtime user
├── docker-compose.yml      # api + db (Postgres) + redis, 3 containers
├── docker-entrypoint.sh    # Runs `alembic upgrade head` before starting the app
├── .dockerignore
└── .env.example
```

## Getting started (local, without Docker)

1. Create a virtualenv and install dependencies:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy the environment template and adjust as needed:
   ```bash
   cp .env.example .env
   ```
3. Run PostgreSQL locally (or via Docker — see below) matching the
   credentials in `.env`.
4. Start the API with auto-reload:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open Swagger UI: http://localhost:8000/docs
   Try `GET /api/v1/health` — expect a `200` with a JSON success envelope.

## Getting started (Docker Compose — recommended)

```bash
cp .env.example .env
docker compose up --build
```

This brings up three containers: the FastAPI app (`api`), PostgreSQL
(`db`), and Redis (`redis`). On startup, `api` automatically runs
`alembic upgrade head` (via `docker-entrypoint.sh`) before starting the
server — no manual migration step needed for a fresh environment.

Swagger UI: http://localhost:8000/docs

Stop everything: `docker compose down` (add `-v` to also delete the
Postgres/Redis data volumes — see "Volumes" below).

### Docker networking

All three containers join one Docker-managed bridge network
(`career_toolkit_net`, defined at the bottom of `docker-compose.yml`).
Docker runs an internal DNS server on this network, so containers reach
each other **by service name**, not `localhost` and not the host
machine's IP:

- `api` connects to Postgres at `db:5432` (not `localhost:5432`) and to
  Redis at `redis:6379` — set via the `POSTGRES_HOST` / `REDIS_URL`
  overrides in `docker-compose.yml`'s `api.environment` block.
- The `ports:` mappings (`"8000:8000"`, `"5432:5432"`, `"6379:6379"`) are
  a *separate* concern: they publish a container's port to the **host**
  machine, for you to reach from outside Docker (e.g. `psql -h
  localhost` from your terminal, or a browser hitting
  `localhost:8000/docs`). The `api` container never uses these
  host-mapped ports to reach `db`/`redis` — it uses the internal network
  and service-name DNS directly. This is why `.env.example` sets
  `POSTGRES_HOST=db` (the Docker Compose default) while local
  non-Docker development overrides it to `localhost`.
- Containers *not* on `career_toolkit_net` (there are none here, but if
  you added one without listing it under `networks:`) couldn't resolve
  `db` or `redis` at all — network membership, not just "running in the
  same `docker compose up`", is what makes name resolution work.

### Volumes

Three named volumes, declared once under the top-level `volumes:` key and
mounted into their respective containers:

- `postgres_data` → `db`'s `/var/lib/postgresql/data`. This is where
  Postgres's actual on-disk data files live. Without it, `docker compose
  down && docker compose up` would start from a completely empty
  database every time — the container filesystem is destroyed when a
  container is removed, but a *named volume* is a separate, independent
  storage unit that survives that removal, and gets re-attached to the
  new `db` container on the next `up`.
- `redis_data` → `redis`'s `/data`, same idea — cached responses and
  revoked-refresh-token entries survive a container restart.
- `uploads_data` → `api`'s `/app/uploads`, for any temp resume files
  written during processing.

Separately, `api` also has a **bind mount** (`- .:/app`), not a named
volume — this maps your local `backend/` folder directly into the
container at `/app`, which is what makes `uvicorn --reload` pick up code
edits instantly. Bind mounts and named volumes solve different problems:
bind mounts share a folder you already have on the host (source code);
named volumes give a container its *own* managed storage that has no
host-filesystem equivalent (a database's data files aren't "yours" to
edit directly). This is also why the installed Python packages live at
`/opt/venv` (see `Dockerfile`) instead of inside `/app` — if they were
inside `/app`, the bind mount would shadow them with your local
(dependency-free) source tree and the container would fail to start.

## Deploying later on AWS ECS

The PRD (section 12) targets **ECS Fargate** for the backend, RDS for
Postgres, and ElastiCache for Redis — i.e., the same three logical
services as `docker-compose.yml`, just each replaced by a managed AWS
equivalent instead of a sibling container:

1. **Push the image.** Build and push the existing `Dockerfile` — no
   changes needed — to **ECR** (Elastic Container Registry):
   ```bash
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker build -t career-toolkit-api .
   docker tag career-toolkit-api:latest <account>.dkr.ecr.<region>.amazonaws.com/career-toolkit-api:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/career-toolkit-api:latest
   ```
2. **Replace `db` with RDS, `redis` with ElastiCache.** Provision an RDS
   PostgreSQL instance and an ElastiCache Redis cluster instead of
   running them as containers. Nothing in the app changes — it already
   only knows about `POSTGRES_HOST`/`REDIS_URL` as configuration, not
   "a container named db" — you just point those settings at the RDS
   endpoint and ElastiCache endpoint instead.
3. **Replace `docker-compose.yml`'s env vars with an ECS task
   definition.** Non-secret values (`APP_ENV`, `LOG_LEVEL`,
   `ATS_WEIGHT_*`, etc.) go in the task definition's `environment` list;
   secrets (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `GITHUB_TOKEN`) go in
   **AWS Secrets Manager** or **SSM Parameter Store** and are referenced
   in the task definition's `secrets` list — never baked into the image
   or committed as a plain `.env` (this is exactly why `.dockerignore`
   excludes `.env` from the build context).
4. **Replace `docker-compose.yml`'s bridge network with a VPC.** The ECS
   service runs its tasks inside private subnets of a VPC; RDS and
   ElastiCache live in the same VPC (usually the same private subnets),
   and security groups — not a Compose `networks:` block — control which
   resources can reach which ports. The `api` task's security group needs
   an outbound rule to RDS's port 5432 and ElastiCache's port 6379, and
   RDS/ElastiCache's security groups need an inbound rule from the `api`
   task's security group. This is the direct AWS equivalent of
   `career_toolkit_net`.
5. **Replace the host-mapped ports with an ALB.** Instead of `docker
   compose`'s `"8000:8000"`, an **Application Load Balancer** target
   group points at the ECS service's tasks on port 8000; the ALB is what
   gets the public DNS name / HTTPS certificate (via ACM), not the tasks
   themselves.
6. **Replace `uploads_data` with S3.** ECS Fargate tasks are ephemeral
   and don't support the kind of persistent named volume Compose uses
   for `postgres_data`/`redis_data` (those responsibilities move to
   RDS/ElastiCache anyway, which manage their own storage). For the
   `uploads_data` use case specifically, the PRD already specifies S3
   (private bucket) as the production target — the app would swap
   `ResumeFileRepository`'s local-disk implementation for an S3-backed
   one, exactly the extension point its own docstring calls out.
7. **CI/CD**: GitHub Actions (or CodePipeline) builds the image on
   push, pushes to ECR, and triggers `aws ecs update-service
   --force-new-deployment` — matching the PRD's CI/CD row in section 12.

Nothing about the application code or `Dockerfile` needs to change for
any of this — the entire point of driving configuration through
`Settings`/environment variables (Module 1) rather than hardcoding
`localhost`/`db` anywhere is that swapping "a Postgres container" for
"an RDS endpoint" is a configuration change, not a code change.

## LinkedIn Optimizer scoring engine

`POST /api/v1/linkedin/analyze` accepts either a JSON body of pasted profile
sections (headline, about, experience, education, skills, certifications,
projects, featured, recommendations) or a multipart LinkedIn "Save to PDF"
export — the router picks between them by `Content-Type` (see
`app/api/v1/linkedin.py`). Either way, LinkedIn is never scraped: pasted
content or the user's own PDF export are the only two inputs (PRD 15).

### Architecture

```
app/services/linkedin_analysis/   # framework-agnostic scoring engine
├── types.py                       # LinkedInCategory, LinkedInProfileContext, result dataclasses
├── config.py                      # LinkedInAnalysisWeights / LinkedInAnalysisConfig — every tunable
├── base.py                        # CategoryScorer interface
├── section_scorer.py              # generic wrapper: one linkedin_heuristics function -> one category
├── completeness_scorer.py         # Profile Completeness + Featured + Recommendations
├── insights.py                    # profile_strength label, keyword suggestions, recruiter tips, next steps
└── scorer.py                      # LinkedInProfileScorer — the public entrypoint class

app/utils/linkedin_heuristics.py   # pure, rule-based per-section scoring functions (no AI/LLM)
app/utils/linkedin_section_parser.py  # PDF export text -> structured sections
app/schemas/linkedin.py            # request/response Pydantic contracts
app/services/linkedin_service.py   # orchestrates input handling + calls the engine + maps to the response
```

`LinkedInService` builds one `LinkedInProfileContext` from whichever input
method was used, and calls `LinkedInProfileScorer.score()` exactly once —
that single call returns everything the response needs (overall score,
per-category breakdown, missing sections, rewrite suggestions, keyword
suggestions, recruiter tips, profile strength, and next steps), so the two
input methods can never diverge in how a profile is judged. The engine
itself has no FastAPI/Pydantic/DB import — it's directly reusable from a
script, notebook, or background job (see `tests/test_linkedin_analysis.py`
for examples that call it standalone).

### Scoring logic

Eight weighted categories combine into the overall 0–100 score:

| Category | What it measures | Default weight |
|---|---|---|
| Headline | Length, value-prop structure, absence of cliché filler | 0.10 |
| About | Length, paragraph structure, call-to-action | 0.15 |
| Experience | Bullet structure, action verbs, quantified achievements | 0.20 |
| Skills | Distinct skill count, duplicates | 0.15 |
| Education | Degree/institution keywords, graduation year | 0.10 |
| Projects | Project count, links, description depth | 0.10 |
| Certifications | Certification count, dates | 0.05 |
| Completeness | Core-section presence + Featured + Recommendations | 0.15 |

The first seven categories each delegate to one `app.utils.linkedin_heuristics
.score_*` function — pure, deterministic rule sets already covered by their
own tests in `tests/test_linkedin_heuristics.py`. `section_scorer.py`'s
`SectionCategoryScorer` is a single reusable wrapper around all seven
(rather than seven near-duplicate classes), since they only differ in which
context field they read and which heuristic function judges it. A missing or
whitespace-only section scores a hard 0 with an "add this section"
suggestion, rather than being silently skipped.

**Completeness** (`completeness_scorer.py`) is the one category that reasons
across the whole profile rather than one section: it averages (a) the
fraction of the seven core sections present, (b) whether a Featured section
was provided, and (c) how many Recommendations were provided against
`config.target_recommendation_count`.

### Heuristics vs. the engine layer

Two layers of "no hardcoded values" apply here, deliberately kept separate:

- `app/utils/linkedin_heuristics.py`'s internal thresholds (e.g. "a headline
  under 15 characters loses 35 points") were built and tested in the prior
  part of this feature and are **not** re-tuned by this change — they're
  each section's own rule set, independently testable in isolation.
- `app/services/linkedin_analysis/config.py` is the tunable surface added by
  this change: category **weights** (`LinkedInAnalysisWeights`, normalized to
  sum to 1.0 with a warning if a misconfigured `.env` doesn't), the
  Completeness category's `target_recommendation_count`, the
  `profile_strength_thresholds` score-to-label mapping, the generic
  `recruiter_keyword_pool`, and how many `next_steps`/`keyword_suggestions`
  are returned. All of these are overridable via environment variables (see
  `.env.example`'s `LINKEDIN_WEIGHT_*` / `LINKEDIN_TARGET_RECOMMENDATION_COUNT`)
  or by constructing `LinkedInAnalysisConfig(...)` directly (e.g. in a test
  or script) — nothing about scoring behavior is a magic number buried in a
  scorer.

### Where a future LLM integration would go

Per the PRD's open question (section 15: "hybrid — rules for objective
checks, LLM for qualitative feedback"), this module is **rules-only** by
design — no OpenAI/Claude/Gemini or any other AI provider call exists
anywhere in this package. The architecture is intentionally shaped so an
LLM-based layer can be added later without disturbing the existing rule
engine:

- A qualitative rewrite pass (e.g. "rewrite this About section in a more
  confident tone") would be a new, optional post-processing step in
  `LinkedInService._analyze()`, called after `LinkedInProfileScorer.score()`
  returns — it would enrich `rewrite_suggestions` with LLM-generated prose
  variants rather than replacing the deterministic scores, the same way the
  Resume Analyzer's PRD envisions "rules + LLM" as additive, not either/or.
- A role-aware version of `keyword_suggestions` (see `insights.py`'s
  docstring) is the most natural integration point: swap
  `config.recruiter_keyword_pool`'s generic list for a taxonomy sourced from
  the Skill-Gap Advisor's per-role skills (`app/services/skill_gap/`), or
  from an LLM call informed by `LinkedInProfileContext.target_role` (already
  a field on the context, currently unused).
- Because every scorer returns a plain `RawSignalScore` (score + suggestions
  + details) and the engine has no FastAPI/DB dependency, adding an LLM
  client would only touch `LinkedInService` (or a new optional scorer/
  post-processor) — `scorer.py`'s weighting/aggregation logic would not need
  to change.

## Running tests

```bash
pytest -v
```

## Database migrations (Alembic)

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

In Docker, this already happens automatically on container start (see
`docker-entrypoint.sh`) — you only need to run `alembic upgrade head`
manually for local (non-Docker) development, or `alembic revision
--autogenerate` whenever you add/change a model.
