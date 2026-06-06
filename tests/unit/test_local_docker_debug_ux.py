from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_value(name: str) -> str | None:
    for line in (REPO_ROOT / ".env.example").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    return None


def test_env_example_enables_local_redis_rate_limits_and_debug_logs() -> None:
    assert _env_value("ENABLE_REDIS_RATE_LIMITS") == "true"
    assert _env_value("DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE") == "60"
    assert _env_value("DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS") == "5"
    assert _env_value("LOG_LEVEL") == "DEBUG"
    assert _env_value("STRUCTURED_LOGS") == "false"
    assert _env_value("GUNICORN_LOG_LEVEL") == "debug"
    assert _env_value("CELERY_LOG_LEVEL") == "DEBUG"


def test_production_docs_recommend_info_structured_logging() -> None:
    combined = "\n".join(
        [
            (REPO_ROOT / "docs/configuration.md").read_text(),
            (REPO_ROOT / "docs/deployment.md").read_text(),
        ]
    )

    assert "LOG_LEVEL=INFO" in combined
    assert "STRUCTURED_LOGS=true" in combined
    assert "GUNICORN_LOG_LEVEL=info" in combined
    assert "CELERY_LOG_LEVEL=INFO" in combined


def test_docker_refresh_script_is_executable_safe_and_syntax_valid() -> None:
    script = REPO_ROOT / "scripts/docker-refresh.sh"
    content = script.read_text()

    assert script.stat().st_mode & stat.S_IXUSR
    assert "docker compose down -v" not in content
    assert "git reset" not in content
    subprocess.run(["bash", "-n", str(script)], cwd=REPO_ROOT, check=True)


def test_parallel_test_scripts_are_explicit_and_syntax_valid() -> None:
    unit_script = REPO_ROOT / "scripts/test-unit-parallel.sh"
    safe_script = REPO_ROOT / "scripts/test-parallel-safe.sh"

    for script in (unit_script, safe_script):
        content = script.read_text()
        assert script.stat().st_mode & stat.S_IXUSR
        assert "DATABASE_URL=" not in content
        assert "pytest -n auto" not in content
        assert "PYTEST_XDIST_WORKERS" in content or script == safe_script
        subprocess.run(["bash", "-n", str(script)], cwd=REPO_ROOT, check=True)

    unit_content = unit_script.read_text()
    assert "min(20, cores)" in unit_content
    assert '--dist loadscope' in unit_content
    assert 'pytest tests/unit -n "$WORKERS"' in unit_content

    safe_content = safe_script.read_text()
    assert "tests/integration" in safe_content
    assert "tests/e2e" in safe_content
    assert "tests/browser" in safe_content


def test_openai_gateway_smoke_example_compiles_and_uses_openai_env_convention() -> None:
    example = REPO_ROOT / "examples/openai_gateway_smoke.py"
    content = example.read_text()

    subprocess.run([sys.executable, "-m", "py_compile", str(example)], cwd=REPO_ROOT, check=True)
    forbidden = [
        "SLAIF" + "_API_KEY",
        "SLAIF" + "_BASE_URL",
        "OPENAI_API_KEY=" + "sk-",
        "sk-" + "proj",
        "sk-" + "live",
        "sk-" + "real",
        "Bearer " + "sk-",
    ]
    for value in forbidden:
        assert value not in content
    assert "OpenAI()" in content
