"""210-a GUI reviewed route configuration + provider preparation (unit).

Fake-persistence ASGI/Jinja seams over the real admin app:

- the NEW reviewed route-configuration router (GET form, READ-ONLY plan,
  purpose-bound token, apply) with the shared services faked at the
  module seam while the REAL pure preview and REAL review-intent
  builder/verifier run for real;
- the 210-a provider CREATE/EDIT additions (prepare-disabled default,
  notes intents, known-shape secret refusals before any write, lock
  ordering) and the provider detail display projection;
- the legacy route form refusal re-display privacy law (advanced
  capabilities bytes blanked, retained free-form values redacted);
- the route CREATE intent (sole activation control; legacy checkbox
  semantics preserved; the shared read-only creation validation runs
  in the caller transaction before the write).

No database, no network, no credential loading: the core
configuration/transaction law (199) stays authoritative and is not
re-proved here.
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api import admin as admin_mod
from slaif_gateway.api import admin_provider_route_configuration as cfg
from slaif_gateway.api.admin_review_intent import (
    build_batch_review_token,
    build_route_review_token,
)
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.schemas.admin_catalog import AdminProviderDetail
from slaif_gateway.schemas.key_batch import render_key_batch_plan
from slaif_gateway.schemas.provider_route_configuration import (
    ProviderRouteConfigError,
    ProviderRouteStaleError,
    render_route_update_plan,
)
from slaif_gateway.services.admin_session_service import AdminSessionService
from slaif_gateway.services.provider_route_configuration import (
    preview_route_update,
)

from tests.unit.test_admin_key_actions_routes import _app, _settings
from tests.unit.test_admin_key_batch_209 import _make_plan as _make_batch_plan
from tests.unit.test_provider_route_configuration import (
    FakeProviderRow,
    FakeRouteRow,
)

ADMIN_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
SESSION_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
OTHER_ADMIN_ID = uuid.UUID("cccccccc-0000-4000-8000-000000000003")

# Recognized credential shape (199 law: "Bearer <token>" is refused).
CANARY = "Bearer abcdef1234567890canary"
CANARY_MASKED = "Bearer ***"


class _State:
    """Per-test fake persistence + call record."""

    def __init__(self) -> None:
        self.route = FakeRouteRow()
        self.provider_row = FakeProviderRow()
        self.preview_calls: list[dict[str, Any]] = []
        self.preview_exc: BaseException | None = None
        self.execute_calls: list[dict[str, Any]] = []
        self.execute_exc: BaseException | None = None
        self.execute_noop = False
        self.validate_calls: list[dict[str, Any]] = []
        self.validate_exc: BaseException | None = None
        self.route_create_calls: list[dict[str, Any]] = []
        self.route_update_calls: list[dict[str, Any]] = []
        self.audit_calls: list[dict[str, Any]] = []
        self.provider_create_calls: list[dict[str, Any]] = None  # set per test
        self.provider_update_calls: list[dict[str, Any]] = None
        self.provider_lock_calls: list[str] = None


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
        from slaif_gateway.services.admin_session_service import (
            AdminSessionContext,
        )

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

    # --- reviewed route-config router seams (module namespace) --------
    class _RoutesRepo:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def get_model_route_by_id(self, route_id: uuid.UUID) -> Any:
            return state.route

    class _ProvidersRepo:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def get_provider_config_by_provider(self, provider: str) -> Any:
            if provider != state.provider_row.provider:
                return None
            return state.provider_row

    async def fake_preview(
        session: Any,
        route_id: str,
        external_tool_ceilings: Any = None,
        profile_dir: str = "",
        **edits: Any,
    ) -> Any:
        state.preview_calls.append(dict(edits))
        if state.preview_exc is not None:
            raise state.preview_exc
        return preview_route_update(
            state.route, state.provider_row, external_tool_ceilings=external_tool_ceilings,
            profile_dir=profile_dir, **edits,
        )

    def _row_from_proposed(plan: Any) -> Any:
        document = render_route_update_plan(plan)
        proposed = document.get("preview", {}).get("proposed_configuration") or {}
        row = dataclasses.replace(
            state.route,
            requested_model=proposed.get("requested_model", state.route.requested_model),
            match_type=proposed.get("match_type", state.route.match_type),
            endpoint=proposed.get("endpoint", state.route.endpoint),
            provider=proposed.get("provider", state.route.provider),
            upstream_model=proposed.get("upstream_model", state.route.upstream_model),
            priority=proposed.get("priority", state.route.priority),
            visible_in_models=proposed.get(
                "visible_in_models", state.route.visible_in_models
            ),
            supports_streaming=proposed.get(
                "supports_streaming", state.route.supports_streaming
            ),
            enabled=proposed.get("enabled", state.route.enabled),
            notes=proposed.get("notes", state.route.notes),
        )
        caps = proposed.get("capabilities")
        if caps is not None:
            row = dataclasses.replace(row, capabilities=caps)
        return row

    async def fake_execute(
        session: Any,
        plan: Any,
        reason: str = "",
        external_tool_ceilings: Any = None,
        profile_dir: str = "",
        actor_admin_id: Any = None,
    ) -> Any:
        state.execute_calls.append(
            {
                "plan": plan,
                "reason": reason,
                "actor_admin_id": actor_admin_id,
            }
        )
        if state.execute_exc is not None:
            raise state.execute_exc
        if state.execute_noop:
            return state.route
        return _row_from_proposed(plan)

    async def fake_choices(request: Any, form: Any) -> dict[str, Any]:
        from slaif_gateway.services.admin_record_choices import RecordChoice

        return {
            "provider": [
                RecordChoice(id=state.provider_row.provider, label=state.provider_row.provider)
            ],
            "requested_model": [],
            "upstream_model": [],
            "endpoint": [],
            "completion_profile": [],
        }

    monkeypatch.setattr(cfg, "ModelRoutesRepository", _RoutesRepo)
    monkeypatch.setattr(cfg, "ProviderConfigsRepository", _ProvidersRepo)
    monkeypatch.setattr(cfg, "preview_route_update_for_route", fake_preview)
    monkeypatch.setattr(cfg, "execute_route_update_plan", fake_execute)
    monkeypatch.setattr(cfg, "_route_config_form_choices", fake_choices)

    # --- admin.py route/provider seams (module namespace) --------------
    async def fake_route_provider_choices(request: Any) -> list[Any]:
        # the real loader returns provider list rows (with .provider slug)
        from types import SimpleNamespace

        return [
            SimpleNamespace(
                id=state.provider_row.provider, provider=state.provider_row.provider
            )
        ]

    class _AdminRoutesRepo:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def create_model_route(self, **kwargs: Any) -> Any:
            state.route_create_calls.append(dict(kwargs))
            return dataclasses.replace(state.route, id=str(uuid.uuid4()))

        async def update_model_route(self, route_id: Any, **kwargs: Any) -> Any:
            state.route_update_calls.append({"route_id": route_id, **kwargs})
            return state.route

    class _AuditRepo:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def add_audit_log(self, **kwargs: Any) -> None:
            state.audit_calls.append(dict(kwargs))

    async def fake_validate_candidate(session: Any, **kwargs: Any) -> None:
        state.validate_calls.append(dict(kwargs))
        if state.validate_exc is not None:
            raise state.validate_exc

    class _ProviderService:
        def __init__(self, provider_configs_repository: Any, audit_repository: Any) -> None:
            pass

        async def create_provider_config(self, **kwargs: Any) -> Any:
            assert state.provider_create_calls is not None
            state.provider_create_calls.append(dict(kwargs))
            return dataclasses.replace(state.provider_row, provider=kwargs["provider"])

        async def update_provider_config(self, provider_id: str, **kwargs: Any) -> Any:
            assert state.provider_update_calls is not None
            state.provider_update_calls.append(dict(kwargs))
            return dataclasses.replace(state.provider_row, id=uuid.UUID(provider_id))

    monkeypatch.setattr(admin_mod, "_load_route_provider_choices", fake_route_provider_choices)
    monkeypatch.setattr(admin_mod, "ModelRoutesRepository", _AdminRoutesRepo)
    monkeypatch.setattr(admin_mod, "AuditRepository", _AuditRepo)
    monkeypatch.setattr(admin_mod, "validate_route_creation_candidate", fake_validate_candidate)
    monkeypatch.setattr(admin_mod, "ProviderConfigService", _ProviderService)

    class _AdminProvidersRepo:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def get_provider_config_for_update(self, provider_or_id: Any) -> Any:
            assert state.provider_lock_calls is not None
            state.provider_lock_calls.append(str(provider_or_id))
            if provider_or_id in (
                state.provider_row.provider,
                str(state.provider_row.id),
            ):
                return state.provider_row
            return None

    monkeypatch.setattr(admin_mod, "ProviderConfigsRepository", _AdminProvidersRepo)

    tc = TestClient(app)
    tc.cookies.set("slaif_admin_session", "session-plaintext")
    return tc


def _settings_with_profile_dir() -> Any:
    return _settings(COMPLETION_SERVICE_PROFILE_DIR="/tmp/slaif210-profiles")


def _token_from_html(html: str) -> str:
    match = re.search(
        r'name="route_config_review_intent" value="([^"]+)"', html
    )
    assert match is not None, "review token hidden input missing"
    return match.group(1)


# ---------------------------------------------------------------------------
# GET form
# ---------------------------------------------------------------------------


class TestRouteConfigurationFormGet:
    def test_get_renders_current_route_state(self, client: TestClient) -> None:
        response = client.get(f"/admin/routes/{state_route_id()}/configuration")
        assert response.status_code == 200
        html = response.text
        assert "zap-it-1" in html  # requested model (FakeRouteRow default)
        assert "route notes" in html  # notes_current projection
        assert 'id="key-clone-heading"' not in html  # sanity: not another page

    def test_get_unknown_route_404(self, client: TestClient, state: _State) -> None:
        state.route = None  # type: ignore[assignment]
        response = client.get(f"/admin/routes/{state_route_id()}/configuration")
        assert response.status_code == 404
        assert "Model route not found" in response.text


def state_route_id() -> str:
    return str(uuid.UUID("11111111-2222-4333-8444-555555555555"))


# ---------------------------------------------------------------------------
# POST plan (READ ONLY)
# ---------------------------------------------------------------------------


def _plan_post(client: TestClient, **extra: Any) -> Any:
    payload = {
        "csrf_token": "dashboard-csrf",
        "capabilities_source": extra.pop("capabilities_source", "unchanged"),
        "requested_model_action": "unchanged",
        "match_type_action": "unchanged",
        "endpoint_action": "unchanged",
        "provider_action": "unchanged",
        "upstream_model_action": "unchanged",
        "priority_action": "unchanged",
        "visible_in_models_action": "unchanged",
        "supports_streaming_action": "unchanged",
        "notes_intent": "preserve",
        "codex_context_action": "unchanged",
        "codex_default_output_action": "unchanged",
        "codex_max_output_action": "unchanged",
        "media_image_action": "unchanged",
        "media_video_tokens_action": "unchanged",
        "media_video_frames_action": "unchanged",
        "completion_action": "unchanged",
    }
    payload.update(extra)
    return client.post(
        f"/admin/routes/{state_route_id()}/configuration/plan", data=payload
    )


class TestRouteConfigurationPlan:
    def test_unchanged_source_renders_review_with_token(self, client: TestClient, state: _State) -> None:
        response = _plan_post(client)
        assert response.status_code == 200
        assert "no-store" in response.headers.get("cache-control", "").lower()
        token = _token_from_html(response.text)
        assert len(token) > 100
        assert len(state.preview_calls) == 1
        assert state.execute_calls == []

    def test_guided_leaf_change_renders_diff(self, client: TestClient, state: _State) -> None:
        response = _plan_post(
            client,
            capabilities_source="guided",
            codex_max_output_action="set",
            codex_max_output_value="100000",
            priority_action="set",
            priority="50",
        )
        assert response.status_code == 200, response.text
        assert _token_from_html(response.text)
        html = response.text
        # readable diff: the changed canonical values are shown
        assert "100000" in html
        assert "50" in html
        # the signed token embeds the reviewed plan (booleans only here)
        assert state.preview_calls[-1].get("capability_patch") is not None

    def test_full_document_replacement_renders_review(self, client: TestClient, state: _State) -> None:
        import json as _json

        document = _json.dumps(
            {
                "schema_version": 1,
                "capabilities": {
                    "chat_completions": {
                        "chat_text": True,
                        "chat_streaming": True,
                        "chat_function_tools": False,
                    },
                    "codex_limits": {
                        "context_window_tokens": 1050000,
                        "default_max_output_tokens": 32768,
                        "max_output_tokens": 128000,
                    },
                },
            }
        )
        response = _plan_post(
            client,
            capabilities_source="full",
            capabilities_document=document,
        )
        assert response.status_code == 200, response.text
        assert _token_from_html(response.text)
        assert state.preview_calls[-1].get("capabilities_document") is not None


def _reviewed_token(state: _State, **plan_extra: Any) -> str:
    """Build one REAL purpose-bound token over the REAL pure preview."""
    edits = dict(plan_extra)
    plan = preview_route_update(
        state.route, state.provider_row, **edits
    )
    document = render_route_update_plan(plan)
    settings = _settings()
    return build_route_review_token(
        admin_session_secret=settings.ADMIN_SESSION_SECRET,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        plan_document=document,
        route_target=state_route_id(),
        external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
        profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
    )


def _apply_post(
    client: TestClient,
    token: str,
    *,
    confirm: bool = True,
    reason: str = "reviewed route change",
    route_id: str | None = None,
    csrf: str = "dashboard-csrf",
) -> Any:
    payload: dict[str, str] = {
        "csrf_token": csrf,
        "route_config_review_intent": token,
        "reason": reason,
    }
    if confirm:
        payload["confirm_apply"] = "true"
    return client.post(
        f"/admin/routes/{route_id or state_route_id()}/configuration/apply",
        data=payload,
    )


class TestRouteConfigurationApply:
    def test_valid_apply_records_applied_result(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        response = _apply_post(client, token)
        assert response.status_code == 200
        html = response.text
        assert "The reviewed plan was applied" in html
        assert len(state.execute_calls) == 1
        call = state.execute_calls[0]
        assert call["reason"] == "reviewed route change"
        assert call["actor_admin_id"] == ADMIN_ID
        # the token is reviewed data, never retained on the result page
        assert token not in html
        assert 'name="route_config_review_intent"' not in html

    def test_zero_diff_plan_is_noop(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state)  # no edits: zero-diff plan
        response = _apply_post(client, token)
        assert response.status_code == 200
        assert "zero-diff no-op" in response.text
        assert len(state.execute_calls) == 1

    def test_missing_confirm_refused(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        response = _apply_post(client, token, confirm=False)
        assert response.status_code == 400
        assert "Confirm the reviewed route configuration plan" in response.text
        assert state.execute_calls == []

    def test_missing_reason_refused(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        response = _apply_post(client, token, reason="")
        assert response.status_code == 400
        assert "Enter an audit reason" in response.text
        assert state.execute_calls == []

    def test_overlong_reason_refused_before_execution(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        response = _apply_post(client, token, reason="r" * 513)
        assert response.status_code == 400
        assert "Audit reason is too long" in response.text
        assert state.execute_calls == []

    def test_512_char_reason_accepted(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        response = _apply_post(client, token, reason="r" * 512)
        assert response.status_code == 200
        assert len(state.execute_calls) == 1
        assert state.execute_calls[0]["reason"] == "r" * 512

    def test_tampered_token_refused(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        # flip the last digest character
        tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
        response = _apply_post(client, tampered)
        assert response.status_code == 400
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_malformed_token_refused(self, client: TestClient, state: _State) -> None:
        response = _apply_post(client, "not-a-valid-token")
        assert response.status_code == 400
        assert "missing or invalid" in response.text
        assert state.execute_calls == []

    def test_expired_token_refused(self, client: TestClient, state: _State) -> None:
        plan = preview_route_update(state.route, state.provider_row, priority=50)
        document = render_route_update_plan(plan)
        settings = _settings()
        token = build_route_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            plan_document=document,
            route_target=state_route_id(),
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
            now=datetime.now(UTC) - timedelta(hours=1),
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        assert "has expired" in response.text
        assert state.execute_calls == []

    def test_wrong_route_target_refused(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        other = str(uuid.uuid4())
        response = _apply_post(client, token, route_id=other)
        assert response.status_code == 400
        # a valid token for one route is never valid for another route URL
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_wrong_actor_refused(self, client: TestClient, state: _State, monkeypatch) -> None:
        token = _reviewed_token(state, priority=50)

        other_admin = AdminUser(
            id=OTHER_ADMIN_ID,
            email="other@example.org",
            display_name="Other Admin",
            password_hash="argon2-hash",
            role="admin",
            is_active=True,
        )
        other_session = AdminSession(
            id=SESSION_ID,
            admin_user_id=OTHER_ADMIN_ID,
            session_token_hash="sha256:session",
            csrf_token_hash="sha256:csrf",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        other_session.admin_user = other_admin

        async def validate_admin_session(self, **kwargs):
            from slaif_gateway.services.admin_session_service import (
                AdminSessionContext,
            )

            return AdminSessionContext(
                admin_user=other_admin, admin_session=other_session
            )

        monkeypatch.setattr(
            AdminSessionService, "validate_admin_session", validate_admin_session
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_cross_purpose_batch_token_refused(self, client: TestClient, state: _State) -> None:
        settings = _settings()
        batch_document = render_key_batch_plan(_make_batch_plan())
        token = build_batch_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            plan_document=batch_document,
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        # a different signed purpose is refused, never executed
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_cross_purpose_compatibility_token_refused(
        self, client: TestClient, state: _State
    ) -> None:
        # 212-a: a validly signed Codex-compatibility review token is a
        # different signed purpose: the route-configuration verifier
        # refuses it and the plan never executes.
        from slaif_gateway.api.admin_review_intent import (
            build_compatibility_review_token,
        )
        from tests.unit.test_admin_compatibility_212 import _module_review_doc

        settings = _settings()
        token = build_compatibility_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            review_document=_module_review_doc(
                operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
            ),
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        # a different signed purpose is refused, never executed
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_cross_purpose_replay_token_refused(
        self, client: TestClient, state: _State
    ) -> None:
        # 213-a: a validly signed replay-maintenance review token is a
        # different signed purpose: the route-configuration verifier
        # refuses it and the plan never executes.
        import uuid as _uuid

        from slaif_gateway.api.admin_review_intent import (
            build_replay_review_token,
        )
        from slaif_gateway.schemas.codex_replay_maintenance import ReplayScope
        from tests.unit.test_admin_replay_maintenance_213 import _review_doc

        settings = _settings()
        token = build_replay_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            review_document=_review_doc(
                scope=ReplayScope(
                    key_id=_uuid.UUID("cccccccc-0000-4000-8000-000000000003")
                )
            ),
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        # a different signed purpose is refused, never executed
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_stale_provider_context_refused(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        state.execute_exc = ProviderRouteStaleError(
            "The destination provider configuration no longer matches "
            "the reviewed plan."
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        assert "no longer matches" in response.text
        assert "The reviewed plan was applied" not in response.text


# ---------------------------------------------------------------------------
# POST plan: fixed refusals + privacy
# ---------------------------------------------------------------------------


class TestRouteConfigurationPlanRefusals:
    def test_dual_source_refused_and_document_blanked(self, client: TestClient, state: _State) -> None:
        import json as _json

        document = _json.dumps(
            {
                "schema_version": 1,
                "capabilities": {
                    "chat_completions": {
                        "chat_text": True,
                        "chat_streaming": True,
                        "chat_function_tools": False,
                    },
                },
                "audit": CANARY,
            }
        )
        response = _plan_post(
            client,
            capabilities_source="guided",
            codex_max_output_action="set",
            codex_max_output_value="100000",
            capabilities_document=document,
        )
        assert response.status_code == 400
        assert "single" in response.text.lower() or "both" in response.text.lower()
        # the complete document is blanked before the rerender
        assert CANARY not in response.text
        assert state.preview_calls == []
        assert state.execute_calls == []

    def test_unknown_action_refused_with_fixed_message(self, client: TestClient, state: _State) -> None:
        response = _plan_post(client, priority_action="bogus")
        assert response.status_code == 400
        assert "Priority" in response.text or "priority" in response.text
        assert "try again" not in response.text
        assert state.preview_calls == []

    def test_bad_capability_leaf_value_refused(self, client: TestClient, state: _State) -> None:
        response = _plan_post(
            client,
            capabilities_source="guided",
            codex_max_output_action="set",
            codex_max_output_value="abc",
        )
        assert response.status_code == 400
        assert state.preview_calls == []

    def test_notes_clear_with_text_refused(self, client: TestClient, state: _State) -> None:
        response = _plan_post(client, notes_intent="clear", notes="keep me")
        assert response.status_code == 400
        assert "clear" in response.text.lower()
        assert state.preview_calls == []

    def test_notes_canary_reaches_shared_validator_without_echo(self, client: TestClient, state: _State) -> None:
        response = _plan_post(client, notes_intent="replace", notes=CANARY)
        assert response.status_code == 400
        # the SHARED validator refuses (field named, value never echoed)
        assert "notes" in response.text.lower()
        assert "credential" in response.text.lower()
        assert CANARY not in response.text
        assert len(state.preview_calls) == 1
        assert state.execute_calls == []

    def test_retry_rerender_keeps_fresh_route_state(self, client: TestClient, state: _State) -> None:
        state.route = dataclasses.replace(state.route, notes="original-route-notes")
        response = _plan_post(client, notes_intent="bogus")
        assert response.status_code == 400
        # the read-only current projection still comes from the route
        assert "original-route-notes" in response.text
        assert "Notes intent must be preserve, replace, or clear" in response.text

    def test_unknown_destination_provider_refused(self, client: TestClient, state: _State) -> None:
        response = _plan_post(client, provider_action="set", provider="nope")
        assert response.status_code == 400
        assert "Select a known provider config" in response.text
        assert state.preview_calls == []


# ---------------------------------------------------------------------------
# Route CREATE intent (210-a admin.py additions)
# ---------------------------------------------------------------------------


def _route_create_post(client: TestClient, **extra: Any) -> Any:
    payload = {
        "csrf_token": "dashboard-csrf",
        "requested_model": "new-model-1",
        "match_type": "exact",
        "endpoint": "chat.completions",
        "provider": "mod-a",
        "upstream_model": "",
        "priority": "100",
        "capabilities": "",
        "notes": "",
        "reason": "add reviewed route",
    }
    payload.update(extra)
    return client.post("/admin/routes/new", data=payload, follow_redirects=False)


CAPS_JSON = (
    '{"chat_completions": {"chat_text": true, "chat_streaming": true, '
    '"chat_function_tools": false}}'
)


class TestRouteCreateIntent:
    def test_automatic_empty_capabilities_enables(self, client: TestClient, state: _State) -> None:
        response = _route_create_post(client, creation_intent="automatic")
        assert response.status_code == 303
        assert len(state.validate_calls) == 1
        assert state.validate_calls[0]["enabled"] is True
        assert len(state.route_create_calls) == 1
        assert state.route_create_calls[0]["enabled"] is True
        assert len(state.audit_calls) == 1

    def test_automatic_with_capabilities_prepares_disabled(self, client: TestClient, state: _State) -> None:
        response = _route_create_post(client, creation_intent="automatic", capabilities=CAPS_JSON)
        assert response.status_code == 303
        assert state.validate_calls[0]["enabled"] is False
        assert state.route_create_calls[0]["enabled"] is False

    def test_prepare_disabled(self, client: TestClient, state: _State) -> None:
        response = _route_create_post(client, creation_intent="prepare_disabled")
        assert response.status_code == 303
        assert state.route_create_calls[0]["enabled"] is False

    def test_explicit_enable_with_capabilities(self, client: TestClient, state: _State) -> None:
        response = _route_create_post(
            client, creation_intent="explicit_enable", capabilities=CAPS_JSON, enabled="true"
        )
        assert response.status_code == 303
        # the checkbox submitted alongside is ignored, the intent decides
        assert state.route_create_calls[0]["enabled"] is True

    def test_bogus_intent_refused_before_validation(self, client: TestClient, state: _State) -> None:
        response = _route_create_post(client, creation_intent="bogus")
        assert response.status_code == 400
        assert "intent" in response.text.lower()
        assert state.validate_calls == []
        assert state.route_create_calls == []
        assert state.audit_calls == []

    def test_legacy_checkbox_semantics_preserved(self, client: TestClient, state: _State) -> None:
        # NO creation_intent field: the legacy enabled checkbox wins
        response = _route_create_post(client, enabled="true")
        assert response.status_code == 303
        assert state.route_create_calls[0]["enabled"] is True
        assert state.validate_calls == []

    def test_legacy_no_checkbox_disabled(self, client: TestClient, state: _State) -> None:
        response = _route_create_post(client)
        assert response.status_code == 303
        assert state.route_create_calls[0]["enabled"] is False
        assert state.validate_calls == []

    def test_validation_refusal_writes_nothing(self, client: TestClient, state: _State) -> None:
        state.validate_exc = ProviderRouteConfigError(
            "The selected provider configuration is missing."
        )
        response = _route_create_post(client, creation_intent="automatic")
        assert response.status_code == 400
        assert "The selected provider configuration is missing." in response.text
        assert state.route_create_calls == []
        assert state.audit_calls == []

    def test_validation_uses_actual_ceilings_and_profile_dir(self, client: TestClient, state: _State, monkeypatch) -> None:
        app = _app(_settings_with_profile_dir())
        from tests.unit.test_admin_key_actions_routes import _FakeSessionmaker

        app.state.db_sessionmaker = _FakeSessionmaker()
        tc = TestClient(app)
        tc.cookies.set("slaif_admin_session", "session-plaintext")
        response = _route_create_post(tc, creation_intent="automatic")
        assert response.status_code == 303
        call = state.validate_calls[0]
        assert call["profile_dir"] == "/tmp/slaif210-profiles"
        settings = _settings_with_profile_dir()
        assert call["external_tool_ceilings"] == settings.get_external_tool_operator_ceilings()


# ---------------------------------------------------------------------------
# Provider CREATE / EDIT (210-a admin.py additions)
# ---------------------------------------------------------------------------


def _provider_create_post(client: TestClient, **extra: Any) -> Any:
    payload = {
        "csrf_token": "dashboard-csrf",
        "provider": "mod-b",
        "display_name": "Mod B",
        "kind": "openai_compatible",
        "base_url": "https://svc-b.example/v1",
        "api_key_env_var": "SVC_B_KEY",
        "timeout_seconds": "300",
        "max_retries": "2",
        "notes": "",
        "reason": "add provider",
    }
    payload.update(extra)
    return client.post("/admin/providers/new", data=payload, follow_redirects=False)


def _provider_edit_post(client: TestClient, provider_id: str, **extra: Any) -> Any:
    payload = {
        "csrf_token": "dashboard-csrf",
        "provider": "mod-a",
        "display_name": "Mod A",
        "kind": "openai_compatible",
        "base_url": "https://svc-a.example/v1",
        "api_key_env_var": "SVC_A_KEY",
        "enabled": "true",
        "timeout_seconds": "30",
        "max_retries": "0",
        "notes": "",
        "notes_intent": "preserve",
        "reason": "update provider",
    }
    payload.update(extra)
    return client.post(
        f"/admin/providers/{provider_id}/edit", data=payload, follow_redirects=False
    )


class TestProviderCreate:
    def test_default_form_prepares_disabled(self, client: TestClient) -> None:
        response = client.get("/admin/providers/new")
        assert response.status_code == 200
        assert 'name="enabled" checked' not in response.text
        assert "prepare" in response.text.lower() or "disabled" in response.text.lower()

    def test_valid_create_prepares_disabled_by_default(self, client: TestClient, state: _State) -> None:
        state.provider_create_calls = []
        response = _provider_create_post(client, notes="fresh notes")
        assert response.status_code == 303
        call = state.provider_create_calls[0]
        assert call["enabled"] is False
        assert call["notes"] == "fresh notes"  # replace (legacy default)

    def test_enabled_checked_still_works(self, client: TestClient, state: _State) -> None:
        state.provider_create_calls = []
        response = _provider_create_post(client, enabled="true")
        assert response.status_code == 303
        assert state.provider_create_calls[0]["enabled"] is True

    def test_notes_canary_refused_before_write(self, client: TestClient, state: _State) -> None:
        state.provider_create_calls = []
        response = _provider_create_post(client, notes=CANARY)
        assert response.status_code == 400
        assert "notes: value must not contain recognized credential patterns." in response.text
        assert CANARY not in response.text
        assert state.provider_create_calls == []

    def test_display_name_canary_refused_before_write(self, client: TestClient, state: _State) -> None:
        state.provider_create_calls = []
        response = _provider_create_post(client, display_name=CANARY)
        assert response.status_code == 400
        assert "display_name: value must not contain recognized credential patterns." in response.text
        assert CANARY not in response.text
        assert state.provider_create_calls == []


class TestProviderEdit:
    def test_lock_then_update_order(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(client, str(state.provider_row.id))
        assert response.status_code == 303
        assert state.provider_lock_calls == [str(state.provider_row.id)]
        assert len(state.provider_update_calls) == 1

    def test_preserve_blank_keeps_notes(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(client, str(state.provider_row.id), notes_intent="preserve")
        assert response.status_code == 303
        call = state.provider_update_calls[0]
        assert call["notes"] is None
        assert call["clear_notes"] is False

    def test_replace_blank_keeps_notes_service_semantics(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(client, str(state.provider_row.id), notes_intent="replace")
        assert response.status_code == 303
        call = state.provider_update_calls[0]
        # blank replacement is NOT an implicit clear (the GUI law)
        assert call["notes"] is None
        assert call["clear_notes"] is False

    def test_replace_with_text_replaces(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(
            client, str(state.provider_row.id), notes_intent="replace", notes="new notes"
        )
        assert response.status_code == 303
        call = state.provider_update_calls[0]
        assert call["notes"] == "new notes"
        assert call["clear_notes"] is False

    def test_clear_blank_clears_notes(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(client, str(state.provider_row.id), notes_intent="clear")
        assert response.status_code == 303
        call = state.provider_update_calls[0]
        assert call["notes"] is None
        assert call["clear_notes"] is True

    def test_clear_with_text_refused_before_lock(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(
            client, str(state.provider_row.id), notes_intent="clear", notes="keep me"
        )
        assert response.status_code == 400
        assert "clearing" in response.text.lower() or "clear" in response.text.lower()
        assert state.provider_lock_calls == []
        assert state.provider_update_calls == []

    def test_notes_canary_refused_before_lock(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(
            client, str(state.provider_row.id), notes_intent="replace", notes=CANARY
        )
        assert response.status_code == 400
        assert "notes: value must not contain recognized credential patterns." in response.text
        assert CANARY not in response.text
        assert state.provider_lock_calls == []
        assert state.provider_update_calls == []

    def test_missing_provider_404(self, client: TestClient, state: _State) -> None:
        state.provider_update_calls = []
        state.provider_lock_calls = []
        response = _provider_edit_post(client, str(uuid.uuid4()))
        assert response.status_code == 404
        assert state.provider_update_calls == []


# ---------------------------------------------------------------------------
# Provider DETAIL display projection
# ---------------------------------------------------------------------------


def _provider_detail_row(**overrides: Any) -> AdminProviderDetail:
    base: dict[str, Any] = {
        "id": uuid.UUID("dddddddd-0000-4000-8000-000000000004"),
        "provider": "mod-a",
        "display_name": "Mod A",
        "kind": "openai_compatible",
        "enabled": False,
        "base_url": "https://svc-a.example/v1",
        "api_key_env_var": "SVC_A_KEY",
        "timeout_seconds": 30,
        "max_retries": 0,
        "notes": "normal notes",
        "route_count": 1,
        "pricing_rule_count": 0,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "route_summaries": (),
        "pricing_summaries": (),
    }
    base.update(overrides)
    return AdminProviderDetail(**base)


def _detail_client_for(
    client: TestClient, monkeypatch, row: AdminProviderDetail
) -> TestClient:
    @asynccontextmanager
    async def fake_scope(request: Any):
        class _Service:
            async def get_provider_detail(self, provider_config_id: Any) -> Any:
                return row

        yield _Service()

    monkeypatch.setattr(admin_mod, "_admin_catalog_dashboard_service_scope", fake_scope)
    return client


class TestProviderDetailProjection:
    def test_stored_notes_canary_masked_env_name_literal(
        self, client: TestClient, monkeypatch
    ) -> None:
        row = _provider_detail_row(notes=CANARY)
        tc = _detail_client_for(client, monkeypatch, row)
        response = tc.get(f"/admin/providers/{row.id}")
        assert response.status_code == 200
        html = response.text
        assert CANARY not in html
        assert CANARY_MASKED in html
        # the ENV variable NAME stays literal (never redacted)
        assert "SVC_A_KEY" in html
        # the source row is never mutated
        assert row.notes == CANARY

    def test_base_url_and_display_name_canaries_masked(
        self, client: TestClient, monkeypatch
    ) -> None:
        row = _provider_detail_row(
            display_name=f"Mod {CANARY}",
            base_url=f"https://svc.example/key={CANARY}",
        )
        tc = _detail_client_for(client, monkeypatch, row)
        response = tc.get(f"/admin/providers/{row.id}")
        assert response.status_code == 200
        html = response.text
        # both retained free-form fields are masked through the projection
        assert CANARY not in html
        assert f"Mod {CANARY_MASKED}" in html
        assert f"https://svc.example/key={CANARY_MASKED}" in html
        assert "SVC_A_KEY" in html
        assert row.base_url == f"https://svc.example/key={CANARY}"
        assert row.display_name == f"Mod {CANARY}"

    def test_ordinary_values_pass_through(
        self, client: TestClient, monkeypatch
    ) -> None:
        row = _provider_detail_row()
        tc = _detail_client_for(client, monkeypatch, row)
        response = tc.get(f"/admin/providers/{row.id}")
        assert response.status_code == 200
        assert row.notes in response.text
        assert row.display_name in response.text


# ---------------------------------------------------------------------------
# Legacy route form refusal re-display (210-a privacy law)
# ---------------------------------------------------------------------------


class TestRouteFormRefusalRedisplay:
    def test_create_refusal_blanks_capabilities_and_redacts_notes(
        self, client: TestClient, state: _State
    ) -> None:
        import json as _json

        document = _json.dumps({"audit_trail": CANARY})
        response = client.post(
            "/admin/routes/new",
            data={
                "csrf_token": "dashboard-csrf",
                "requested_model": "new-model-1",
                "match_type": "exact",
                "endpoint": "chat.completions",
                "provider": "mod-a",
                "upstream_model": "",
                "priority": "100",
                "capabilities": document,
                "notes": f"see {CANARY} for details",
                "reason": "",  # triggers the refusal AFTER capabilities parse
            },
            follow_redirects=False,
        )
        assert response.status_code == 400
        html = response.text
        # the submitted advanced bytes are never re-rendered
        assert CANARY not in html
        # the fixed refusal is shown
        assert "reason" in html.lower()
        assert state.route_create_calls == []
        assert state.validate_calls == []

    def test_edit_refusal_same_law(self, client: TestClient, state: _State) -> None:
        import json as _json

        document = _json.dumps({"audit_trail": CANARY})
        response = client.post(
            f"/admin/routes/{state_route_id()}/edit",
            data={
                "csrf_token": "dashboard-csrf",
                "requested_model": "zap-it-1",
                "match_type": "exact",
                "endpoint": "chat.completions",
                "provider": "mod-a",
                "upstream_model": "",
                "priority": "100",
                "capabilities": document,
                "notes": f"see {CANARY} for details",
                "reason": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 400
        assert CANARY not in response.text
        assert state.route_update_calls == []

    def test_get_form_not_affected(self, client: TestClient) -> None:
        response = client.get("/admin/routes/new")
        assert response.status_code == 200
        # the default form renders its fixed vocabulary
        assert 'name="creation_intent"' in response.text


# ---------------------------------------------------------------------------
# Route review-intent boundary regressions (210-a)
# ---------------------------------------------------------------------------


class TestRouteReviewIntentBoundaries:
    def test_wrong_session_same_actor_refused(self, client: TestClient, state: _State) -> None:
        from slaif_gateway.api.admin_review_intent import build_route_review_token as build

        plan = preview_route_update(state.route, state.provider_row, priority=50)
        document = render_route_update_plan(plan)
        settings = _settings()
        other_session = uuid.uuid4()
        token = build(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=ADMIN_ID,  # same actor
            admin_session_id=other_session,  # different session
            plan_document=document,
            route_target=state_route_id(),
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        response = _apply_post(client, token)
        assert response.status_code == 400
        assert "not valid for this signed-in admin" in response.text
        assert state.execute_calls == []

    def test_non_ascii_mac_refused_safely(self, client: TestClient, state: _State) -> None:
        token = _reviewed_token(state, priority=50)
        body, separator, digest = token.rpartition(".")
        tampered = body + "." + "0" * 63 + "\u00e9"  # non-ASCII digest char
        response = _apply_post(client, tampered)
        # the format guard refuses BEFORE compare_digest (no TypeError/500)
        assert response.status_code == 400
        assert "missing or invalid" in response.text
        assert state.execute_calls == []

    def test_complete_document_64kib_limit_refused_before_preview(
        self, client: TestClient, state: _State
    ) -> None:
        document = '{"pad": "' + "x" * 70000 + '", "schema_version": 1}'
        response = _plan_post(
            client,
            capabilities_source="full",
            capabilities_document=document,
        )
        assert response.status_code == 400
        assert "exceeds the bounded" in response.text
        # the complete document is blanked before the rerender
        assert "x" * 70000 not in response.text
        assert state.preview_calls == []
        assert state.execute_calls == []

    def test_canonical_plan_over_128kib_refused_before_render_and_signing(
        self, client: TestClient, state: _State, monkeypatch
    ) -> None:
        async def huge_preview(
            session: Any,
            route_id: str,
            external_tool_ceilings: Any = None,
            profile_dir: str = "",
            **edits: Any,
        ) -> Any:
            # a VALID plan whose canonical document exceeds the 128 KiB
            # budget (notes is carried in the plan and both previews)
            return preview_route_update(
                state.route,
                state.provider_row,
                external_tool_ceilings=external_tool_ceilings,
                profile_dir=profile_dir,
                notes="n" * 64800,
                **edits,
            )

        monkeypatch.setattr(cfg, "preview_route_update_for_route", huge_preview)
        response = _plan_post(client, notes_intent="preserve")
        assert response.status_code == 400
        assert "exceeds the bounded" in response.text
        # refused BEFORE review rendering / signed-token construction
        assert 'name="route_config_review_intent"' not in response.text
        assert state.execute_calls == []

    def test_verifier_decoded_bound_refuses_oversized_plan_despite_wrapper_fit(
        self, client: TestClient, state: _State
    ) -> None:
        """The decoded canonical-plan bound is enforced at VERIFY even
        when the base64url token fits the wrapper allowance (the real
        missing-bound bug: wrapper slack is not the plan cap)."""
        import base64
        import json as _json

        from slaif_gateway.api.admin_review_intent import (
            REVIEW_INTENT_ROUTE_PURPOSE,
            _digest,
        )

        plan = preview_route_update(state.route, state.provider_row, notes="n" * 64800)
        document = render_route_update_plan(plan)
        settings = _settings()
        secret = settings.ADMIN_SESSION_SECRET
        payload = {
            "purpose": REVIEW_INTENT_ROUTE_PURPOSE,
            "admin_user_id": str(ADMIN_ID),
            "admin_session_id": str(SESSION_ID),
            "expires_at": (datetime.now(UTC) + timedelta(seconds=900)).isoformat(),
            "route_target": state_route_id(),
            "plan": document,
        }
        encoded = _json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        token = base64.urlsafe_b64encode(encoded).decode("ascii") + "." + _digest(secret, encoded)
        # sanity: the token fits the wrapper allowance ...
        from slaif_gateway.api.admin_review_intent import (
            MAX_REVIEW_INTENT_ROUTE_TOKEN_CHARS,
        )
        from slaif_gateway.schemas.provider_route_configuration import (
            ROUTE_PLAN_FILE_MAX_BYTES,
        )

        assert len(token) <= MAX_REVIEW_INTENT_ROUTE_TOKEN_CHARS
        canonical = _json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        assert len(canonical) > ROUTE_PLAN_FILE_MAX_BYTES  # ... but the plan does not
        response = _apply_post(client, token)
        assert response.status_code == 400
        assert "exceeds the bounded" in response.text
        assert state.execute_calls == []
