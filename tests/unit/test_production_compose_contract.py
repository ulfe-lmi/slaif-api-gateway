from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / "deploy/production/load-secrets.sh"
_RUN_SPEC = importlib.util.spec_from_file_location("qualification_run", ROOT / "scripts/production-qualification/run.py")
assert _RUN_SPEC is not None and _RUN_SPEC.loader is not None
_RUN_MODULE = importlib.util.module_from_spec(_RUN_SPEC)
_RUN_SPEC.loader.exec_module(_RUN_MODULE)


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


def test_production_nginx_keeps_admin_landing_exact_and_metrics_private() -> None:
    source = (ROOT / "nginx/production.conf").read_text(encoding="utf-8")

    exact_admin = source.index("location = /admin {")
    admin_prefix = source.index("location /admin/ {")
    assert exact_admin < admin_prefix
    assert "proxy_pass http://api:8000;" in source[exact_admin:admin_prefix]
    assert "return 301" not in source[exact_admin:]
    assert "location /metrics" not in source
    assert "location = /metrics" not in source


def test_production_qualification_requires_real_redirect_following_and_authorized_metrics() -> None:
    source = (ROOT / "scripts/production-qualification/run.py").read_text(encoding="utf-8")

    assert "class _NoRedirect" not in source
    assert "urlsplit(landing_url).path != \"/admin\"" in source
    assert "status != 200" in source
    assert "positive_prometheus_sample_counts" in source
    assert '"positive_sample_present"' in source
    assert '"gateway_http_requests_total"' in source
    assert '"gateway_provider_requests_total"' in source
    assert '"gateway_tokens_total"' in source
    assert '"gateway_cost_eur_total"' in source
    assert "exec\",\n                \"-T\",\n                \"api\"" in source
    assert "--network" not in source
    assert '"network", "inspect"' in source
    assert '"exec", provider_container' in source


def test_positive_prometheus_sample_counts_rejects_metadata_zero_malformed_and_unrelated_lines() -> None:
    exposition = """\
# HELP gateway_http_requests_total HTTP requests
# TYPE gateway_http_requests_total counter
gateway_http_requests_total{method=\"GET\"} 4
gateway_http_requests_total_created{method=\"GET\"} 99
# HELP gateway_provider_requests_total provider requests
# TYPE gateway_provider_requests_total counter
gateway_provider_requests_total{provider=\"qualification-double\"} 0
# HELP gateway_tokens_total token totals
# TYPE gateway_tokens_total counter
# HELP gateway_cost_eur_total cost totals
# TYPE gateway_cost_eur_total counter
gateway_cost_eur_total{provider=\"qualification-double\"} NaN
gateway_http_requests_total{broken 3
unrelated_metric 500
"""

    assert _RUN_MODULE.positive_prometheus_sample_counts(exposition) == {
        "gateway_http_requests_total": 1,
        "gateway_provider_requests_total": 0,
        "gateway_tokens_total": 0,
        "gateway_cost_eur_total": 0,
    }

    assert _RUN_MODULE.positive_prometheus_sample_counts(
        "gateway_tokens_total{provider=\"qualification-double\"} 2.5e1\n"
    )["gateway_tokens_total"] == 1


def test_concurrency_validation_requires_correlated_active_stream_facts() -> None:
    reservation = {
        "endpoint": "/v1/chat/completions",
        "reservation_provider": "qualification-double",
        "reservation_resolved_model": "qualification-model",
        "reservation_streaming": "true",
        "reservation_status": "pending",
        "accounting_status": "pending",
    }
    valid = {
        "status": 200,
        "request_id_present": True,
        "thread_alive": True,
        "provider_forward_delta": 1,
        "redis_slots": 1,
        "reservation": reservation,
    }
    assert _RUN_MODULE.active_stream_is_valid(**valid) is True
    assert _RUN_MODULE.active_stream_is_valid(**valid, expected_endpoint="/v1/responses") is False
    assert _RUN_MODULE.active_stream_is_valid(
        **{**valid, "reservation": {**reservation, "endpoint": "/v1/responses"}},
        expected_endpoint="/v1/responses",
    ) is True
    for field, value in (
        ("status", 503),
        ("request_id_present", False),
        ("thread_alive", False),
        ("provider_forward_delta", 0),
        ("redis_slots", 0),
        ("reservation", None),
    ):
        candidate = {**valid, field: value}
        assert _RUN_MODULE.active_stream_is_valid(**candidate) is False


def test_concurrency_validation_bounds_recovery_overlap_and_final_evidence() -> None:
    assert _RUN_MODULE.recovery_503_is_safe(
        status=503,
        error_code="redis_rate_limit_unavailable",
        thread_alive=False,
        provider_forward_delta=0,
        redis_slots=0,
        accounting_unchanged=True,
    )
    for field, value in (
        ("status", 200),
        ("error_code", "other"),
        ("thread_alive", True),
        ("provider_forward_delta", 1),
        ("redis_slots", 1),
        ("accounting_unchanged", False),
    ):
        values = {
            "status": 503,
            "error_code": "redis_rate_limit_unavailable",
            "thread_alive": False,
            "provider_forward_delta": 0,
            "redis_slots": 0,
            "accounting_unchanged": True,
        }
        values[field] = value
        assert _RUN_MODULE.recovery_503_is_safe(**values) is False

    valid_overlap = {
        "status": 429,
        "error_code": "concurrency_rate_limit_exceeded",
        "provider_forward_delta": 0,
        "accounting_unchanged": True,
        "original_reservation_pending": True,
        "redis_slots": 1,
        "first_thread_alive": True,
    }
    assert _RUN_MODULE.overlap_evidence_is_valid(**valid_overlap) is True
    for field, value in (
        ("status", 200),
        ("error_code", "redis_rate_limit_unavailable"),
        ("provider_forward_delta", 1),
        ("accounting_unchanged", False),
        ("original_reservation_pending", False),
        ("redis_slots", 0),
        ("first_thread_alive", False),
    ):
        candidate = {**valid_overlap, field: value}
        assert _RUN_MODULE.overlap_evidence_is_valid(**candidate) is False

    evidence = _RUN_MODULE.bounded_concurrency_evidence(
        recovery_503_count=0,
        overlap_status=429,
        overlap_error_code="concurrency_rate_limit_exceeded",
        overlap_provider_forward_delta=0,
        overlap_accounting_unchanged=True,
        original_reservation_pending=True,
        original_thread_alive=True,
        active_slot=True,
        released_slot=True,
        following_status=200,
    )
    serialized = json.dumps(evidence)
    assert "body" not in serialized
    assert "secret" not in serialized
    assert "request_id" not in evidence


def test_active_stream_rejects_extra_or_mismatched_termination_facts() -> None:
    reservation = {
        "endpoint": "/v1/responses",
        "reservation_provider": "qualification-double",
        "reservation_resolved_model": "qualification-model",
        "reservation_streaming": "true",
        "reservation_status": "pending",
        "accounting_status": "pending",
    }
    valid = {
        "status": 200,
        "request_id_present": True,
        "thread_alive": True,
        "provider_forward_delta": 1,
        "redis_slots": 1,
        "reservation": reservation,
        "expected_endpoint": "/v1/responses",
    }
    assert _RUN_MODULE.active_stream_is_valid(**valid) is True
    for field, value in (
        ("status", 201),
        ("thread_alive", False),
        ("provider_forward_delta", 0),
        ("provider_forward_delta", 2),
        ("redis_slots", 0),
        ("redis_slots", 2),
        ("reservation", {**reservation, "reservation_provider": "other"}),
        ("reservation", {**reservation, "reservation_status": "released"}),
        ("reservation", {**reservation, "endpoint": "/v1/chat/completions"}),
    ):
        candidate = {**valid, field: value}
        assert _RUN_MODULE.active_stream_is_valid(**candidate) is False


def test_gateway_key_uuid_validation_and_bounded_termination_evidence() -> None:
    valid_uuid = "01234567-89ab-cdef-0123-456789abcdef"
    assert _RUN_MODULE.validate_gateway_key_id(valid_uuid) == valid_uuid
    for malformed in (
        "0123456789ab-cdef-0123-456789abcdef",
        "01234567-89ab-cdef-0123-456789abcde!",
        "01234567-89AB-cdef-0123-456789abcdef",
        "01234567-89ab-cdef-0123-456789abcdef;echo-no",
    ):
        with pytest.raises(ValueError):
            _RUN_MODULE.validate_gateway_key_id(malformed)

    evidence = _RUN_MODULE.bounded_api_termination_evidence(
        recovery_503_count=1,
        active_status=200,
        active_error_code="",
        active_request_id_present=True,
        active_thread_alive=True,
        active_provider_forward_delta=1,
        active_redis_slots=1,
        active_reservation_present=True,
        pending_before_kill=True,
        restart_ready=True,
        terminal_reservation_status="released",
        terminal_accounting_status="failed",
        counters_cleared=True,
        audit_present=True,
        client_thread_terminated_after_kill=True,
        provider_count_stable_after_kill=True,
    )
    serialized = json.dumps(evidence)
    assert "body" not in serialized
    assert "secret" not in serialized
    assert "url" not in serialized
    assert evidence["client_thread_terminated_after_kill"] is True
    assert evidence["provider_count_stable_after_kill"] is True
    assert set(evidence) == {
        "recovery_503_count",
        "active_status",
        "active_error_code",
        "active_request_id_present",
        "active_thread_alive",
        "active_provider_forward_delta",
        "active_redis_slots",
        "active_reservation_present",
        "pending_before_kill",
        "restart_ready",
        "terminal_reservation_status",
        "terminal_accounting_status",
        "counters_cleared",
        "audit_present",
        "client_thread_terminated_after_kill",
        "provider_count_stable_after_kill",
    }


def test_readyz_parser_requires_exact_ready_facts_and_bounds_not_ready() -> None:
    ready_payload = {
        "status": "ok",
        "database": "ok",
        "schema": "ok",
        "redis": "ok",
        "provider_secrets": "ok",
        "missing_provider_secret_env_vars": "must-not-be-emitted",
    }
    ready = _RUN_MODULE.parse_readyz_observation(200, ready_payload)
    assert ready["ready"] is True
    assert ready["redis_outage"] is False
    assert _RUN_MODULE.parse_readyz_observation(503, ready_payload)["ready"] is False
    assert _RUN_MODULE.parse_readyz_observation(
        200,
        {**ready_payload, "schema": "not_ready"},
    )["ready"] is False
    assert _RUN_MODULE.parse_readyz_observation(
        200,
        {**ready_payload, "provider_secrets": "missing"},
    )["ready"] is False
    assert _RUN_MODULE.parse_readyz_observation(
        503,
        {"status": "not_ready", "database": "ok", "redis": "error"},
    )["redis_outage"] is True
    assert _RUN_MODULE.parse_readyz_observation(200, ["not", "an", "object"])["state"] == "invalid"
    assert _RUN_MODULE.parse_readyz_observation(200, "malformed")["ready"] is False


def test_readyz_stability_counter_resets_and_bounded_evidence_is_content_free() -> None:
    count = 0
    count = _RUN_MODULE.readiness_consecutive_count(count, True)
    count = _RUN_MODULE.readiness_consecutive_count(count, True)
    assert count == 2
    assert _RUN_MODULE.readiness_consecutive_count(count, False) == 0
    observation = _RUN_MODULE.parse_readyz_observation(
        200,
        {"status": "ok", "database": "ok", "schema": "ok", "redis": "ok"},
    )
    evidence = _RUN_MODULE.bounded_readiness_evidence(observation, consecutive_successes=4)
    assert evidence == {
        "status": 200,
        "state": "ok",
        "database": "ok",
        "schema": "ok",
        "redis": "ok",
        "provider_secrets_ok": True,
        "consecutive_successes": 4,
    }
    assert "url" not in json.dumps(evidence)
    assert "missing_provider_secret_env_vars" not in json.dumps(evidence)
    assert _RUN_MODULE.public_readyz_denial_is_valid(403) is True
    assert _RUN_MODULE.public_readyz_denial_is_valid(404) is True
    assert _RUN_MODULE.public_readyz_denial_is_valid(200) is False


def test_public_readyz_probe_requires_exact_containers_and_inspected_subnet_membership() -> None:
    assert _RUN_MODULE.single_container_id("nginx-id\n", "nginx") == "nginx-id"
    for output in ("", "nginx-id\nother-id\n"):
        with pytest.raises(ValueError):
            _RUN_MODULE.single_container_id(output, "nginx")

    inspected = {
        "nginx-id": {"IPv4Address": "198.18.0.2/15"},
        "provider-id": {"IPv4Address": "198.18.0.3/15"},
    }
    assert _RUN_MODULE.inspected_ipv4_for_container(inspected, "nginx-id", "198.18.0.0/15") == "198.18.0.2"
    assert _RUN_MODULE.inspected_ipv4_for_container(inspected, "provider-id", "198.18.0.0/15") == "198.18.0.3"
    for container_id, subnet in (
        ("missing-id", "198.18.0.0/15"),
        ("nginx-id", "192.168.0.0/16"),
        ("nginx-id", "not-a-subnet"),
    ):
        with pytest.raises(ValueError):
            _RUN_MODULE.inspected_ipv4_for_container(inspected, container_id, subnet)


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
