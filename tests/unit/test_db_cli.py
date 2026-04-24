from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings

runner = CliRunner()


def test_db_check_config_without_database_url(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = runner.invoke(app, ["db", "check-config"])

    assert result.exit_code == 0
    assert "DATABASE_URL configured: no" in result.stdout


def test_db_show_url_redacts_password(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://alice:supersecret@localhost:5432/slaif_gateway",
    )

    result = runner.invoke(app, ["db", "show-url"])

    assert result.exit_code == 0
    assert "supersecret" not in result.stdout
    assert "***" in result.stdout
