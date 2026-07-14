"""
Tests for POST /api/v1/resume/analyze (Module 2: validation + text extraction).

Run with:
    pytest -v tests/test_resume.py
"""

import io

import docx
import pytest
from httpx import AsyncClient


def _build_test_docx_bytes(text: str = "Jane Doe\nSoftware Engineer\nPython, FastAPI, SQL") -> bytes:
    """Build a minimal, real, valid .docx file in memory using python-docx."""
    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_test_pdf_bytes(text: str = "Hello Resume") -> bytes:
    """
    Build a minimal, hand-crafted (non-xref-strict) PDF in memory.

    pdfminer/pdfplumber can recover text from PDFs with a missing/invalid
    xref table via their fallback full-file scan, so this is sufficient
    for exercising the real extraction path without adding a PDF-writing
    dependency just for tests.
    """
    content_stream = f"BT /F1 24 Tf 20 100 Td ({text}) Tj ET".encode()
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(len(content_stream)).encode() + b" >>\n"
        b"stream\n" + content_stream + b"\nendstream endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"%%EOF"
    )
    return pdf


@pytest.mark.asyncio
async def test_analyze_valid_docx_extracts_text(client: AsyncClient) -> None:
    file_bytes = _build_test_docx_bytes()
    files = {
        "file": (
            "resume.docx",
            file_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["filename"] == "resume.docx"
    assert data["file_type"] == "docx"
    assert "Jane Doe" in data["extracted_text"]
    assert data["word_count"] > 0
    assert data["character_count"] == len(data["extracted_text"])

    ats = data["ats_score"]
    assert 0 <= ats["overall_score"] <= 100
    for category in ("keyword_match", "formatting", "section_completeness", "achievements", "parseability"):
        assert category in ats["breakdown"]
        assert 0 <= ats["breakdown"][category]["score"] <= 100
    assert isinstance(ats["missing_sections"], list)
    assert isinstance(ats["suggestions"], list)


@pytest.mark.asyncio
async def test_analyze_valid_pdf_extracts_text(client: AsyncClient) -> None:
    file_bytes = _build_test_pdf_bytes("Hello Resume")
    files = {"file": ("resume.pdf", file_bytes, "application/pdf")}

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["file_type"] == "pdf"
    assert "Hello Resume" in body["data"]["extracted_text"]
    assert "ats_score" in body["data"]
    assert 0 <= body["data"]["ats_score"]["overall_score"] <= 100


@pytest.mark.asyncio
async def test_analyze_with_job_description_returns_missing_keywords(client: AsyncClient) -> None:
    resume_bytes = _build_test_docx_bytes(
        "Jane Doe\njane@email.com\n\nSkills\nPython, Docker\n\nExperience\nBuilt internal tools"
    )
    files = {
        "file": (
            "resume.docx",
            resume_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    data = {
        "job_description": (
            "We need a Senior Backend Engineer skilled in Python, Kubernetes, "
            "PostgreSQL, and AWS. Docker experience is a plus."
        )
    }

    response = await client.post("/api/v1/resume/analyze", files=files, data=data)

    assert response.status_code == 200
    ats = response.json()["data"]["ats_score"]
    missing = ats["missing_keywords"]
    assert "kubernetes" in missing
    assert "postgresql" in missing
    # "python" and "docker" appear in both resume and JD, so should NOT be missing.
    assert "python" not in missing
    assert "docker" not in missing


@pytest.mark.asyncio
async def test_analyze_rejects_unsupported_extension(client: AsyncClient) -> None:
    files = {"file": ("resume.txt", b"plain text resume", "text/plain")}

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 415
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_analyze_rejects_mismatched_mime_type(client: AsyncClient) -> None:
    # .pdf extension but a Content-Type that isn't in the allowed list.
    files = {"file": ("resume.pdf", _build_test_pdf_bytes(), "image/png")}

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_analyze_rejects_oversized_file(client: AsyncClient) -> None:
    # One byte over the 5MB default limit, with a valid PDF signature.
    oversized_content = b"%PDF-1.4\n" + (b"0" * (5 * 1024 * 1024 + 1))
    files = {"file": ("resume.pdf", oversized_content, "application/pdf")}

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 413
    assert response.json()["error_code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_analyze_rejects_content_signature_mismatch(client: AsyncClient) -> None:
    # .pdf extension and application/pdf MIME type, but the bytes aren't a real PDF.
    files = {"file": ("resume.pdf", b"this is not actually a pdf file", "application/pdf")}

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_analyze_rejects_empty_file(client: AsyncClient) -> None:
    files = {"file": ("resume.pdf", b"", "application/pdf")}

    response = await client.post("/api/v1/resume/analyze", files=files)

    assert response.status_code == 413
    assert response.json()["error_code"] == "FILE_TOO_LARGE"
