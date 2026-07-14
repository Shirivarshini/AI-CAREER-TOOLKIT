"""
Tests for POST /api/v1/skills/gap (Skill-Gap Advisor module).

Run with:
    pytest -v tests/test_skill_gap.py
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_analyze_with_resume_and_github_skills(client: AsyncClient) -> None:
    payload = {
        "resume_skills": ["Python", "SQL", "Docker", "Git", "REST API"],
        "github_skills": ["Python", "JavaScript"],
        "target_role": "Backend Developer",
    }

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]

    assert data["target_role"] == "Backend Developer"
    assert 0 <= data["match_percentage"] <= 100

    matched_names = {m["skill"] for m in data["matched_skills"]}
    assert "Python" in matched_names
    assert "SQL" in matched_names
    assert "Docker" in matched_names
    assert "Git" in matched_names

    # "Python" was found in both resume and GitHub skills.
    python_match = next(m for m in data["matched_skills"] if m["skill"] == "Python")
    assert set(python_match["sources"]) == {"resume", "github"}

    missing = data["missing_skills"]
    assert "must_have" in missing and "nice_to_have" in missing
    for skill_entry in missing["must_have"]:
        # every missing skill in this taxonomy has a learning resource
        assert skill_entry["resource"] is not None
        assert skill_entry["resource"]["url"].startswith("http")


@pytest.mark.asyncio
async def test_analyze_resume_only_matches_role_alias_case_insensitively(client: AsyncClient) -> None:
    payload = {
        "resume_skills": ["python", "sql", "excel", "pandas", "statistics", "data visualization"],
        "target_role": "data analytics",  # lowercase alias of "Data Analyst"
    }

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_role"] == "Data Analyst"  # resolved to the canonical name
    assert data["match_percentage"] == 100.0
    assert data["missing_skills"]["must_have"] == []


@pytest.mark.asyncio
async def test_analyze_recognizes_skill_aliases(client: AsyncClient) -> None:
    # "JS" and "Postgres" should normalize to "JavaScript" / "PostgreSQL".
    payload = {
        "resume_skills": ["JS", "React", "HTML", "CSS", "Git", "Responsive Design", "Accessibility"],
        "target_role": "Frontend Developer",
    }

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    matched_names = {m["skill"] for m in data["matched_skills"]}
    assert "JavaScript" in matched_names  # matched via the "js" alias
    assert data["missing_skills"]["must_have"] == []


@pytest.mark.asyncio
async def test_analyze_unknown_role_returns_clear_404_with_available_roles(client: AsyncClient) -> None:
    payload = {"resume_skills": ["Python"], "target_role": "Astronaut"}

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "TARGET_ROLE_NOT_FOUND"
    assert "Backend Developer" in body["message"]


@pytest.mark.asyncio
async def test_analyze_rejects_empty_skill_lists(client: AsyncClient) -> None:
    payload = {"resume_skills": [], "github_skills": [], "target_role": "Backend Developer"}

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_analyze_rejects_missing_target_role(client: AsyncClient) -> None:
    payload = {"resume_skills": ["Python"]}

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_no_matching_skills_still_returns_full_breakdown(client: AsyncClient) -> None:
    payload = {"resume_skills": ["Underwater Basket Weaving"], "target_role": "DevOps Engineer"}

    response = await client.post("/api/v1/skills/gap", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched_skills"] == []
    assert data["match_percentage"] == 0.0
    assert len(data["missing_skills"]["must_have"]) > 0
