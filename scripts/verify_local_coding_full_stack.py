#!/usr/bin/env python3
"""Bounded 155-f verifier for the real Codex/Gateway/Local Coding path.

The verifier is deliberately fail-closed and emits only fixed facts.  It is a
task-local evidence tool, not a deployment or production runner.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = Path("/home/ubuntu/codex-work/slaif-local-coding").resolve()
RUNTIME_REFERENCE = Path("/tmp/slaif-155f-runtime.env")
GATEWAY_REPORT_HEAD = "6bb67f4ca19f231b2f214e30c964ea0aac685d3e"
GATEWAY_IMPLEMENTATION_HEAD = "4eb768254fcde0a4108bcabb35f175a74bd07a3f"
GATEWAY_ACTIVATION_HEAD = "7e6c8fa8c67f5957de1d740d7b592a5dfbb15358"
LOCAL_REPORT_HEAD = "6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8"
LOCAL_SIGNED_CONTRACT_HEAD = "356be8345dd71d6fddf829278651d18e485731d4"
CODEX_VERSION = "0.149.0"
CODEX_MODEL = "qwen3.8-27b"
FAILURE_MODEL = "155f-synthetic-provider-failure"
CODEX_MODULE_ID = "codex-0.149-responses-v1"
CODEX_MODULE_VERSION = "3"
CODEX_FIXTURE_SHA256 = "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec"
SESSION_FIXTURE = REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json"
HISTORICAL_FIXTURE = REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-structural.json"
V2_FIXTURE = REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-structural-v2.json"
HISTORICAL_FIXTURE_SHA256 = "0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d"
V2_FIXTURE_SHA256 = "baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1"
ORDER_PATH = REPO_ROOT / "oap/orders/155-f-real-codex-local-coding-qwen-acceptance.md"
TASK_DB = "slaif_gateway_oap_155f_live"
SERVICE_TOKEN_ENV = "SLAIF_155F_LOCAL_SERVICE_TOKEN"
SIGNING_SECRET_ENV = "SLAIF_155F_LOCAL_SIGNING_SECRET"
QWEN_TOKEN_ENV = "QWEN3090_API_KEY"
MAX_OUTPUT_BYTES = 256 * 1024
LOCAL_METRICS_URL_PATH = "/metrics"
RELAY_BODY_LIMIT = 512 * 1024


class VerificationError(RuntimeError):
    """A fixed verifier failure that cannot reflect private values."""


@dataclass(frozen=True, slots=True)
class RuntimeReference:
    endpoint: str
    credential_source: Path


@dataclass(frozen=True, slots=True)
class SeededKey:
    gateway_key_id: uuid.UUID
    owner_id: uuid.UUID
    plaintext: str


def _run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: float = 120) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("command_failed") from exc
    if len(result.stdout) > MAX_OUTPUT_BYTES or len(result.stderr) > MAX_OUTPUT_BYTES:
        raise VerificationError("command_output_exceeded")
    return result


def _safe_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return str(parsed) == value


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = _run(["git", *args], cwd=cwd)
    if result.returncode != 0:
        raise VerificationError("git_check_failed")
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise VerificationError("git_output_invalid") from exc


def _verify_commit_topology() -> None:
    current_head = _git("rev-parse", "HEAD")
    if _git("rev-parse", f"{GATEWAY_ACTIVATION_HEAD}^1") != GATEWAY_REPORT_HEAD:
        raise VerificationError("gateway_activation_parent_mismatch")
    activation_changed = _git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", GATEWAY_ACTIVATION_HEAD
    )
    if activation_changed.splitlines() != [
        "oap/active",
        "oap/orders/155-f-real-codex-local-coding-qwen-acceptance.md",
    ]:
        raise VerificationError("gateway_activation_not_order_only")
    if _run(
        ["git", "merge-base", "--is-ancestor", GATEWAY_ACTIVATION_HEAD, current_head],
        cwd=REPO_ROOT,
    ).returncode != 0:
        raise VerificationError("gateway_activation_ancestry_failed")
    if _git("rev-parse", f"{GATEWAY_REPORT_HEAD}^1") != GATEWAY_IMPLEMENTATION_HEAD:
        raise VerificationError("gateway_report_parent_mismatch")
    changed = _git("diff-tree", "--no-commit-id", "--name-only", "-r", GATEWAY_REPORT_HEAD)
    if changed != "oap/reports/155-e-codex-thread-namespace-and-key-bound-session.md":
        raise VerificationError("gateway_report_not_report_only")
    if _run(["git", "merge-base", "--is-ancestor", GATEWAY_REPORT_HEAD, "HEAD"], cwd=REPO_ROOT).returncode != 0:
        raise VerificationError("gateway_report_ancestry_failed")
    if _git("rev-parse", "HEAD", cwd=LOCAL_ROOT) != LOCAL_REPORT_HEAD:
        raise VerificationError("local_report_head_mismatch")
    if _git("status", "--porcelain", cwd=LOCAL_ROOT):
        raise VerificationError("local_dependency_not_clean")
    if _run(["git", "merge-base", "--is-ancestor", LOCAL_SIGNED_CONTRACT_HEAD, LOCAL_REPORT_HEAD], cwd=LOCAL_ROOT).returncode != 0:
        raise VerificationError("local_signed_contract_ancestry_failed")
    for pr, expected in (("291", GATEWAY_REPORT_HEAD), ("7", LOCAL_REPORT_HEAD)):
        result = _run(["gh", "pr", "view", pr, "--repo", "ulfe-lmi/slaif-api-gateway" if pr == "291" else "ulfe-lmi/slaif-local-coding", "--json", "state,isDraft,headRefOid,mergeStateStatus,autoMergeRequest"])
        if result.returncode != 0:
            raise VerificationError("github_pr_state_unavailable")
        try:
            state = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError("github_pr_state_invalid") from exc
        if state.get("state") != "OPEN" or state.get("isDraft") is not False or state.get("headRefOid") != expected or state.get("mergeStateStatus") not in {"CLEAN", "MERGEABLE"} or state.get("autoMergeRequest") is not None:
            raise VerificationError("github_pr_state_mismatch")
    checks = _run(["gh", "pr", "checks", "291", "--repo", "ulfe-lmi/slaif-api-gateway"])
    if checks.returncode != 0:
        raise VerificationError("github_checks_unavailable")
    check_lines = checks.stdout.decode("utf-8").splitlines()
    if len(check_lines) < 10 or any(line.split(maxsplit=2)[1] != "pass" for line in check_lines if len(line.split(maxsplit=2)) >= 2):
        raise VerificationError("github_checks_not_green")
    if _git(
        "diff", "--exit-code", f"{GATEWAY_REPORT_HEAD}^1", GATEWAY_REPORT_HEAD, "--", "oap/reports"
    ):
        raise VerificationError("gateway_report_diff_failed")
    strategic_order = Path(
        "/home/ubuntu/codex-work/slaif-api-gateway/oap/orders/155-f-real-codex-local-coding-qwen-acceptance.md"
    )
    if ORDER_PATH.read_bytes() != strategic_order.read_bytes():
        raise VerificationError("order_bytes_mismatch")
    if (REPO_ROOT / "oap/active").read_text(encoding="utf-8") != "155-f\n":
        raise VerificationError("active_selector_mismatch")


def _read_runtime_reference() -> RuntimeReference:
    try:
        mode = stat.S_IMODE(RUNTIME_REFERENCE.stat().st_mode)
    except OSError as exc:
        raise VerificationError("runtime_reference_unavailable") from exc
    if mode != 0o600 or RUNTIME_REFERENCE.stat().st_uid != os.getuid():
        raise VerificationError("runtime_reference_permissions")
    entries: dict[str, str] = {}
    try:
        for line in RUNTIME_REFERENCE.read_text(encoding="utf-8").splitlines():
            if not line or "=" not in line:
                raise VerificationError("runtime_reference_format")
            key, value = line.split("=", 1)
            entries[key] = value
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError("runtime_reference_unreadable") from exc
    if set(entries) != {"SLAIF_155F_QWEN_BASE_URL", "SLAIF_155F_QWEN_CREDENTIAL_SOURCE"}:
        raise VerificationError("runtime_reference_keys")
    endpoint = entries["SLAIF_155F_QWEN_BASE_URL"]
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.path or parsed.query or parsed.fragment:
        raise VerificationError("runtime_endpoint_shape")
    source = Path(entries["SLAIF_155F_QWEN_CREDENTIAL_SOURCE"])
    try:
        source_stat = source.stat()
    except OSError as exc:
        raise VerificationError("credential_source_unavailable") from exc
    if not stat.S_ISREG(source_stat.st_mode) or source.is_symlink() or source_stat.st_uid != os.getuid() or not os.access(source, os.R_OK):
        raise VerificationError("credential_source_shape")
    return RuntimeReference(endpoint=endpoint, credential_source=source)


def _source_qwen_credential_only_for_local(runtime: RuntimeReference) -> None:
    """Source the credential once and pass only the selected variable onward."""
    script = (
        "set +x; . \"$SLAIF_155F_CREDENTIAL_SOURCE\" >/dev/null 2>&1; "
        "test -n \"${QWEN3090_API_KEY:-}\"; "
        "exec /usr/bin/env -i PATH=\"${PATH:-/usr/bin:/bin}\" "
        "QWEN3090_API_KEY=\"${QWEN3090_API_KEY}\" "
        "python3 -c 'import os; raise SystemExit(0 if os.environ.get(\"QWEN3090_API_KEY\") else 1)'"
    )
    result = _run(
        ["bash", "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "SLAIF_155F_CREDENTIAL_SOURCE": str(runtime.credential_source),
        },
        timeout=10,
    )
    if result.returncode != 0:
        raise VerificationError("protected_qwen_credential_unavailable")


def _verify_fixtures() -> None:
    import scripts.capture_codex_protocol as capture

    if hashlib.sha256(HISTORICAL_FIXTURE.read_bytes()).hexdigest() != HISTORICAL_FIXTURE_SHA256:
        raise VerificationError("historical_fixture_changed")
    if hashlib.sha256(V2_FIXTURE.read_bytes()).hexdigest() != V2_FIXTURE_SHA256:
        raise VerificationError("structural_fixture_changed")
    fixture = json.loads(SESSION_FIXTURE.read_bytes())
    capture.validate_0149_session_fixture(fixture)
    if hashlib.sha256(capture.canonical_json_bytes(fixture)).hexdigest() != CODEX_FIXTURE_SHA256:
        raise VerificationError("session_fixture_digest_mismatch")
    if fixture["relationships"]["selected_source"]["canonical_key"] != "session_id":
        raise VerificationError("session_source_mismatch")
    if fixture["relationships"]["same_session_stability"] is not True or fixture["relationships"]["cross_session_isolation"] is not True:
        raise VerificationError("session_relationship_missing")


def _verify_protected_model_health(runtime: RuntimeReference) -> None:
    probe = (
        "import json, os, urllib.request; "
        "url=os.environ['SLAIF_155F_QWEN_BASE_URL'].rstrip('/')+'/models'; "
        "request=urllib.request.Request(url, headers={'Authorization': 'Bearer '+os.environ['QWEN3090_API_KEY']}); "
        "response=urllib.request.urlopen(request, timeout=20); "
        "payload=json.load(response); "
        "data=payload.get('data') if isinstance(payload, dict) else None; "
        f"raise SystemExit(0 if response.status == 200 and isinstance(data, list) and any(isinstance(item, dict) and item.get('id') == {CODEX_MODEL!r} for item in data) else 1)"
    )
    script = (
        "set +x; . \"$SLAIF_155F_CREDENTIAL_SOURCE\" >/dev/null 2>&1; "
        "test -n \"${QWEN3090_API_KEY:-}\"; "
        "exec /usr/bin/env -i PATH=\"${PATH:-/usr/bin:/bin}\" "
        "SLAIF_155F_QWEN_BASE_URL=\"${SLAIF_155F_QWEN_BASE_URL}\" "
        "QWEN3090_API_KEY=\"${QWEN3090_API_KEY}\" "
        "python3 -c \"$SLAIF_155F_PROBE\""
    )
    result = _run(
        ["bash", "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "SLAIF_155F_CREDENTIAL_SOURCE": str(runtime.credential_source),
            "SLAIF_155F_QWEN_BASE_URL": runtime.endpoint,
            "SLAIF_155F_PROBE": probe,
        },
        timeout=30,
    )
    if result.returncode != 0:
        raise VerificationError("protected_model_mismatch")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _install_codex(root: Path) -> Path:
    install = root / "codex-install"
    install.mkdir(mode=0o700)
    result = _run(["npm", "init", "-y"], cwd=install, timeout=30)
    if result.returncode != 0:
        raise VerificationError("codex_install_failed")
    result = _run(["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", f"@openai/codex@{CODEX_VERSION}"], cwd=install, timeout=180)
    if result.returncode != 0:
        raise VerificationError("codex_install_failed")
    binary = install / "node_modules/.bin/codex"
    result = _run([str(binary), "--version"], timeout=10)
    if result.returncode != 0 or result.stdout != f"codex-cli {CODEX_VERSION}\n".encode("ascii"):
        raise VerificationError("codex_version_mismatch")
    return binary


def _docker_prefix() -> tuple[str, ...]:
    direct = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    if direct.returncode == 0:
        return ("docker",)
    sudoed = _run(
        ["sudo", "-n", "docker", "info", "--format", "{{.ServerVersion}}"], timeout=15
    )
    if sudoed.returncode == 0:
        return ("sudo", "-n", "docker")
    raise VerificationError("docker_boundary_unavailable")


def _docker(*args: str, timeout: float = 180) -> subprocess.CompletedProcess[bytes]:
    return _run([*_docker_prefix(), *args], timeout=timeout)


def _start_postgres(root: Path) -> tuple[str, str, bool]:
    image = "postgres:16"
    image_before = _docker("image", "inspect", image).returncode == 0
    if not image_before and _docker("pull", image).returncode != 0:
        raise VerificationError("postgres_image_unavailable")
    name = f"slaif-155f-postgres-{os.getpid()}"
    _docker("rm", "-f", name, timeout=30)
    started = False
    try:
        result = _docker(
            "run",
            "-d",
            "--name",
            name,
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            "POSTGRES_PASSWORD=slaif-155f-db",
            "-e",
            f"POSTGRES_DB={TASK_DB}",
            "-p",
            "127.0.0.1::5432",
            image,
            timeout=60,
        )
        if result.returncode != 0:
            raise VerificationError("postgres_start_failed")
        started = True
        port_result = _docker("port", name, "5432/tcp", timeout=30)
        if port_result.returncode != 0:
            raise VerificationError("postgres_port_failed")
        try:
            port_text = port_result.stdout.decode("ascii")
            port = int(port_text.rsplit(":", 1)[1].strip())
        except (UnicodeDecodeError, ValueError, IndexError) as exc:
            raise VerificationError("postgres_port_failed") from exc
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = _docker(
                "exec", name, "pg_isready", "-U", "postgres", "-d", TASK_DB, timeout=10
            )
            if ready.returncode == 0:
                database = _docker(
                    "exec",
                    name,
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    TASK_DB,
                    "-Atqc",
                    "select current_database()",
                    timeout=10,
                )
                if database.returncode != 0 or database.stdout.strip() != TASK_DB.encode("ascii"):
                    raise VerificationError("postgres_named_database_missing")
                return (
                    f"postgresql+asyncpg://postgres:slaif-155f-db@127.0.0.1:{port}/{TASK_DB}",
                    name,
                    not image_before,
                )
            time.sleep(1)
        raise VerificationError("postgres_ready_timeout")
    except Exception:
        if started:
            _docker("rm", "-f", name, timeout=30)
        raise


async def _seed_database(
    database_url: str, *, relay_port: int, failure_port: int
) -> tuple[SeededKey, SeededKey]:
    sys.path.insert(0, str(REPO_ROOT / "app"))
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.config import Settings
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService
    from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        async with sessions() as session:
            suffix = secrets.token_hex(8)
            institution = await InstitutionsRepository(session).create_institution(name=f"155f-{suffix}", country="SI")
            owner = await OwnersRepository(session).create_owner(name="Verifier", surname="155f", email=f"155f-{suffix}@example.invalid", institution_id=institution.id)
            cohort = await CohortsRepository(session).create_cohort(name=f"155f-{suffix}", description="disposable", starts_at=now - timedelta(minutes=1), ends_at=now + timedelta(hours=1))
            provider_configs = ProviderConfigsRepository(session)
            await provider_configs.create_provider_config(
                provider="local-coding",
                display_name="155f local",
                base_url=f"http://127.0.0.1:{relay_port}/v1",
                api_key_env_var=SERVICE_TOKEN_ENV,
                enabled=True,
                timeout_seconds=300,
                max_retries=0,
            )
            await provider_configs.create_provider_config(
                provider="synthetic-failure",
                display_name="155f failure",
                base_url=f"http://127.0.0.1:{failure_port}/v1",
                api_key_env_var="SLAIF_155F_FAILURE_KEY",
                enabled=True,
                timeout_seconds=10,
                max_retries=0,
            )
            capabilities = default_responses_capabilities()
            capabilities.update({"streaming": True, "image_input": True, "codex_request_envelope": True, "codex_client_tools": True, "codex_streaming_tool_events": True})
            await ModelRoutesRepository(session).create_model_route(
                requested_model=CODEX_MODEL,
                provider="local-coding",
                upstream_model=CODEX_MODEL,
                match_type="exact",
                endpoint="/v1/responses",
                priority=1,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={
                    "responses": capabilities,
                    "local_coding": {
                        "contract_version": "local-coding-v1",
                        "route_name": "qwen38-vision-codex",
                        "tool_policy_version": "responses-tool-policy-v1",
                        "identity_mode": "signed_identity_v1",
                        "replay_mode": "process_local_ttl_lru",
                        "deployment_mode": "single_worker",
                    },
                },
            )
            failure_capabilities = default_responses_capabilities()
            await ModelRoutesRepository(session).create_model_route(
                requested_model=FAILURE_MODEL,
                provider="synthetic-failure",
                upstream_model=FAILURE_MODEL,
                match_type="exact",
                endpoint="/v1/responses",
                priority=1,
                visible_in_models=False,
                supports_streaming=False,
                capabilities={"responses": failure_capabilities},
            )
            pricing = PricingRulesRepository(session)
            for provider, model in (
                ("local-coding", CODEX_MODEL),
                ("synthetic-failure", FAILURE_MODEL),
            ):
                await pricing.create_pricing_rule(
                    provider=provider,
                    upstream_model=model,
                    endpoint="/v1/responses",
                    valid_from=now - timedelta(minutes=1),
                    currency="EUR",
                    input_price_per_1m=Decimal("1"),
                    output_price_per_1m=Decimal("1"),
                    request_price=Decimal("0"),
                )
            service = KeyService(settings=Settings(), gateway_keys_repository=GatewayKeysRepository(session), one_time_secrets_repository=OneTimeSecretsRepository(session), audit_repository=AuditRepository(session), model_routes_repository=ModelRoutesRepository(session))
            policy = {"version": 1, "local_coding_repository_scope": "155f-repository", "allowed_capabilities": ["codex_request_envelope", "codex_client_tools", "codex_streaming_tool_events"], "client_module": {"id": CODEX_MODULE_ID, "version": CODEX_MODULE_VERSION, "fixture_sha256": CODEX_FIXTURE_SHA256}}
            key_input = dict(owner_id=owner.id, cohort_id=cohort.id, valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1), cost_limit_eur=Decimal("20"), token_limit_total=2_000_000, request_limit_total=50, allowed_models=[CODEX_MODEL, FAILURE_MODEL], allowed_endpoints=["/v1/models", "/v1/responses"], responses_policy=policy)
            created = await service.create_gateway_key(CreateGatewayKeyInput(**key_input, note="155f disposable key"))
            second_input = dict(key_input)
            second_input["request_limit_total"] = 1
            second = await service.create_gateway_key(CreateGatewayKeyInput(**second_input, note="155f disposable second key"))
            await session.commit()
            return SeededKey(created.gateway_key_id, created.owner_id, created.plaintext_key), SeededKey(second.gateway_key_id, second.owner_id, second.plaintext_key)
    except Exception as exc:
        raise VerificationError("database_seed_failed") from exc
    finally:
        await engine.dispose()


def _gateway_environment(database_url: str, *, gateway_port: int, service_token: str, signing_secret: str, derivation_secret: str, encryption_key: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(REPO_ROOT / "app"), "PYTHONDONTWRITEBYTECODE": "1", "APP_ENV": "test", "DATABASE_URL": database_url, "GATEWAY_KEY_PREFIX": "sk-slaif-", "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-", "ACTIVE_HMAC_KEY_VERSION": "1", "TOKEN_HMAC_SECRET_V1": "155f-gateway-hmac-secret-012345678901", "ADMIN_SESSION_SECRET": "155f-admin-secret-012345678901", "ONE_TIME_SECRET_ENCRYPTION_KEY": encryption_key, "ENABLE_REDIS_RATE_LIMITS": "false", "ENABLE_ADMIN_DASHBOARD": "false", "ENABLE_EMAIL_DELIVERY": "false", "ENABLE_METRICS": "true", "LOG_LEVEL": "WARNING", "STRUCTURED_LOGS": "true", "LOCAL_CODING_SERVICE_TOKEN": service_token, "LOCAL_CODING_SIGNING_SECRET_V1": signing_secret, "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1": derivation_secret, "SLAIF_155F_FAILURE_KEY": "synthetic-failure-key", "UVICORN_ACCESS_LOG": "false", "APP_BASE_URL": f"http://127.0.0.1:{gateway_port}"}
    return env


def _local_config(root: Path, *, local_port: int, runtime: RuntimeReference) -> Path:
    config = root / "local-coding.toml"
    body = f'''[server]\nlisten_host = "127.0.0.1"\nlisten_port = {local_port}\n\n[gateway_ingress]\nmode = "service_bearer_signed_identity_v1"\nservice_token_env = "{SERVICE_TOKEN_ENV}"\nsigning_secret_env = "{SIGNING_SECRET_ENV}"\n\n[upstream]\nbase_url = "{runtime.endpoint}"\napi_key_env = "{QWEN_TOKEN_ENV}"\nmodel = "{CODEX_MODEL}"\nconnect_timeout_seconds = 10\nrequest_timeout_seconds = 300\nwrite_timeout_seconds = 30\npool_timeout_seconds = 10\n\n[compiler]\nenabled = true\napi_key_env = "{QWEN_TOKEN_ENV}"\n\n[cache]\nbackend = "filesystem"\nroot = "{(root / "cache").as_posix()}"\nfallback_root = "{(root / "cache-fallback").as_posix()}"\n\n[constitution]\nenabled = true\nidentity_source = "signed_request"\n\n[observation]\n\n[[routes]]\nname = "qwen38-vision-codex"\nmodel = "{CODEX_MODEL}"\nmax_images_per_request = 1\nimage_overflow_policy = "retain_newest"\nresponses_tool_policy = "drop_disabled_codex_search"\nobservation_enabled = true\nconstitution_enabled = true\n'''
    config.write_text(body, encoding="utf-8")
    config.chmod(0o600)
    return config


@dataclass(frozen=True, slots=True)
class CapturedRequest:
    path: str
    body: bytes
    headers: dict[str, str]


class _ForwardingRelay(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], local_port: int) -> None:
        super().__init__(server_address, _RelayHandler)
        self.local_port = local_port
        self.captured: list[CapturedRequest] = []
        self.response_statuses: list[int] = []
        self.forwarded = 0
        self.rejected = 0
        self._capture_lock = threading.Lock()

    def remember(self, request: CapturedRequest) -> None:
        with self._capture_lock:
            self.captured.append(request)
            self.forwarded += 1

    def remember_response(self, status: int) -> None:
        with self._capture_lock:
            self.response_statuses.append(status)

    def snapshot(self) -> tuple[CapturedRequest, ...]:
        with self._capture_lock:
            return tuple(self.captured)


class _RelayHandler(http.server.BaseHTTPRequestHandler):
    server: _ForwardingRelay

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _forward(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length < 0 or length > RELAY_BODY_LIMIT:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        headers = {
            key.lower(): value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        captured = CapturedRequest(path=self.path, body=body, headers=headers)
        self.server.remember(captured)
        try:
            with httpx.Client(timeout=300, follow_redirects=False) as client:
                response = client.request(
                    self.command,
                    f"http://127.0.0.1:{self.server.local_port}{self.path}",
                    headers=headers,
                    content=body,
                )
        except httpx.HTTPError:
            self.server.rejected += 1
            self.send_error(502)
            return
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            if key.lower() not in {"content-length", "connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)
        self.server.remember_response(response.status_code)

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()


class _FailureServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, _FailureHandler)
        self.calls = 0
        self._calls_lock = threading.Lock()

    def record_call(self) -> None:
        with self._calls_lock:
            self.calls += 1


class _FailureHandler(http.server.BaseHTTPRequestHandler):
    server: _FailureServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        self.server.record_call()
        length = int(self.headers.get("content-length", "0"))
        if length > RELAY_BODY_LIMIT:
            self.send_error(413)
            return
        self.rfile.read(length)
        body = b'{"error":{"message":"synthetic provider failure","type":"server_error","code":"synthetic_failure"}}'
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.send_response(404)
        self.end_headers()


def _start_relay(local_port: int) -> tuple[_ForwardingRelay, threading.Thread]:
    relay = _ForwardingRelay(("127.0.0.1", 0), local_port)
    thread = threading.Thread(target=relay.serve_forever, name="155f-relay", daemon=True)
    thread.start()
    return relay, thread


def _start_failure_server() -> tuple[_FailureServer, threading.Thread]:
    server = _FailureServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, name="155f-failure", daemon=True)
    thread.start()
    return server, thread


def _start_process(command: list[str], *, cwd: Path, env: dict[str, str], source: Path | None = None) -> subprocess.Popen[bytes]:
    if source is None:
        return subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    selected = (
        "set +x; . \"$SLAIF_155F_CREDENTIAL_SOURCE\" >/dev/null 2>&1; "
        "test -n \"${QWEN3090_API_KEY:-}\"; "
        "exec /usr/bin/env -i PATH=\"${PATH:-/usr/bin:/bin}\" "
        "PYTHONPATH=\"${PYTHONPATH:-}\" "
        "SLAIF_155F_LOCAL_SERVICE_TOKEN=\"${SLAIF_155F_LOCAL_SERVICE_TOKEN}\" "
        "SLAIF_155F_LOCAL_SIGNING_SECRET=\"${SLAIF_155F_LOCAL_SIGNING_SECRET}\" "
        "QWEN3090_API_KEY=\"${QWEN3090_API_KEY}\" \"$@\""
    )
    launcher = [
        "bash",
        "-c",
        selected,
        "155f-local-launch",
        *command,
    ]
    local_env = dict(env)
    local_env["SLAIF_155F_CREDENTIAL_SOURCE"] = str(source)
    return subprocess.Popen(
        launcher,
        cwd=cwd,
        env=local_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_http(url: str, *, expected: set[int] = {200}, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=5, follow_redirects=False)
            if response.status_code in expected:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise VerificationError("service_ready_timeout")


def _relay_request(
    relay: _ForwardingRelay, path: str, headers: dict[str, str], body: bytes
) -> int:
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(
                f"http://127.0.0.1:{relay.server_address[1]}{path}",
                headers=headers,
                content=body,
            )
            status = response.status_code
    except httpx.HTTPError as exc:
        raise VerificationError("relay_replay_failed") from exc
    return status


def _replay_request(relay: _ForwardingRelay, request: CapturedRequest) -> int:
    return _relay_request(relay, request.path, request.headers, request.body)


async def _verify_accounting(database_url: str, keys: tuple[SeededKey, SeededKey], raw_markers: tuple[str, ...]) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    total_rows = 0
    try:
        async with sessions() as session:
            for key in keys:
                gateway_key = await session.get(GatewayKey, key.gateway_key_id)
                reservations = list((await session.execute(select(QuotaReservation).where(QuotaReservation.gateway_key_id == key.gateway_key_id))).scalars())
                ledgers = list((await session.execute(select(UsageLedger).where(UsageLedger.gateway_key_id == key.gateway_key_id))).scalars())
                if gateway_key is None or not reservations or len(reservations) != len(ledgers):
                    raise VerificationError("accounting_rows_incomplete")
                total_rows += len(reservations)
                if gateway_key.tokens_reserved_total != 0 or any(row.status != "finalized" for row in reservations):
                    non_failure = [row for row in reservations if row.requested_model != FAILURE_MODEL]
                    if gateway_key.tokens_reserved_total != 0 or any(
                        row.status != "finalized" for row in non_failure
                    ) or any(row.status == "pending" for row in reservations):
                        raise VerificationError("accounting_not_terminal")
                for reservation in reservations:
                    if reservation.quota_mode != "strict_bounded" or reservation.external_tool_capabilities != [] or reservation.external_tool_destination_ids != [] or reservation.external_tool_provider is not None or reservation.external_tool_route_id is not None:
                        raise VerificationError("accounting_external_facts")
                for ledger in ledgers:
                    encoded = json.dumps({"response_metadata": ledger.response_metadata, "usage_raw": ledger.usage_raw, "error_message": ledger.error_message}, default=str)
                    if any(marker in encoded for marker in raw_markers):
                        raise VerificationError("accounting_raw_identity_leak")
                    if any("external_tool" in key_name.lower() or "hold" in key_name.lower() or "fee" in key_name.lower() for key_name in _metadata_keys(ledger.response_metadata)):
                        raise VerificationError("accounting_external_metadata")
                    if ledger.accounting_status not in {"finalized", "failed"}:
                        raise VerificationError("accounting_status_incomplete")
                    if ledger.requested_model != FAILURE_MODEL and ledger.accounting_status != "finalized":
                        raise VerificationError("success_ledger_not_finalized")
                    if ledger.total_tokens < 0 or (ledger.actual_cost_eur is not None and ledger.actual_cost_eur < 0):
                        raise VerificationError("accounting_values_invalid")
                successful_ledgers = [
                    ledger for ledger in ledgers if ledger.requested_model != FAILURE_MODEL
                ]
                if gateway_key.requests_used_total != len(successful_ledgers):
                    raise VerificationError("accounting_request_counter_mismatch")
                if gateway_key.tokens_used_total != sum(
                    ledger.total_tokens for ledger in successful_ledgers
                ):
                    raise VerificationError("accounting_token_counter_mismatch")
                actual_cost = sum(
                    (ledger.actual_cost_eur or 0) for ledger in successful_ledgers
                )
                if gateway_key.cost_used_eur != actual_cost:
                    raise VerificationError("accounting_cost_counter_mismatch")
    finally:
        await engine.dispose()
    return total_rows


async def _verify_failure_accounting(database_url: str, key: SeededKey) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            gateway_key = await session.get(GatewayKey, key.gateway_key_id)
            reservations = list(
                (
                    await session.execute(
                        select(QuotaReservation).where(
                            QuotaReservation.gateway_key_id == key.gateway_key_id
                        )
                    )
                ).scalars()
            )
            ledgers = list(
                (
                    await session.execute(
                        select(UsageLedger).where(UsageLedger.gateway_key_id == key.gateway_key_id)
                    )
                ).scalars()
            )
            if gateway_key is None or len(reservations) != len(ledgers):
                raise VerificationError("failure_accounting_rows_incomplete")
            released = [row for row in reservations if row.status == "released"]
            if len(released) != 1 or gateway_key.tokens_reserved_total != 0:
                raise VerificationError("failure_reservation_not_released")
            failure_ledgers = [row for row in ledgers if row.accounting_status == "failed"]
            if len(failure_ledgers) != 1:
                raise VerificationError("failure_ledger_not_terminal")
    finally:
        await engine.dispose()


def _metadata_keys(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _metadata_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _metadata_keys(child)


@dataclass(frozen=True, slots=True)
class LocalMetrics:
    ingress_responses: int
    compiler_attempts: int
    cache_hits: int
    cache_misses: int
    rehydration_hits: int
    rehydration_injected: int
    tool_policy_drops: int
    upstream_failures: int


def _metric_total(metrics_text: str, metric_name: str, *, label_filter: str | None = None) -> int:
    total = 0
    for line in metrics_text.splitlines():
        if not line or line.startswith("#") or not line.startswith(metric_name):
            continue
        if not (line[len(metric_name) :].startswith(" ") or line[len(metric_name) :].startswith("{")):
            continue
        if label_filter is not None and label_filter not in line:
            continue
        try:
            total += int(float(line.rsplit(" ", 1)[1]))
        except (ValueError, IndexError):
            raise VerificationError("local_metrics_invalid")
    return total


def _local_metrics(port: int) -> LocalMetrics:
    try:
        response = httpx.get(f"http://127.0.0.1:{port}{LOCAL_METRICS_URL_PATH}", timeout=10)
    except httpx.HTTPError as exc:
        raise VerificationError("local_metrics_unavailable") from exc
    if response.status_code != 200:
        raise VerificationError("local_metrics_unavailable")
    text = response.text
    return LocalMetrics(
        ingress_responses=_metric_total(
            text, "slaif_requests_total", label_filter='status="200"'
        ),
        compiler_attempts=_metric_total(text, "slaif_constitution_compiler_attempts_total"),
        cache_hits=_metric_total(text, "slaif_constitution_cache_hits_total"),
        cache_misses=_metric_total(text, "slaif_constitution_cache_misses_total"),
        rehydration_hits=_metric_total(
            text, "slaif_constitution_rehydration_total", label_filter='state="hit"'
        ),
        rehydration_injected=_metric_total(
            text, "slaif_constitution_rehydration_total", label_filter='reason="rehydrated"'
        ),
        tool_policy_drops=_metric_total(
            text,
            "slaif_responses_tool_policy_total",
            label_filter='reason="disabled_codex_search_removed"',
        ),
        upstream_failures=_metric_total(text, "slaif_upstream_failures_total"),
    )


def _successful_relay_count(statuses: tuple[int, ...] | list[int]) -> int:
    """Count only the fixed 200 response class accepted as provider forwarding."""
    return sum(status == 200 for status in statuses)


def _assert_local_bound_privacy(
    requests: tuple[CapturedRequest, ...],
    *,
    raw_aliases: set[str],
    service_token: str,
) -> None:
    """Reject raw client aliases in Local-bound data, allowing signed fields."""
    service_authorization = f"Bearer {service_token}"
    for request in requests:
        if any(alias.encode("utf-8") in request.body for alias in raw_aliases):
            raise VerificationError("raw_client_alias_forwarded")
        for name, value in request.headers.items():
            if name.lower().startswith("x-slaif-"):
                continue
            if name.lower() == "authorization" and value == service_authorization:
                continue
            if any(alias in value for alias in raw_aliases):
                raise VerificationError("raw_client_alias_forwarded")


def _assert_required_evidence(evidence: dict[str, object]) -> None:
    required = (
        "session_a1_a2_equal",
        "session_b_different",
        "session_second_key_different",
        "cache_reuse_observed",
        "rehydration_observed",
        "exact_replay_rejected",
        "failure_rollback_observed",
        "provider_counts_observed",
        "postgres_rows_observed",
        "hosted_tools_stripped",
        "privacy_observed",
        "post_cleanup_model_ok",
    )
    if any(evidence.get(name) is not True for name in required):
        raise VerificationError("required_composed_evidence_missing")
    if type(evidence.get("provider_calls")) is not int or evidence["provider_calls"] <= 0:
        raise VerificationError("provider_call_count_missing")
    if type(evidence.get("relay_calls")) is not int or evidence["relay_calls"] <= 0:
        raise VerificationError("relay_call_count_missing")
    if evidence["provider_calls"] != evidence.get("relay_calls"):
        raise VerificationError("provider_call_count_mismatch")


def _run_composed(root: Path, runtime: RuntimeReference, codex_binary: Path) -> dict[str, object]:
    import scripts.capture_codex_protocol as capture
    from openai import OpenAI

    postgres_url, container, pulled = _start_postgres(root)
    gateway = local = None
    relay = failure_server = None
    relay_thread = failure_thread = None
    gateway_port = _free_port()
    local_port = 18031
    service_token = secrets.token_urlsafe(32)
    signing_secret = secrets.token_urlsafe(32)
    derivation_secret = secrets.token_urlsafe(32)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    gateway_env = _gateway_environment(
        postgres_url,
        gateway_port=gateway_port,
        service_token=service_token,
        signing_secret=signing_secret,
        derivation_secret=derivation_secret,
        encryption_key=encryption_key,
    )
    env_for_migration = dict(os.environ, **gateway_env)
    env_for_migration.pop("TEST_DATABASE_URL", None)
    migration = _run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env_for_migration,
        timeout=120,
    )
    if migration.returncode != 0:
        raise VerificationError("migration_failed")
    relay, relay_thread = _start_relay(local_port)
    failure_server, failure_thread = _start_failure_server()
    previous_environment = os.environ.copy()
    os.environ.update(gateway_env)
    try:
        seeded = asyncio.run(_seed_database(postgres_url, relay_port=relay.server_address[1], failure_port=failure_server.server_address[1]))
    finally:
        os.environ.clear()
        os.environ.update(previous_environment)
    key_one, key_two = seeded
    local_config = _local_config(root, local_port=local_port, runtime=runtime)
    local_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(LOCAL_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SLAIF_155F_LOCAL_SERVICE_TOKEN": service_token,
        "SLAIF_155F_LOCAL_SIGNING_SECRET": signing_secret,
    }
    try:
        local = _start_process(
            ["uv", "run", "--project", str(LOCAL_ROOT), "--frozen", "slaif-local-coding", "--config", str(local_config)],
            cwd=LOCAL_ROOT,
            env=local_env,
            source=runtime.credential_source,
        )
        gateway = _start_process(
            [sys.executable, "-m", "uvicorn", "slaif_gateway.main:app", "--host", "127.0.0.1", "--port", str(gateway_port), "--no-access-log", "--log-level", "warning"],
            cwd=REPO_ROOT,
            env=gateway_env,
        )
        _wait_http(f"http://127.0.0.1:{local_port}/healthz")
        _wait_http(f"http://127.0.0.1:{local_port}/readyz")
        _wait_http(f"http://127.0.0.1:{gateway_port}/healthz")
        client = OpenAI(api_key=key_one.plaintext, base_url=f"http://127.0.0.1:{gateway_port}/v1", max_retries=0)
        session_a = str(uuid.uuid4())
        session_b = str(uuid.uuid4())
        installation = str(uuid.uuid4())
        raw_aliases = {session_a, session_b, installation}

        def metadata(session: str) -> dict[str, str]:
            turn = str(uuid.uuid4())
            window = str(uuid.uuid4())
            raw_aliases.update({session, turn, window})
            return {
                "session_id": session,
                "thread_id": session,
                "root_turn_id": turn,
                "turn_id": turn,
                "x-codex-installation-id": installation,
                "x-codex-window-id": window,
            }

        def request_body(text: str, session: str, *, image: bool = False) -> dict[str, object]:
            content: list[dict[str, str]] = [{"type": "input_text", "text": text}]
            if image:
                content.append({"type": "input_image", "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="})
            return {
                "model": CODEX_MODEL,
                "input": [{"type": "message", "role": "user", "content": content}],
                "extra_body": {"client_metadata": metadata(session)},
            }

        baseline = _local_metrics(local_port)
        relay_start = len(relay.response_statuses)
        models = client.models.list()
        if not any(item.id == CODEX_MODEL for item in models.data):
            raise VerificationError("gateway_model_visibility_failed")
        client.responses.create(
            **request_body("155f ordinary", session_a),
            tools=[{"type": "function", "name": "local_lookup", "description": "local", "parameters": {"type": "object"}}],
        )
        streamed = client.responses.create(
            **request_body("155f stream", session_a),
            stream=True,
        )
        stream_events = list(streamed)
        if not any(getattr(event, "type", None) == "response.completed" for event in stream_events):
            raise VerificationError("stream_completion_event_missing")
        client.responses.create(
            **request_body("155f image", session_a, image=True),
        )
        project_text = "# AGENTS.md instructions for /synthetic\n\n<INSTRUCTIONS>\nMUST use bounded synthetic policy.\n</INSTRUCTIONS>"
        project_body = {
            "model": CODEX_MODEL,
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": project_text}]}],
            "tools": [{"type": "tool_search"}, {"type": "web_search"}],
            "extra_body": {"client_metadata": metadata(session_a)},
        }
        client.responses.create(**project_body)
        client.responses.create(**project_body)
        no_root_body = {
            **request_body("155f zero root", session_a),
        }
        client.responses.create(**no_root_body)

        home = root / "codex-home"
        work = root / "codex-work"
        catalog = root / "codex-catalog.json"
        home.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        codex_env = capture._isolated_environment(home)
        codex_env["OPENAI_API_KEY"] = key_one.plaintext
        codex_env["SLAIF_CODEX_CAPTURE_API_KEY"] = key_one.plaintext
        capture._write_0149_model_catalog(codex_binary, catalog, environment=codex_env, model=CODEX_MODEL)
        first_index = len(relay.snapshot())
        first = _run(capture._exec_command_0149(codex_binary, workdir=work, port=gateway_port, model=CODEX_MODEL, model_catalog=catalog, output_path=root / "codex-out-1", ephemeral=False), cwd=REPO_ROOT, env=codex_env, timeout=180)
        if first.returncode != 0:
            raise VerificationError("codex_session_a_failed")
        thread = capture._session_capture_thread_id(first.stdout)
        first_capture = relay.snapshot()[first_index:]
        if len(first_capture) != 1:
            raise VerificationError("codex_session_a_request_count")
        second_index = len(relay.snapshot())
        second = _run(capture._exec_resume_command_0149(codex_binary, workdir=work, port=gateway_port, model=CODEX_MODEL, model_catalog=catalog, output_path=root / "codex-out-2", thread_id=thread), cwd=work, env=codex_env, timeout=180)
        if second.returncode != 0:
            raise VerificationError("codex_session_resume_failed")
        second_capture = relay.snapshot()[second_index:]
        if len(second_capture) != 1:
            raise VerificationError("codex_session_resume_request_count")
        third_index = len(relay.snapshot())
        third = _run(capture._exec_command_0149(codex_binary, workdir=work, port=gateway_port, model=CODEX_MODEL, model_catalog=catalog, output_path=root / "codex-out-3", ephemeral=False), cwd=REPO_ROOT, env=codex_env, timeout=180)
        if third.returncode != 0:
            raise VerificationError("codex_session_b_failed")
        third_capture = relay.snapshot()[third_index:]
        if len(third_capture) != 1:
            raise VerificationError("codex_session_b_request_count")
        session_a1 = first_capture[0].headers.get("x-slaif-session")
        session_a2 = second_capture[0].headers.get("x-slaif-session")
        session_b_value = third_capture[0].headers.get("x-slaif-session")
        if not session_a1 or session_a1 != session_a2:
            raise VerificationError("signed_session_a_relationship_failed")
        if not session_b_value or session_b_value == session_a1:
            raise VerificationError("signed_session_b_isolation_failed")
        replay_status = _replay_request(relay, first_capture[0])
        if replay_status != 409:
            raise VerificationError("exact_replay_not_rejected")
        bad_signature = dict(first_capture[0].headers)
        bad_signature["x-slaif-signature"] = "v1=" + "0" * 64
        if _relay_request(relay, first_capture[0].path, bad_signature, first_capture[0].body) != 403:
            raise VerificationError("signature_tamper_not_rejected")
        if _relay_request(relay, first_capture[0].path, first_capture[0].headers, first_capture[0].body + b" ") != 403:
            raise VerificationError("body_tamper_not_rejected")
        if _relay_request(relay, "/v1/chat/completions", first_capture[0].headers, first_capture[0].body) != 403:
            raise VerificationError("path_tamper_not_rejected")
        if _relay_request(relay, first_capture[0].path + "?tamper=1", first_capture[0].headers, first_capture[0].body) != 403:
            raise VerificationError("query_tamper_not_rejected")
        second_client = OpenAI(api_key=key_two.plaintext, base_url=f"http://127.0.0.1:{gateway_port}/v1", max_retries=0)
        second_key_index = len(relay.snapshot())
        second_client.responses.create(**request_body("155f second key", session_a))
        second_key_capture = relay.snapshot()[second_key_index:]
        if len(second_key_capture) != 1 or second_key_capture[0].headers.get("x-slaif-session") in {None, session_a1}:
            raise VerificationError("signed_session_second_key_isolation_failed")
        over_quota_before = len(relay.snapshot())
        try:
            second_client.responses.create(**request_body("155f over quota", session_a))
        except Exception:
            pass
        else:
            raise VerificationError("over_quota_not_rejected")
        if len(relay.snapshot()) != over_quota_before:
            raise VerificationError("over_quota_forwarded")
        invalid_key_before = len(relay.snapshot())
        try:
            OpenAI(api_key="sk-slaif-invalid", base_url=f"http://127.0.0.1:{gateway_port}/v1", max_retries=0).models.list()
        except Exception:
            pass
        else:
            raise VerificationError("invalid_key_not_rejected")
        if len(relay.snapshot()) != invalid_key_before:
            raise VerificationError("invalid_key_forwarded")
        malformed_before = len(relay.snapshot())
        try:
            client.responses.create(
                model=CODEX_MODEL,
                input=request_body("155f malformed aliases", session_a)["input"],
                extra_body={"client_metadata": {"session_id": session_a, "thread_id": str(uuid.uuid4())}},
            )
        except Exception:
            pass
        else:
            raise VerificationError("unequal_aliases_not_rejected")
        if len(relay.snapshot()) != malformed_before:
            raise VerificationError("unequal_aliases_forwarded")
        try:
            client.responses.create(**{**request_body("155f hosted", session_a), "tools": [{"type": "web_search"}], "tool_choice": "required"})
        except Exception:
            pass
        else:
            raise VerificationError("hosted_tool_choice_not_rejected")
        adapter_required_before = len(relay.snapshot())
        try:
            client.responses.create(
                **{
                    **request_body("155f adapter required", session_a),
                    "tools": [{"type": "tool_search"}, {"type": "web_search"}],
                    "tool_choice": "required",
                }
            )
        except Exception:
            pass
        else:
            raise VerificationError("adapter_required_not_rejected")
        if len(relay.snapshot()) != adapter_required_before:
            raise VerificationError("adapter_required_forwarded")
        local_before_failure = _local_metrics(local_port)
        before_failure = len(relay.snapshot())
        try:
            client.responses.create(**{**request_body("155f failure", session_a), "model": FAILURE_MODEL})
        except Exception:
            pass
        else:
            raise VerificationError("synthetic_failure_not_observed")
        if len(relay.snapshot()) != before_failure or failure_server.calls != 1:
            raise VerificationError("failure_provider_call_count_invalid")
        local_after_failure = _local_metrics(local_port)
        if local_after_failure != local_before_failure:
            raise VerificationError("failure_reached_local_cache")
        asyncio.run(_verify_failure_accounting(postgres_url, key_one))
        relay_statuses = relay.response_statuses[relay_start:]
        provider_calls = local_after_failure.ingress_responses - baseline.ingress_responses
        relay_calls = _successful_relay_count(relay_statuses)
        database_rows = asyncio.run(
            _verify_accounting(
                postgres_url,
                (key_one, key_two),
                (session_a, session_b, installation),
            )
        )
        if database_rows != relay_calls + 1:
            raise VerificationError("accounting_row_count_mismatch")
        final_metrics = _local_metrics(local_port)
        if final_metrics.cache_hits <= baseline.cache_hits or final_metrics.rehydration_hits <= baseline.rehydration_hits or final_metrics.rehydration_injected <= baseline.rehydration_injected:
            raise VerificationError("cache_rehydration_evidence_missing")
        if final_metrics.tool_policy_drops <= baseline.tool_policy_drops:
            raise VerificationError("hosted_tool_strip_evidence_missing")
        if final_metrics.ingress_responses <= baseline.ingress_responses:
            raise VerificationError("provider_metrics_missing")
        provider_calls = final_metrics.ingress_responses - baseline.ingress_responses
        if provider_calls <= 0:
            raise VerificationError("provider_call_count_missing")
        _assert_local_bound_privacy(
            relay.snapshot(), raw_aliases=raw_aliases, service_token=service_token
        )
        if any(
            key.plaintext.encode() in request.body
            or key.plaintext in request.headers.get("authorization", "")
            for key in (key_one, key_two)
            for request in relay.snapshot()
        ):
            raise VerificationError("gateway_key_forwarded_to_local")
        evidence = {
            "session_a1_a2_equal": True,
            "session_b_different": True,
            "session_second_key_different": True,
            "cache_reuse_observed": True,
            "rehydration_observed": True,
            "exact_replay_rejected": True,
            "failure_rollback_observed": True,
            "provider_counts_observed": True,
            "postgres_rows_observed": True,
            "hosted_tools_stripped": True,
            "privacy_observed": True,
            "post_cleanup_model_ok": False,
            "provider_calls": provider_calls,
            "relay_calls": relay_calls,
        }
        return evidence
    finally:
        for process in (local, gateway):
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for server, thread in ((relay, relay_thread), (failure_server, failure_thread)):
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=10)
        _docker("rm", "-f", container, timeout=30)
        if pulled:
            _docker("rmi", "postgres:16", timeout=60)


def run() -> dict[str, object]:
    _verify_commit_topology()
    runtime = _read_runtime_reference()
    _verify_fixtures()
    _verify_protected_model_health(runtime)
    _source_qwen_credential_only_for_local(runtime)
    with tempfile.TemporaryDirectory(prefix="slaif-155f-", dir="/tmp") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        codex_binary = _install_codex(root)
        # Re-run the exact no-provider relationship gate before any DB/container.
        import scripts.capture_codex_protocol as capture
        live = capture.capture_live_0149_session(codex_binary=codex_binary, expected_version=CODEX_VERSION, model=CODEX_MODEL, profile="responses-session-relationship-v3")
        if capture.canonical_json_bytes(live) != SESSION_FIXTURE.read_bytes():
            raise VerificationError("exact_relationship_fixture_mismatch")
        result = _run_composed(root, runtime, codex_binary)
    _verify_protected_model_health(runtime)
    result["post_cleanup_model_ok"] = True
    _assert_required_evidence(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = run()
        _assert_required_evidence(result)
    except VerificationError as exc:
        print(f"RESULT=BLOCKED code={exc}")
        return 1
    except Exception:
        print("RESULT=BLOCKED code=unexpected_failure")
        return 1
    del result
    print("RESULT=OK status=real_composed_acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
