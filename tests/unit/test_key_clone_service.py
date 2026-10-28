"""Unit tests for the objective-198 standard-key clone plan/execute service.

Pure fakes: no database, no email transport. The fake key service returns a
deterministic canonical version-1 export document and records create inputs,
so canonical-policy semantics (None vs [], nullable rates, unlimited quotas)
are asserted on the exact builder payload.
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.schemas.key_clone import (
    VALIDITY_ABSOLUTE,
    VALIDITY_COPY_SOURCE_EXPIRY,
    VALIDITY_DURATION_FROM_NOW,
    KeyClonePlanError,
    compute_source_fingerprint,
    parse_clone_plan_document,
    render_clone_plan,
)
from slaif_gateway.schemas.key_configuration import (
    KeyConfiguration,
    key_configuration_export,
)
from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult
from slaif_gateway.services.key_clone_service import (
    KeyCloneConfirmationRequiredError,
    KeyCloneEligibilityError,
    KeyCloneReceiptAmbiguousError,
    KeyClonePlanMismatchError,
    KeyCloneService,
    KeyCloneReviewedPolicyMismatchError,
    KeyCloneSourceSecretShapeError,
    KeyCloneStalePlanError,
    KeyCloneTargetMissingError,
    KeyCloneTargetValidityError,
    KeyCloneUnsupportedIsolationError,
    KeyCloneUnsupportedSourcePolicyError,
)
from slaif_gateway.services.key_errors import GatewayKeyNotFoundError

SOURCE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SOURCE_OWNER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
TARGET_OWNER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
TARGET_COHORT_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
ADMIN_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

FENCED_POLICY_BLOCK = {
    "version": 1,
    "mode": "external_tool_fenced",
    "allowed_capabilities": ["provider_connector"],
    "allowed_destination_ids": ["connector:crm"],
    "max_provider_tool_calls_per_request": 1,
    "single_request_overrun_acknowledged": True,
}


def _base_config() -> KeyConfiguration:
    config = KeyConfiguration()
    config.allowed_models = ["gpt-test-mini"]
    config.allow_all_models = False
    config.allowed_endpoints = ["/v1/chat/completions", "/v1/responses"]
    config.allow_all_endpoints = False
    config.cost_limit_eur = Decimal("25.00")
    config.token_limit_total = 100000
    config.request_limit_total = None
    return config


def _base_export_document() -> dict[str, object]:
    return key_configuration_export(_base_config())


BASE_DOC = _base_export_document()
_ABSENT = object()


def _source_row(**overrides) -> GatewayKey:
    kwargs = dict(
        id=SOURCE_ID,
        owner_id=SOURCE_OWNER_ID,
        public_key_id="pub-source",
        status="active",
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        key_purpose="standard",
        capability_policy_mode="standard",
        external_tool_fence_state="none",
        metadata_json={},
        allowed_models=["gpt-test-mini"],
        allowed_endpoints=["/v1/chat/completions", "/v1/responses"],
        allow_all_models=False,
        allow_all_endpoints=False,
        cost_limit_eur=Decimal("25.00"),
        token_limit_total=100000,
        request_limit_total=None,
    )
    kwargs.update(overrides)
    return GatewayKey(**kwargs)


class FakeOwnersRepository:
    def __init__(self, owner_ids=()):
        self.owner_ids = set(owner_ids)

    async def get_owner_by_id(self, owner_id):
        return object() if owner_id in self.owner_ids else None


class FakeCohortsRepository:
    def __init__(self, cohort_ids=()):
        self.cohort_ids = set(cohort_ids)

    async def get_cohort_by_id(self, cohort_id):
        return object() if cohort_id in self.cohort_ids else None


class FakeAuditRepository:
    def __init__(self):
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def add_audit_log(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


class FakeEmailDeliveryService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    async def create_pending_key_email_delivery(
        self,
        *,
        gateway_key_id,
        one_time_secret_id,
        owner_id,
        actor_admin_id=None,
        reason=None,
    ):
        self.calls.append(
            dict(
                gateway_key_id=gateway_key_id,
                one_time_secret_id=one_time_secret_id,
                owner_id=owner_id,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
        )
        return PendingKeyEmailResult(
            email_delivery_id=uuid.uuid4(),
            one_time_secret_id=one_time_secret_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            recipient_email="owner@example.invalid",
            status="pending",
        )


class FakeKeysRepository:
    def __init__(self, source_row: GatewayKey, targets=None):
        self.source_row = source_row
        self.targets: dict[uuid.UUID, GatewayKey] = dict(targets or {})
        self.lock_calls = 0
        self.receipt_calls: list[tuple] = []
        self.attach_calls: list[tuple] = []
        self.found_source = True
        self.isolation = "read committed"

    async def get_gateway_key_by_id(self, key_id):
        if key_id == self.source_row.id and self.found_source:
            return self.source_row
        return self.targets.get(key_id)

    async def get_gateway_key_for_update(self, key_id):
        self.lock_calls += 1
        if key_id == self.source_row.id and self.found_source:
            return self.source_row
        return None

    async def current_transaction_isolation(self):
        return self.isolation

    async def find_clone_receipts(
        self, *, source_gateway_key_id, operation_uuid
    ):
        self.receipt_calls.append((source_gateway_key_id, operation_uuid))
        matches: list[GatewayKey] = []
        for target in self.targets.values():
            metadata = target.metadata_json or {}
            receipt = metadata.get("clone_receipt") or {}
            if (
                receipt.get("source_gateway_key_id") == str(source_gateway_key_id)
                and receipt.get("operation_uuid") == str(operation_uuid)
            ):
                matches.append(target)
        return matches

    async def attach_clone_receipt(self, gateway_key_id, **kwargs):
        self.attach_calls.append((gateway_key_id, kwargs))
        target = self.targets[gateway_key_id]
        metadata = dict(target.metadata_json or {})
        metadata["clone_receipt"] = {
            "source_gateway_key_id": str(kwargs["source_gateway_key_id"]),
            "operation_uuid": str(kwargs["operation_uuid"]),
            "target_gateway_key_id": str(gateway_key_id),
            "target_owner_id": str(kwargs["target_owner_id"]),
            "one_time_secret_id": str(kwargs["one_time_secret_id"]),
            "email_delivery_id": (
                str(kwargs["email_delivery_id"]) if kwargs["email_delivery_id"] else None
            ),
            "source_fingerprint": kwargs["source_fingerprint"],
            "policy_fingerprint": kwargs["policy_fingerprint"],
            "source_public_key_id": kwargs["source_public_key_id"],
            "source_valid_until": kwargs["source_valid_until"],
            "target_cohort_id": (
                str(kwargs["target_cohort_id"]) if kwargs["target_cohort_id"] else None
            ),
            "requires_fenced_confirmation": kwargs["requires_fenced_confirmation"],
            "validity_mode": kwargs["validity_mode"],
            "validity_duration_seconds": kwargs["validity_duration_seconds"],
            "validity_from": kwargs["validity_from"],
            "validity_until": kwargs["validity_until"],
            "status": "created",
        }
        target.metadata_json = metadata


class FakeKeyService:
    def __init__(self, keys_repo: FakeKeysRepository, export_document=BASE_DOC):
        self.keys_repo = keys_repo
        self.export_document = export_document
        self.export_calls: list[object] = []
        self.create_calls: list[object] = []
        self.plaintext_key = "sk-slaif-fakepub.fake-once-only-secret-material"

    async def export_gateway_key_configuration(self, gateway_key_id):
        self.export_calls.append(gateway_key_id)
        return self.export_document

    async def create_gateway_key(self, payload):
        self.create_calls.append(payload)
        target_id = uuid.uuid4()
        ots_id = uuid.uuid4()
        row = GatewayKey(
            id=target_id,
            owner_id=payload.owner_id,
            public_key_id=f"pub-{target_id.hex[:10]}",
            status="active",
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            key_purpose=payload.key_purpose,
            capability_policy_mode=payload.capability_policy_mode,
            metadata_json={},
        )
        self.keys_repo.targets[target_id] = row
        return CreatedGatewayKey(
            gateway_key_id=target_id,
            owner_id=payload.owner_id,
            public_key_id=row.public_key_id,
            display_prefix="sk-slaif-fakepub",
            plaintext_key=self.plaintext_key,
            one_time_secret_id=ots_id,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
        )


def _make_service(
    source_row: GatewayKey | None = None,
    *,
    export_document=BASE_DOC,
    owner_ids=(TARGET_OWNER_ID,),
    cohort_ids=(TARGET_COHORT_ID,),
):
    source_row = source_row or _source_row()
    keys_repo = FakeKeysRepository(source_row)
    key_service = FakeKeyService(keys_repo, export_document=export_document)
    service = KeyCloneService(
        settings=Settings(),
        key_service=key_service,
        gateway_keys_repository=keys_repo,
        owners_repository=FakeOwnersRepository(owner_ids),
        cohorts_repository=FakeCohortsRepository(cohort_ids),
        email_delivery_service=FakeEmailDeliveryService(),
        audit_repository=FakeAuditRepository(),
    )
    return service, source_row, keys_repo, key_service


def _build_plan(service, **overrides):
    kwargs = dict(
        source_gateway_key_id=SOURCE_ID,
        target_owner_id=TARGET_OWNER_ID,
        target_cohort_id=None,
        validity_mode=VALIDITY_DURATION_FROM_NOW,
        validity_duration_seconds=3600,
        now=NOW,
    )
    kwargs.update(overrides)
    return asyncio.run(service.build_plan(**kwargs))


def _execute(service, plan_document, **overrides):
    plan = parse_clone_plan_document(plan_document)
    kwargs = dict(
        plan=plan,
        reason="clone for unit test",
        actor_admin_id=ADMIN_ID,
        confirm_external_tool_fenced=False,
        create_email_delivery=False,
        now=NOW,
    )
    kwargs.update(overrides)
    return asyncio.run(service.execute_plan(**kwargs))


# --- plan build ---------------------------------------------------------------


def test_build_plan_returns_strict_nonsecret_document() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)

    assert document["schema_version"] == 1
    uuid.UUID(document["operation_uuid"])
    assert document["source_gateway_key_id"] == str(SOURCE_ID)
    assert document["source_public_key_id"] == "pub-source"
    expected_fp = compute_source_fingerprint(
        public_key_id="pub-source",
        status="active",
        valid_from=source_row.valid_from,
        valid_until=source_row.valid_until,
        key_purpose="standard",
        capability_policy_mode="standard",
        policy_document=BASE_DOC,
    )
    assert document["source_fingerprint"] == expected_fp
    assert document["target_owner_id"] == str(TARGET_OWNER_ID)
    assert document["target_cohort_id"] is None
    assert document["validity"] == {"mode": VALIDITY_DURATION_FROM_NOW, "duration_seconds": 3600}
    assert document["policy"] == BASE_DOC
    assert document["requires_fenced_confirmation"] is False
    assert document["preview"]["valid_until"] == (NOW + timedelta(hours=1)).isoformat()

    # Non-secret: no token material, no raw metadata, no usage anywhere.
    assert "token_hash" not in json.dumps(document)
    assert "sk-slaif" not in json.dumps(document)

    # Dry-run performs no mutation and no audit.
    assert keys_repo.attach_calls == []
    assert service._audit.calls == []
    assert key_service.create_calls == []


def test_build_plan_rejects_ineligible_sources() -> None:
    cases = {
        "calibration": dict(key_purpose="trusted_calibration"),
        "discovery_mode": dict(capability_policy_mode="trusted_calibration_discovery"),
        "suspended": dict(status="suspended"),
        "revoked": dict(status="revoked"),
        "fenced": dict(external_tool_fence_state="fenced"),
        "not_yet_valid": dict(valid_from=NOW + timedelta(days=1)),
        "expired": dict(valid_until=NOW - timedelta(days=1)),
    }
    for name, overrides in cases.items():
        service, *_ = _make_service(_source_row(**overrides))
        with pytest.raises(KeyCloneEligibilityError):
            _build_plan(service)
        # No mutation or audit on rejection.
        assert service._audit.calls == []


def test_build_plan_rejects_missing_target_owner_or_cohort() -> None:
    service, *_ = _make_service(owner_ids=())
    with pytest.raises(KeyCloneTargetMissingError):
        _build_plan(service)
    service, *_ = _make_service(cohort_ids=())
    with pytest.raises(KeyCloneTargetMissingError):
        _build_plan(service, target_cohort_id=TARGET_COHORT_ID)
    service, *_ = _make_service()
    assert service._audit.calls == []


def test_build_plan_rejects_nondefault_or_malformed_responses_live_burn() -> None:
    default_block = {
        "version": 1,
        "enabled": True,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }
    # Absent is fine (covered by the happy path); an exact default block is fine.
    service, *_ = _make_service(_source_row(metadata_json={"responses_streaming_live_burn": default_block}))
    document = _build_plan(service)
    assert document["schema_version"] == 1

    bad_blocks = [
        {"version": 1, "enabled": False, "cost_margin_eur": "0.000000000", "token_margin": 0},
        {"version": 1, "enabled": True, "cost_margin_eur": "0.000000000", "token_margin": 7},
        {"version": 1, "enabled": True, "cost_margin_eur": "0.000000000", "token_margin": 0, "bogus": 1},
        "not-a-dict",
        {"version": 2, "enabled": True, "cost_margin_eur": "0.000000000", "token_margin": 0},
    ]
    for block in bad_blocks:
        service, *_ = _make_service(
            _source_row(metadata_json={"responses_streaming_live_burn": block})
        )
        with pytest.raises(KeyCloneUnsupportedSourcePolicyError):
            _build_plan(service)


def test_build_plan_rejects_known_secret_shapes_in_kept_source_strings() -> None:
    for secret_shape in (
        "sk-proj-AAAAAAAAAAAAAAAAAAAAAA",
        "Bearer abcdefgh12345678",
        "sk-slaif-abcdef42.once-only-secret-material",
        "api_key=supersecretvalue",
    ):
        config = _base_config()
        config.allowed_models = [secret_shape]
        doc = key_configuration_export(config)
        service, *_ = _make_service(export_document=doc)
        with pytest.raises(KeyCloneSourceSecretShapeError):
            _build_plan(service)


def test_fingerprint_is_stable_under_usage_drift() -> None:
    row_a = _source_row()
    row_b = _source_row(
        cost_used_eur=Decimal("12.5"),
        tokens_used_total=999,
        requests_used_total=42,
        last_used_at=NOW,
        updated_at=NOW,
    )
    fp_a = compute_source_fingerprint(
        public_key_id=row_a.public_key_id,
        status=row_a.status,
        valid_from=row_a.valid_from,
        valid_until=row_a.valid_until,
        key_purpose=row_a.key_purpose,
        capability_policy_mode=row_a.capability_policy_mode,
        policy_document=BASE_DOC,
    )
    fp_b = compute_source_fingerprint(
        public_key_id=row_b.public_key_id,
        status=row_b.status,
        valid_from=row_b.valid_from,
        valid_until=row_b.valid_until,
        key_purpose=row_b.key_purpose,
        capability_policy_mode=row_b.capability_policy_mode,
        policy_document=BASE_DOC,
    )
    assert fp_a == fp_b

    # But a configuration change moves the fingerprint.
    row_c = _source_row(valid_until=NOW + timedelta(days=31))
    fp_c = compute_source_fingerprint(
        public_key_id=row_c.public_key_id,
        status=row_c.status,
        valid_from=row_c.valid_from,
        valid_until=row_c.valid_until,
        key_purpose=row_c.key_purpose,
        capability_policy_mode=row_c.capability_policy_mode,
        policy_document=BASE_DOC,
    )
    assert fp_c != fp_a


def test_plan_validity_modes_and_rejections() -> None:
    service, *_ = _make_service()
    doc = _build_plan(
        service,
        validity_mode=VALIDITY_COPY_SOURCE_EXPIRY,
        validity_duration_seconds=None,
    )
    assert doc["validity"]["source_valid_until"].endswith("+00:00")

    doc = _build_plan(
        service,
        validity_mode=VALIDITY_ABSOLUTE,
        validity_duration_seconds=None,
        validity_from=(NOW + timedelta(days=1)).isoformat(),
        validity_until=(NOW + timedelta(days=2)).isoformat(),
    )
    assert doc["validity"]["mode"] == VALIDITY_ABSOLUTE

    with pytest.raises(KeyCloneTargetValidityError):
        _build_plan(
            service,
            validity_mode=VALIDITY_ABSOLUTE,
            validity_duration_seconds=None,
            validity_from=(NOW + timedelta(days=2)).isoformat(),
            validity_until=(NOW + timedelta(days=1)).isoformat(),
        )
    with pytest.raises(KeyCloneTargetValidityError):
        _build_plan(
            service,
            validity_mode=VALIDITY_ABSOLUTE,
            validity_duration_seconds=None,
            validity_from=(NOW - timedelta(days=3)).isoformat(),
            validity_until=(NOW - timedelta(days=1)).isoformat(),
        )


def test_plan_schema_rejects_tampered_documents() -> None:
    service, *_ = _make_service()
    document = _build_plan(service)

    def _expect_reject(mutator, fragment=None):
        tampered = copy.deepcopy(document)
        mutator(tampered)
        with pytest.raises(KeyClonePlanError):
            parse_clone_plan_document(tampered)

    _expect_reject(lambda d: d.update({"schema_version": 2}))
    _expect_reject(lambda d: d.update({"bogus_field": 1}))
    _expect_reject(lambda d: d.update({"source_fingerprint": "x" * 64}))
    _expect_reject(lambda d: d.update({"operation_uuid": "not-a-uuid"}))
    _expect_reject(lambda d: d["validity"].update({"duration_seconds": True}))
    _expect_reject(lambda d: d["validity"].update({"bogus": 1}))
    _expect_reject(lambda d: d.update({"preview": {"bogus": "x"}}))
    _expect_reject(lambda d: d.update({"requires_fenced_confirmation": "yes"}))


# --- execute ------------------------------------------------------------------


def test_execute_creates_independent_target_with_receipt_and_audit() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    result = _execute(service, document, create_email_delivery=True)

    assert result.status == "created"
    assert result.plaintext_key is not None
    assert result.target_gateway_key_id is not None
    assert result.target_gateway_key_id != str(SOURCE_ID)
    assert result.target_public_key_id != "pub-source"
    assert result.valid_from == NOW
    assert result.valid_until == NOW + timedelta(hours=1)

    payload = key_service.create_calls[0]
    assert payload.owner_id == TARGET_OWNER_ID
    assert payload.note == "clone for unit test"
    assert payload.created_by_admin_id == ADMIN_ID
    assert payload.key_purpose == "standard"
    assert payload.capability_policy_mode == "standard"

    # Pending delivery + receipt + clone audit all inside the operation.
    assert len(service._email_delivery.calls) == 1
    assert len(keys_repo.attach_calls) == 1
    assert [c["action"] for c in service._audit.calls] == ["gateway_key_cloned"]
    audit = service._audit.calls[0]
    assert audit["entity_id"] == uuid.UUID(result.target_gateway_key_id)
    assert audit["new_values"]["source_gateway_key_id"] == str(SOURCE_ID)
    assert audit["new_values"]["operation_uuid"] == result.operation_uuid
    # No plaintext or raw secret material in the audit.
    assert result.plaintext_key not in json.dumps(audit["new_values"])


def test_execute_rejects_stale_plan_without_writes() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    # The source configuration changes after the plan was written.
    service._key_service.export_document = key_configuration_export(
        _base_config()
    )
    source_row.valid_until = NOW + timedelta(days=31)

    with pytest.raises(KeyCloneStalePlanError):
        _execute(service, document)
    assert key_service.create_calls == []
    assert service._audit.calls == []
    assert keys_repo.attach_calls == []


def test_execute_deduplicates_exact_repeat_as_already_applied() -> None:
    service, *_ = _make_service()
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"

    second = _execute(service, document)
    assert second.status == "already-applied"
    assert second.target_gateway_key_id == first.target_gateway_key_id
    assert second.plaintext_key is None
    assert service._key_service.create_calls.__len__() == 1
    # Only the FIRST execution audited.
    assert len(service._audit.calls) == 1


def test_execute_stays_identifiable_after_source_edit() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"

    # Source is edited AFTER the committed operation: a retry must still
    # return the recorded target (never a new key, never a stale refusal).
    source_row.status = "suspended"
    source_row.valid_until = NOW + timedelta(days=31)
    second = _execute(service, document)
    assert second.status == "already-applied"
    assert second.target_gateway_key_id == first.target_gateway_key_id
    assert len(key_service.create_calls) == 1


def test_execute_refuses_changed_plan_with_same_operation() -> None:
    service, *_ = _make_service()
    document = _build_plan(service)
    _execute(service, document)

    changed = copy.deepcopy(document)
    changed["validity"] = {
        "mode": VALIDITY_ABSOLUTE,
        "valid_from": (NOW + timedelta(days=1)).isoformat(),
        "valid_until": (NOW + timedelta(days=2)).isoformat(),
    }
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, changed)

    changed_cohort = copy.deepcopy(document)
    changed_cohort["target_cohort_id"] = str(TARGET_COHORT_ID)
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, changed_cohort)
    # No second key was created.
    assert len(service._key_service.create_calls) == 1


def test_execute_requires_fresh_fenced_confirmation() -> None:
    config = _base_config()
    config.external_tool_policy = dict(FENCED_POLICY_BLOCK)
    doc = key_configuration_export(config)
    service, source_row, keys_repo, key_service = _make_service(
        _source_row(metadata_json={"external_tool_policy": dict(FENCED_POLICY_BLOCK)}),
        export_document=doc,
    )
    plan_document = _build_plan(service)
    assert plan_document["requires_fenced_confirmation"] is True

    with pytest.raises(KeyCloneConfirmationRequiredError):
        _execute(service, plan_document)
    assert key_service.create_calls == []

    result = _execute(service, plan_document, confirm_external_tool_fenced=True)
    assert result.status == "created"
    assert key_service.create_calls[0].confirm_external_tool_fenced is True


def test_execute_missing_source_is_not_found() -> None:
    service, *_ = _make_service()
    keys_repo = service._keys
    keys_repo.found_source = False
    document = _build_plan(_make_service()[0])  # built before the source vanished
    with pytest.raises(GatewayKeyNotFoundError):
        _execute(service, document)
    assert service._key_service.create_calls == []


def test_execute_refuses_when_source_became_ineligible() -> None:
    service, source_row, *_ = _make_service()
    document = _build_plan(service)
    source_row.status = "suspended"
    with pytest.raises(KeyCloneEligibilityError):
        _execute(service, document)
    assert service._key_service.create_calls == []


def test_execute_rejects_expired_absolute_validity() -> None:
    # The window is valid at plan time but expires before execution time.
    service = _make_service()[0]
    document = _build_plan(
        service,
        validity_mode=VALIDITY_ABSOLUTE,
        validity_duration_seconds=None,
        validity_from=(NOW - timedelta(days=2)).isoformat(),
        validity_until=(NOW + timedelta(seconds=5)).isoformat(),
    )
    with pytest.raises(KeyCloneTargetValidityError):
        _execute(service, document, now=NOW + timedelta(seconds=6))


def test_canonical_semantics_none_vs_empty_and_nullable_rates() -> None:
    # Providers ABSENT (None) = unrestricted; explicit [] = deny all.
    for providers_value, expected_rendered, expected_input in (
        ("absent", _ABSENT, None),
        (None, None, None),
        ([], [], []),
    ):
        config = _base_config()
        if providers_value != "absent":
            config.allowed_providers = providers_value
        doc = key_configuration_export(config)
        service, *_ = _make_service(export_document=doc)
        plan_document = _build_plan(service)
        rendered = plan_document["policy"].get("allowed_providers", _ABSENT)
        assert rendered == expected_rendered
        result = _execute(service, plan_document)
        assert result.status == "created"
        assert service._key_service.create_calls[-1].allowed_providers == expected_input

    # Nullable rate members: explicit null stays inherit; set member survives.
    config = _base_config()
    config.rate_limit_policy = {"requests_per_minute": 30, "window_seconds": 60}
    doc = key_configuration_export(config)
    service, *_ = _make_service(export_document=doc)
    plan_document = _build_plan(service)
    assert plan_document["policy"]["rate_limit_policy"] == {
        "requests_per_minute": 30,
        "window_seconds": 60,
    }
    _execute(service, plan_document)
    payload = service._key_service.create_calls[-1]
    assert payload.rate_limit_policy == {"requests_per_minute": 30, "window_seconds": 60}

    # Unlimited lifetime quotas stay None (never a large sentinel).
    config = _base_config()
    config.cost_limit_eur = None
    config.token_limit_total = None
    doc = key_configuration_export(config)
    service, *_ = _make_service(export_document=doc)
    plan_document = _build_plan(service)
    assert plan_document["policy"]["cost_limit_eur"] is None
    assert plan_document["policy"]["token_limit_total"] is None
    _execute(service, plan_document)
    payload = service._key_service.create_calls[-1]
    assert payload.cost_limit_eur is None
    assert payload.token_limit_total is None


def test_plan_round_trip_preserves_preview() -> None:
    service, *_ = _make_service()
    document = _build_plan(service)
    plan = parse_clone_plan_document(document)
    assert plan.preview is not None
    re_rendered = render_clone_plan(plan)
    assert re_rendered == document


# --- 198-b: stable retry namespace, reviewed policy truth, isolation/clock ----


def test_execute_changed_owner_retry_refuses() -> None:
    other_owner = uuid.UUID("99999999-9999-4999-8999-999999999999")
    service, source_row, keys_repo, key_service = _make_service(
        owner_ids=(TARGET_OWNER_ID, other_owner)
    )
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"

    # Changing ONLY the (mutable) target owner under the SAME source/operation
    # must NOT create a second key: the receipt lookup is owner-independent and
    # the full business-plan identity mismatch refuses.
    changed = copy.deepcopy(document)
    changed["target_owner_id"] = str(other_owner)
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, changed)
    assert len(key_service.create_calls) == 1


def test_execute_edited_review_policy_before_create_refuses() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    # The operator widens the REVIEWED policy after build but before first
    # execution; the clone must refuse rather than silently create either the
    # source's narrower policy or the widened one.
    edited = copy.deepcopy(document)
    edited["policy"]["allow_all_models"] = True
    with pytest.raises(KeyCloneReviewedPolicyMismatchError):
        _execute(service, edited)
    assert key_service.create_calls == []


def test_execute_same_operation_different_policy_after_commit_mismatch() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    _execute(service, document)
    # A different policy under the SAME completed operation is a mismatch, not
    # an already-applied no-op.
    changed = copy.deepcopy(document)
    changed["policy"]["cost_limit_eur"] = "30.00"
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, changed)
    assert len(key_service.create_calls) == 1


def test_execute_refuses_repeatableread_isolation() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    keys_repo.isolation = "repeatable read"
    with pytest.raises(KeyCloneUnsupportedIsolationError):
        _execute(service, document)
    assert key_service.create_calls == []
    assert service._audit.calls == []


def test_execute_refuses_when_source_expires_while_acquiring_lock(monkeypatch) -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    # The clock advances past the source's valid_until WHILE the lock is being
    # acquired; the post-lock execution-time sample must see the expiry.
    expired_now = source_row.valid_until + timedelta(seconds=1)

    async def lock_and_advance_clock(key_id):
        # Dotted-target monkeypatch so teardown restores the real clock (the
        # direct module assignment leaked the lambda beyond this test).
        monkeypatch.setattr(
            "slaif_gateway.services.key_clone_service._now", lambda: expired_now
        )
        return source_row

    monkeypatch.setattr(keys_repo, "get_gateway_key_for_update", lock_and_advance_clock)
    with pytest.raises(KeyCloneEligibilityError):
        asyncio.run(
            service.execute_plan(
                plan=parse_clone_plan_document(document),
                reason="clone",
                actor_admin_id=ADMIN_ID,
                confirm_external_tool_fenced=False,
                create_email_delivery=False,
            )
        )
    assert key_service.create_calls == []


def test_execute_refuses_ambiguous_duplicate_receipts() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"
    first_target = keys_repo.targets[uuid.UUID(first.target_gateway_key_id)]
    # Corrupted state: a second key carries the SAME (source, operation)
    # receipt; the lookup must refuse rather than silently choose .first().
    dup = GatewayKey(
        id=uuid.uuid4(),
        owner_id=TARGET_OWNER_ID,
        public_key_id="pub-dup",
        status="active",
        valid_from=NOW,
        valid_until=NOW + timedelta(days=1),
        key_purpose="standard",
        capability_policy_mode="standard",
        external_tool_fence_state="none",
        metadata_json=dict(first_target.metadata_json or {}),
    )
    keys_repo.targets[dup.id] = dup
    with pytest.raises(KeyCloneReceiptAmbiguousError):
        _execute(service, document)
    assert len(key_service.create_calls) == 1


def test_execute_refuses_legacy_a_shape_receipt() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"
    first_target = keys_repo.targets[uuid.UUID(first.target_gateway_key_id)]
    # Simulate a legacy a-shape receipt lacking the new identity members.
    receipt = dict((first_target.metadata_json or {})["clone_receipt"])
    for field in ("policy_fingerprint", "target_owner_id", "requires_fenced_confirmation"):
        receipt.pop(field, None)
    metadata = dict(first_target.metadata_json or {})
    metadata["clone_receipt"] = receipt
    first_target.metadata_json = metadata
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, document)
    assert len(key_service.create_calls) == 1


# --- 198-c: complete reviewed business identity ------------------------------


def test_execute_copy_source_expiry_reviewed_mismatch_refuses_before_create() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(
        service,
        validity_mode=VALIDITY_COPY_SOURCE_EXPIRY,
        validity_duration_seconds=None,
    )
    # Tamper ONLY the reviewed copy-source-expiry date; the fresh locked
    # source still has the original expiry. First execution must refuse
    # before any write - never substitute another expiry.
    tampered = copy.deepcopy(document)
    tampered["validity"]["source_valid_until"] = (
        (source_row.valid_until + timedelta(days=300)).isoformat()
    )
    with pytest.raises(KeyCloneReviewedPolicyMismatchError):
        _execute(service, tampered)
    assert key_service.create_calls == []
    assert service._audit.calls == []


def test_execute_changed_source_public_id_on_completed_operation_refuses() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"
    tampered = copy.deepcopy(document)
    tampered["source_public_key_id"] = "contradictory-public-id"
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, tampered)
    assert len(key_service.create_calls) == 1


def test_execute_changed_reviewed_expiry_on_completed_operation_refuses() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(
        service,
        validity_mode=VALIDITY_COPY_SOURCE_EXPIRY,
        validity_duration_seconds=None,
    )
    first = _execute(service, document)
    assert first.status == "created"
    tampered = copy.deepcopy(document)
    tampered["validity"]["source_valid_until"] = (
        (source_row.valid_until + timedelta(days=300)).isoformat()
    )
    with pytest.raises(KeyClonePlanMismatchError):
        _execute(service, tampered)
    assert len(key_service.create_calls) == 1


def test_execute_original_repeat_after_real_source_expiry_edit_still_already_applied() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(
        service,
        validity_mode=VALIDITY_COPY_SOURCE_EXPIRY,
        validity_duration_seconds=None,
    )
    first = _execute(service, document)
    assert first.status == "created"
    # An ACTUAL source validity edit changes the source fingerprint (a fresh
    # execution would be stale) but must NOT change the identity of a
    # completed operation: the ORIGINAL repeat still dedups.
    source_row.valid_until = source_row.valid_until + timedelta(days=45)
    repeated = _execute(service, document)
    assert repeated.status == "already-applied"
    assert repeated.target_gateway_key_id == first.target_gateway_key_id
    assert len(key_service.create_calls) == 1


def test_inert_preview_change_does_not_affect_execution() -> None:
    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(service)
    first = _execute(service, document)
    assert first.status == "created"
    # Only the explicitly inert preview block may vary without affecting
    # execution identity.
    varied = copy.deepcopy(document)
    varied["preview"] = {
        "valid_from": "2026-10-28T13:00:00+00:00",
        "valid_until": "2026-10-29T13:00:00+00:00",
        "note": "operator-annotated preview text",
    }
    repeated = _execute(service, varied)
    assert repeated.status == "already-applied"
    assert repeated.target_gateway_key_id == first.target_gateway_key_id
    assert len(key_service.create_calls) == 1


def test_receipt_carries_complete_business_identity() -> None:
    from slaif_gateway.schemas.key_clone import CLONE_RECEIPT_METADATA_KEY

    service, source_row, keys_repo, key_service = _make_service()
    document = _build_plan(
        service,
        validity_mode=VALIDITY_COPY_SOURCE_EXPIRY,
        validity_duration_seconds=None,
    )
    first = _execute(service, document)
    assert first.status == "created"
    target = keys_repo.targets[uuid.UUID(first.target_gateway_key_id)]
    receipt = (target.metadata_json or {})[CLONE_RECEIPT_METADATA_KEY]
    assert receipt["source_public_key_id"] == "pub-source"
    assert receipt["source_valid_until"] == source_row.valid_until.isoformat()
    # No key material or provider references in the bounded safe receipt.
    for value in receipt.values():
        assert not (isinstance(value, str) and value.startswith("sk-"))


# --- 198-c: consumable dry-run (strict round trip) ----------------------------


def test_build_plan_duration_at_documented_maximum_remains_consumable() -> None:
    from slaif_gateway.schemas.key_clone import MAX_VALIDITY_DURATION_SECONDS

    service, *_ = _make_service()
    document = _build_plan(
        service, validity_duration_seconds=MAX_VALIDITY_DURATION_SECONDS
    )
    # A successful dry-run document must re-parse with the SAME strict schema
    # (including the preview block) - the operator can execute what was shown.
    plan = parse_clone_plan_document(document)
    assert plan.validity_duration_seconds == MAX_VALIDITY_DURATION_SECONDS


def test_build_plan_duration_over_documented_maximum_fails_safely() -> None:
    from slaif_gateway.schemas.key_clone import MAX_VALIDITY_DURATION_SECONDS

    service, *_ = _make_service()
    over = MAX_VALIDITY_DURATION_SECONDS + 1
    with pytest.raises(KeyClonePlanError) as excinfo:
        _build_plan(service, validity_duration_seconds=over)
    # Fixed safe error: bounded vocabulary only; the generated value, any DB
    # state, audit, or plan file is never involved.
    assert "bounded maximum" in str(excinfo.value)
    assert str(over) not in str(excinfo.value)
