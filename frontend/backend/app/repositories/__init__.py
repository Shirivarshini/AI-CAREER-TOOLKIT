"""
Repository layer package.

Repositories are the only layer allowed to run SQLAlchemy queries. They
take an `AsyncSession` (injected via `Depends(get_db)`) and expose
domain-specific data-access methods (e.g. `get_by_email`, `create`,
`list_by_user`). This isolates persistence details from business logic
in the service layer, and makes repositories easy to mock in unit tests.

Future modules will add, e.g.:
    app/repositories/user_repository.py
    app/repositories/resume_repository.py
    app/repositories/github_repository.py
    app/repositories/linkedin_repository.py
    app/repositories/skill_gap_repository.py
"""
