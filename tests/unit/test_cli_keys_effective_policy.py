"""Unit tests for the new 197 CLI surfaces (lazy setter, effective view,
safe lookup/paging, route explanation) with faked runtimes only."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import GatewayKeyManagementResult
from slaif_gateway.services.key_policy_inspection import (
    KeyPolicyInspectionContext,
)

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
PUBLIC_ID = "publicid1234567890abcdefghijkl"
BEARER = f"sk-slaif-{PUBLIC_ID}." + "A" * 43

runner = CliRunner()


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def _key_row(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "id": KEY_ID,
        "public_key_id": PUBLIC_ID,
        "key_prefix": "sk-slaif-",
        "key_hint": "sk-slaif-publ",
        "owner_id": OWNER_ID,
        "cohort_id": None,
        "status": "active",
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
        "cost_limit_eur": None,
        "token_limit_total": None,
        "request_limit_total": None,
        "cost_used_eur": Decimal("0"),
        "tokens_used_total": 0,
        "requests_used_total": 0,
        "cost_reserved_eur": Decimal("0"),
        "tokens_reserved_total": 0,
        "requests_reserved_total": 0,
        "created_at": NOW - timedelta(hours=2),
        "updated_at": NOW - timedelta(hours=1),
        "revoked_at": None,
        "revoked_reason": None,
        "allowed_models": ["model-a"],
        "allowed_endpoints": ["/v1/models", "/v1/chat/completions"],
        "allow_all_models": False,
        "allow_all_endpoints": False,
        "key_purpose": "standard",
        "capability_policy_mode": "standard",
        "calibration_metadata": {},
        "template_id": None,
        "template_revision_id": None,
        "metadata_json": {},
        "rate_limit_requests_per_minute": None,
        "rate_limit_tokens_per_minute": None,
        "max_concurrent_requests": None,
        "external_tool_fence_state": "none",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _management_result() -> GatewayKeyManagementResult:
    return GatewayKeyManagementResult(
        gateway_key_id=KEY_ID,
        public_key_id=PUBLIC_ID,
        status="active",
        updated_at=NOW,
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        lazy_throttling_policy={
            "mode": "wait",
            "max_wait_seconds": 30,
            "max_waiting_requests": 2,
        },
        allowed_models=["model-a"],
        allowed_endpoints=["/v1/models", "/v1/chat/completions"],
        allow_all_models=False,
        allow_all_endpoints=False,
    )


class _FakeKeysRepository:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = list(rows)

    async def get_gateway_key_by_id(self, key_id: uuid.UUID):
        for row in self._rows:
            if row.id == key_id:
                return row
        return None

    async def get_gateway_key_by_public_key_id(self, public_key_id: str):
        for row in self._rows:
            if row.public_key_id == public_key_id:
                return row
        return None

    async def list_gateway_keys(
        self, *, owner_id=None, cohort_id=None, status=None, limit=100, offset=0
    ):
        rows = [
            row
            for row in self._rows
            if (owner_id is None or row.owner_id == owner_id)
            and (cohort_id is None or row.cohort_id == cohort_id)
            and (status is None or row.status == status)
        ]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        return rows[offset : offset + limit]


class _FakeKeyService:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[object] = []
        self.error = error

    async def update_gateway_key_lazy_throttling(self, payload):
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return _management_result()


@pytest.fixture
def fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_FakeKeysRepository, _FakeKeyService, Settings]:
    rows = [_key_row()]
    repo = _FakeKeysRepository(rows)
    service = _FakeKeyService()
    settings = _settings(
        LAZY_THROTTLING_MAX_WAIT_SECONDS=120, LAZY_THROTTLING_MAX_WAITING_PER_KEY=16
    )

    @asynccontextmanager
    async def _fake_key_runtime() -> AsyncIterator[tuple[object, object, object]]:
        yield settings, repo, service

    monkeypatch.setattr(keys_cli, "_key_runtime", _fake_key_runtime)
    monkeypatch.setattr(keys_cli, "get_settings", lambda: settings)
    return repo, service, settings


@pytest.fixture
def fake_inspection_runtime(
    monkeypatch: pytest.MonkeyPatch, rows: list[SimpleNamespace] | None = None
) -> tuple[_FakeKeysRepository, Settings]:
    settings = _settings()
    repo = _FakeKeysRepository(rows if rows is not None else [_key_row()])
    context = KeyPolicyInspectionContext(
        model_routes=object(),  # unused in report path
        provider_configs=object(),
    )

    @asynccontextmanager
    async def _fake_policy_runtime() -> AsyncIterator[tuple[object, object, object]]:
        yield settings, repo, context

    monkeypatch.setattr(keys_cli, "_policy_inspection_runtime", _fake_policy_runtime)
    return repo, settings


def _invoke(*args: str) -> object:
    return runner.invoke(app, list(args))


# --- set-lazy-throttling ------------------------------------------------------


def test_set_lazy_throttling_help(fake_runtime) -> None:
    result = _invoke("keys", "set-lazy-throttling", "--help")
    assert result.exit_code == 0
    assert "--max-wait-seconds" in result.output
    assert "--clear" in result.output


def test_set_lazy_wait_requires_both_bounds(fake_runtime) -> None:
    _, service, _ = fake_runtime
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "30",
        "--reason",
        "r",
    )
    assert result.exit_code != 0
    assert "requires both" in result.output
    assert service.calls == []


def test_set_lazy_wait_stores_explicit_policy(fake_runtime) -> None:
    _, service, _ = fake_runtime
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "30",
        "--max-waiting-requests",
        "2",
        "--reason",
        "bounded wait for batch runs",
        "--json",
    )
    assert result.exit_code == 0, result.output
    payload = service.calls[0]
    assert payload.lazy_throttling_policy == {
        "mode": "wait",
        "max_wait_seconds": 30,
        "max_waiting_requests": 2,
    }
    assert payload.reason == "bounded wait for batch runs"
    body = json.loads(result.output)
    # Backward-compatible management result shape plus the additive field.
    assert body["gateway_key_id"] == str(KEY_ID)
    assert body["public_key_id"] == PUBLIC_ID
    assert body["lazy_throttling_policy"]["mode"] == "wait"


def test_set_lazy_reject_clears_stored_policy(fake_runtime) -> None:
    _, service, _ = fake_runtime
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "reject",
        "--reason",
        "stop waiting",
        "--json",
    )
    assert result.exit_code == 0, result.output
    assert service.calls[0].lazy_throttling_policy is None


def test_set_lazy_reject_bounds_validated_but_inactive(fake_runtime) -> None:
    _, service, _ = fake_runtime
    ok = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "reject",
        "--max-wait-seconds",
        "30",
        "--max-waiting-requests",
        "2",
        "--reason",
        "r",
    )
    assert ok.exit_code == 0, ok.output
    assert service.calls[0].lazy_throttling_policy is None

    over = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "reject",
        "--max-wait-seconds",
        "9999",
        "--reason",
        "r",
    )
    assert over.exit_code != 0
    assert "operator ceiling" in over.output
    assert len(service.calls) == 1


def test_set_lazy_low_ceiling_still_allows_reject_and_clear(fake_runtime) -> None:
    _, service, settings = fake_runtime
    settings.LAZY_THROTTLING_MAX_WAIT_SECONDS = 10
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--clear",
        "--reason",
        "r",
    )
    assert result.exit_code == 0, result.output
    assert service.calls[0].lazy_throttling_policy is None


def test_set_lazy_flag_conflicts_rejected(fake_runtime) -> None:
    _, service, _ = fake_runtime
    for args in (
        ["--clear", "--mode", "wait", "--max-wait-seconds", "5", "--max-waiting-requests", "1"],
        ["--mode", "wait"],
        [],
    ):
        result = _invoke("keys", "set-lazy-throttling", str(KEY_ID), *args, "--reason", "r")
        assert result.exit_code != 0
    assert service.calls == []


def test_set_lazy_requires_reason(fake_runtime) -> None:
    _, service, _ = fake_runtime
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "5",
        "--max-waiting-requests",
        "1",
    )
    assert result.exit_code != 0
    assert "--reason is required" in result.output
    assert service.calls == []


def test_set_lazy_rejects_non_positive_and_float_bounds(fake_runtime) -> None:
    _, service, _ = fake_runtime
    zero = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "0",
        "--max-waiting-requests",
        "1",
        "--reason",
        "r",
    )
    assert zero.exit_code != 0
    floaty = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "1.5",
        "--max-waiting-requests",
        "1",
        "--reason",
        "r",
    )
    assert floaty.exit_code != 0
    assert service.calls == []


def test_set_lazy_unknown_key_is_safe_not_found(fake_runtime) -> None:
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        "99999999-9999-4999-8999-999999999999",
        "--clear",
        "--reason",
        "r",
        "--json",
    )
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert "error" in body


def test_set_lazy_service_error_surfaces_safe_message(
    monkeypatch: pytest.MonkeyPatch, fake_runtime
) -> None:
    from slaif_gateway.services.key_errors import InvalidGatewayKeyLimitsError

    _, service, _ = fake_runtime
    service.error = InvalidGatewayKeyLimitsError(
        "Lazy throttling max_wait_seconds exceeds the operator ceiling.",
        param="max_wait_seconds",
    )
    result = _invoke(
        "keys",
        "set-lazy-throttling",
        str(KEY_ID),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "30",
        "--max-waiting-requests",
        "2",
        "--reason",
        "r",
        "--json",
    )
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert "exceeds the operator ceiling" in body["error"]["message"]


# --- policy effective ----------------------------------------------------------


def test_policy_effective_json_shape(fake_inspection_runtime) -> None:
    result = _invoke("keys", "policy", "effective", str(KEY_ID), "--json")
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["view"] == "effective-key-policy"
    assert body["scope"] == "configuration-only"
    assert body["key"]["gateway_key_id"] == str(KEY_ID)
    assert body["key"]["status_note"] is None
    rates = body["rate_limits"]
    assert rates["requests_per_window"]["source"] == "none"
    assert rates["window_seconds"] == {
        "configured": None,
        "effective": 60,
        "source": "default",
    }
    assert body["lazy_throttling"]["stored_state"] == "absent"
    assert body["lazy_throttling"]["mode"] == "reject"
    assert body["quotas"]["cost_eur"]["unlimited"] is True
    assert body["quotas"]["cost_eur"]["remaining"] is None
    assert body["redis_configuration"]["enabled"] is False


def test_policy_effective_inherited_warning_and_key_sources(
    monkeypatch: pytest.MonkeyPatch, fake_inspection_runtime
) -> None:
    row = _key_row(
        rate_limit_requests_per_minute=1,
        metadata_json={"rate_limit_policy": {"window_seconds": 10}},
    )
    fake_inspection_runtime  # keep fixture active
    # Re-point the runtime at the rate-configured row.
    from slaif_gateway.cli import keys as keys_module

    settings = _settings(DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=500)
    repo = _FakeKeysRepository([row])

    @asynccontextmanager
    async def _rt() -> AsyncIterator[tuple[object, object, object]]:
        yield settings, repo, KeyPolicyInspectionContext(
            model_routes=object(), provider_configs=object()
        )

    monkeypatch.setattr(keys_module, "_policy_inspection_runtime", _rt)
    result = _invoke("keys", "policy", "effective", str(KEY_ID), "--json")
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["rate_limits"]["requests_per_window"] == {
        "configured": 1,
        "effective": 1,
        "source": "key",
    }
    assert body["rate_limits"]["tokens_per_window"] == {
        "configured": None,
        "effective": 500,
        "source": "deployment",
    }
    assert body["rate_limits"]["window_seconds"]["source"] == "key"
    assert (
        "Inherited deployment token rate still applies despite an unlimited "
        "lifetime token quota."
    ) in body["rate_limits"]["warnings"]
    assert body["rate_limits"]["count_semantics"] == "counts per selected window"


def test_policy_effective_text_and_unknown_key(fake_inspection_runtime) -> None:
    text = _invoke("keys", "policy", "effective", str(KEY_ID))
    assert text.exit_code == 0
    assert "effective-key-policy" in text.output

    missing = _invoke(
        "keys", "policy", "effective", "99999999-9999-4999-8999-999999999999", "--json"
    )
    assert missing.exit_code == 1


# --- policy explain-route (unit-level) ------------------------------------------


def test_policy_explain_route_requires_model(fake_inspection_runtime) -> None:
    result = _invoke("keys", "policy", "explain-route", str(KEY_ID), "--json")
    assert result.exit_code != 0


def test_policy_explain_route_unknown_key(fake_inspection_runtime) -> None:
    result = _invoke(
        "keys",
        "policy",
        "explain-route",
        "99999999-9999-4999-8999-999999999999",
        "--model",
        "model-a",
        "--json",
    )
    assert result.exit_code == 1


# --- list paging + owner email --------------------------------------------------


def _three_rows() -> list[SimpleNamespace]:
    base = _key_row()
    rows = []
    for index in range(3):
        rows.append(
            _key_row(
                id=uuid.UUID(f"00000000-0000-4000-8000-{index:012d}"),
                public_key_id=f"pub{index}abcdef",
                created_at=NOW - timedelta(hours=3 - index),
            )
        )
    del base
    return rows


def test_list_paging_json_and_backward_compat(
    monkeypatch: pytest.MonkeyPatch, fake_runtime
) -> None:
    rows = _three_rows()
    _, service, settings = fake_runtime
    repo = _FakeKeysRepository(rows)
    settings.LAZY_THROTTLING_MAX_WAIT_SECONDS = 120

    @asynccontextmanager
    async def _rt() -> AsyncIterator[tuple[object, object, object]]:
        yield settings, repo, service

    monkeypatch.setattr(keys_cli, "_key_runtime", _rt)

    page1 = _invoke("keys", "list", "--limit", "2", "--json")
    assert page1.exit_code == 0, page1.output
    body1 = json.loads(page1.output)
    assert len(body1["keys"]) == 2
    assert body1["paging"] == {
        "limit": 2,
        "offset": 0,
        "returned": 2,
        "has_more": True,
        "next_offset": 2,
    }

    page2 = _invoke("keys", "list", "--limit", "2", "--offset", "2", "--json")
    body2 = json.loads(page2.output)
    assert body2["paging"]["has_more"] is False
    assert body2["paging"]["next_offset"] is None
    seen = [k["public_key_id"] for k in body1["keys"]] + [
        k["public_key_id"] for k in body2["keys"]
    ]
    assert len(set(seen)) == 3


def test_list_owner_email_unknown_is_safe(
    monkeypatch: pytest.MonkeyPatch, fake_runtime
) -> None:
    async def _no_owner(owner_email: str, *, expected_owner_id: uuid.UUID | None):
        raise keys_cli.CliKeyError("No owner exists for the provided email.")

    monkeypatch.setattr(keys_cli, "_resolve_owner_id", _no_owner)
    result = _invoke("keys", "list", "--owner-email", "ghost@example.invalid", "--json")
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["error"]["code"] == "cli_error"
    assert "ghost@example.invalid" not in result.output


def test_list_owner_email_and_id_conflict(fake_runtime) -> None:
    result = _invoke(
        "keys",
        "list",
        "--owner-id",
        str(OWNER_ID),
        "--owner-email",
        "a@example.invalid",
    )
    assert result.exit_code != 0


def test_list_limit_and_offset_bounds(fake_runtime) -> None:
    assert _invoke("keys", "list", "--limit", "0").exit_code != 0
    assert _invoke("keys", "list", "--limit", "100000").exit_code != 0
    assert _invoke("keys", "list", "--offset", "-1").exit_code != 0


# --- show safe lookup -------------------------------------------------------------


def test_show_by_uuid_and_public_id(fake_runtime) -> None:
    by_uuid = _invoke("keys", "show", str(KEY_ID), "--json")
    assert by_uuid.exit_code == 0, by_uuid.output
    body = json.loads(by_uuid.output)
    assert body["public_key_id"] == PUBLIC_ID

    by_public = _invoke("keys", "show", PUBLIC_ID, "--json")
    assert by_public.exit_code == 0, by_public.output
    assert json.loads(by_public.output)["id"] == str(KEY_ID)


def test_show_refuses_bearer_shaped_input_without_echo(fake_runtime) -> None:
    result = _invoke("keys", "show", BEARER, "--json")
    assert result.exit_code == 1
    assert "Full key material cannot be used for lookup" in result.output
    assert BEARER not in result.output


def test_show_unknown_reference_is_not_found(fake_runtime) -> None:
    result = _invoke("keys", "show", "nosuchpublicid", "--json")
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert "error" in body
