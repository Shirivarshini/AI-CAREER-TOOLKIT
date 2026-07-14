"""
Unit tests for the ATS Scoring Engine (`app.services.ats_scoring`).

These tests exercise `ATSScorer` directly — with plain strings, no HTTP
layer, no FastAPI `TestClient` — deliberately, to prove the engine is
genuinely reusable outside the API (as designed; see the package
docstring in `app/services/ats_scoring/__init__.py`).

Run with:
    pytest -v tests/test_ats_scoring.py
"""

import pytest

from app.services.ats_scoring import ATSScorer, ATSScoringConfig, ATSScoringContext, ATSScoringWeights
from app.services.ats_scoring.types import ATSCategory

STRONG_RESUME = """
Jane Doe
jane.doe@email.com | (555) 987-6543

Summary
Backend engineer focused on distributed systems and developer tooling.

Skills
Python, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, Redis, SQLAlchemy

Experience
- Led migration of a monolith to microservices, cutting deploy time by 70%
- Built a CI/CD pipeline used by 12 engineering teams
- Reduced P95 API latency by 45% through query and index optimization
- Mentored 3 junior engineers and led weekly architecture reviews

Education
B.S. Computer Science, State University, 2018
"""

WEAK_RESUME = """
Bob

worked on stuff at a company doing various tasks and responsibilities
helped with things
"""


def _context(text: str, job_description: str | None = None) -> ATSScoringContext:
    return ATSScoringContext(
        resume_text=text,
        file_extension=".pdf",
        file_size_bytes=len(text.encode()),
        job_description=job_description,
    )


class TestATSScorerOverallBehavior:
    def test_overall_score_within_bounds(self) -> None:
        scorer = ATSScorer()
        result = scorer.score(_context(STRONG_RESUME))
        assert 0 <= result.overall_score <= 100

    def test_strong_resume_scores_higher_than_weak_resume(self) -> None:
        scorer = ATSScorer()
        strong = scorer.score(_context(STRONG_RESUME))
        weak = scorer.score(_context(WEAK_RESUME))
        assert strong.overall_score > weak.overall_score

    def test_breakdown_contains_all_five_categories(self) -> None:
        scorer = ATSScorer()
        result = scorer.score(_context(STRONG_RESUME))
        assert set(result.breakdown.keys()) == {
            ATSCategory.KEYWORD_MATCH,
            ATSCategory.FORMATTING,
            ATSCategory.SECTION_COMPLETENESS,
            ATSCategory.ACHIEVEMENTS,
            ATSCategory.PARSEABILITY,
        }
        for category_result in result.breakdown.values():
            assert 0 <= category_result.score <= 100
            assert 0 <= category_result.weight <= 1

    def test_missing_sections_detected_on_incomplete_resume(self) -> None:
        scorer = ATSScorer()
        result = scorer.score(_context(WEAK_RESUME))
        assert len(result.missing_sections) > 0

    def test_complete_resume_has_no_missing_sections(self) -> None:
        scorer = ATSScorer()
        result = scorer.score(_context(STRONG_RESUME))
        assert result.missing_sections == []

    def test_suggestions_are_present_for_weak_resume(self) -> None:
        scorer = ATSScorer()
        result = scorer.score(_context(WEAK_RESUME))
        assert len(result.suggestions) > 0
        assert all(isinstance(s, str) for s in result.suggestions)


class TestKeywordMatchWithJobDescription:
    def test_missing_keywords_only_populated_with_job_description(self) -> None:
        scorer = ATSScorer()
        without_jd = scorer.score(_context(STRONG_RESUME))
        assert without_jd.missing_keywords == []

        with_jd = scorer.score(
            _context(STRONG_RESUME, job_description="Looking for a Rust and Golang engineer.")
        )
        assert "rust" in with_jd.missing_keywords
        assert "golang" in with_jd.missing_keywords

    def test_matched_keywords_are_not_reported_missing(self) -> None:
        scorer = ATSScorer()
        result = scorer.score(
            _context(STRONG_RESUME, job_description="Must know Python and PostgreSQL.")
        )
        assert "python" not in result.missing_keywords
        assert "postgresql" not in result.missing_keywords


class TestConfigurableWeights:
    def test_custom_weights_change_overall_score(self) -> None:
        # Two configs that are identical except one puts ~all weight on
        # keyword_match, the other ~all weight on achievements. Since
        # STRONG_RESUME scores differently on each category, overall
        # scores must differ.
        keyword_heavy = ATSScoringConfig(
            weights=ATSScoringWeights(
                keyword_match=0.96, formatting=0.01, section_completeness=0.01,
                achievements=0.01, parseability=0.01,
            )
        )
        achievement_heavy = ATSScoringConfig(
            weights=ATSScoringWeights(
                keyword_match=0.01, formatting=0.01, section_completeness=0.01,
                achievements=0.96, parseability=0.01,
            )
        )

        score_a = ATSScorer(config=keyword_heavy).score(_context(STRONG_RESUME)).overall_score
        score_b = ATSScorer(config=achievement_heavy).score(_context(STRONG_RESUME)).overall_score

        assert score_a != score_b

    def test_weights_not_summing_to_one_are_normalized(self) -> None:
        # 10 + 10 + 10 + 10 + 10 = 50, not 100 — should be normalized to
        # equal 0.2 each rather than raising or silently breaking scoring.
        weights = ATSScoringWeights(
            keyword_match=10, formatting=10, section_completeness=10,
            achievements=10, parseability=10,
        )
        config = ATSScoringConfig(weights=weights)
        result = ATSScorer(config=config).score(_context(STRONG_RESUME))

        assert 0 <= result.overall_score <= 100
        total_weight = sum(r.weight for r in result.breakdown.values())
        assert total_weight == pytest.approx(1.0, abs=1e-6)

    def test_reusable_across_multiple_calls(self) -> None:
        """A single ATSScorer instance can score multiple resumes independently."""
        scorer = ATSScorer()
        result_1 = scorer.score(_context(STRONG_RESUME))
        result_2 = scorer.score(_context(WEAK_RESUME))
        # Scoring one resume must not mutate state that affects the next.
        result_1_again = scorer.score(_context(STRONG_RESUME))
        assert result_1.overall_score == result_1_again.overall_score
        assert result_1.overall_score != result_2.overall_score
