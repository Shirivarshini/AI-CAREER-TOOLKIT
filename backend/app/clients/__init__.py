"""
Third-party API clients.

Why this package exists
------------------------
Clean architecture keeps "talking to an external service over HTTP" out
of the service layer: services orchestrate business logic and depend on
a client's typed interface, not on `httpx`/URLs/HTTP status codes
directly. Each external integration (GitHub REST API now; LinkedIn PDF
parsing needs no client since it never calls a remote API, per PRD 5.3's
ToS-driven "no scraping" design; future integrations would follow the
same pattern) gets its own module here.

Where future code should go
----------------------------
A new external API integration gets its own `<service>_client.py` in this
package, following `github_client.py`'s shape: a small class that raises
`app.core.exceptions.AppException` subclasses on failure, never leaks raw
`httpx` exceptions or response objects past its own boundary, and is
constructed with `Settings` (never hardcoded URLs/tokens).
"""
