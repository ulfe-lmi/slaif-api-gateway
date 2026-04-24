from typer.testing import CliRunner

from slaif_gateway.cli.main import app


runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "slaif-api-gateway 0.1.0" in result.stdout
