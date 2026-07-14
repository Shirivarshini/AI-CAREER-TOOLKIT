"""
Service layer package.

Services contain business logic and orchestrate one or more repositories
and/or external API clients. Routers (app/api/v1/*.py) call services;
services call repositories — routers never talk to the database directly.

Future modules will add, e.g.:
    app/services/resume_service.py
    app/services/github_service.py
    app/services/linkedin_service.py
    app/services/skill_gap_service.py
    app/services/auth_service.py
    app/services/report_service.py
"""
