from __future__ import annotations

from copy import deepcopy

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway import startup_warnings
from slaif_gateway.startup_warnings import emit_startup_configuration_warnings
from slaif_gateway.utils.secrets import generate_secret_key


class _FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, str]]] = []

    def warning(self, event: str, **fields: str) -> None:
        self.warnings.append((event, fields))


def _production_settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:database-password@localhost:5432/slaif",
        "REDIS_URL": "redis://:redis-password@localhost:6379/0",
        "TOKEN_HMAC_SECRET_V1": "hmac-secret-value-" + ("h" * 32),
        "ADMIN_SESSION_SECRET": "admin-session-secret-" + ("a" * 32),
        "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
        "OPENAI_UPSTREAM_API_KEY": "sk-openai-upstream-secret",
        "OPENROUTER_API_KEY": "sk-or-openrouter-secret",
    }
    values.update(overrides)
    return Settings(**values)


def _warning_text(fake_logger: _FakeLogger) -> str:
    parts: list[str] = []
    for event, fields in fake_logger.warnings:
        parts.append(event)
        parts.extend(str(value) for value in fields.values())
    return "\n".join(parts)


def test_production_metrics_public_override_emits_warning(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings(METRICS_PUBLIC_IN_PRODUCTION=True)

    emit_startup_configuration_warnings(settings)

    assert len(fake_logger.warnings) == 1
    assert "Production metrics are explicitly configured as public" in fake_logger.warnings[0][0]
    assert fake_logger.warnings[0][1]["setting"] == "METRICS_PUBLIC_IN_PRODUCTION"


def test_production_readyz_details_emits_warning(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings(READYZ_INCLUDE_DETAILS=True)

    emit_startup_configuration_warnings(settings)

    assert len(fake_logger.warnings) == 1
    assert "Production readiness details are enabled" in fake_logger.warnings[0][0]
    assert fake_logger.warnings[0][1]["setting"] == "READYZ_INCLUDE_DETAILS"


def test_production_metrics_auth_disabled_emits_warning(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings(METRICS_REQUIRE_AUTH=False)

    emit_startup_configuration_warnings(settings)

    assert len(fake_logger.warnings) == 1
    assert "Production metrics authentication is explicitly disabled" in fake_logger.warnings[0][0]
    assert fake_logger.warnings[0][1]["setting"] == "METRICS_REQUIRE_AUTH"


def test_non_production_defaults_do_not_emit_production_warnings(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = Settings(APP_ENV="test", DATABASE_URL=None)

    emit_startup_configuration_warnings(settings)

    assert fake_logger.warnings == []


def test_safe_production_settings_do_not_emit_warnings(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings()

    emit_startup_configuration_warnings(settings)

    assert fake_logger.warnings == []


def test_production_openai_api_key_boundary_warning_is_safe(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-slaif-public.secret")
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings()

    emit_startup_configuration_warnings(settings)

    assert len(fake_logger.warnings) == 1
    assert fake_logger.warnings[0][1]["setting"] == "OPENAI_API_KEY"
    text = _warning_text(fake_logger)
    assert "OPENAI_UPSTREAM_API_KEY" in text
    assert "sk-slaif-public.secret" not in text


def test_startup_warnings_do_not_log_secrets(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings(
        METRICS_PUBLIC_IN_PRODUCTION=True,
        READYZ_INCLUDE_DETAILS=True,
    )

    emit_startup_configuration_warnings(settings)

    text = _warning_text(fake_logger)
    forbidden_values = (
        settings.DATABASE_URL,
        settings.REDIS_URL,
        settings.TOKEN_HMAC_SECRET_V1,
        settings.ADMIN_SESSION_SECRET,
        settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
        settings.OPENAI_UPSTREAM_API_KEY,
        settings.OPENROUTER_API_KEY,
        "database-password",
        "redis-password",
    )
    for value in forbidden_values:
        assert value is not None
        assert value not in text


def test_startup_warning_helper_does_not_mutate_settings(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    monkeypatch.setattr(startup_warnings, "logger", fake_logger)
    settings = _production_settings(
        METRICS_PUBLIC_IN_PRODUCTION=True,
        READYZ_INCLUDE_DETAILS=True,
    )
    before = deepcopy(settings.model_dump())

    emit_startup_configuration_warnings(settings)

    assert settings.model_dump() == before


def test_create_app_emits_startup_warnings_once(monkeypatch) -> None:
    calls: list[Settings] = []

    def fake_emit(settings: Settings) -> None:
        calls.append(settings)

    monkeypatch.setattr("slaif_gateway.main.emit_startup_configuration_warnings", fake_emit)
    settings = Settings(APP_ENV="test", DATABASE_URL=None)

    create_app(settings)

    assert calls == [settings]
