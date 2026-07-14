"""
Centralized application settings.

Why this file exists
---------------------
Every other module (database, security, logging, API routers) needs
configuration values (DB credentials, JWT secret, feature flags, etc.).
Instead of scattering `os.getenv()` calls across the codebase, we define
a single, typed, validated `Settings` object here using pydantic-settings.

How it works
------------
- `Settings` reads from environment variables (and a local `.env` file in
  development) and validates/coerces their types.
- `get_settings()` is wrapped with `lru_cache` so the environment is parsed
  only once per process and the same instance is reused everywhere
  (cheap dependency injection via FastAPI's `Depends(get_settings)`).

Where future code should go
----------------------------
- Add new config fields here as new modules need them (e.g. GITHUB_TOKEN
  for the GitHub Analysis module, SMTP_* for the Report/email module).
- Do NOT hardcode secrets/config elsewhere — always extend this class.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, loaded from environment variables / .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AI Career Toolkit API"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Database ---
    POSTGRES_USER: str = "career_toolkit_user"
    POSTGRES_PASSWORD: str = "change_me"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "career_toolkit"
    DATABASE_URL: str | None = None  # optional explicit override

    # --- Redis ---
    REDIS_ENABLED: bool = False
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Auth / JWT ---
    JWT_SECRET_KEY: str = "change_me_to_a_long_random_string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- CORS ---
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- File uploads ---
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 5

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- ATS Scoring weights (Module 3) ---
    # Relative importance of each of the five ATS scoring categories.
    # Must sum to 1.0; ATSScoringConfig normalizes automatically (with a
    # warning) if a misconfigured .env doesn't. See
    # app/services/ats_scoring/config.py for how these are consumed.
    ATS_WEIGHT_KEYWORD_MATCH: float = 0.30
    ATS_WEIGHT_FORMATTING: float = 0.15
    ATS_WEIGHT_SECTION_COMPLETENESS: float = 0.20
    ATS_WEIGHT_ACHIEVEMENTS: float = 0.20
    ATS_WEIGHT_PARSEABILITY: float = 0.15

    # --- GitHub Profile Analysis (Module 4) ---
    # Personal access token used for GitHub REST API calls. Optional but
    # strongly recommended: unauthenticated requests are capped at 60/hr
    # per PRD section 8/14; an authenticated token raises this to 5,000/hr.
    # Needs no special scopes — only public data is ever requested.
    GITHUB_TOKEN: str | None = None
    GITHUB_API_BASE_URL: str = "https://api.github.com"
    GITHUB_API_TIMEOUT_SECONDS: float = 10.0

    # How many of a user's own (non-fork) repositories, ranked by engagement
    # (stars/forks), are treated as their "best work" — this is the closest
    # REST-API-only proxy for GitHub's Pinned Repositories, which the GitHub
    # REST v3 API cannot read (pinning is GraphQL v4-only). See
    # app/services/github_analysis/top_repos_scorer.py for the full rationale.
    GITHUB_TOP_REPOS_LIMIT: int = 6

    # Of those top repositories, how many get their README fetched and
    # quality-scored. Kept smaller than GITHUB_TOP_REPOS_LIMIT to bound the
    # number of extra API calls (and rate-limit spend) per analysis.
    GITHUB_README_ANALYSIS_LIMIT: int = 5

    # How long a completed GitHub profile analysis is cached for, keyed by
    # username (see app/core/cache.py). Balances rate-limit conservation
    # against staleness — a user re-analyzing right after fixing their
    # profile within this window will see cached (stale) results.
    GITHUB_ANALYSIS_CACHE_TTL_SECONDS: int = 900  # 15 minutes

    # Relative importance of each of the four GitHub scoring categories.
    # Must sum to 1.0; GitHubAnalysisConfig normalizes automatically (with a
    # warning) if a misconfigured .env doesn't. See
    # app/services/github_analysis/config.py for how these are consumed.
    GITHUB_WEIGHT_REPOSITORY_PORTFOLIO: float = 0.25
    GITHUB_WEIGHT_TOP_REPOSITORIES: float = 0.20
    GITHUB_WEIGHT_README_QUALITY: float = 0.30
    GITHUB_WEIGHT_ACTIVITY: float = 0.25

    # --- LinkedIn Optimizer (Module 6: scoring engine) ---
    # Relative importance of each of the eight LinkedIn scoring categories.
    # Must sum to 1.0; LinkedInAnalysisConfig normalizes automatically (with
    # a warning) if a misconfigured .env doesn't. See
    # app/services/linkedin_analysis/config.py for how these are consumed.
    LINKEDIN_WEIGHT_HEADLINE: float = 0.10
    LINKEDIN_WEIGHT_ABOUT: float = 0.15
    LINKEDIN_WEIGHT_EXPERIENCE: float = 0.20
    LINKEDIN_WEIGHT_SKILLS: float = 0.15
    LINKEDIN_WEIGHT_EDUCATION: float = 0.10
    LINKEDIN_WEIGHT_PROJECTS: float = 0.10
    LINKEDIN_WEIGHT_CERTIFICATIONS: float = 0.05
    LINKEDIN_WEIGHT_COMPLETENESS: float = 0.15

    # Number of LinkedIn recommendations that earns a full recommendations
    # sub-score within the Completeness category.
    LINKEDIN_TARGET_RECOMMENDATION_COUNT: int = 2

    # --- Skill-Gap Advisor (Module 5) ---
    # Path to the JSON file backing the role/skill taxonomy (relative to the
    # backend project root, or absolute). Per the task: "Store taxonomy in
    # JSON for now. Later this should migrate to PostgreSQL" — see
    # app/repositories/skill_taxonomy_repository.py for how that swap is
    # designed to happen without touching the service/API layers.
    SKILL_TAXONOMY_PATH: str = "app/data/skill_taxonomy.json"

    @computed_field  # type: ignore[misc]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Build the async SQLAlchemy DB URI unless an explicit override is given."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def SYNC_DATABASE_URI(self) -> str:
        """Sync DB URI used only by Alembic migrations (psycopg2 driver)."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def MAX_UPLOAD_SIZE_BYTES(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @computed_field  # type: ignore[misc]
    @property
    def SKILL_TAXONOMY_ABSOLUTE_PATH(self) -> str:
        """
        Resolve `SKILL_TAXONOMY_PATH` to an absolute path, relative to the
        backend project root (this file's location: app/config/settings.py),
        not to the process's current working directory — so the app finds
        the taxonomy file correctly regardless of where `uvicorn`/pytest is
        launched from. An already-absolute `SKILL_TAXONOMY_PATH` is used as-is.
        """
        path = Path(self.SKILL_TAXONOMY_PATH)
        if path.is_absolute():
            return str(path)
        project_root = Path(__file__).resolve().parent.parent.parent
        return str(project_root / path)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton (parsed once per process)."""
    return Settings()
