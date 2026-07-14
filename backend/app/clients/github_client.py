"""
GitHub REST API client.

Why this file exists
---------------------
`GitHubAnalysisService` needs profile, repository, README, and activity
data from GitHub. This class is the *only* place in the codebase that
knows about GitHub's REST API shape (endpoints, headers, pagination,
rate-limit headers, base64-encoded file content) — the service layer
works with plain dicts/strings and typed exceptions, never `httpx`.

How it works
------------
- One shared `httpx.AsyncClient` per `GitHubClient` instance, created with
  the API base URL, required headers (`Accept`, `X-GitHub-Api-Version`,
  and a `User-Agent` — GitHub's API rejects requests without one), and an
  `Authorization: Bearer <token>` header when `GITHUB_TOKEN` is set (per
  PRD 8/14: unauthenticated calls are capped at 60/hr vs. 5,000/hr with a
  token).
- Every method translates GitHub's HTTP responses into either plain
  Python data or one of `app.core.exceptions`' typed exceptions:
    * 404 on the user endpoint  -> `GitHubUserNotFoundError` (per PRD
      5.2: "a clear message rather than a generic error").
    * 403/429 with a spent rate-limit budget -> `RateLimitExceededError`.
    * Any other non-2xx / network failure -> `ExternalServiceError`.
- `get_readme_text` treats a 404 as "this repo has no README" (returns
  `None`) rather than an error — a missing README is an expected, scoring
  -relevant signal per PRD 6.2, not a failure.

Known REST API limitations (by design, not omissions)
-------------------------------------------------------
- **Pinned repositories**: GitHub's REST v3 API has no endpoint for a
  user's pinned repositories — that data is only exposed via the GraphQL
  v4 API (`pinnedItems` on `User`). Per the task's "Use GitHub REST API"
  requirement, this client stays REST-only; `top_repos_scorer.py`
  documents the engagement-ranked proxy used instead.
- **Full contribution history**: REST offers no "contribution graph"
  endpoint either (that's GraphQL's `contributionsCollection`, or the
  HTML profile page). `list_public_events` uses `/users/{username}/events
  /public`, which GitHub caps at the last ~90 days / 300 events — used as
  a recent-activity signal, not a full history.
- **Repository pagination**: `list_repos` fetches a single page of up to
  100 repositories (`per_page=100`), which comfortably covers the vast
  majority of individual profiles. Multi-page pagination (via the `Link`
  response header) can be added here later without changing the client's
  public interface.

Where future code should go
----------------------------
Additional GitHub endpoints (e.g. `/repos/{owner}/{repo}/languages` for a
byte-weighted language breakdown, if the primary-language heuristic in
`repository_portfolio_scorer.py` is ever judged insufficient) get a new
method on this class, following the same response-handling pattern.
"""

import base64
import logging

import httpx

from app.config.settings import Settings
from app.core.exceptions import ExternalServiceError, GitHubUserNotFoundError, RateLimitExceededError

logger = logging.getLogger(__name__)

_API_VERSION = "2022-11-28"
_USER_AGENT = "ai-career-toolkit-backend"


class GitHubClient:
    """Thin async wrapper around the GitHub REST API's public, unauthenticated-safe endpoints."""

    def __init__(self, settings: Settings) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": _USER_AGENT,
        }
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

        self._client = httpx.AsyncClient(
            base_url=settings.GITHUB_API_BASE_URL,
            headers=headers,
            timeout=settings.GITHUB_API_TIMEOUT_SECONDS,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool. Call once per app lifetime, not per request."""
        await self._client.aclose()

    async def get_user(self, username: str) -> dict:
        """
        GET /users/{username} — public profile fields (name, bio, followers,
        public_repos, created_at, avatar_url, html_url, ...).

        Raises GitHubUserNotFoundError if the account doesn't exist.
        """
        response = await self._request("GET", f"/users/{username}")
        return response.json()

    async def list_repos(self, username: str) -> list[dict]:
        """
        GET /users/{username}/repos — up to 100 of the user's repositories
        (own + forks; each entry's `fork` field distinguishes them),
        sorted by most recently pushed so the "top" slice skews toward
        active work.
        """
        response = await self._request(
            "GET",
            f"/users/{username}/repos",
            params={"per_page": 100, "sort": "pushed", "type": "owner"},
        )
        return response.json()

    async def get_readme_text(self, owner: str, repo: str) -> str | None:
        """
        GET /repos/{owner}/{repo}/readme — decoded README content, or None
        if the repository has no README (a 404 here is an expected,
        scoring-relevant outcome, not an error).
        """
        response = await self._request(
            "GET", f"/repos/{owner}/{repo}/readme", allow_404=True
        )
        if response is None:
            return None

        payload = response.json()
        if payload.get("encoding") != "base64" or "content" not in payload:
            # GitHub falls back to a different retrieval mechanism for very
            # large files; treat as "content unavailable" rather than guess.
            return None

        try:
            raw = base64.b64decode(payload["content"])
            return raw.decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("Failed to decode README for %s/%s: %s", owner, repo, exc)
            return None

    async def list_public_events(self, username: str) -> list[dict]:
        """
        GET /users/{username}/events/public — the user's recent public
        activity (pushes, PRs, issues, etc). GitHub limits this to roughly
        the last 90 days / 300 events; used as a recent-activity signal
        (see module docstring's "Known REST API limitations").
        """
        response = await self._request(
            "GET", f"/users/{username}/events/public", params={"per_page": 100}, allow_404=True
        )
        if response is None:
            return []
        return response.json()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        allow_404: bool = False,
    ) -> httpx.Response | None:
        """
        Shared request/error-handling path for every method above.

        `allow_404=True` returns `None` on a 404 instead of raising —
        used for endpoints where "not found" is a valid, expected outcome
        (a repo with no README, a user with no public events) rather than
        a genuine error condition.
        """
        try:
            response = await self._client.request(method, path, params=params)
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(
                f"GitHub API request to {path} timed out."
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"Failed to reach the GitHub API ({path}): {exc}"
            ) from exc

        if response.status_code == 404:
            if allow_404:
                return None
            raise GitHubUserNotFoundError(
                "No GitHub user was found with that username. Double-check the spelling."
            )

        if response.status_code in (403, 429) and response.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitExceededError(
                "The GitHub API rate limit has been reached. Please try again later, or "
                "configure GITHUB_TOKEN to raise the limit from 60/hr to 5,000/hr."
            )

        if response.status_code >= 400:
            logger.warning("GitHub API error %s on %s: %s", response.status_code, path, response.text[:200])
            raise ExternalServiceError(
                f"The GitHub API returned an unexpected error ({response.status_code}) for {path}."
            )

        return response
