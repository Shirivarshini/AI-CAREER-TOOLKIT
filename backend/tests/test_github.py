"""
Tests for POST /api/v1/github/analyze (GitHub Analysis module).

The GitHub REST API is mocked via `respx` — no real network calls are
made, so these tests are deterministic and don't spend real GitHub API
rate-limit budget.

Run with:
    pytest -v tests/test_github.py
"""

import base64
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from httpx import AsyncClient

GITHUB_API = "https://api.github.com"

_README_MARKDOWN = """# Awesome Project

A small tool that does something useful for developers.

## Installation

```bash
pip install awesome-project
```

## Usage

```python
import awesome_project
awesome_project.run()
```

This project is actively maintained.
"""


def _user_payload(username: str, public_repos: int = 2) -> dict:
    return {
        "login": username,
        "id": 12345,
        "avatar_url": f"https://avatars.githubusercontent.com/u/12345",
        "html_url": f"https://github.com/{username}",
        "public_repos": public_repos,
        "followers": 42,
        "created_at": "2018-01-01T00:00:00Z",
    }


def _repos_payload() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "name": "awesome-project",
            "description": "A small tool that does something genuinely useful for developers.",
            "stargazers_count": 15,
            "forks_count": 3,
            "language": "Python",
            "fork": False,
            "pushed_at": (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "html_url": "https://github.com/testuser/awesome-project",
        },
        {
            "name": "second-project",
            "description": "",
            "stargazers_count": 0,
            "forks_count": 0,
            "language": "JavaScript",
            "fork": False,
            "pushed_at": (now - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "html_url": "https://github.com/testuser/second-project",
        },
        {
            "name": "someone-elses-fork",
            "description": "A fork",
            "stargazers_count": 0,
            "forks_count": 0,
            "language": "Python",
            "fork": True,
            "pushed_at": (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "html_url": "https://github.com/testuser/someone-elses-fork",
        },
    ]


def _events_payload() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {"type": "PushEvent", "created_at": (now - timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for offset in (1, 3, 5, 5, 10)  # day 5 duplicated on purpose -> should dedupe to distinct dates
    ]


def _readme_payload() -> dict:
    encoded = base64.b64encode(_README_MARKDOWN.encode("utf-8")).decode("ascii")
    return {"encoding": "base64", "content": encoded}


def _mock_github_success(username: str) -> None:
    respx.get(f"{GITHUB_API}/users/{username}").mock(
        return_value=httpx.Response(200, json=_user_payload(username))
    )
    respx.get(f"{GITHUB_API}/users/{username}/repos").mock(
        return_value=httpx.Response(200, json=_repos_payload())
    )
    respx.get(f"{GITHUB_API}/users/{username}/events/public").mock(
        return_value=httpx.Response(200, json=_events_payload())
    )
    respx.route(method="GET", url__regex=rf"{GITHUB_API}/repos/{username}/.+/readme$").mock(
        return_value=httpx.Response(200, json=_readme_payload())
    )


@pytest.mark.asyncio
@respx.mock
async def test_analyze_valid_profile_returns_full_report(client: AsyncClient) -> None:
    _mock_github_success("testuser")

    response = await client.post("/api/v1/github/analyze", json={"username": "testuser"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]

    assert data["username"] == "testuser"
    assert data["profile_url"] == "https://github.com/testuser"

    stats = data["statistics"]
    assert stats["non_fork_repos"] == 2  # fork excluded
    assert stats["total_stars"] == 15
    assert stats["total_forks"] == 3
    assert stats["followers"] == 42
    assert isinstance(stats["language_distribution"], list)
    assert stats["active_days_recent_window"] == 4  # 5 events, one duplicate day -> 4 distinct days

    assert len(data["top_repositories"]) == 2  # only non-fork repos are eligible
    top_names = {r["name"] for r in data["top_repositories"]}
    assert top_names == {"awesome-project", "second-project"}
    awesome = next(r for r in data["top_repositories"] if r["name"] == "awesome-project")
    assert awesome["has_readme"] is True

    score = data["profile_score"]
    assert 0 <= score["overall_score"] <= 100
    for category in ("repository_portfolio", "top_repositories", "readme_quality", "activity"):
        assert category in score["breakdown"]
        assert 0 <= score["breakdown"][category]["score"] <= 100
    assert isinstance(score["suggestions"], list)
    # second-project has an empty description -> should be named in a suggestion
    assert any("second-project" in s for s in score["suggestions"])


@pytest.mark.asyncio
@respx.mock
async def test_analyze_uses_cache_on_second_call(client: AsyncClient) -> None:
    _mock_github_success("cacheduser")

    first = await client.post("/api/v1/github/analyze", json={"username": "cacheduser"})
    assert first.status_code == 200

    user_route = respx.get(f"{GITHUB_API}/users/cacheduser")
    calls_before = user_route.call_count

    second = await client.post("/api/v1/github/analyze", json={"username": "cacheduser"})
    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]

    # A cache hit must not re-fetch the user profile from GitHub.
    assert user_route.call_count == calls_before


@pytest.mark.asyncio
@respx.mock
async def test_analyze_nonexistent_user_returns_clear_404(client: AsyncClient) -> None:
    respx.get(f"{GITHUB_API}/users/ghostuser").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    response = await client.post("/api/v1/github/analyze", json={"username": "ghostuser"})

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "GITHUB_USER_NOT_FOUND"


@pytest.mark.asyncio
@respx.mock
async def test_analyze_rate_limited_returns_429(client: AsyncClient) -> None:
    respx.get(f"{GITHUB_API}/users/limiteduser").mock(
        return_value=httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0"},
        )
    )

    response = await client.post("/api/v1/github/analyze", json={"username": "limiteduser"})

    assert response.status_code == 429
    assert response.json()["error_code"] == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_analyze_rejects_invalid_username_format(client: AsyncClient) -> None:
    response = await client.post("/api/v1/github/analyze", json={"username": "-invalid-"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_analyze_rejects_empty_username(client: AsyncClient) -> None:
    response = await client.post("/api/v1/github/analyze", json={"username": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
@respx.mock
async def test_analyze_profile_with_no_repos_scores_gracefully(client: AsyncClient) -> None:
    respx.get(f"{GITHUB_API}/users/emptyuser").mock(
        return_value=httpx.Response(200, json=_user_payload("emptyuser", public_repos=0))
    )
    respx.get(f"{GITHUB_API}/users/emptyuser/repos").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{GITHUB_API}/users/emptyuser/events/public").mock(
        return_value=httpx.Response(200, json=[])
    )

    response = await client.post("/api/v1/github/analyze", json={"username": "emptyuser"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["statistics"]["non_fork_repos"] == 0
    assert data["profile_score"]["overall_score"] == 0.0
    assert len(data["profile_score"]["suggestions"]) > 0
