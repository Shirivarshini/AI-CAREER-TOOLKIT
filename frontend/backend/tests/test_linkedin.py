"""
Tests for POST /api/v1/linkedin/analyze (LinkedIn Optimizer).

Covers both input methods (pasted JSON, PDF export) and both response
generations: Part 1's per-section results and Part 2's weighted overall
score / breakdown / keyword suggestions / recruiter tips / profile
strength / next steps (see `app/services/linkedin_analysis/` and
`tests/test_linkedin_analysis.py` for engine-level unit tests).

Run with:
    pytest -v tests/test_linkedin.py
"""

import pytest
from httpx import AsyncClient


def _build_test_linkedin_pdf_bytes() -> bytes:
    """
    Build a minimal, hand-crafted (non-xref-strict) PDF in memory whose
    text layout mimics a LinkedIn 'Save to PDF' profile export closely
    enough for `parse_linkedin_sections` to detect each section.

    Same technique as `tests/test_resume.py`'s `_build_test_pdf_bytes`:
    pdfplumber/pdfminer can recover text via a fallback full-file scan even
    without a strict xref table, so this avoids adding a PDF-writing
    dependency just for tests.
    """
    lines = [
        "Jane Doe",
        "Backend Engineer | Python, FastAPI, Distributed Systems",
        "San Francisco Bay Area",
        "Summary",
        "Backend engineer with 5 years building and scaling APIs. Open to new opportunities in backend engineering.",
        "Experience",
        "- Led migration of a monolith to microservices, reducing p95 latency by 30%.",
        "- Built a CI/CD pipeline that cut deploy time from 40 minutes to 5 minutes.",
        "Education",
        "B.Sc. Computer Science, MIT, 2016",
        "Skills",
        "Python, FastAPI, PostgreSQL, Docker, AWS, System Design",
        "Licenses & Certifications",
        "AWS Certified Solutions Architect, 2022",
        "Projects",
        "Open-source rate limiter library, https://github.com/example/rate-limiter",
        "Internal analytics dashboard, https://github.com/example/dashboard",
    ]

    content_ops = ["BT", "/F1 12 Tf", "20 750 Td", f"({lines[0]}) Tj"]
    for line in lines[1:]:
        content_ops.append("0 -20 Td")
        escaped = line.replace("(", r"\(").replace(")", r"\)")
        content_ops.append(f"({escaped}) Tj")
    content_ops.append("ET")
    content_stream = "\n".join(content_ops).encode()

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 400 800] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(len(content_stream)).encode() + b" >>\n"
        b"stream\n" + content_stream + b"\nendstream endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"%%EOF"
    )
    return pdf


@pytest.mark.asyncio
async def test_analyze_json_body_success(client: AsyncClient) -> None:
    payload = {
        "headline": "Backend Engineer | Python, FastAPI, Distributed Systems",
        "about": (
            "Backend engineer with 5 years building and scaling APIs. "
            "Open to new opportunities — feel free to reach out."
        ),
        "experience": (
            "- Led migration of a monolith to microservices, reducing latency by 30%.\n"
            "- Built a CI/CD pipeline that cut deploy time by 80%."
        ),
        "education": "B.Sc. Computer Science, MIT, 2016",
        "skills": "Python, FastAPI, PostgreSQL, Docker, AWS, System Design",
    }

    response = await client.post("/api/v1/linkedin/analyze", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["input_method"] == "json"
    assert data["sections"]["headline"]["present"] is True
    assert data["sections"]["headline"]["score"] is not None
    # certifications / projects were not provided -> detected as missing
    assert "certifications" in data["missing_sections"]
    assert "projects" in data["missing_sections"]
    assert data["sections"]["certifications"]["present"] is False
    assert data["sections"]["certifications"]["score"] is None
    # Part 2: weighted overall score, breakdown, and insights fields.
    assert 0 <= data["overall_score"] <= 100
    assert set(data["breakdown"].keys()) == {
        "headline", "about", "experience", "skills", "education",
        "projects", "certifications", "completeness",
    }
    for category in data["breakdown"].values():
        assert 0 <= category["score"] <= 100
        assert 0 <= category["weight"] <= 1
    assert data["profile_strength"] in {"Excellent", "Strong", "Needs Improvement", "Weak"}
    assert isinstance(data["next_steps"], list)
    assert isinstance(data["recruiter_tips"], list) and len(data["recruiter_tips"]) > 0
    assert isinstance(data["keyword_suggestions"], list)
    assert "certifications" in data["rewrite_suggestions"]


@pytest.mark.asyncio
async def test_analyze_json_body_empty_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/linkedin/analyze", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_analyze_json_body_whitespace_only_treated_as_missing(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/linkedin/analyze",
        json={"headline": "Backend Engineer", "about": "   "},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sections"]["about"]["present"] is False
    assert "about" in data["missing_sections"]


@pytest.mark.asyncio
async def test_analyze_pdf_upload_success(client: AsyncClient) -> None:
    file_bytes = _build_test_linkedin_pdf_bytes()
    files = {"file": ("linkedin_export.pdf", file_bytes, "application/pdf")}

    response = await client.post("/api/v1/linkedin/analyze", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["input_method"] == "pdf"
    # At least the clearly-labeled sections should have been detected.
    assert data["sections"]["experience"]["present"] is True
    assert data["sections"]["skills"]["present"] is True
    assert data["sections"]["education"]["present"] is True
    assert 0 <= data["overall_score"] <= 100
    assert data["profile_strength"] in {"Excellent", "Strong", "Needs Improvement", "Weak"}


@pytest.mark.asyncio
async def test_analyze_rejects_non_pdf_extension(client: AsyncClient) -> None:
    files = {"file": ("export.docx", b"not a real docx", "application/pdf")}

    response = await client.post("/api/v1/linkedin/analyze", files=files)

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_analyze_rejects_oversized_pdf(client: AsyncClient) -> None:
    oversized_content = b"%PDF-1.4\n" + (b"0" * (5 * 1024 * 1024 + 1))
    files = {"file": ("linkedin_export.pdf", oversized_content, "application/pdf")}

    response = await client.post("/api/v1/linkedin/analyze", files=files)

    assert response.status_code == 413
    assert response.json()["error_code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_analyze_rejects_mismatched_content_signature(client: AsyncClient) -> None:
    # Declares .pdf but the actual bytes don't start with the "%PDF" signature.
    files = {"file": ("linkedin_export.pdf", b"this is not really a pdf", "application/pdf")}

    response = await client.post("/api/v1/linkedin/analyze", files=files)

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_analyze_rejects_unsupported_content_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/linkedin/analyze",
        content=b"headline=hello",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_analyze_json_body_with_featured_and_recommendations(client: AsyncClient) -> None:
    """Featured and Recommendations feed the Completeness category, not their own `sections` entry."""
    payload = {
        "headline": "Backend Engineer | Python, FastAPI, Distributed Systems",
        "about": "Backend engineer with 5 years building and scaling APIs. Open to opportunities.",
        "featured": "Blog post: Scaling FastAPI — https://example.com/post",
        "recommendations": "Great engineer, highly recommend — Manager A\nAlways delivers — Peer B",
    }

    response = await client.post("/api/v1/linkedin/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert "featured" not in data["sections"]
    assert "recommendations" not in data["sections"]
    assert data["breakdown"]["completeness"]["score"] > 0


@pytest.mark.asyncio
async def test_analyze_json_body_without_featured_or_recommendations_scores_lower_completeness(
    client: AsyncClient,
) -> None:
    base_payload = {
        "headline": "Backend Engineer | Python, FastAPI, Distributed Systems",
        "about": "Backend engineer with 5 years building and scaling APIs. Open to opportunities.",
        "experience": "- Led migration of a monolith to microservices, reducing latency by 30%.",
        "education": "B.Sc. Computer Science, MIT, 2016",
        "skills": "Python, FastAPI, PostgreSQL, Docker, AWS, System Design",
        "certifications": "AWS Certified Solutions Architect, 2022",
        "projects": "Rate limiter library, https://github.com/example/rate-limiter",
    }
    with_extras = await client.post(
        "/api/v1/linkedin/analyze",
        json={
            **base_payload,
            "featured": "Blog post: Scaling FastAPI — https://example.com/post",
            "recommendations": "Great engineer — Manager A\nAlways delivers — Peer B",
        },
    )
    without_extras = await client.post("/api/v1/linkedin/analyze", json=base_payload)

    assert with_extras.status_code == 200
    assert without_extras.status_code == 200
    with_score = with_extras.json()["data"]["breakdown"]["completeness"]["score"]
    without_score = without_extras.json()["data"]["breakdown"]["completeness"]["score"]
    assert with_score > without_score
