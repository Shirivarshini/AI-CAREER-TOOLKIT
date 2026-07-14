"""
Unit tests for `app/utils/linkedin_heuristics.py` and
`app/utils/linkedin_section_parser.py` — pure functions, no HTTP/DB
involved, mirroring `tests/test_ats_scoring.py`'s style of testing the
scoring engine directly.

Run with:
    pytest -v tests/test_linkedin_heuristics.py
"""

from app.utils import linkedin_heuristics as heuristics
from app.utils.linkedin_section_parser import extract_headline, parse_linkedin_sections


def test_score_headline_penalizes_short_generic_headline() -> None:
    weak = heuristics.score_headline("Engineer")
    strong = heuristics.score_headline(
        "Senior Backend Engineer | Python, FastAPI, Distributed Systems"
    )

    assert weak.score < strong.score
    assert weak.suggestions


def test_score_headline_flags_cliche_phrases() -> None:
    result = heuristics.score_headline("Passionate hardworking team player")
    assert any("filler" in s.lower() for s in result.suggestions)


def test_score_about_rewards_length_and_cta() -> None:
    short_no_cta = heuristics.score_about("I am a software engineer.")
    substantial_with_cta = heuristics.score_about(
        "Backend engineer with 5 years of experience building scalable APIs "
        "and distributed systems. I care deeply about developer experience "
        "and reliability.\n\nFeel free to reach out if you'd like to connect "
        "or chat about backend architecture." * 2
    )

    assert short_no_cta.score < substantial_with_cta.score


def test_score_experience_rewards_bullets_verbs_and_numbers() -> None:
    weak = heuristics.score_experience("Responsible for the backend team and various tasks.")
    strong = heuristics.score_experience(
        "- Led a team of 5 engineers to redesign the checkout flow, increasing conversion by 12%.\n"
        "- Reduced API latency by 40% through query optimization and caching."
    )

    assert strong.score > weak.score


def test_score_education_detects_degree_and_year() -> None:
    weak = heuristics.score_education("Some school")
    strong = heuristics.score_education("B.Sc. Computer Science, MIT, 2016")

    assert strong.score > weak.score


def test_score_skills_scales_with_count() -> None:
    few = heuristics.score_skills("Python")
    many = heuristics.score_skills(
        "Python, FastAPI, PostgreSQL, Docker, AWS, System Design, Redis, Kafka, gRPC, CI/CD"
    )

    assert many.score > few.score


def test_score_certifications_rewards_year_present() -> None:
    no_year = heuristics.score_certifications("AWS Certified Solutions Architect")
    with_year = heuristics.score_certifications("AWS Certified Solutions Architect, 2022")

    assert with_year.score >= no_year.score


def test_score_projects_rewards_links_and_detail() -> None:
    weak = heuristics.score_projects("Side project")
    strong = heuristics.score_projects(
        "Open-source rate limiter library used by several internal services, "
        "https://github.com/example/rate-limiter\n"
        "Internal analytics dashboard built with FastAPI and React, "
        "https://github.com/example/dashboard"
    )

    assert strong.score > weak.score


def test_extract_headline_skips_name_and_contact_lines() -> None:
    text = "Jane Doe\nBackend Engineer | Python, FastAPI\njane@example.com\nSan Francisco Bay Area"
    headline = extract_headline(text)
    assert headline == "Backend Engineer | Python, FastAPI"


def test_parse_linkedin_sections_detects_labeled_sections() -> None:
    text = (
        "Jane Doe\n"
        "Backend Engineer | Python\n"
        "Summary\n"
        "Experienced backend engineer.\n"
        "Experience\n"
        "- Led the checkout redesign.\n"
        "Education\n"
        "B.Sc. Computer Science, MIT, 2016\n"
        "Skills\n"
        "Python, FastAPI, PostgreSQL\n"
    )

    sections = parse_linkedin_sections(text)

    assert sections["headline"] == "Backend Engineer | Python"
    assert sections["about"] == "Experienced backend engineer."
    assert "checkout redesign" in sections["experience"]
    assert "MIT" in sections["education"]
    assert sections["skills"] == "Python, FastAPI, PostgreSQL"
    assert sections["certifications"] is None
    assert sections["projects"] is None
