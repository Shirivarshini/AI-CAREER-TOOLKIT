"""
Tests for AWS-deployment-readiness concerns: the fail-fast production
secrets check, structured JSON logging, and DB engine configuration.

Run with:
    pytest -v tests/test_deployment.py
"""

import json
import logging

import pytest


class TestProductionSecretSafety:
    """Settings must refuse to start with APP_ENV=production and placeholder secrets."""

    def test_refuses_default_jwt_secret_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import Settings

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-password")

        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            Settings(_env_file=None)

    def test_refuses_default_db_password_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import Settings

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "a-real-random-secret-value")

        with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
            Settings(_env_file=None)

    def test_allows_production_with_real_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import Settings

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "a-real-random-secret-value")
        monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-password")

        settings = Settings(_env_file=None)
        assert settings.IS_PRODUCTION is True

    def test_allows_default_secrets_outside_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import Settings

        monkeypatch.setenv("APP_ENV", "development")

        settings = Settings(_env_file=None)
        assert settings.IS_PRODUCTION is False


class TestGunicornWorkerCountEnvParsing:
    """GUNICORN_WORKERS='' (the .env.example default) must not break settings parsing."""

    def test_empty_gunicorn_workers_falls_back_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import Settings

        monkeypatch.setenv("GUNICORN_WORKERS", "")
        settings = Settings(_env_file=None)
        assert settings.GUNICORN_WORKERS is None

    def test_explicit_gunicorn_workers_is_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import Settings

        monkeypatch.setenv("GUNICORN_WORKERS", "4")
        settings = Settings(_env_file=None)
        assert settings.GUNICORN_WORKERS == 4


class TestJsonLogFormatter:
    """The production JSON log formatter must produce valid, queryable JSON lines."""

    def test_formats_basic_record_as_valid_json(self) -> None:
        from app.core.logging_config import _JsonFormatter

        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello %s", args=("world",), exc_info=None,
        )

        parsed = json.loads(formatter.format(record))

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "app.test"
        assert parsed["message"] == "hello world"
        assert "timestamp" in parsed

    def test_surfaces_extra_fields_as_top_level_keys(self) -> None:
        from app.core.logging_config import _JsonFormatter

        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="request handled", args=(), exc_info=None,
        )
        record.method = "GET"
        record.status_code = 200

        parsed = json.loads(formatter.format(record))

        assert parsed["method"] == "GET"
        assert parsed["status_code"] == 200

    def test_includes_exception_traceback_when_present(self) -> None:
        from app.core.logging_config import _JsonFormatter

        formatter = _JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="app.test", level=logging.ERROR, pathname=__file__, lineno=1,
                msg="something failed", args=(), exc_info=sys.exc_info(),
            )

        parsed = json.loads(formatter.format(record))

        assert "exception" in parsed
        assert "ValueError: boom" in parsed["exception"]


class TestDatabaseEngineConfig:
    """The async engine must be configured from Settings, ready for RDS."""

    def test_engine_pool_settings_come_from_settings(self) -> None:
        from app.config.settings import get_settings
        from app.core.database import engine

        settings = get_settings()
        assert engine.pool.size() == settings.DB_POOL_SIZE

    def test_ssl_disabled_by_default_for_local_postgres(self) -> None:
        from app.core.database import _connect_args

        # Local/Docker-Compose Postgres (POSTGRES_SSL_MODE=disable, the
        # default) must not have `ssl` forced on, or the connection fails.
        assert _connect_args == {}

    @pytest.mark.asyncio
    async def test_check_database_connection_survives_raw_driver_exceptions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Regression test for the bug caught during manual gunicorn testing:
        a connection-level failure (e.g. ECONNREFUSED) raises the raw
        driver/OS exception during pool checkout, not a wrapped
        SQLAlchemyError. check_database_connection() must catch it and
        return False, never let it propagate.
        """
        from app.core import database as database_module

        class _ExplodingConnectContextManager:
            async def __aenter__(self):
                raise ConnectionRefusedError("[Errno 111] Connection refused")

            async def __aexit__(self, *args):
                return False

        # AsyncEngine.connect is a read-only instance attribute (it's a
        # bound method resolved via the class) — patch it on the class,
        # not the instance.
        monkeypatch.setattr(
            type(database_module.engine), "connect", lambda self: _ExplodingConnectContextManager()
        )

        result = await database_module.check_database_connection()

        assert result is False
