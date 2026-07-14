"""
Unit tests for the LinkedIn Analysis Engine (`app.services.linkedin_analysis`).

These tests exercise `LinkedInProfileScorer` directly — with plain
`LinkedInProfileContext` dataclasses, no HTTP layer, no FastAPI `TestClient`
— deliberately, to prove the engine is genuinely reusable outside the API
(as designed; see the package docstring in
`app/services/linkedin_analysis/__init__.py`). Mirrors the style of
`tests/test_ats_scoring.py`.

Run with:
    pytest -v tests/test_linkedin_analysis.py
"""

import pytest

from app.services.linkedin_analysis import (
    LinkedInAnalysisConfig,
    LinkedInAnalysisWeights,
    LinkedInCategory,
    LinkedInProfileContext,
    LinkedInProfileScorer,
)

STRONG_PROFILE = LinkedInProfileContext(
    headline="Backend Engineer | Python, FastAPI, Distributed Systems",
    about=(
        "Backend engineer with 5 years building and scaling APIs for high-growth "
        "startups. Focused on distributed systems, developer tooling, and mentoring "
        "junior engineers. Open to new opportunities — feel free to reach out.\n\n"
        "Previously shipped payments infrastructure processing millions of transactions."
    ),
    experience=(
        "- Led migration of a monolith to microservices, reducing p95 latency by 30%.\n"
        "- Built a CI/CD pipeline that cut deploy time from 40 minutes to 5 minutes.\n"
        "- Mentored 3 junior engineers and drove weekly architecture reviews."
    ),
    education="B.Sc. Computer Science, MIT, 2016",
    skills="Python, FastAPI, PostgreSQL, Docker, AWS, System Design, Kubernetes, Redis",
    certifications="AWS Certified Solutions Architect, 2022",
    projects="Open-source rate limiter library, https://github.com/example/rate-limiter",
    featured="Blog post: Scaling FastAPI to 1M requests/day — https://example.com/post",
    recommendations="Great engineer, highly recommend — Manager A\nAlways delivers — Peer B",
)

EMPTY_PROFILE = LinkedInProfileContext()

PARTIAL_PROFILE = LinkedInProfileContext(headline="Dev", about="   ", skills="Python")


class TestLinkedInProfileScorerOverallBehavior:
    def test_overall_score_within_bounds(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(STRONG_PROFILE)
        assert 0 <= result.overall_score <= 100

    def test_strong_profile_scores_higher_than_empty_profile(self) -> None:
        scorer = LinkedInProfileScorer()
        strong = scorer.score(STRONG_PROFILE)
        empty = scorer.score(EMPTY_PROFILE)
        assert strong.overall_score > empty.overall_score

    def test_empty_profile_scores_zero(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(EMPTY_PROFILE)
        assert result.overall_score == 0.0
        assert result.profile_strength == "Weak"

    def test_breakdown_contains_all_eight_categories(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(STRONG_PROFILE)
        assert set(result.breakdown.keys()) == {
            LinkedInCategory.HEADLINE,
            LinkedInCategory.ABOUT,
            LinkedInCategory.EXPERIENCE,
            LinkedInCategory.SKILLS,
            LinkedInCategory.EDUCATION,
            LinkedInCategory.PROJECTS,
            LinkedInCategory.CERTIFICATIONS,
            LinkedInCategory.COMPLETENESS,
        }
        for category_result in result.breakdown.values():
            assert 0 <= category_result.score <= 100
            assert 0 <= category_result.weight <= 1

    def test_reusable_across_multiple_calls(self) -> None:
        """A single LinkedInProfileScorer instance can score multiple profiles independently."""
        scorer = LinkedInProfileScorer()
        result_1 = scorer.score(STRONG_PROFILE)
        result_2 = scorer.score(EMPTY_PROFILE)
        result_1_again = scorer.score(STRONG_PROFILE)
        assert result_1.overall_score == result_1_again.overall_score
        assert result_1.overall_score != result_2.overall_score


class TestMissingSectionsAndSuggestions:
    def test_missing_sections_detected_on_partial_profile(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(PARTIAL_PROFILE)
        assert LinkedInCategory.ABOUT in result.missing_sections
        assert LinkedInCategory.EXPERIENCE in result.missing_sections
        assert LinkedInCategory.HEADLINE not in result.missing_sections

    def test_whitespace_only_section_treated_as_missing(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(PARTIAL_PROFILE)
        assert not result.breakdown[LinkedInCategory.ABOUT].present
        assert result.breakdown[LinkedInCategory.ABOUT].score == 0.0

    def test_complete_profile_has_no_missing_sections(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(STRONG_PROFILE)
        assert result.missing_sections == []

    def test_rewrite_suggestions_are_section_specific(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(PARTIAL_PROFILE)
        # Missing sections get an "add this section" suggestion under their own key.
        assert any("about" in s.lower() for s in result.rewrite_suggestions[LinkedInCategory.ABOUT])
        # Completeness is a meta-category, not one of the seven rewrite-suggestion keys.
        assert LinkedInCategory.COMPLETENESS not in result.rewrite_suggestions

    def test_suggestions_are_all_strings(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(EMPTY_PROFILE)
        for suggestions in result.rewrite_suggestions.values():
            assert all(isinstance(s, str) for s in suggestions)


class TestCompletenessCategory:
    def test_missing_featured_and_recommendations_lower_completeness_score(self) -> None:
        scorer = LinkedInProfileScorer()
        with_extras = scorer.score(STRONG_PROFILE)

        without_extras_ctx = LinkedInProfileContext(
            headline=STRONG_PROFILE.headline,
            about=STRONG_PROFILE.about,
            experience=STRONG_PROFILE.experience,
            education=STRONG_PROFILE.education,
            skills=STRONG_PROFILE.skills,
            certifications=STRONG_PROFILE.certifications,
            projects=STRONG_PROFILE.projects,
            featured=None,
            recommendations=None,
        )
        without_extras = scorer.score(without_extras_ctx)

        assert (
            with_extras.breakdown[LinkedInCategory.COMPLETENESS].score
            > without_extras.breakdown[LinkedInCategory.COMPLETENESS].score
        )

    def test_completeness_is_never_reported_missing(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(EMPTY_PROFILE)
        assert result.breakdown[LinkedInCategory.COMPLETENESS].present is True


class TestProfileStrengthAndInsights:
    def test_profile_strength_matches_thresholds(self) -> None:
        config = LinkedInAnalysisConfig()
        scorer = LinkedInProfileScorer(config=config)
        strong = scorer.score(STRONG_PROFILE)
        empty = scorer.score(EMPTY_PROFILE)

        thresholds = dict(config.profile_strength_thresholds)
        assert strong.profile_strength in thresholds.values()
        assert empty.profile_strength == "Weak"

    def test_keyword_suggestions_empty_when_no_text_to_scan(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(EMPTY_PROFILE)
        assert result.keyword_suggestions == []

    def test_keyword_suggestions_capped_at_config_max(self) -> None:
        config = LinkedInAnalysisConfig(max_keyword_suggestions=2)
        scorer = LinkedInProfileScorer(config=config)
        result = scorer.score(PARTIAL_PROFILE)
        assert len(result.keyword_suggestions) <= 2

    def test_recruiter_tips_are_non_empty_for_any_profile(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(STRONG_PROFILE)
        assert len(result.recruiter_tips) > 0

    def test_next_steps_prioritizes_missing_sections_first(self) -> None:
        scorer = LinkedInProfileScorer()
        result = scorer.score(PARTIAL_PROFILE)
        assert len(result.next_steps) > 0
        # The first next step should be about a missing section, not a
        # low-scoring-but-present one, since missing sections are the
        # highest-leverage fix.
        assert "add a" in result.next_steps[0].lower()

    def test_next_steps_capped_at_config_count(self) -> None:
        config = LinkedInAnalysisConfig(next_steps_count=2)
        scorer = LinkedInProfileScorer(config=config)
        result = scorer.score(EMPTY_PROFILE)
        assert len(result.next_steps) <= 2


class TestConfigurableWeights:
    def test_custom_weights_change_overall_score(self) -> None:
        # Two configs that are identical except one puts ~all weight on
        # experience, the other ~all weight on certifications. Since
        # STRONG_PROFILE scores differently on each category, overall
        # scores must differ.
        experience_heavy = LinkedInAnalysisConfig(
            weights=LinkedInAnalysisWeights(
                headline=0.01, about=0.01, experience=0.90, skills=0.01,
                education=0.01, projects=0.01, certifications=0.01, completeness=0.04,
            )
        )
        certifications_heavy = LinkedInAnalysisConfig(
            weights=LinkedInAnalysisWeights(
                headline=0.01, about=0.01, experience=0.01, skills=0.01,
                education=0.01, projects=0.01, certifications=0.90, completeness=0.04,
            )
        )

        score_a = LinkedInProfileScorer(config=experience_heavy).score(PARTIAL_PROFILE).overall_score
        score_b = LinkedInProfileScorer(config=certifications_heavy).score(PARTIAL_PROFILE).overall_score

        assert score_a != score_b

    def test_weights_not_summing_to_one_are_normalized(self) -> None:
        # All eight at 10 sums to 80, not 100 — should be normalized to
        # equal 0.125 each rather than raising or silently breaking scoring.
        weights = LinkedInAnalysisWeights(
            headline=10, about=10, experience=10, skills=10,
            education=10, projects=10, certifications=10, completeness=10,
        )
        config = LinkedInAnalysisConfig(weights=weights)
        result = LinkedInProfileScorer(config=config).score(STRONG_PROFILE)

        assert 0 <= result.overall_score <= 100
        total_weight = sum(r.weight for r in result.breakdown.values())
        assert total_weight == pytest.approx(1.0, abs=1e-6)

    def test_negative_or_zero_total_weight_raises(self) -> None:
        with pytest.raises(ValueError):
            LinkedInAnalysisWeights(
                headline=0, about=0, experience=0, skills=0,
                education=0, projects=0, certifications=0, completeness=0,
            )
