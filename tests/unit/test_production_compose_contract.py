from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / "deploy/production/load-secrets.sh"


def _loader_env(tmp_path: Path) -> dict[str, str]:
    names = {
        "DATABASE_URL": "postgresql+asyncpg://slaif:password@postgres:5432/slaif_gateway",
        "TOKEN_HMAC_SECRET_V1": "hmac-value-with-trailing-newline\n",
        "ADMIN_SESSION_SECRET": "admin-session",
        "ONE_TIME_SECRET_ENCRYPTION_KEY": "one-time-key",
        "OPENAI_UPSTREAM_API_KEY": "upstream-openai",
        "OPENROUTER_API_KEY": "upstream-openrouter",
        "REDIS_URL": "redis://:password@redis:6379/0",
    }
    env = {"APP_ENV": "production"}
    for name, value in names.items():
        path = tmp_path / name.lower()
        path.write_bytes(value.encode())
        env[f"{name}_FILE"] = str(path)
    return env


def test_production_compose_contract_is_self_consistent() -> None:
    result = subprocess.run(
        ["python", "scripts/verify_production_compose.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT=OK" in result.stdout


def test_secret_loader_preserves_secret_bytes_without_logging_values(tmp_path: Path) -> None:
    env = os.environ.copy()
    for name in (
        "DATABASE_URL",
        "TOKEN_HMAC_SECRET_V1",
        "ADMIN_SESSION_SECRET",
        "ONE_TIME_SECRET_ENCRYPTION_KEY",
            "OPENAI_UPSTREAM_API_KEY",
            "OPENROUTER_API_KEY",
            "REDIS_URL",
    ):
        env.pop(name, None)
    env.update(_loader_env(tmp_path))
    result = subprocess.run(
        [str(LOADER), "python", "-c", "import json,os; print(json.dumps({k: len(os.environ[k]) for k in ('DATABASE_URL','TOKEN_HMAC_SECRET_V1','ADMIN_SESSION_SECRET','ONE_TIME_SECRET_ENCRYPTION_KEY','OPENAI_UPSTREAM_API_KEY','OPENROUTER_API_KEY','REDIS_URL')}))"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "DATABASE_URL": len("postgresql+asyncpg://slaif:password@postgres:5432/slaif_gateway"),
        "TOKEN_HMAC_SECRET_V1": len("hmac-value-with-trailing-newline\n"),
        "ADMIN_SESSION_SECRET": len("admin-session"),
        "ONE_TIME_SECRET_ENCRYPTION_KEY": len("one-time-key"),
        "OPENAI_UPSTREAM_API_KEY": len("upstream-openai"),
        "OPENROUTER_API_KEY": len("upstream-openrouter"),
        "REDIS_URL": len("redis://:password@redis:6379/0"),
    }
    assert "upstream-openai" not in result.stderr


def test_secret_loader_rejects_direct_and_file_conflict(tmp_path: Path) -> None:
    env = _loader_env(tmp_path)
    env["DATABASE_URL"] = "direct-value"
    result = subprocess.run(
        [str(LOADER), "true"],
        cwd=ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ambiguous configuration" in result.stderr
