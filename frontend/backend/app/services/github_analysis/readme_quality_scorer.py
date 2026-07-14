"""
README Quality category scorer.

Why this file exists
---------------------
Per PRD 6.2: "README-quality assessment on top repos" with suggestions
that are "specific and actionable (e.g., naming which repos need
READMEs)." This scorer evaluates each analyzed repository's README
content directly (not just presence/absence) and names exactly which
repos are missing one.

How it works
------------
`context.readme_analyzed_repos` (populated by `GitHubAnalysisService` —
the top `config.readme_analysis_limit` repos, each with `readme_text`
fetched, or `None` if the repo has no README) is scored per-repo, then
averaged:
  - A repo with no README scores 0 for this signal — missing entirely is
    the worst outcome, not a neutral one.
  - A repo with a README is scored as the average of four equally
    weighted sub-signals: content length, heading structure, presence of
    a code example, and mention of an onboarding-style section
    ("usage", "install", "getting started", etc.) — see
    `app/utils/readme_quality.py` for the underlying pure functions.

Where future code should go
----------------------------
If deeper README analysis is wanted later (e.g. an LLM-based qualitative
read, matching PRD 15's "hybrid: rules + LLM" recommendation for the
Resume module), it would slot in as an additional sub-signal in
`_score_single_readme`, gated behind a config flag — the category
interface does not need to change.
"""

from app.services.github_analysis.base import SignalScorer
from app.services.github_analysis.config import GitHubAnalysisConfig
from app.services.github_analysis.types import GitHubProfileContext, RawSignalScore, RepoSummary
from app.utils.readme_quality import (
    contains_any_section,
    has_code_block,
    has_headings,
    word_count,
)


class ReadmeQualityScorer(SignalScorer):
    """Scores the content quality of READMEs across the analyzed top repositories."""

    def __init__(self, config: GitHubAnalysisConfig) -> None:
        self._config = config

    def score(self, context: GitHubProfileContext) -> RawSignalScore:
        analyzed = context.readme_analyzed_repos

        if not analyzed:
            return RawSignalScore(
                score=0.0,
                suggestions=[
                    "No repositories were available to check for READMEs. Add a public "
                    "repository and give it a README describing what it does."
                ],
                details={"repos_missing_readmes": []},
            )

        per_repo_scores: list[float] = []
        missing: list[str] = []
        thin: list[str] = []

        for repo in analyzed:
            if not repo.readme_text or not repo.readme_text.strip():
                per_repo_scores.append(0.0)
                missing.append(repo.name)
                continue

            repo_score = self._score_single_readme(repo)
            per_repo_scores.append(repo_score)
            if repo_score < 50:
                thin.append(repo.name)

        score = round(sum(per_repo_scores) / len(per_repo_scores), 2)

        suggestions: list[str] = []
        if missing:
            preview = ", ".join(missing[:5])
            suggestions.append(f"Add READMEs to: {preview}.")
        if thin:
            preview = ", ".join(thin[:5])
            suggestions.append(
                f"Expand the READMEs in {preview} with a clear description, setup/usage "
                "instructions, and a code example — thin READMEs read as unfinished work."
            )

        return RawSignalScore(
            score=score,
            suggestions=suggestions,
            details={"repos_missing_readmes": missing},
        )

    def _score_single_readme(self, repo: RepoSummary) -> float:
        text = repo.readme_text or ""
        words = word_count(text)

        length_score = min(words / self._config.good_readme_word_count, 1.0) * 100
        structure_score = 100.0 if has_headings(text) else 40.0
        code_example_score = 100.0 if has_code_block(text) else 50.0
        section_score = 100.0 if contains_any_section(text, self._config.readme_signal_sections) else 50.0

        return round((length_score + structure_score + code_example_score + section_score) / 4, 2)
