"""
Skill taxonomy repository.

Why this file exists
---------------------
Clean architecture calls for isolating *where the taxonomy data lives*
behind a repository, so `SkillGapService` and `SkillGapAnalyzer` never
know or care whether a role's required skills came from a JSON file, a
database, or an in-memory fixture in a test. Per the task: "Store
taxonomy in JSON for now. Later this should migrate to PostgreSQL." —
this interface is what makes that migration a one-file change.

This is not a database repository yet (no `SkillTaxonomy` table exists —
PRD section 11's data model only persists *results* via `SkillGapResult`,
not the taxonomy itself). It's a *read-only reference-data* repository,
which is still the correct place for this concern under clean
architecture: the service layer stays storage-agnostic and only calls
`get_taxonomy` / `list_roles`.

How it works
------------
- `SkillTaxonomyRepository` is the abstract interface: `get_taxonomy(role)
  -> RoleTaxonomy | None` and `list_roles() -> list[str]`.
- `JSONSkillTaxonomyRepository` is the only implementation today. It
  parses `app/data/skill_taxonomy.json` once at construction time (the
  file is small and static — no benefit to re-reading it per request) and
  builds two lookup structures: canonical role name -> `RoleTaxonomy`, and
  every alias (plus the canonical name itself, all lowercased/trimmed) ->
  canonical role name. `get_taxonomy()` normalizes the requested role the
  same way before looking it up, so "backend developer", "Backend
  Developer", and "backend engineer" (an alias) all resolve to the same
  taxonomy.
- `reload()` re-parses the file on demand — useful for a future admin
  endpoint that updates the taxonomy without restarting the process, and
  for tests that swap in a different taxonomy file.

Where future code should go
----------------------------
When the taxonomy migrates to PostgreSQL, add a sibling
`PostgresSkillTaxonomyRepository` (bound to `Depends(get_db)`,
constructing `RoleTaxonomy`/`SkillRequirement` dataclasses from ORM rows
the same way this class builds them from JSON) implementing the same
`SkillTaxonomyRepository` interface, and swap it in via
`get_skill_taxonomy_repository()` in `app/services/skill_gap_service.py`
— `SkillGapService` and `SkillGapAnalyzer` will not need to change at all.
"""

import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.core.exceptions import AppException
from app.services.skill_gap.types import LearningResource, RoleTaxonomy, SkillRequirement

logger = logging.getLogger(__name__)


class SkillTaxonomyLoadError(AppException):
    """Raised when the skill taxonomy source (a JSON file today) is missing or malformed."""

    error_code = "SKILL_TAXONOMY_LOAD_ERROR"


class SkillTaxonomyRepository(ABC):
    """Interface for reading the role/skill taxonomy, independent of storage backend."""

    @abstractmethod
    def get_taxonomy(self, role: str) -> RoleTaxonomy | None:
        """Return the `RoleTaxonomy` matching `role` (by canonical name or alias), or None."""
        raise NotImplementedError

    @abstractmethod
    def list_roles(self) -> list[str]:
        """Return every canonical role name available in the taxonomy, for dropdowns/error messages."""
        raise NotImplementedError


def _normalize_role_key(role: str) -> str:
    return " ".join(role.strip().lower().split())


class JSONSkillTaxonomyRepository(SkillTaxonomyRepository):
    """Loads the role/skill taxonomy from a JSON file (see `app/data/skill_taxonomy.json`)."""

    def __init__(self, json_path: str | Path) -> None:
        self._json_path = Path(json_path)
        self._taxonomies_by_role: dict[str, RoleTaxonomy] = {}
        self._alias_to_role: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Re-parse the taxonomy JSON file from disk, replacing the in-memory index."""
        if not self._json_path.exists():
            raise SkillTaxonomyLoadError(f"Skill taxonomy file not found: {self._json_path}")

        try:
            raw = json.loads(self._json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SkillTaxonomyLoadError(
                f"Skill taxonomy file at {self._json_path} is not valid JSON: {exc}"
            ) from exc

        taxonomies_by_role: dict[str, RoleTaxonomy] = {}
        alias_to_role: dict[str, str] = {}

        for entry in raw.get("roles", []):
            try:
                taxonomy = self._parse_role_entry(entry)
            except (KeyError, TypeError) as exc:
                raise SkillTaxonomyLoadError(
                    f"Malformed role entry in {self._json_path}: {exc}"
                ) from exc

            role_key = _normalize_role_key(taxonomy.role)
            taxonomies_by_role[role_key] = taxonomy
            alias_to_role[role_key] = role_key
            for alias in taxonomy.aliases:
                alias_to_role[_normalize_role_key(alias)] = role_key

        self._taxonomies_by_role = taxonomies_by_role
        self._alias_to_role = alias_to_role
        logger.info("Loaded skill taxonomy for %d role(s) from %s", len(taxonomies_by_role), self._json_path)

    def get_taxonomy(self, role: str) -> RoleTaxonomy | None:
        role_key = self._alias_to_role.get(_normalize_role_key(role))
        if role_key is None:
            return None
        return self._taxonomies_by_role.get(role_key)

    def list_roles(self) -> list[str]:
        return sorted(taxonomy.role for taxonomy in self._taxonomies_by_role.values())

    @staticmethod
    def _parse_role_entry(entry: dict) -> RoleTaxonomy:
        return RoleTaxonomy(
            role=entry["role"],
            aliases=tuple(entry.get("aliases", [])),
            must_have=tuple(
                JSONSkillTaxonomyRepository._parse_requirement(item) for item in entry.get("must_have", [])
            ),
            nice_to_have=tuple(
                JSONSkillTaxonomyRepository._parse_requirement(item)
                for item in entry.get("nice_to_have", [])
            ),
        )

    @staticmethod
    def _parse_requirement(item: dict) -> SkillRequirement:
        resource_data = item.get("resource")
        resource = (
            LearningResource(title=resource_data["title"], url=resource_data["url"])
            if resource_data
            else None
        )
        return SkillRequirement(skill=item["skill"], resource=resource)


@lru_cache
def get_skill_taxonomy_repository() -> SkillTaxonomyRepository:
    """
    Return a process-wide cached `SkillTaxonomyRepository` singleton.

    Cached (rather than constructed per-request, like `ResumeFileRepository`)
    because this repository does real I/O + parsing at construction time —
    re-reading and re-indexing a static JSON file on every request would be
    wasted work. `settings.SKILL_TAXONOMY_ABSOLUTE_PATH` is the only input,
    so this stays trivially swappable in tests via `lru_cache`'s `.cache_
    clear()` plus a monkeypatched `Settings`.
    """
    from app.config.settings import get_settings

    settings = get_settings()
    return JSONSkillTaxonomyRepository(settings.SKILL_TAXONOMY_ABSOLUTE_PATH)
