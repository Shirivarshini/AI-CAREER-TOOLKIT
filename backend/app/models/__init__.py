"""
Model package - importing every ORM model here registers it on
`app.core.database.Base.metadata`, which `alembic/env.py` points
`target_metadata` at for autogeneration.

Where future code should go
----------------------------
Add one `from app.models.<module> import <Model>  # noqa: F401` line per
new table, alongside the one below.
"""

from app.models.user import User  # noqa: F401
from app.models.analysis import (  # noqa: F401
    GitHubAnalysis,
    LinkedInAnalysis,
    ResumeAnalysis,
    SkillGapResult,
)
