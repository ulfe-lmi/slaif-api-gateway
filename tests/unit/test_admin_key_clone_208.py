"""208-a GUI reviewed key cloning: focused unit qualification.

Fake-persistence ASGI/Jinja seams over the real admin app: the clone
router's auth/CSRF, core-eligibility display, review-intent binding
(actor/session/expiry/tamper/size), apply confirmation/reason/delivery
binding, one-time plaintext channel law, post-commit delivery-failure
recovery, and read-only receipt recovery (including malformed-receipt
refusal) are qualified here. No database, no SMTP, no broker: the
service layer is faked at the KeyCloneService seam and the one-time
plaintext is a synthetic value asserted as booleans only.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.services.admin_key_dashboard import (
    AdminKeyDashboardService,
    AdminKeyNotFoundError,
)
from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
    AdminSessionService,
)
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.services.key_clone_service import (
    KeyCloneEligibilityError,
    KeyCloneReceiptAmbiguousError,
    KeyCloneReceiptMalformedError,
    KeyCloneReceiptProjection,
    KeyCloneResult,
    KeyCloneService,
    KeyCloneSourceSecretShapeError,
    KeyCloneStalePlanError,
    KeyCloneTargetMissingError,
)
from slaif_gateway.services.key_errors import GatewayKeyNotFoundError
from slaif_gateway.schemas.key_clone import (
    CLONE_RECEIPT_METADATA_KEY,
    MAX_CLONE_PLAN_FILE_BYTES,
)
from slaif_gateway.api import admin_review_intent as intent

from tests.unit.test_admin_key_actions_routes import _app, _settings

# Synthetic values only; asserted as booleans, never echoed.
CANARY = "sk-slaif-canary-" + "7" * 40
PLAINTEXT = "sk-slaif-probe-" + "0" * 40

ADMIN_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()
SOURCE_ID = uuid.uuid4()
TARGET_ID = uuid.uuid4()
TARGET_OWNER_ID = uuid.uuid4()


def _key_detail() -> SimpleNamespace:
    return SimpleNamespace(
        id=SOURCE_ID,
        public_key_id="pk_source_key_123",
        key_prefix="sk-slaif-",
        key_hint="hint",
        owner_id=TARGET_OWNER_ID,
        owner_display_name="Grace Hopper",
        owner_email="owner@example.org",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        status="active",
        computed_display_status="active",
        can_suspend=True,
        can_activate=False,
        can_revoke=True,
        can_rotate=True,
        valid_from=datetime(2026, 10, 1, tzinfo=UTC),
        valid_until=datetime(2027, 10, 1, tzinfo=UTC),
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        cost_used_eur=0,
        tokens_used_total=0,
        requests_used_total=0,
        cost_reserved_eur=0,
        tokens_reserved_total=0,
        requests_reserved_total=0,
        allowed_models=("m1",),
        allowed_endpoints=("/v1/chat/completions",),
        allow_all_models=False,
        allow_all_endpoints=False,
        key_purpose="standard",
        capability_policy_mode="standard",
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=None,
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def _plan_document(**overrides: Any) -> dict[str, Any]:
    doc = {
        "schema_version": 1,
        "operation_uuid": str(uuid.uuid4()),
        "source_gateway_key_id": str(SOURCE_ID),
        "source_public_key_id": "pk_source_key_123",
        "source_fingerprint": "ab" * 32,
        "target_owner_id": str(TARGET_OWNER_ID),
        "target_cohort_id": None,
        "validity": {"mode": "duration-from-now", "duration_seconds": 3600},
        "policy": {
            "schema_version": 1,
            "allowed_providers": ["openai"],
            "allowed_models": ["m1"],
            "allowed_endpoints": ["/v1/chat/completions"],
            "cost_limit_eur": "1234.560000000",
            "token_limit_total": 1500000,
            "request_limit_total": 4200,
            "rate_limit_policy": {
                "requests_per_minute": 60,
                "tokens_per_minute": 1000000,
                "max_concurrent_requests": 4,
                "window_seconds": 60,
            },
            "lazy_throttling_policy": {
                "mode": "wait",
                "max_wait_seconds": 30,
                "max_waiting_requests": 2,
            },
            "chat_streaming_live_burn_policy": {
                "version": 1,
                "enabled": False,
                "cost_margin_eur": "0.000000000",
                "token_margin": 0,
            },
        },
        "requires_fenced_confirmation": False,
        "preview": {
            "valid_from": "2026-10-31T12:00:00+00:00",
            "valid_until": "2026-10-31T13:00:00+00:00",
            "note": "Preview only; recomputed from EXECUTION time and the fresh source.",
        },
    }
    doc.update(overrides)
    return doc


def _result(**overrides: Any) -> KeyCloneResult:
    base = dict(
        status="created",
        operation_uuid="00000000-0000-4000-8000-000000000001",
        source_gateway_key_id=str(SOURCE_ID),
        source_fingerprint="ab" * 32,
        requires_fenced_confirmation=False,
        target_gateway_key_id=str(TARGET_ID),
        target_public_key_id="pk_target_key_999",
        one_time_secret_id=str(uuid.uuid4()),
        email_delivery_id=None,
        valid_from=datetime(2026, 10, 31, tzinfo=UTC),
        valid_until=datetime(2026, 10, 31, 13, 0, 0, tzinfo=UTC),
        plaintext_key=PLAINTEXT,
    )
    base.update(overrides)
    return KeyCloneResult(**base)


class _State:
    """Service seam state: what the faked clone service returns/raises."""

    def __init__(self) -> None:
        self.build_plan_doc: dict[str, Any] | None = None
        self.build_plan_exc: Exception | None = None
        self.execute_result: KeyCloneResult | None = None
        self.execute_exc: Exception | None = None
        self.execute_calls: list[dict[str, Any]] = []
        self.receipt: KeyCloneReceiptProjection | None = None
        self.receipt_exc: Exception | None = None
        self.detail: SimpleNamespace | None = _key_detail()


@pytest.fixture()
def state() -> _State:
    return _State()


@pytest.fixture()
def client(monkeypatch, state: _State) -> TestClient:
    app = _app()
    admin_user = AdminUser(
        id=ADMIN_ID,
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=SESSION_ID,
        admin_user_id=ADMIN_ID,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, admin_session_row, csrf_token):
        return csrf_token == "dashboard-csrf"

    async def refresh_csrf_token(self, admin_session_id=None):
        return "dashboard-csrf"

    monkeypatch.setattr(
        AdminSessionService, "validate_admin_session", validate_admin_session
    )
    monkeypatch.setattr(
        AdminSessionService, "verify_session_csrf_token", verify_session_csrf_token
    )
    monkeypatch.setattr(
        AdminSessionService, "refresh_csrf_token", refresh_csrf_token
    )

    async def get_key_detail(self, key_id):
        if state.detail is None or key_id != SOURCE_ID:
            raise AdminKeyNotFoundError()
        return state.detail

    async def build_plan(self, **kwargs):
        if state.build_plan_exc is not None:
            raise state.build_plan_exc
        return state.build_plan_doc or _plan_document()

    async def execute_plan(self, **kwargs):
        state.execute_calls.append(kwargs)
        if state.execute_exc is not None:
            raise state.execute_exc
        return state.execute_result or _result()

    async def find_clone_receipt(self, **kwargs):
        if state.receipt_exc is not None:
            raise state.receipt_exc
        return state.receipt or _receipt_projection(kwargs["operation_uuid"])

    monkeypatch.setattr(
        AdminKeyDashboardService, "get_key_detail", get_key_detail
    )
    monkeypatch.setattr(KeyCloneService, "build_plan", build_plan)
    monkeypatch.setattr(KeyCloneService, "execute_plan", execute_plan)
    monkeypatch.setattr(KeyCloneService, "find_clone_receipt", find_clone_receipt)

    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return client


def _receipt_projection(operation_uuid: uuid.UUID) -> KeyCloneReceiptProjection:
    return KeyCloneReceiptProjection(
        status="created",
        source_gateway_key_id=str(SOURCE_ID),
        operation_uuid=str(operation_uuid),
        target_gateway_key_id=str(TARGET_ID),
        target_public_key_id="pk_target_key_999",
        target_status="active",
        validity_mode="duration-from-now",
    )


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _token_from_html(html: str) -> str:
    match = re.search(r'name="clone_review_intent" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _review(client: TestClient, **overrides) -> "TestClient":
    data = {
        "csrf_token": "dashboard-csrf",
        "target_owner_id": str(TARGET_OWNER_ID),
        "target_cohort_id": "",
        "validity_mode": "duration-from-now",
        "duration_value": "1",
        "duration_unit": "hours",
        "email_delivery_mode": "none",
    }
    data.update(overrides)
    return client.post(f"/admin/keys/{SOURCE_ID}/clone/review", data=data)


def _apply(client: TestClient, token: str, **overrides) -> "TestClient":
    data = {
        "csrf_token": "dashboard-csrf",
        "clone_review_intent": token,
        "confirm_apply": "true",
        "reason": "208 unit clone",
    }
    data.update(overrides)
    return client.post(f"/admin/keys/{SOURCE_ID}/clone/apply", data=data)


# ---------------------------------------------------------------------------
# Review-intent token (pure)
# ---------------------------------------------------------------------------


def _small_plan() -> dict[str, Any]:
    return _plan_document()


def test_intent_roundtrip_and_expiry() -> None:
    plan = _small_plan()
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=plan,
        delivery_mode="none",
        now=datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC),
    )
    document, mode = intent.verify_review_intent_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        now=datetime(2026, 10, 31, 12, 14, 59, tzinfo=UTC),
    )
    assert mode == "none"
    assert document["operation_uuid"] == plan["operation_uuid"]
    with pytest.raises(intent.AdminReviewIntentError):
        intent.verify_review_intent_token(
            admin_session_secret="s" * 40,
            token=token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            now=datetime(2026, 10, 31, 12, 15, 0, tzinfo=UTC),
        )


def test_intent_wrong_actor_or_session_refused() -> None:
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=_small_plan(),
        delivery_mode="pending",
    )
    for kwargs in (
        {"admin_user_id": uuid.uuid4(), "admin_session_id": SESSION_ID},
        {"admin_user_id": ADMIN_ID, "admin_session_id": uuid.uuid4()},
    ):
        with pytest.raises(intent.AdminReviewIntentError):
            intent.verify_review_intent_token(
                admin_session_secret="s" * 40, token=token, **kwargs
            )


def test_intent_tampered_body_refused() -> None:
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=_small_plan(),
        delivery_mode="none",
    )
    body, dot, digest = token.rpartition(".")
    chars = list(body)
    chars[10] = "A" if chars[10] != "A" else "B"
    with pytest.raises(intent.AdminReviewIntentError):
        intent.verify_review_intent_token(
            admin_session_secret="s" * 40,
            token="".join(chars) + dot + digest,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )


def test_intent_non_ascii_digest_is_controlled_refusal() -> None:
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=_small_plan(),
        delivery_mode="none",
    )
    body = token.rpartition(".")[0]
    with pytest.raises(intent.AdminReviewIntentError):
        intent.verify_review_intent_token(
            admin_session_secret="s" * 40,
            token=body + "." + "\u00e9" * 64,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )


def test_intent_malformed_formats_refused() -> None:
    for bad in ("", "abc", "a." + "0" * 64, "!!!." + "0" * 64, "a." + "g" * 64):
        with pytest.raises(intent.AdminReviewIntentError):
            intent.verify_review_intent_token(
                admin_session_secret="s" * 40,
                token=bad,
                admin_user_id=ADMIN_ID,
                admin_session_id=SESSION_ID,
            )


def test_intent_builder_enforces_decoded_plan_bound(monkeypatch) -> None:
    # Simulate a (hypothetical) core-valid document whose canonical bytes
    # exceed the 128 KiB envelope: the builder must still refuse it with a
    # fixed safe message (the strict parser alone imposes no byte limit).
    # The parser is stubbed below, so the core list bounds do not apply;
    # 200 x 256-char items per list make the canonical form ~205 KiB.
    monkeypatch.setattr(intent, "parse_clone_plan_document", lambda doc: None)
    oversized = _small_plan()
    oversized["policy"] = dict(_small_plan()["policy"], allowed_models=["m" * 256] * 200)
    oversized["policy"]["allowed_endpoints"] = ["e" * 256] * 200
    oversized["policy"]["allowed_providers"] = ["p" * 256] * 200
    oversized["policy"]["external_tool_policy"] = {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": [],
        "allowed_destination_ids": ["d" * 256] * 200,
        "max_provider_tool_calls_per_request": 1,
        "single_request_overrun_acknowledged": False,
    }
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.build_review_intent_token(
            admin_session_secret="s" * 40,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            plan_document=oversized,
            delivery_mode="none",
        )
    assert excinfo.value.message == intent._TOO_LARGE_MESSAGE
    assert len(intent._canonical_json(oversized)) > MAX_CLONE_PLAN_FILE_BYTES


def test_intent_core_supported_scope_still_builds() -> None:
    # Every field at the core's own maximum (100 items x 256 chars) is still
    # a core-supported plan and must build within the documented overhead.
    plan = _small_plan()
    plan["policy"] = {
        "schema_version": 1,
        "allowed_models": ["m" * 256] * 100,
        "allowed_endpoints": ["e" * 256] * 100,
        "allowed_providers": ["p" * 256] * 100,
        "external_tool_policy": {
            "version": 1,
            "mode": "external_tool_fenced",
            "allowed_capabilities": [],
            "allowed_destination_ids": ["d" * 256] * 100,
            "max_provider_tool_calls_per_request": 1,
            "single_request_overrun_acknowledged": False,
        },
    }
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=plan,
        delivery_mode="enqueue",
    )
    assert len(token) <= intent.MAX_REVIEW_INTENT_TOKEN_CHARS
    document, mode = intent.verify_review_intent_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    assert mode == "enqueue"
    assert len(document["policy"]["allowed_models"]) == 100


def test_intent_builder_refuses_nonconformant_plan() -> None:
    bad = _small_plan()
    bad["bogus_field"] = "x"
    with pytest.raises(Exception):
        intent.build_review_intent_token(
            admin_session_secret="s" * 40,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            plan_document=bad,
            delivery_mode="none",
        )


# ---------------------------------------------------------------------------
# Authn / authz
# ---------------------------------------------------------------------------


def test_clone_form_unauthenticated_redirects() -> None:
    app = _app()
    client = TestClient(app)
    response = client.get(f"/admin/keys/{SOURCE_ID}/clone", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_clone_routes_disabled_dashboard_404(client) -> None:
    app = _app(_settings(ENABLE_ADMIN_DASHBOARD=False))
    # Re-auth on the disabled app.
    admin_user = AdminUser(
        id=ADMIN_ID,
        email="admin@example.org",
        display_name="A",
        password_hash="h",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=SESSION_ID,
        admin_user_id=ADMIN_ID,
        session_token_hash="sha256:s",
        csrf_token_hash="sha256:c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user
    disabled = TestClient(app)
    disabled.cookies.set("slaif_admin_session", "session-plaintext")
    response = disabled.get(f"/admin/keys/{SOURCE_ID}/clone", follow_redirects=False)
    assert response.status_code in (303, 404)


def test_clone_form_malformed_id_404(client) -> None:
    response = client.get("/admin/keys/not-a-uuid/clone", follow_redirects=False)
    assert response.status_code == 404


def test_clone_form_vanished_source_404(client, state: _State) -> None:
    state.detail = None
    response = client.get(f"/admin/keys/{SOURCE_ID}/clone", follow_redirects=False)
    assert response.status_code == 404


def test_review_without_csrf_refused_before_service(client, state: _State) -> None:
    response = client.post(
        f"/admin/keys/{SOURCE_ID}/clone/review",
        data={"csrf_token": "wrong", "target_owner_id": str(TARGET_OWNER_ID)},
    )
    assert response.status_code in (303, 400)
    assert not state.execute_calls
    assert state.build_plan_exc is None


def test_apply_without_csrf_refused(client, state: _State) -> None:
    response = client.post(
        f"/admin/keys/{SOURCE_ID}/clone/apply",
        data={"csrf_token": "wrong", "confirm_apply": "true", "reason": "x"},
    )
    assert response.status_code in (303, 400)
    assert not state.execute_calls


# ---------------------------------------------------------------------------
# Form page
# ---------------------------------------------------------------------------


def test_clone_form_eligible_source(client, state: _State) -> None:
    response = client.get(f"/admin/keys/{SOURCE_ID}/clone")
    assert response.status_code == 200
    assert "pk_source_key_123" in response.text
    assert "not eligible for cloning" not in response.text
    assert "Review clone plan" in response.text


def test_clone_form_unsupported_ineligible_source(client, state: _State) -> None:
    state.build_plan_exc = KeyCloneEligibilityError(param="source.status")
    response = client.get(f"/admin/keys/{SOURCE_ID}/clone")
    assert response.status_code == 200
    assert "not eligible for cloning" in response.text


def test_clone_form_unsupported_secret_shape(client, state: _State) -> None:
    state.build_plan_exc = KeyCloneSourceSecretShapeError(param="policy")
    response = client.get(f"/admin/keys/{SOURCE_ID}/clone")
    assert response.status_code == 200
    assert "recognized secret" in response.text


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


def test_review_renders_plan_bound_token_and_policy_summaries(client, state: _State) -> None:
    response = _review(client)
    assert response.status_code == 200, "review should render"
    assert "Review Clone Plan" in response.text
    assert "pk_source_key_123" in response.text
    assert "Wait for capacity: max wait 30s, max 2 waiting per key" in response.text
    assert "60 req/min, 1M tokens/min, 4 concurrent, 60s window" in response.text
    assert "EUR 1,234.56" in response.text
    assert "1.5M" in response.text
    assert "Chat live-burn: off (margins ignored)" in response.text
    assert "Check this operation's outcome" in response.text
    token = _token_from_html(response.text)
    assert token.count(".") == 1
    # The review state is hidden form data, never rendered as readable text.
    token_echoed = token in response.text.replace('value="%s"' % token, "", 1)
    assert not token_echoed


def test_review_lazy_reject_mode_renders_reject(client, state: _State) -> None:
    state.build_plan_doc = _plan_document()
    state.build_plan_doc["policy"]["lazy_throttling_policy"] = {
        "mode": "reject",
        "max_wait_seconds": 30,
        "max_waiting_requests": 2,
    }
    response = _review(client, validity_mode="copy-source-expiry", duration_value="")
    assert response.status_code == 200
    assert "Reject immediately (default)" in response.text
    assert "Wait for capacity" not in response.text


def test_review_rate_window_readout_non_minute(client, state: _State) -> None:
    # The runtime meters counts in the configured window: a 10s window
    # must be labeled by the window, not as per-minute.
    state.build_plan_doc = _plan_document()
    state.build_plan_doc["policy"]["rate_limit_policy"] = {
        "requests_per_minute": 30,
        "tokens_per_minute": 10000,
        "max_concurrent_requests": 2,
        "window_seconds": 10,
    }
    response = _review(client, validity_mode="copy-source-expiry", duration_value="")
    assert response.status_code == 200
    assert "30 requests, 0.01M tokens per 10s window" in response.text
    assert "max 2 concurrent" in response.text
    no_per_minute = "req/min" not in response.text and "tokens/min" not in response.text
    assert no_per_minute, "non-minute window must not be labeled per minute"


def test_review_rate_window_readout_minute_default(client, state: _State) -> None:
    # Minute (60s) and omitted windows keep the existing per-minute grammar.
    state.build_plan_doc = _plan_document()
    response = _review(client, validity_mode="copy-source-expiry", duration_value="")
    assert response.status_code == 200
    assert "60 req/min" in response.text
    assert "1M tokens/min" in response.text
    assert "4 concurrent" in response.text
    # Null responses_policy: neutral readout, no blanket "disabled" claim
    # (gateway default/legacy resolution plus endpoint/route gates apply).
    assert (
        "No explicit Responses policy: optional key capability grants are absent"
        in response.text
    )
    assert "Responses disabled" not in response.text


def test_review_unknown_source_is_controlled_404(client, state: _State) -> None:
    state.build_plan_exc = GatewayKeyNotFoundError()
    response = _review(client)
    assert response.status_code == 404
    assert not state.execute_calls


def test_review_ineligible_source_safe_400_no_echo(client, state: _State) -> None:
    state.build_plan_exc = KeyCloneEligibilityError(param="source.status")
    response = _review(client)
    assert response.status_code == 400
    assert "not eligible for cloning" in response.text
    token_present = "clone_review_intent" in response.text
    assert not token_present


def test_review_target_missing_safe_400(client, state: _State) -> None:
    state.build_plan_exc = KeyCloneTargetMissingError(param="target_owner_id")
    response = _review(client)
    assert response.status_code == 400
    assert "does not exist" in response.text


def test_review_validation_errors_are_fixed_and_safe(client, state: _State) -> None:
    # Bad owner UUID (ordinary value preserved for correction).
    response = _review(client, target_owner_id="not-a-uuid")
    assert response.status_code == 400
    assert "not-a-uuid" in response.text
    # Bad mode.
    response = _review(client, validity_mode="bad-mode")
    assert response.status_code == 400
    assert "validity mode" in response.text
    # Zero duration.
    response = _review(client, duration_value="0")
    assert response.status_code == 400
    assert "positive" in response.text
    # Non-whole duration.
    response = _review(client, duration_value="1.5")
    assert response.status_code == 400
    # Over-maximum duration.
    response = _review(client, duration_value="999999999999", duration_unit="days")
    assert response.status_code == 400
    assert "bounded maximum" in response.text
    # Absolute mode without both times.
    response = _review(
        client,
        validity_mode="absolute",
        duration_value="",
        valid_from="2026-11-01T00:00",
        valid_until="",
    )
    assert response.status_code == 400
    # Copy-source-expiry with stray duration.
    response = _review(
        client,
        validity_mode="copy-source-expiry",
        duration_value="5",
    )
    assert response.status_code == 400
    assert "leave the" in response.text
    assert not state.execute_calls


def test_review_send_now_without_email_config_refused(client, state: _State) -> None:
    response = _review(client, email_delivery_mode="send-now")
    assert response.status_code == 400
    assert "Email delivery must be enabled" in response.text


def test_review_canary_owner_value_not_echoed(client, state: _State) -> None:
    response = _review(client, target_owner_id=CANARY)
    assert response.status_code == 400
    canary_absent = CANARY not in response.text
    assert canary_absent, "credential-shaped owner value was echoed"


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def test_apply_created_plaintext_exactly_once_no_store(client, state: _State) -> None:
    response = _review(client)
    token = _token_from_html(response.text)
    result = client.post(
        f"/admin/keys/{SOURCE_ID}/clone/apply",
        data={"csrf_token": "dashboard-csrf", "clone_review_intent": token,
              "confirm_apply": "true", "reason": "208 unit clone"},
    )
    assert result.status_code == 200
    assert result.text.count(PLAINTEXT) == 1, "plaintext must appear exactly once"
    cache_control = result.headers.get("cache-control", "")
    assert cache_control.startswith("no-store")
    assert len(state.execute_calls) == 1
    assert state.execute_calls[0]["create_email_delivery"] is False
    assert state.execute_calls[0]["actor_admin_id"] == ADMIN_ID


def test_apply_repeat_same_operation_already_applied_no_plaintext(
    client, state: _State
) -> None:
    response = _review(client)
    token = _token_from_html(response.text)
    first = _apply(client, token)
    assert first.status_code == 200
    state.execute_result = _result(
        status="already-applied",
        operation_uuid=state.execute_calls[0]["plan"].operation_uuid,
        plaintext_key=None,
    )
    repeat = _apply(client, token)
    assert repeat.status_code == 200
    assert "Already Applied" in repeat.text
    plaintext_absent = PLAINTEXT not in repeat.text
    assert plaintext_absent


def test_apply_tampered_token_refused_before_execution(client, state: _State) -> None:
    response = _review(client)
    token = _token_from_html(response.text)
    body, dot, digest = token.rpartition(".")
    chars = list(body)
    chars[10] = "A" if chars[10] != "A" else "B"
    result = _apply(client, "".join(chars) + dot + digest)
    assert result.status_code == 400
    assert not state.execute_calls


def test_apply_wrong_actor_refused(client, state: _State) -> None:
    plan = _small_plan()
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=uuid.uuid4(),  # a different admin than the signed-in one
        admin_session_id=SESSION_ID,
        plan_document=plan,
        delivery_mode="none",
    )
    result = _apply(client, token)
    assert result.status_code == 400
    assert "not valid for this signed-in admin" in result.text
    assert not state.execute_calls


def test_apply_expired_refused(client, state: _State) -> None:
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=_small_plan(),
        delivery_mode="none",
        ttl_seconds=60,
        now=datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC),
    )
    result = _apply(client, token)
    assert result.status_code == 400
    assert "expired" in result.text
    assert not state.execute_calls


def test_apply_source_mismatch_refused(client, state: _State) -> None:
    foreign = _small_plan()
    foreign["source_gateway_key_id"] = str(uuid.uuid4())
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=foreign,
        delivery_mode="none",
    )
    result = _apply(client, token)
    assert result.status_code == 400
    assert "different source key" in result.text
    assert not state.execute_calls


def test_apply_missing_confirmation_refused(client, state: _State) -> None:
    response = _review(client)
    token = _token_from_html(response.text)
    result = client.post(
        f"/admin/keys/{SOURCE_ID}/clone/apply",
        data={"csrf_token": "dashboard-csrf", "clone_review_intent": token,
              "reason": "no confirmation"},
    )
    assert result.status_code == 400
    assert not state.execute_calls


def test_apply_reason_bound(client, state: _State) -> None:
    response = _review(client)
    token = _token_from_html(response.text)
    blank = _apply(client, token, reason="   ")
    assert blank.status_code == 400
    over = _apply(client, token, reason="x" * 513)
    assert over.status_code == 400
    assert not state.execute_calls
    ok = _apply(client, token, reason="x" * 512)
    assert ok.status_code == 200
    assert len(state.execute_calls) == 1


def test_apply_delivery_binding_comes_only_from_token(client, state: _State) -> None:
    response = _review(client)  # token bound to "none"
    token = _token_from_html(response.text)
    # A forged mutable field must not change the reviewed channel.
    result = _apply(client, token, email_delivery_mode="send-now")
    assert result.status_code == 200
    assert state.execute_calls[-1]["create_email_delivery"] is False


def test_apply_fenced_confirmation_required(client, state: _State) -> None:
    state.build_plan_doc = _plan_document(requires_fenced_confirmation=True)
    response = _review(client)
    assert response.status_code == 200
    token = _token_from_html(response.text)
    refused = _apply(client, token)
    assert refused.status_code == 400
    assert "fenced" in refused.text
    assert not state.execute_calls
    accepted = _apply(client, token, confirm_external_tool_fenced="true")
    assert accepted.status_code == 200
    assert state.execute_calls[-1]["confirm_external_tool_fenced"] is True


def test_apply_stale_plan_safe_400(client, state: _State) -> None:
    response = _review(client)
    token = _token_from_html(response.text)
    state.execute_exc = KeyCloneStalePlanError(param="source_fingerprint")
    result = _apply(client, token)
    assert result.status_code == 400
    assert "stale" in result.text


def test_apply_send_now_post_commit_failure_recovery(
    client, monkeypatch, state: _State
) -> None:
    settings = _settings(
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="smtp.test",
        SMTP_FROM="ops@example.org",
    )
    app = _app(settings)
    # Re-run the session/clone seams against THIS app instance.
    admin_user = AdminUser(
        id=ADMIN_ID, email="admin@example.org", display_name="A",
        password_hash="h", role="admin", is_active=True,
    )
    admin_session = AdminSession(
        id=SESSION_ID, admin_user_id=ADMIN_ID,
        session_token_hash="sha256:s", csrf_token_hash="sha256:c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_csrf(self, row, csrf_token):
        return csrf_token == "dashboard-csrf"

    async def refresh(self, admin_session_id=None):
        return "dashboard-csrf"

    monkeypatch.setattr(AdminSessionService, "validate_admin_session", validate)
    monkeypatch.setattr(AdminSessionService, "verify_session_csrf_token", verify_csrf)
    monkeypatch.setattr(AdminSessionService, "refresh_csrf_token", refresh)

    async def get_key_detail(self, key_id):
        if key_id != SOURCE_ID:
            raise AdminKeyNotFoundError()
        return _key_detail()

    async def build_plan(self, **kwargs):
        return _plan_document()

    delivery_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    async def execute_plan(self, **kwargs):
        state.execute_calls.append(kwargs)
        return _result(
            email_delivery_id=str(delivery_id), one_time_secret_id=str(secret_id)
        )

    async def send_pending_key_email(self, **kwargs):
        raise EmailError("smtp down")

    monkeypatch.setattr(AdminKeyDashboardService, "get_key_detail", get_key_detail)
    monkeypatch.setattr(KeyCloneService, "build_plan", build_plan)
    monkeypatch.setattr(KeyCloneService, "execute_plan", execute_plan)
    monkeypatch.setattr(
        EmailDeliveryService, "send_pending_key_email", send_pending_key_email
    )

    c = TestClient(app)
    c.cookies.set("slaif_admin_session", "session-plaintext")
    review = c.post(
        f"/admin/keys/{SOURCE_ID}/clone/review",
        data={"csrf_token": "dashboard-csrf", "target_owner_id": str(TARGET_OWNER_ID),
              "validity_mode": "copy-source-expiry", "email_delivery_mode": "send-now"},
    )
    assert review.status_code == 200
    token = _token_from_html(review.text)
    result = c.post(
        f"/admin/keys/{SOURCE_ID}/clone/apply",
        data={"csrf_token": "dashboard-csrf", "clone_review_intent": token,
              "confirm_apply": "true", "reason": "208 dispatch failure"},
    )
    assert result.status_code == 200
    assert "Created With Delivery Failure" in result.text
    assert str(delivery_id) in result.text
    assert str(TARGET_ID) in result.text
    assert "second clone is NOT needed" in result.text
    plaintext_absent = PLAINTEXT not in result.text
    assert plaintext_absent
    # The clone itself was committed exactly once, with delivery creation.
    assert state.execute_calls[-1]["create_email_delivery"] is True


# ---------------------------------------------------------------------------
# Recovery (read-only)
# ---------------------------------------------------------------------------


def test_recovery_created_projection(client, state: _State) -> None:
    operation = uuid.uuid4()
    response = client.get(
        f"/admin/keys/{SOURCE_ID}/clone/receipts?operation={operation}"
    )
    assert response.status_code == 200
    assert "completed and created exactly one target key" in response.text
    assert str(TARGET_ID) in response.text
    assert not state.execute_calls


def test_recovery_not_found_assumes_nothing(client, state: _State) -> None:
    state.receipt = KeyCloneReceiptProjection(
        status="not-found",
        source_gateway_key_id=str(SOURCE_ID),
        operation_uuid=str(uuid.uuid4()),
    )
    operation = state.receipt.operation_uuid
    response = client.get(
        f"/admin/keys/{SOURCE_ID}/clone/receipts?operation={operation}"
    )
    assert response.status_code == 200
    assert "No clone receipt matches" in response.text
    assert "NOTHING is assumed" in response.text
    assert not state.execute_calls


def test_recovery_ambiguous_refused(client, state: _State) -> None:
    state.receipt_exc = KeyCloneReceiptAmbiguousError(param="operation_uuid")
    response = client.get(
        f"/admin/keys/{SOURCE_ID}/clone/receipts?operation={uuid.uuid4()}"
    )
    assert response.status_code == 200
    assert "Multiple clone receipts" in response.text


def test_recovery_canary_operation_redacted(client, state: _State) -> None:
    response = client.get(
        f"/admin/keys/{SOURCE_ID}/clone/receipts?operation={CANARY}"
    )
    assert response.status_code == 200
    canary_absent = CANARY not in response.text
    assert canary_absent, "credential-shaped operation value was echoed"
    assert "operation UUID" in response.text


def test_recovery_ordinary_invalid_value_preserved(client, state: _State) -> None:
    response = client.get(f"/admin/keys/{SOURCE_ID}/clone/receipts?operation=abc")
    assert response.status_code == 200
    assert 'value="abc"' in response.text
    assert "32 hexadecimal digits" in response.text


# ---------------------------------------------------------------------------
# Read-only receipt projection (direct service seam)
# ---------------------------------------------------------------------------


class _FakeKeysRepository:
    def __init__(self, receipts: list, source: object) -> None:
        self._receipts = receipts
        self._source = source

    async def get_gateway_key_by_id(self, key_id):
        return self._source

    async def find_clone_receipts(self, *, source_gateway_key_id, operation_uuid):
        return self._receipts


def _service_with_receipts(receipts: list):
    from slaif_gateway.config import Settings

    source = SimpleNamespace(id=uuid.uuid4(), public_key_id="pk_src")
    service = KeyCloneService(
        settings=Settings(APP_ENV="test"),
        key_service=object(),
        gateway_keys_repository=_FakeKeysRepository(receipts, source),
        owners_repository=object(),
        cohorts_repository=object(),
        email_delivery_service=object(),
        audit_repository=object(),
    )
    return service, source


def _full_receipt(source_id: uuid.UUID, operation: uuid.UUID, target: uuid.UUID, **overrides):
    receipt = {
        "source_gateway_key_id": str(source_id),
        "operation_uuid": str(operation),
        "target_gateway_key_id": str(target),
        "target_owner_id": str(uuid.uuid4()),
        "one_time_secret_id": str(uuid.uuid4()),
        "email_delivery_id": None,
        "source_fingerprint": "ab" * 32,
        "policy_fingerprint": "cd" * 32,
        "source_public_key_id": "pk_src",
        "source_valid_until": "2026-12-01T00:00:00+00:00",
        "target_cohort_id": None,
        "requires_fenced_confirmation": False,
        "validity_mode": "duration-from-now",
        "validity_duration_seconds": 3600,
        "validity_from": None,
        "validity_until": None,
        "status": "created",
    }
    receipt.update(overrides)
    return receipt


def _target_row(target: uuid.UUID, receipt: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=target,
        public_key_id="pk_tgt",
        owner_id=uuid.uuid4(),
        cohort_id=None,
        status="active",
        metadata_json={CLONE_RECEIPT_METADATA_KEY: receipt},
    )


def test_find_clone_receipt_valid_and_not_found() -> None:
    import asyncio

    source, operation, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service, _ = _service_with_receipts(
        [_target_row(target, _full_receipt(source, operation, target))]
    )
    projection = asyncio.run(
        service.find_clone_receipt(source_gateway_key_id=source, operation_uuid=operation)
    )
    assert projection.status == "created"
    assert projection.target_gateway_key_id == str(target)
    empty, _ = _service_with_receipts([])
    projection = asyncio.run(
        empty.find_clone_receipt(source_gateway_key_id=source, operation_uuid=operation)
    )
    assert projection.status == "not-found"


def test_find_clone_receipt_malformed_variants_refused() -> None:
    import asyncio

    source, operation, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    variants = [
        # The review's synthetic case: only the two query IDs are present.
        {"source_gateway_key_id": str(source), "operation_uuid": str(operation)},
        _full_receipt(source, operation, target, source_fingerprint=123),
        _full_receipt(source, operation, target, validity_duration_seconds=True),
        _full_receipt(source, operation, target, requires_fenced_confirmation="false"),
        _full_receipt(source, operation, target, validity_mode="copy"),
        _full_receipt(source, operation, target, status="done"),
        _full_receipt(source, operation, target, source_gateway_key_id=str(uuid.uuid4())),
        _full_receipt(source, operation, target, target_gateway_key_id=str(uuid.uuid4())),
        _full_receipt(source, operation, target, source_public_key_id="x" * 300),
        _full_receipt(source, operation, target, one_time_secret_id=None),
        {k: v for k, v in _full_receipt(source, operation, target).items() if k != "status"},
        "not-a-dict",
    ]
    for receipt in variants:
        service, _ = _service_with_receipts([_target_row(target, receipt)])
        with pytest.raises(KeyCloneReceiptMalformedError):
            asyncio.run(
                service.find_clone_receipt(
                    source_gateway_key_id=source, operation_uuid=operation
                )
            )


def test_find_clone_receipt_ambiguous_refused() -> None:
    import asyncio

    source, operation, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = _target_row(target, _full_receipt(source, operation, target))
    service, _ = _service_with_receipts([row, row])
    with pytest.raises(KeyCloneReceiptAmbiguousError):
        asyncio.run(
            service.find_clone_receipt(
                source_gateway_key_id=source, operation_uuid=operation
            )
        )
