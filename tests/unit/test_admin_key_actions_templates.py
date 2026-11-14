import re
import asyncio
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.key_clone_service import (
    KeyCloneError,
    KeyCloneReceiptProjection,
)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return self


class _FakeSessionmaker:
    def __call__(self):
        return _FakeSession()


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "admin-session-secret-that-must-not-render",
        "OPENAI_UPSTREAM_API_KEY": "sk-provider-secret-placeholder",
        "OPENROUTER_API_KEY": "sk-or-provider-secret-placeholder",
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _detail(
    *,
    status: str = "active",
    display_status: str = "active",
    can_suspend: bool = True,
    can_activate: bool = False,
    can_revoke: bool = True,
    can_rotate: bool = True,
) -> AdminKeyDetail:
    row = AdminKeyListRow(
        id=uuid.uuid4(),
        public_key_id="public-action-id",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=uuid.uuid4(),
        owner_display_name="Safe Owner",
        owner_email="owner@example.org",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        status=status,
        computed_display_status=display_status,
        can_suspend=can_suspend,
        can_activate=can_activate,
        can_revoke=can_revoke,
        can_rotate=can_rotate,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        cost_limit_eur=Decimal("5.000000000"),
        token_limit_total=1000,
        request_limit_total=100,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        requests_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
        allowed_models=("gpt-test",),
        allowed_endpoints=("/v1/chat/completions",),
        allow_all_models=False,
        allow_all_endpoints=False,
        key_purpose="standard",
        capability_policy_mode="standard",
        calibration_metadata={},
        template_id=None,
        template_revision_id=None,
        allowed_models_summary="gpt-test",
        allowed_endpoints_summary="/v1/chat/completions",
        allowed_providers_summary="All",
        rate_limit_policy_summary="Default",
        responses_policy=None,
        responses_policy_summary="None",
        chat_streaming_live_burn_policy={
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
            "token_margin": 0,
        },
        chat_streaming_live_burn_policy_summary=(
            "Chat Completions streaming enabled; cost margin EUR 0.000000000; token margin 0"
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return AdminKeyDetail(
        **asdict(row),
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=None,
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def _login_and_detail(monkeypatch, client: TestClient, key: AdminKeyDetail) -> None:
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="password_hash_must_not_render",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session_hash_must_not_render",
        csrf_token_hash="csrf_hash_must_not_render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client.cookies.set("slaif_admin_session", "session-token-must-not-render")


def test_key_detail_renders_lifecycle_forms_for_valid_actions(monkeypatch) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/suspend"' in html
    assert f'action="/admin/keys/{key.id}/revoke"' in html
    assert f'action="/admin/keys/{key.id}/activate"' not in html
    assert 'name="csrf_token" value="rendered-csrf-token"' in html
    assert 'name="confirm_revoke" value="true"' in html
    assert "I understand revocation is permanent." in html
    assert "Revoke key" in html


def test_key_detail_renders_validity_and_limit_forms(monkeypatch) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/validity"' in html
    assert f'action="/admin/keys/{key.id}/limits"' in html
    assert 'name="csrf_token" value="rendered-csrf-token"' in html
    assert 'name="valid_from"' in html
    assert 'name="valid_until"' in html
    assert key.valid_from.isoformat() in html
    assert key.valid_until.isoformat() in html
    assert 'name="cost_limit_eur"' in html
    assert 'name="token_limit"' in html
    assert 'name="request_limit"' in html
    assert 'name="clear_cost_limit" value="true"' in html
    assert 'name="clear_token_limit" value="true"' in html
    assert 'name="clear_request_limit" value="true"' in html
    assert str(key.cost_limit_eur) in html
    assert str(key.token_limit_total) in html
    assert str(key.request_limit_total) in html
    assert "PostgreSQL-backed key policy" in html
    assert "Redis operational rate limits are configured separately" in html
    assert "Used and reserved counters are not reset" in html


def test_key_detail_renders_chat_streaming_live_burn_form(monkeypatch) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/chat-streaming-live-burn"' in html
    assert "Chat Completions streaming live-burn monitoring" in html
    assert 'name="chat_streaming_live_burn_enabled" value="true" checked' in html
    # 206-b: the zero-valued valid numeric default renders 0 (the stale
    # 0.000000000 oracle predates the zero-input representation fix).
    # The non-zero value (see the disabled-form case below) keeps its
    # exact digits: -0.250000000.
    assert 'name="chat_streaming_live_burn_cost_margin_eur" value="0"' in html
    assert 'name="chat_streaming_live_burn_token_margin" value="0"' in html
    assert "PostgreSQL hard quota limits remain independent and authoritative" in html
    assert "Margins are ignored while monitoring is off" in html
    assert "Live estimates are provisional, not invoice-grade" in html
    assert "detail-chat-streaming-live-burn-fields" in html
    assert "data-streaming-live-burn-surface" in html
    # 193-a: bundled local scripts carry a content-revision query string.
    assert re.search(r'src="/admin/static/js/streaming-live-burn\.js\?v=[0-9a-f]{16}"', html)
    assert "https://cdn" not in html.lower()
    assert "react" not in html.lower()
    assert "vue" not in html.lower()


def test_key_detail_renders_disabled_chat_live_burn_fields(monkeypatch) -> None:
    key = replace(
        _detail(),
        chat_streaming_live_burn_policy={
            "version": 1,
            "enabled": False,
            "cost_margin_eur": "-0.250000000",
            "token_margin": -250,
        },
        chat_streaming_live_burn_policy_summary=(
            "Chat live-burn: off (margins ignored), cost margin EUR -0.250000000, "
            "token margin -250"
        ),
    )
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert 'name="chat_streaming_live_burn_enabled" value="true" checked' not in html
    assert "live-burn-fields-disabled" in html
    # Adapted to the actual DOM: the dynamic margin inputs carry their
    # stable ids and the linked live-burn help association (219-b), so
    # assert the real attribute set on the actual control tags.
    cost = re.search(
        r'<input[^>]*name="chat_streaming_live_burn_cost_margin_eur"[^>]*>',
        html,
    )
    token = re.search(
        r'<input[^>]*name="chat_streaming_live_burn_token_margin"[^>]*>',
        html,
    )
    assert cost, "cost margin input missing"
    assert token, "token margin input missing"
    assert 'value="-0.250000000"' in cost.group(0)
    assert 'inputmode="decimal"' in cost.group(0)
    assert "disabled" in cost.group(0)
    assert 'value="-250"' in token.group(0)
    assert 'inputmode="numeric"' in token.group(0)
    assert "disabled" in token.group(0)
    assert (
        'aria-describedby="detail-chat-streaming-live-burn-hint"' in cost.group(0)
    )
    assert (
        'aria-describedby="detail-chat-streaming-live-burn-hint"' in token.group(0)
    )


def test_key_detail_renders_usage_reset_form(monkeypatch) -> None:
    key = replace(
        _detail(),
        cost_used_eur=Decimal("3.000000000"),
        tokens_used_total=30,
        requests_used_total=3,
        cost_reserved_eur=Decimal("4.000000000"),
        tokens_reserved_total=40,
        requests_reserved_total=4,
    )
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/reset-usage"' in html
    assert 'name="csrf_token" value="rendered-csrf-token"' in html
    assert 'name="confirm_reset_usage" value="true"' in html
    assert 'name="reset_reserved" value="true"' in html
    assert 'name="confirm_reset_reserved" value="true"' in html
    assert "Reserved counters normally represent in-flight quota reservations" in html
    assert "admin repair action" in html
    assert "does not delete usage ledger history" in html
    assert "Hard quota limits remain unchanged" in html
    assert "Redis rate-limit counters are not reset" in html
    # 206-a: usage readouts display grouped money and millions of
    # tokens; the exact token count stays in the title attribute.
    assert "EUR 3" in html
    assert "0.00003M tokens" in html
    assert 'title="30 tokens"' in html
    assert "3 requests" in html
    assert "EUR 4" in html
    assert "0.00004M tokens" in html
    assert 'title="40 tokens"' in html
    assert "4 requests" in html


def test_key_detail_renders_rotation_form(monkeypatch) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/rotate"' in html
    assert 'name="csrf_token" value="rendered-csrf-token"' in html
    assert 'name="confirm_rotate" value="true"' in html
    assert 'name="keep_old_active" value="true"' in html
    assert 'name="email_delivery_mode"' in html
    assert "None - show replacement once in browser" in html
    assert "lost keys cannot be resent" in html
    assert "Send-now and enqueue suppress browser plaintext display" in html
    assert "Rotate key" in html


def test_suspended_key_detail_renders_activation_form(monkeypatch) -> None:
    key = _detail(status="suspended", display_status="suspended", can_suspend=False, can_activate=True)
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/activate"' in html
    assert f'action="/admin/keys/{key.id}/suspend"' not in html
    assert f'action="/admin/keys/{key.id}/revoke"' in html


def test_revoked_key_detail_disables_lifecycle_forms(monkeypatch) -> None:
    key = replace(
        _detail(
            status="revoked",
            display_status="revoked",
            can_suspend=False,
            can_activate=False,
            can_revoke=False,
            can_rotate=False,
        ),
        revoked_at=datetime.now(UTC),
        revoked_reason="course ended",
    )
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f"/admin/keys/{key.id}/suspend" not in html
    assert f"/admin/keys/{key.id}/activate" not in html
    assert f"/admin/keys/{key.id}/revoke" not in html
    assert f"/admin/keys/{key.id}/rotate" not in html
    assert "disabled" in html


def test_key_detail_action_panel_does_not_render_sensitive_values(monkeypatch) -> None:
    settings = _settings()
    key = _detail()
    client = TestClient(_app(settings))
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert key.public_key_id in html
    assert "plaintext-key-must-not-render" not in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash_must_not_render" not in html
    assert "session-token-must-not-render" not in html
    assert "session_hash_must_not_render" not in html
    assert "resend" not in html.lower()
    assert "resend" not in html.lower()


def test_key_detail_renders_lazy_throttling_wait_values_and_usable_inputs(monkeypatch) -> None:
    key = replace(
        _detail(),
        lazy_throttling_policy={
            "mode": "wait",
            "max_wait_seconds": 45,
            "max_waiting_requests": 3,
        },
        lazy_throttling_policy_summary=(
            "Mode: wait; max wait: 45s; max waiting per key: 3; "
            "applies to Chat Completions and Responses before provider execution"
        ),
    )
    client = TestClient(
        _app(
            _settings(
                ENABLE_REDIS_RATE_LIMITS=True,
                REDIS_URL="redis://localhost:16379/0",
            )
        )
    )
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert "Mode: wait; max wait: 45s; max waiting per key: 3" in html
    assert f'action="/admin/keys/{key.id}/lazy-throttling"' in html
    assert (
        'name="lazy_throttling_mode" value="wait" data-lazy-throttling-mode '
        'aria-describedby="key-lazy-help" checked'
    ) in html
    assert (
        'value="reject" data-lazy-throttling-mode aria-describedby="key-lazy-help" checked'
    ) not in html
    assert 'name="lazy_throttling_max_wait_seconds" value="45"' in html
    assert 'name="lazy_throttling_max_waiting_requests" value="3"' in html
    # Server-rendered inputs stay usable with JS disabled (no disabled attr).
    assert "data-lazy-throttling-field disabled" not in html
    assert "data-lazy-throttling-field disabled>" not in html
    assert 'data-lazy-throttling-field aria-describedby="key-lazy-help">' in html
    assert 'name="reason" value="" required' in html
    assert "Redis rate limiting is currently disabled" not in html


def test_key_detail_renders_lazy_throttling_reject_defaults_and_inactive_warning(
    monkeypatch,
) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert "Mode: reject (immediate 429); no waiting configured" in html
    assert (
        'name="lazy_throttling_mode" value="reject" data-lazy-throttling-mode '
        'aria-describedby="key-lazy-help" checked'
    ) in html
    assert (
        'value="wait" data-lazy-throttling-mode aria-describedby="key-lazy-help" checked'
    ) not in html
    assert 'name="lazy_throttling_max_wait_seconds" value="30"' in html
    assert 'name="lazy_throttling_max_waiting_requests" value="2"' in html
    # Default settings leave Redis rate limiting off: state that honestly.
    assert "Redis rate limiting is currently disabled" in html


def test_lazy_throttling_error_redisplay_escapes_invalid_value(monkeypatch) -> None:
    called = False
    key = _detail()

    async def update_gateway_key_lazy_throttling(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_lazy_throttling",
        update_gateway_key_lazy_throttling,
    )
    client = TestClient(_app())

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(
            admin_user=SimpleNamespace(id=uuid.uuid4(), email="a@b.c"),
            admin_session=SimpleNamespace(id=uuid.uuid4()),
        )

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == "rendered-csrf-token"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client.cookies.set("slaif_admin_session", "session-token")

    marker = "<script>alert(185)</script>"
    response = client.post(
        f"/admin/keys/{key.id}/lazy-throttling",
        data={
            "csrf_token": "rendered-csrf-token",
            "lazy_throttling_mode": "wait",
            "lazy_throttling_max_wait_seconds": marker,
            "lazy_throttling_max_waiting_requests": "2",
            "reason": "invalid value",
        },
    )

    assert response.status_code == 400
    assert "positive whole number" in response.text
    assert marker not in response.text
    assert "&lt;script&gt;alert(185)&lt;/script&gt;" in response.text
    assert called is False


# --- 224-q: demo-only key read-page branches ---------------------------------
#
# These emulate the demo gate's request-local fictional admin context
# (the gate stores it on request.state before the handler runs) on top
# of the EXISTING normal read-only handlers and templates. The copy
# database seam is the same class-level fake the normal tests use;
# positive copied-row transport is owned by the 224-q owned-PG test.

Q_OP = "12345678-9abc-4def-8123-456789abcdef"


def _q_demo_page_context(monkeypatch) -> None:
    """Patch the page-context seam in BOTH admin route modules to the
    gate's request-local fictional context (no cookie read in demo)."""
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="demo-admin@example.org",
        display_name="Demo Admin",
        password_hash="password_hash_must_not_render",
        role="superadmin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session_hash_must_not_render",
        csrf_token_hash="csrf_hash_must_not_render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    context = AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def _page_context(_request):
        return context, "demo-csrf-token"

    monkeypatch.setattr(
        "slaif_gateway.api.admin._admin_page_context", _page_context
    )
    monkeypatch.setattr(
        "slaif_gateway.api.admin_key_clone._admin_page_context", _page_context
    )


def _q_norm(text: str) -> str:
    """Whitespace-normalized text (template lines wrap mid-phrase)."""
    return " ".join(text.split())


def _q_normal_session(monkeypatch) -> None:
    """The normal admin-session seam (same as _login_and_detail)."""
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="password_hash_must_not_render",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session_hash_must_not_render",
        csrf_token_hash="csrf_hash_must_not_render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )


def _q_client(monkeypatch, key: AdminKeyDetail, *, demo: bool = True) -> TestClient:
    async def get_key_detail(self, _gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    app = _app()
    if not demo:
        _q_normal_session(monkeypatch)
    else:
        _q_demo_page_context(monkeypatch)

        @app.middleware("http")
        async def _q_demo_state(request, call_next):
            # The template context processor reads this state (the
            # demo gate stores its fictional context on request.state).
            request.state.demo_admin = SimpleNamespace(nav=())
            return await call_next(request)

    @asynccontextmanager
    async def _no_lifespan(_app):
        # The fake sessionmaker stays installed (same posture as the
        # normal tests in this file): no real engine is ever built.
        yield

    app.router.lifespan_context = _no_lifespan
    return TestClient(app)


def _q_clone_runtime(monkeypatch, *, projection=None, error=None) -> None:
    """Fake the clone runtime scope: the ONLY call the receipts page
    makes is the read-only find_clone_receipt."""

    class _FakeCloneService:
        async def find_clone_receipt(self, **kwargs):
            if error is not None:
                raise error
            assert projection is not None
            return projection

    @asynccontextmanager
    async def _scope(_request):
        yield _settings(), _FakeCloneService()

    monkeypatch.setattr(
        "slaif_gateway.api.admin_key_clone._admin_key_clone_runtime_scope",
        _scope,
    )


def test_q_detail_demo_shows_admitted_read_links(monkeypatch) -> None:
    # Trusted-calibration key: the calibration read link is visible...
    key = replace(_detail(), key_purpose="trusted_calibration")
    client = _q_client(monkeypatch, key)
    r = client.get(f"/admin/keys/{key.id}")
    assert r.status_code == 200
    assert f'href="/admin/keys/{key.id}/calibration"' in r.text
    # ...with the demo snapshot warning, and the non-admitted
    # action links stay hidden in demo mode.
    assert "Demo snapshot: this key cannot authenticate requests" in _q_norm(r.text)
    assert "Codex compatibility" not in _q_norm(r.text)
    assert "Replay maintenance" not in _q_norm(r.text)
    assert "configuration.json" not in r.text
    # Standard key: clone + receipts read links with the demo note.
    std = _detail()
    client = _q_client(monkeypatch, std)
    r = client.get(f"/admin/keys/{std.id}")
    assert r.status_code == 200
    assert f'href="/admin/keys/{std.id}/clone"' in r.text
    assert f'href="/admin/keys/{std.id}/clone/receipts"' in r.text
    assert "read-only views of data frozen at snapshot time" in _q_norm(r.text)
    assert "Codex compatibility" not in _q_norm(r.text)
    assert "configuration.json" not in r.text


def test_q_detail_normal_rendering_unchanged(monkeypatch) -> None:
    # Normal admin: the non-admitted links render as before, and the
    # calibration link stays purpose-gated.
    std = _detail()
    with _q_client(monkeypatch, std, demo=False) as client:
        client.cookies.set("slaif_admin_session", "session-token-must-not-render")
        r = client.get(f"/admin/keys/{std.id}")
        assert r.status_code == 200
        assert "Codex compatibility" in _q_norm(r.text)
        assert "Replay maintenance" in _q_norm(r.text)
        assert f'href="/admin/keys/{std.id}/configuration.json"' in r.text
        assert f'href="/admin/keys/{std.id}/calibration"' not in r.text
        assert "read-only views of data frozen at snapshot time" not in _q_norm(r.text)
    trusted = replace(_detail(), key_purpose="trusted_calibration")
    with _q_client(monkeypatch, trusted, demo=False) as client:
        client.cookies.set("slaif_admin_session", "session-token-must-not-render")
        r = client.get(f"/admin/keys/{trusted.id}")
        assert r.status_code == 200
        assert f'href="/admin/keys/{trusted.id}/calibration"' in r.text


def test_q_calibration_demo_banner_and_illustrative_form(monkeypatch) -> None:
    key = replace(_detail(), key_purpose="trusted_calibration")
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/calibration")
        assert r.status_code == 200
        assert "Sanitized demo snapshot display" in _q_norm(r.text)
        assert "frozen at snapshot time" in _q_norm(r.text)
        assert "ILLUSTRATIVE" in _q_norm(r.text)
        assert "NO effect" in _q_norm(r.text)
        assert "no live configuration is read" in _q_norm(r.text)
        # The illustrative form is still rendered (no effect note only).
        assert f'action="/admin/keys/{key.id}/calibration/preview"' in r.text


def test_q_calibration_refuses_non_trusted_key(monkeypatch) -> None:
    # A copied standard key is unsupported for calibration: the
    # existing safe refusal, never a false success page.
    key = _detail()
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/calibration")
        assert r.status_code == 400
        assert "trusted calibration keys" in r.text


def test_q_clone_form_demo_banner_and_view_time_eligibility(monkeypatch) -> None:
    key = _detail()
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone")
        assert r.status_code == 200
        assert "Sanitized demo snapshot display" in _q_norm(r.text)
        assert "frozen at snapshot time" in _q_norm(r.text)
        # The eligibility line is computed at view time over the frozen
        # copied rows - NOT a historical-at-capture claim.
        assert "computed for this copied snapshot AT VIEW TIME" in _q_norm(r.text)
        assert "not a live operational eligibility decision" in _q_norm(r.text)
        assert "Eligibility:" in r.text
        assert f'action="/admin/keys/{key.id}/clone/review"' in r.text


def _q_created_projection() -> KeyCloneReceiptProjection:
    return KeyCloneReceiptProjection(
        status="created",
        source_gateway_key_id="src-" + "a" * 32,
        operation_uuid=Q_OP,
        target_gateway_key_id=str(uuid.uuid4()),
        target_public_key_id="target-public-id",
        target_owner_id=str(uuid.uuid4()),
        target_status="active",
        validity_mode="copy-source-expiry",
    )


def test_q_clone_recovery_demo_honest_outcomes(monkeypatch) -> None:
    key = _detail()
    # (a) No operation: the demo banner over the help form.
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts")
        assert r.status_code == 200
        assert "Sanitized demo snapshot display" in _q_norm(r.text)
        assert "HISTORICAL, recovered from this copy" in _q_norm(r.text)
    # (b) created: the target fields render, but the retry/rotate
    # guidance is suppressed in demo mode.
    _q_clone_runtime(monkeypatch, projection=_q_created_projection())
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts?operation={Q_OP}")
        assert r.status_code == 200
        assert "target-public-id" in r.text
        assert "one-time plaintext is never redisplayed" in _q_norm(r.text)
        assert "Retry a still-unconsumed" not in _q_norm(r.text)
        assert "rotate the key" not in _q_norm(r.text)
    # (c) not-found: the honest NOTHING-assumed wording, and the
    # normal "re-run the plan" guidance paragraph stays suppressed.
    not_found = KeyCloneReceiptProjection(
        status="not-found",
        source_gateway_key_id="src-" + "a" * 32,
        operation_uuid=Q_OP,
    )
    _q_clone_runtime(monkeypatch, projection=not_found)
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts?operation={Q_OP}")
        assert r.status_code == 200
        assert "NOTHING is assumed" in _q_norm(r.text)
        assert "If you reviewed a plan but lost the result" not in _q_norm(r.text)
    # (d) projection error: the fixed safe message with the demo
    # no-retry-guidance wording.
    _q_clone_runtime(monkeypatch, error=KeyCloneError())
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts?operation={Q_OP}")
        assert r.status_code == 200
        assert "Key clone operation failed." in r.text
        assert "no retry guidance is offered in this demo snapshot" in _q_norm(r.text)
        assert "do not start a guessed new clone" not in _q_norm(r.text)


def test_q_clone_recovery_normal_still_shows_retry_guidance(monkeypatch) -> None:
    # The normal template wording is unchanged for non-demo renders.
    key = _detail()
    _q_clone_runtime(monkeypatch, projection=_q_created_projection())
    with _q_client(monkeypatch, key, demo=False) as client:
        client.cookies.set("slaif_admin_session", "session-token-must-not-render")
        r = client.get(f"/admin/keys/{key.id}/clone/receipts?operation={Q_OP}")
        assert r.status_code == 200
        assert "Retry a still-unconsumed pending delivery" in _q_norm(r.text)
        assert "rotate the key" in _q_norm(r.text)
        assert "Sanitized demo snapshot display" not in _q_norm(r.text)


# --- 224-r: demo-only historical clone-receipt chooser ----------------------


def test_r_clone_recovery_demo_chooser_renders(monkeypatch) -> None:
    """The demo chooser renders copied operations as links, with honest
    historical / non-inference wording; the normal render is unchanged."""
    from slaif_gateway.api import admin_key_clone as _akc

    key = _detail()

    def _patch_chooser(chooser) -> None:
        async def _chooser(_request, _source_id):
            return chooser

        monkeypatch.setattr(_akc, "_demo_source_receipt_chooser", _chooser)

    op1 = str(uuid.uuid4())
    op2 = str(uuid.uuid4())

    # Positive: a finite list of copied operations renders as links (the
    # copy's own remapped ids only), with the historical (view-time) label.
    _patch_chooser(_akc._DemoReceiptChooser((op1, op2), False, True))
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts")
        assert r.status_code == 200
        assert "Historical clone operations" in _q_norm(r.text)
        assert f'href="/admin/keys/{key.id}/clone/receipts?operation={op1}"' in r.text
        assert f'href="/admin/keys/{key.id}/clone/receipts?operation={op2}"' in r.text
        assert "at most the first 100" not in _q_norm(r.text)

    # Capped: the finite bound (100) is disclosed.
    _patch_chooser(_akc._DemoReceiptChooser((op1, op2), True, True))
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts")
        assert r.status_code == 200
        assert "at most the first 100" in _q_norm(r.text)

    # Empty: the non-inference wording, no operation links.
    _patch_chooser(_akc._DemoReceiptChooser((), False, True))
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts")
        assert r.status_code == 200
        assert "No historical clone receipts are visible" in _q_norm(r.text)
        assert "does not establish whether the source had clone operations" in _q_norm(r.text)
        assert "/clone/receipts?operation=" not in r.text

    # Unavailable: the fixed safe refusal, no links, no false-empty claim.
    _patch_chooser(_akc._DemoReceiptChooser((), False, False))
    with _q_client(monkeypatch, key) as client:
        r = client.get(f"/admin/keys/{key.id}/clone/receipts")
        assert r.status_code == 200
        assert "Historical clone receipt history is unavailable in this snapshot" in _q_norm(r.text)
        assert "/clone/receipts?operation=" not in r.text

    # Normal (non-demo) render: the chooser is absent entirely.
    _patch_chooser(_akc._DemoReceiptChooser((op1, op2), False, True))
    with _q_client(monkeypatch, key, demo=False) as client:
        client.cookies.set("slaif_admin_session", "session-token-must-not-render")
        r = client.get(f"/admin/keys/{key.id}/clone/receipts")
        assert r.status_code == 200
        assert "Historical clone operations" not in _q_norm(r.text)
        assert "/clone/receipts?operation=" not in r.text


def _kr_real_rows(ops: tuple[str, ...]) -> list[object]:
    """Real SQLAlchemy 2.0 Row objects for the chooser fake.

    The gate-validated copy session returns ``sqlalchemy.engine.Row``
    (never dicts); SQLAlchemy 2.0 removed string subscripting from Row,
    so the fake must exercise the exact API surface the production
    chooser receives (an in-memory stdlib-sqlite engine produces the
    same Row class the asyncpg stack returns).
    """
    from sqlalchemy import create_engine, text

    if not ops:
        return []
    eng = create_engine("sqlite://")
    try:
        with eng.connect() as conn:
            clauses = " UNION ALL ".join(
                f"SELECT :op{i} AS op" for i in range(len(ops))
            )
            return list(
                conn.execute(
                    text(clauses), {f"op{i}": op for i, op in enumerate(ops)}
                ).all()
            )
    finally:
        eng.dispose()


class _KrChooserResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class _KrChooserSession:
    def __init__(self, *, current_db, ro, ops=(), exc=False) -> None:
        self._current_db = current_db
        self._ro = ro
        self._ops = ops
        self._exc = exc

    def begin(self):
        @asynccontextmanager
        async def _begin():
            yield

        return _begin()

    async def scalar(self, stmt) -> object:
        s = str(stmt)
        if "current_database" in s:
            return self._current_db
        if "transaction_read_only" in s:
            return self._ro
        return None

    async def execute(self, stmt, params):
        if self._exc:
            raise RuntimeError("chooser query failed")
        return _KrChooserResult(_kr_real_rows(self._ops))


def _kr_chooser_request(sessionmaker, *, target_db="copydb") -> object:
    from starlette.requests import Request

    from slaif_gateway.demo_web import _demo_display_settings

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin/keys/x/clone/receipts",
        "root_path": "",
        "headers": [],
        "query_string": b"",
        "server": ("demo.test", 443),
        "client": ("127.0.0.1", 1234),
        "app": SimpleNamespace(
            state=SimpleNamespace(
                demo_mode=True, settings=_demo_display_settings()
            )
        ),
    }
    if sessionmaker is not _SENTINEL_NO_ADMIN:
        scope["state"] = {
            "demo_admin": SimpleNamespace(
                target_db=target_db,
                sessionmaker=sessionmaker,
            )
        }
    return Request(scope)


_SENTINEL_NO_ADMIN = object()


def _kr_chooser_factory(session: _KrChooserSession):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def test_r_demo_source_receipt_chooser_law() -> None:
    from slaif_gateway.api import admin_key_clone as _akc

    # Normal (no demo_admin): no copy query, reported available.
    req = _kr_chooser_request(_SENTINEL_NO_ADMIN)
    assert asyncio.run(
        _akc._demo_source_receipt_chooser(req, uuid.UUID(int=1))
    ) == _akc._DemoReceiptChooser((), False, True)

    op1, op2, op3 = (str(uuid.uuid4()) for _ in range(3))

    # A refused read-only recheck is a fixed safe refusal (available=False).
    req = _kr_chooser_request(
        _kr_chooser_factory(_KrChooserSession(current_db="copydb", ro="off"))
    )
    assert asyncio.run(
        _akc._demo_source_receipt_chooser(req, uuid.UUID(int=1))
    ) == _akc._DemoReceiptChooser((), False, False)

    # A wrong current database is a fixed safe refusal.
    req = _kr_chooser_request(
        _kr_chooser_factory(
            _KrChooserSession(current_db="other_db", ro="on", ops=(op1,))
        )
    )
    assert asyncio.run(
        _akc._demo_source_receipt_chooser(req, uuid.UUID(int=1))
    ) == _akc._DemoReceiptChooser((), False, False)

    # Happy path: copied operations are returned (newest order preserved).
    req = _kr_chooser_request(
        _kr_chooser_factory(
            _KrChooserSession(current_db="copydb", ro="on", ops=(op1, op2, op3))
        )
    )
    assert asyncio.run(
        _akc._demo_source_receipt_chooser(req, uuid.UUID(int=1))
    ) == _akc._DemoReceiptChooser((op1, op2, op3), False, True)

    # A failed copy query is a fixed safe refusal (never a silent empty).
    req = _kr_chooser_request(
        _kr_chooser_factory(
            _KrChooserSession(current_db="copydb", ro="on", exc=True)
        )
    )
    assert asyncio.run(
        _akc._demo_source_receipt_chooser(req, uuid.UUID(int=1))
    ) == _akc._DemoReceiptChooser((), False, False)

    # A demo_admin without a usable sessionmaker fails closed (available=False).
    from starlette.requests import Request

    from slaif_gateway.demo_web import _demo_display_settings

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin/keys/x/clone/receipts",
        "root_path": "",
        "headers": [],
        "query_string": b"",
        "server": ("demo.test", 443),
        "client": ("127.0.0.1", 1234),
        "app": SimpleNamespace(
            state=SimpleNamespace(
                demo_mode=True, settings=_demo_display_settings()
            )
        ),
        "state": {"demo_admin": SimpleNamespace(target_db="copydb")},
    }
    assert asyncio.run(
        _akc._demo_source_receipt_chooser(Request(scope), uuid.UUID(int=1))
    ) == _akc._DemoReceiptChooser((), False, False)

    # The bounded cap: 101 operations -> 100 returned and capped=True.
    many = tuple(str(uuid.uuid4()) for _ in range(101))
    req = _kr_chooser_request(
        _kr_chooser_factory(
            _KrChooserSession(current_db="copydb", ro="on", ops=many)
        )
    )
    result = asyncio.run(
        _akc._demo_source_receipt_chooser(req, uuid.UUID(int=1))
    )
    assert result.available is True
    assert result.capped is True
    assert len(result.operations) == 100
    assert result.operations == many[:100]
