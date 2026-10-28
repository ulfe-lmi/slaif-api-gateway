"""Typed CLI key-policy flags and policy files (196-a).

Covers the actual installed Typer/Click option-source tracking on the real
``keys`` app (explicit, omitted, negative, and repeatable forms), file/flag
conflict law, provider mutual exclusion, the bounded policy-file read, the
safe error vocabulary, and the configured Codex profile bootstrap that must
run BEFORE pin authoring in fresh CLI processes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

import slaif_gateway.cli.keys as keys
from slaif_gateway.cli import key_policy_files as helper
from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.schemas.key_configuration import MAX_KEY_CONFIGURATION_FILE_BYTES
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult

runner = CliRunner()
OWNER_ID = str(uuid.uuid4())
KEY_ID = str(uuid.UUID(int=0x4444_0000_4444_4444_8444_444444444444))
ADMIN_ID = str(uuid.uuid4())

PACKAGED_PROFILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "slaif_gateway"
    / "modules"
    / "clients"
    / "profiles"
    / "codex_0162.json"
)


@pytest.fixture(autouse=True)
def _clean_profile_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("CODEX_COMPATIBILITY_PROFILE_FILE", raising=False)
    get_settings.cache_clear()
    yield


@pytest.fixture
def capture_sources(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, bool]]:
    recorded: list[dict[str, bool]] = []
    original = keys.policy_sources

    def wrapper(ctx):  # type: ignore[no-untyped-def]
        sources = original(ctx)
        recorded.append(dict(sources))
        return sources

    monkeypatch.setattr(keys, "policy_sources", wrapper)
    return recorded


@pytest.fixture
def captured_creates(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    captured: list[object] = []

    async def fake(payload):  # type: ignore[no-untyped-def]
        captured.append(payload)
        raise RuntimeError("SENTINEL_PROBE")

    monkeypatch.setattr(keys, "_create_gateway_key", fake)
    monkeypatch.setattr(keys, "_create_gateway_key_with_email_delivery", fake)
    return captured


@pytest.fixture
def captured_updates(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    captured: list[object] = []

    async def fake(payload):  # type: ignore[no-untyped-def]
        captured.append(payload)
        raise RuntimeError("SENTINEL_PROBE")

    monkeypatch.setattr(keys, "_update_configuration", fake)
    return captured


def _last_sources(recorded: list[dict[str, bool]]) -> dict[str, bool]:
    assert recorded, "command never reached the policy-source projection"
    return recorded[-1]


# --------------------------------------------------------------------------
# create: option-source tracking on the real keys app
# --------------------------------------------------------------------------


def test_create_explicit_provider_none_tracked_and_used(
    capture_sources: list[dict[str, bool]], captured_creates: list[object]
) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--provider-none",
            # Provider flags are a typed policy surface: an explicit one-time
            # key channel is required before creation.
            "--show-plaintext",
        ],
    )
    # The sentinel persistence failure is expected; source tracking happens
    # during option processing, before any DB work.
    assert result.exit_code == 1
    sources = _last_sources(capture_sources)
    assert sources.get("provider_none") is True
    assert sources.get("policy_file") is False
    assert captured_creates, "service was not reached"
    assert captured_creates[-1].allowed_providers == []  # type: ignore[union-attr]


def test_create_omitted_flags_are_not_explicit(
    capture_sources: list[dict[str, bool]], captured_creates: list[object]
) -> None:
    result = runner.invoke(
        app,
        ["keys", "create", "--owner-id", OWNER_ID, "--valid-days", "1"],
    )
    assert result.exit_code == 1
    sources = _last_sources(capture_sources)
    assert not any(sources.values()), sources
    assert captured_creates[-1].allowed_providers is None  # type: ignore[union-attr]


def test_create_explicit_negative_flag_is_tracked_with_false_value(
    capture_sources: list[dict[str, bool]], captured_creates: list[object]
) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--no-allow-all-models",
        ],
    )
    assert result.exit_code == 1
    sources = _last_sources(capture_sources)
    assert sources.get("allow_all_models") is True
    assert captured_creates[-1].allow_all_models is False  # type: ignore[union-attr]


def test_create_repeatable_flags_tracked(
    capture_sources: list[dict[str, bool]], captured_creates: list[object]
) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--allowed-model",
            "model-a",
            "--allowed-model",
            "model-b",
        ],
    )
    assert result.exit_code == 1
    sources = _last_sources(capture_sources)
    assert sources.get("allowed_models") is True
    payload = captured_creates[-1]
    assert payload.allowed_models == ["model-a", "model-b"]  # type: ignore[union-attr]


def test_create_provider_flags_are_mutually_exclusive(
    capture_sources: list[dict[str, bool]], captured_creates: list[object]
) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--provider-all",
            "--provider-none",
        ],
    )
    assert result.exit_code != 0
    assert "exactly one" in result.output
    assert captured_creates == []


# --------------------------------------------------------------------------
# create: policy-file law
# --------------------------------------------------------------------------


def _write_policy_file(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document))
    return path


def test_create_policy_file_conflicts_with_explicit_policy_flags(
    tmp_path: Path,
    capture_sources: list[dict[str, bool]],
    captured_creates: list[object],
) -> None:
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--allowed-model",
            "model-a",
        ],
    )
    assert result.exit_code != 0
    assert "only source of policy configuration" in result.output
    assert captured_creates == []
    sources = _last_sources(capture_sources)
    assert sources.get("policy_file") is True
    assert sources.get("allowed_models") is True


def test_create_policy_file_only_reaches_service(
    tmp_path: Path,
    capture_sources: list[dict[str, bool]],
    captured_creates: list[object],
) -> None:
    policy_file = _write_policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "allowed_models": ["model-a"],
            "allowed_endpoints": ["/v1/chat/completions"],
            "allowed_providers": ["openai"],
        },
    )
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--show-plaintext",
        ],
    )
    assert result.exit_code == 1  # sentinel persistence failure only
    assert captured_creates, "service was not reached"
    payload = captured_creates[-1]
    assert payload.allowed_models == ["model-a"]  # type: ignore[union-attr]
    assert payload.allowed_endpoints == ["/v1/chat/completions"]  # type: ignore[union-attr]
    assert payload.allowed_providers == ["openai"]  # type: ignore[union-attr]


def test_create_policy_file_with_explicit_confirmation_control(
    tmp_path: Path,
    capture_sources: list[dict[str, bool]],
    captured_creates: list[object],
) -> None:
    policy_file = _write_policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "external_tool_policy": {
                "version": 1,
                "mode": "external_tool_fenced",
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 3,
                "single_request_overrun_acknowledged": True,
            },
        },
    )
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--show-plaintext",
            "--confirm-external-tool-fenced",
        ],
    )
    assert result.exit_code == 1  # sentinel persistence failure only
    assert captured_creates, "service was not reached"
    payload = captured_creates[-1]
    assert payload.confirm_external_tool_fenced is True  # type: ignore[union-attr]
    assert payload.external_tool_policy["mode"] == "external_tool_fenced"  # type: ignore[index]


def test_create_policy_file_without_confirmation_passes_flag_false(
    tmp_path: Path, captured_creates: list[object]
) -> None:
    policy_file = _write_policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "external_tool_policy": {
                "version": 1,
                "mode": "external_tool_fenced",
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 3,
                "single_request_overrun_acknowledged": True,
            },
        },
    )
    runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--show-plaintext",
        ],
    )
    # The CLI passes the unconfirmed fenced policy through; the service law
    # (confirmed=False, require_reason=True) rejects it.
    assert captured_creates, "service was not reached"
    assert captured_creates[-1].confirm_external_tool_fenced is False  # type: ignore[union-attr]


# --------------------------------------------------------------------------
# create: explicit one-time key channel law for typed surfaces
# --------------------------------------------------------------------------

PLAINTEXT_CANARY = "SYNTHETIC-ONETIME-KEY-CANARY-196"


def _fake_created_result(payload: object) -> CreatedGatewayKey:
    return CreatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=payload.owner_id,  # type: ignore[union-attr]
        public_key_id="synthetic-public",
        display_prefix="synthetic-hint",
        plaintext_key=PLAINTEXT_CANARY,
        one_time_secret_id=uuid.uuid4(),
        valid_from=payload.valid_from,  # type: ignore[union-attr]
        valid_until=payload.valid_until,  # type: ignore[union-attr]
    )


def _patch_successful_create(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(payload):  # type: ignore[no-untyped-def]
        return _fake_created_result(payload)

    monkeypatch.setattr(keys, "_create_gateway_key", fake)


def test_create_policy_file_default_output_rejected_before_creation(
    tmp_path: Path, captured_creates: list[object]
) -> None:
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--reason",
            "196 default-secret probe",
        ],
    )
    assert result.exit_code != 0
    # The Rich usage box wraps long lines; assert a stable fragment plus the
    # pre-creation no-call semantics below.
    assert "Typed key-policy creation requires" in result.output
    assert captured_creates == [], "no key may be created without an explicit key channel"
    assert "plaintext key is shown once" not in result.output


def test_create_provider_flags_default_output_rejected_before_creation(
    captured_creates: list[object]
) -> None:
    for provider_args in (
        ["--allowed-provider", "openai"],
        ["--provider-all"],
        ["--provider-none"],
    ):
        result = runner.invoke(
            app,
            [
                "keys",
                "create",
                "--owner-id",
                OWNER_ID,
                "--valid-days",
                "1",
                *provider_args,
            ],
        )
        assert result.exit_code != 0, provider_args
        assert "Typed key-policy creation requires" in result.output, provider_args
    assert captured_creates == [], "no key may be created without an explicit key channel"


def test_create_policy_file_show_plaintext_still_prints_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_successful_create(monkeypatch)
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--show-plaintext",
        ],
    )
    assert result.exit_code == 0, result.output
    assert PLAINTEXT_CANARY in result.output
    assert "plaintext key is shown once" in result.output


def test_create_policy_file_secret_output_file_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_successful_create(monkeypatch)
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    secret_file = tmp_path / "one-time-key.txt"
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--secret-output-file",
            str(secret_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert secret_file.read_text() == f"{PLAINTEXT_CANARY}\n"
    assert PLAINTEXT_CANARY not in result.output
    assert "0600" in result.output


def test_create_policy_file_email_delivery_enqueue_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(payload):  # type: ignore[no-untyped-def]
        return _fake_created_result(payload)

    async def fake_delivery(payload, *, email_delivery_mode):  # type: ignore[no-untyped-def]
        key_result = await fake_create(payload)
        return keys.KeyEmailDeliveryCliResult(
            key_result=key_result,
            delivery_result=PendingKeyEmailResult(
                email_delivery_id=uuid.uuid4(),
                one_time_secret_id=key_result.one_time_secret_id,
                gateway_key_id=key_result.gateway_key_id,
                owner_id=key_result.owner_id,
                recipient_email=None,
                status="queued",
            ),
            celery_task_id="synthetic-task-id",
        )

    monkeypatch.setattr(keys, "_create_gateway_key", fake_create)
    monkeypatch.setattr(keys, "_create_gateway_key_with_email_delivery", fake_delivery)
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--email-delivery",
            "enqueue",
        ],
    )
    assert result.exit_code == 0, result.output
    assert PLAINTEXT_CANARY not in result.output
    assert "queued" in result.output


def test_create_legacy_flag_free_still_prints_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_successful_create(monkeypatch)
    result = runner.invoke(
        app,
        ["keys", "create", "--owner-id", OWNER_ID, "--valid-days", "1"],
    )
    assert result.exit_code == 0, result.output
    assert PLAINTEXT_CANARY in result.output
    assert "plaintext key is shown once" in result.output


# --------------------------------------------------------------------------
# policy update / export
# --------------------------------------------------------------------------


def test_policy_update_noop_is_rejected(
    capture_sources: list[dict[str, bool]], captured_updates: list[object]
) -> None:
    result = runner.invoke(app, ["keys", "policy", "update", KEY_ID, "--reason", "r"])
    assert result.exit_code != 0
    assert "No requested policy change" in result.output
    assert captured_updates == []


def test_policy_update_explicit_provider_none(
    capture_sources: list[dict[str, bool]], captured_updates: list[object]
) -> None:
    result = runner.invoke(
        app,
        ["keys", "policy", "update", KEY_ID, "--provider-none", "--reason", "r"],
    )
    assert result.exit_code == 1  # sentinel persistence failure only
    sources = _last_sources(capture_sources)
    assert sources.get("provider_none") is True
    payload = captured_updates[-1]
    assert payload.configuration.allowed_providers == []  # type: ignore[union-attr]


def test_policy_update_negative_flag_is_explicit_with_false_value(
    capture_sources: list[dict[str, bool]], captured_updates: list[object]
) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "policy",
            "update",
            KEY_ID,
            "--no-allow-all-models",
            "--reason",
            "r",
        ],
    )
    assert result.exit_code == 1
    sources = _last_sources(capture_sources)
    assert sources.get("allow_all_models") is True
    config = captured_updates[-1].configuration  # type: ignore[union-attr]
    assert config.allow_all_models is False


def test_policy_update_file_conflicts_with_explicit_policy_flags(
    tmp_path: Path,
    capture_sources: list[dict[str, bool]],
    captured_updates: list[object],
) -> None:
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    result = runner.invoke(
        app,
        [
            "keys",
            "policy",
            "update",
            KEY_ID,
            "--policy-file",
            str(policy_file),
            "--allowed-model",
            "model-a",
            "--reason",
            "r",
        ],
    )
    assert result.exit_code != 0
    assert "only source of policy configuration" in result.output
    assert captured_updates == []


def test_policy_export_reaches_service(monkeypatch: pytest.MonkeyPatch) -> None:
    document = {
        "schema_version": 1,
        "allowed_models": ["gpt-test-mini"],
        "responses_policy": None,
        "rate_limit_policy": None,
    }

    async def fake_export(gateway_key_id):  # type: ignore[no-untyped-def]
        assert gateway_key_id == uuid.UUID(KEY_ID)
        return document

    monkeypatch.setattr(keys, "_export_configuration", fake_export)
    result = runner.invoke(app, ["keys", "policy", "export", KEY_ID])
    assert result.exit_code == 0
    assert json.loads(result.output)["responses_policy"] is None


# --------------------------------------------------------------------------
# bounded policy-file read and safe error vocabulary
# --------------------------------------------------------------------------


def test_read_policy_file_reads_at_most_limit_plus_one_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big_file = tmp_path / "big.json"
    big_file.write_bytes(b"{" + b" " * (4 * 1024 * 1024) + b"}")
    io_requests: list[int] = []
    original_open = Path.open

    def traced_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        real = original_open(self, *args, **kwargs)

        class _Traced:
            def __init__(self, handle):
                self._handle = handle

            def read(self, size=-1):
                io_requests.append(size)
                return self._handle.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self._handle.close()

        return _Traced(real)

    monkeypatch.setattr(Path, "open", traced_open)
    try:
        with pytest.raises(Exception) as exc:
            helper.read_policy_file(big_file)
    finally:
        monkeypatch.setattr(Path, "open", original_open)
    assert "size limit" in str(exc.value)
    assert io_requests and all(
        size == MAX_KEY_CONFIGURATION_FILE_BYTES + 1 for size in io_requests
    ), io_requests


def test_read_policy_file_unreadable_message_never_echoes_path() -> None:
    missing = Path("/nonexistent/slaif196/definitely-missing-policy.json")
    with pytest.raises(Exception) as exc:
        helper.read_policy_file(missing)
    message = str(exc.value)
    assert "not readable" in message
    assert "definitely-missing-policy" not in message
    assert "/nonexistent" not in message


def test_policy_file_conflict_helper_rejects_explicit_policy_flags() -> None:
    sources = {"policy_file": True, "allowed_models": True}
    with pytest.raises(Exception) as exc:
        helper.validate_policy_file_conflicts(sources)
    assert "only source of policy configuration" in str(exc.value)
    # Identity/validity-style flags do not conflict.
    helper.validate_policy_file_conflicts({"policy_file": True, "allowed_providers": False})


def test_provider_flags_value_helper_semantics() -> None:
    assert helper.provider_flags_value(
        {}, allowed_providers=None, provider_all=False, provider_none=False
    ) is helper.PROVIDER_ABSENT
    assert helper.provider_flags_value(
        {"provider_all": True}, allowed_providers=None, provider_all=True, provider_none=False
    ) is None
    assert helper.provider_flags_value(
        {"provider_none": True}, allowed_providers=None, provider_all=False, provider_none=True
    ) == []
    assert helper.provider_flags_value(
        {"allowed_providers": True},
        allowed_providers=["openai"],
        provider_all=False,
        provider_none=False,
    ) == ["openai"]
    with pytest.raises(Exception) as exc:
        helper.provider_flags_value(
            {"provider_all": True, "provider_none": True},
            allowed_providers=None,
            provider_all=True,
            provider_none=True,
        )
    assert "exactly one" in str(exc.value)


def test_build_configuration_from_explicit_flags_helper() -> None:
    config = helper.build_configuration_from_explicit_flags(
        {"allowed_models": True, "allow_all_endpoints": True},
        allowed_models=["m1"],
        allowed_endpoints=None,
        allow_all_models=False,
        allow_all_endpoints=True,
    )
    assert config.has("allowed_models")
    assert config.allowed_models == ["m1"]
    assert config.has("allow_all_endpoints") and config.allow_all_endpoints is True
    assert not config.has("allow_all_models")
    assert not config.has("allowed_endpoints")


# --------------------------------------------------------------------------
# configured Codex profile bootstrap BEFORE pin authoring
# --------------------------------------------------------------------------

_CONTROL_BOOTSTRAP_CODE = """
import json, sys
from slaif_gateway.modules.clients.codex_0162 import bootstrap_codex_compatibility_profile
from slaif_gateway.modules.clients.registry import client_module_metadata, get_client_module
bootstrap_codex_compatibility_profile(sys.argv[1])
print(json.dumps(client_module_metadata(get_client_module("codex-0.162-responses-v1"))))
"""

_CHILD_CREATE_CODE = """
import json, sys, uuid
from typer.testing import CliRunner
import slaif_gateway.cli.keys as keys
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import CreatedGatewayKey

def main() -> None:
    policy_file = sys.argv[1]
    seen = []

    async def fake(payload):
        seen.append((payload.responses_policy or {}).get("client_module"))
        return CreatedGatewayKey(
            gateway_key_id=uuid.uuid4(),
            owner_id=payload.owner_id,
            public_key_id="synthetic-public",
            display_prefix="synthetic-hint",
            plaintext_key="SYNTHETIC_ONETIME_NOT_A_REAL_KEY",
            one_time_secret_id=uuid.uuid4(),
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
        )

    keys._create_gateway_key = fake
    result = CliRunner().invoke(
        app,
        [
            "keys", "create", "--owner-id", str(uuid.uuid4()),
            "--valid-days", "1", "--policy-file", policy_file,
            "--show-plaintext", "--reason", "196 fresh-process profile proof",
        ],
    )
    from slaif_gateway.modules.clients.registry import get_client_module
    print(json.dumps({
        "exit_code": result.exit_code,
        "persistence_calls": len(seen),
        "pin": seen[0] if seen else None,
        "registry_after": get_client_module("codex-0.162-responses-v1").module_version,
    }))

main()
"""


def _run_fresh_subprocess(code: str, args: list[str], env_extra: dict[str, str]) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{root / 'app'}"
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"fresh subprocess failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_create_custom_profile_bootstraps_before_pin_authoring(
    tmp_path: Path,
) -> None:
    """A valid configured external profile is bound before pin authoring.

    Each CLI process starts with only the packaged registry, so the
    configured CODEX_COMPATIBILITY_PROFILE_FILE must be bootstrapped in the
    same command that authors a pin. Proven in FRESH subprocesses (the
    registry bootstrap is a process-wide one-shot and must not be
    reconfigured inside the test process).
    """
    profile = tmp_path / "profile.json"
    raw = json.loads(PACKAGED_PROFILE.read_text())
    raw["revision"] = "9"
    profile.write_text(json.dumps(raw))

    pin = _run_fresh_subprocess(_CONTROL_BOOTSTRAP_CODE, [str(profile)], {})
    assert pin["version"] == "9"

    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allowed_models": ["synthetic-model"],
                "allowed_endpoints": ["/v1/responses"],
                "allowed_providers": [],
                "responses_policy": {
                    "version": 1,
                    "allowed_capabilities": [
                        "codex_request_envelope",
                        "codex_client_tools",
                        "codex_streaming_tool_events",
                        "codex_encrypted_reasoning_replay",
                    ],
                    "allowed_local_tool_types": ["function", "custom"],
                    "client_module": pin,
                },
            }
        )
    )

    receipt = _run_fresh_subprocess(
        _CHILD_CREATE_CODE,
        [str(policy)],
        {"CODEX_COMPATIBILITY_PROFILE_FILE": str(profile)},
    )
    assert receipt["exit_code"] == 0, receipt
    assert receipt["persistence_calls"] == 1
    assert receipt["pin"] == pin
    assert receipt["registry_after"] == "9"


def test_create_invalid_configured_profile_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    captured_creates: list[object],
) -> None:
    bad_profile = tmp_path / "bad-profile.json"
    bad_profile.write_text(json.dumps({"revision": 9, "bogus": "no"}))
    monkeypatch.setenv("CODEX_COMPATIBILITY_PROFILE_FILE", str(bad_profile))
    get_settings.cache_clear()
    policy_file = _write_policy_file(tmp_path, {"schema_version": 1})
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            OWNER_ID,
            "--valid-days",
            "1",
            "--policy-file",
            str(policy_file),
            "--show-plaintext",
        ],
    )
    assert result.exit_code == 1
    assert captured_creates == []
    assert "Codex compatibility profile" in result.output
    assert "bogus" not in result.output
