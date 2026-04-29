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


def test_db_upgrade_invokes_alembic_upgrade(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_upgrade(config, revision: str) -> None:
        called["config"] = config
        called["revision"] = revision

    monkeypatch.setattr("slaif_gateway.cli.db.alembic_command.upgrade", fake_upgrade)

    result = runner.invoke(app, ["db", "upgrade"])

    assert result.exit_code == 0
    assert called["revision"] == "head"
    assert called["config"].config_file_name.endswith("alembic.ini")


def test_db_current_invokes_alembic_current(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_current(config, *, verbose: bool) -> None:
        called["config"] = config
        called["verbose"] = verbose

    monkeypatch.setattr("slaif_gateway.cli.db.alembic_command.current", fake_current)

    result = runner.invoke(app, ["db", "current", "--verbose"])

    assert result.exit_code == 0
    assert called["verbose"] is True
    assert called["config"].config_file_name.endswith("alembic.ini")
