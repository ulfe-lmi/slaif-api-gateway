"""213-a GUI Codex replay-reference maintenance (unit).

Fake-persistence ASGI/Jinja seams over the real admin app (the shared
replay-maintenance service is faked at the module seam where a test
needs router logic only; the REAL shared strict plan schema, the real
HMAC review-intent build/verify, and the real scope/UUID/time/TTL
parsers run unpatched):

- pages: auth (303), no-store, dashboard-disabled fixed 404 on every
  route, three explicit scopes (never an implicit default), bound
  key/cohort scope pages with canonical-UUID path grammar (permissive
  shorthand refused), actual record-existence 404s, and the
  known-incoming-alias scope refusal BEFORE any template context;
- inspect: exact shared-service invocation (scope, bounds), read-only
  (no apply, no lock, no audit), fixed no-echo refusals for bad
  scope/bounds with useful scope-aware recovery links, ceiling
  refusal, and requested-model alias withholding;
- preview: blank TTL -> configured default, explicit TTL pass-through,
  TTL bound/format refusals, include-expired explicitness, the normal
  GUI reason convention (bounded nonblank Unicode, required, verbatim
  - never trimmed), reason alias refusal, the strict 32KiB rendered
  plan bound BEFORE signing, and the review-doc alias guard before
  signing/rendering;
- review-intent helper: round-trip with verbatim reason, cross-purpose
  refusal both directions, expired/wrong-actor/wrong-session/tampered
  tokens, unknown/edited plan fields, and the maximum astral-Unicode
  reason round-trip inside the bounded envelope;
- apply: confirmation required, exact single shared-service call with
  the SIGNED plan/reason/actor (posted overrides confer no authority),
  truthful applied/already-applied/no-op projections from the real
  result, stale refusal with fresh-preview recovery, UNCONFIRMED
  generic fallback, and the apply-time alias recheck BEFORE the
  service call.

No database, no network, no credential loading. The native PG module
proves the real transaction/audit/preservation law; the browser module
proves the real operator flow.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api import admin_review_intent as intent
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_replay_review_token,
    verify_replay_review_token,
)
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.schemas.codex_replay_maintenance import (
    ReplayExtendPlan,
    ReplayMaintenanceError,
    ReplayMaintenanceStaleError,
    ReplayScope,
    render_replay_extend_plan,
)
from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
    AdminSessionService,
)
from slaif_gateway.services.codex_replay_maintenance import (
    ReplayExtendResult,
    ReplayExclusionReasons,
    ReplayInspectionSummary,
    ReplayKeySummary,
    ReplayRouteModelGroup,
)
from tests.unit.test_admin_key_actions_routes import _app, _settings

ADMIN_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
OTHER_ADMIN_ID = uuid.UUID("99999999-0000-4000-8000-000000000009")
SESSION_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
OTHER_SESSION_ID = uuid.UUID("88888888-0000-4000-8000-000000000008")
KEY_ID = uuid.UUID("cccccccc-0000-4000-8000-000000000003")
COHORT_ID = uuid.UUID("eeeeeeee-0000-4000-8000-000000000005")
ROUTE_ID = uuid.UUID("ffffffff-0000-4000-8000-000000000006")
CSRF = "replay-csrf"
BASE = "/admin/operations/replay-maintenance"

# Opaque incoming credential value carried as the current admin session
# cookie in the alias canaries (fits no safe grammar).
COOKIE_CANARY = "SESSCANARYcookie123opaque"
# A canonical-UUID-valued incoming credential (session cookie) for
# scope-alias canaries.
COOKIE_UUID_CANARY = KEY_ID


class _FakeService:
    """Records every shared-service call; returns canned results."""

    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.summary: ReplayInspectionSummary | None = None
        self.plan: ReplayExtendPlan | None = None
        self.result: ReplayExtendResult = ReplayExtendResult(
            applied=True,
            already_applied=False,
            updated_references=2,
            selected_keys=1,
            eligible_references=2,
            exclusion_counts={"expired_not_included": 1},
        )
        self.inspect_exc: Exception | None = None
        self.preview_exc: Exception | None = None
        self.apply_exc: Exception | None = None

    def __call__(self, *, repository, audit_repository, settings):
        return self

    async def inspect_replay_references(self, **kwargs):
        self.calls.append(("inspect", kwargs))
        if self.inspect_exc:
            raise self.inspect_exc
        assert self.summary is not None
        return self.summary

    async def preview_replay_extend(self, **kwargs):
        self.calls.append(("preview", kwargs))
        if self.preview_exc:
            raise self.preview_exc
        assert self.plan is not None
        return self.plan

    async def apply_replay_extend(self, **kwargs):
        self.calls.append(("apply", kwargs))
        if self.apply_exc:
            raise self.apply_exc
        return self.result


def _now() -> datetime:
    return datetime.now(UTC)


def _summary(scope: ReplayScope) -> ReplayInspectionSummary:
    now = _now()
    return ReplayInspectionSummary(
        scope_text=scope.scope_text,
        now=now,
        configured_ttl_seconds=31536000,
        keys=1,
        keys_active_or_valid=1,
        references=3,
        active_references=2,
        expired_references=1,
        created_min=now,
        created_max=now,
        expiry_min=now,
        expiry_max=now,
        per_key=(
            ReplayKeySummary(
                key_id=KEY_ID,
                key_status="active",
                references=3,
                active_references=2,
                expired_references=1,
                created_min=now,
                created_max=now,
                expiry_min=now,
                expiry_max=now,
            ),
        ),
        route_model_groups=(
            ReplayRouteModelGroup(route_id=ROUTE_ID, requested_model="model-x", references=3),
        ),
        route_model_groups_total=1,
        route_model_groups_truncated=False,
        reasons=ReplayExclusionReasons(
            key_not_active_or_valid=0,
            ledger_not_finalized=0,
            unsupported_kind=0,
            hmac_version_unavailable=0,
            outside_lifetime=0,
            expired_not_included=1,
        ),
        note="Expiry eligibility is maintenance state, not client or model readiness.",
    )


def _plan(
    scope: ReplayScope,
    *,
    ttl: int = 31536000,
    include_expired: bool = True,
) -> ReplayExtendPlan:
    now = _now()
    return ReplayExtendPlan(
        schema_version=1,
        operation="extend",
        scope=scope,
        created_from=None,
        created_until=None,
        ttl_seconds=ttl,
        configured_ttl_seconds=31536000,
        include_expired=include_expired,
        previewed_at=now,
        selected_keys=1,
        eligible_references=2,
        exclusion_counts={
            "key_not_active_or_valid": 0,
            "ledger_not_finalized": 0,
            "unsupported_kind": 0,
            "hmac_version_unavailable": 0,
            "outside_lifetime": 0,
            "expired_not_included": 1,
        },
        old_expiry_min=now,
        old_expiry_max=now,
        new_expiry_min=now,
        new_expiry_max=now,
        expected_source_fingerprint="0" * 64,
        expected_source_state_fingerprint="1" * 64,
        expected_post_state_fingerprint="2" * 64,
    )


def _review_doc(
    scope: ReplayScope, *, reason: str = "Extend replay refs for Q2 audit window", ttl: int = 31536000
) -> dict[str, Any]:
    return {"plan": render_replay_extend_plan(_plan(scope, ttl=ttl)), "reason": reason}


@pytest.fixture()
def service(monkeypatch) -> _FakeService:
    fake = _FakeService()
    monkeypatch.setattr(
        "slaif_gateway.api.admin_replay_maintenance.CodexReplayMaintenanceService",
        fake,
    )
    return fake


@pytest.fixture()
def client(monkeypatch) -> TestClient:
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
        return AdminSessionContext(
            admin_user=admin_user, admin_session=admin_session
        )

    def verify_session_csrf_token(self, admin_session_row, csrf_token):
        return csrf_token == CSRF

    async def refresh_csrf_token(self, admin_session_id=None):
        return CSRF

    monkeypatch.setattr(
        AdminSessionService, "validate_admin_session", validate_admin_session
    )
    monkeypatch.setattr(
        AdminSessionService, "verify_session_csrf_token", verify_session_csrf_token
    )
    monkeypatch.setattr(
        AdminSessionService, "refresh_csrf_token", refresh_csrf_token
    )

    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository

    class _KeyRow:
        id = KEY_ID
        status = "active"

    class _CohortRow:
        id = COHORT_ID
        name = "team-a"

    async def fake_get_key(self, key_id):
        return _KeyRow() if key_id == KEY_ID else None

    async def fake_get_cohort(self, cohort_id):
        return _CohortRow() if cohort_id == COHORT_ID else None

    monkeypatch.setattr(
        GatewayKeysRepository, "get_gateway_key_by_id", fake_get_key
    )
    monkeypatch.setattr(
        CohortsRepository, "get_cohort_by_id", fake_get_cohort
    )

    c = TestClient(app, follow_redirects=False)
    c.cookies.set("slaif_admin_session", "sess")
    return c


def _scope_fields(scope_kind: str, **extra) -> dict[str, str]:
    fields = {
        "csrf_token": CSRF,
        "scope": scope_kind,
        "created_from": "",
        "created_until": "",
    }
    if scope_kind == "key":
        fields["key_id"] = str(KEY_ID)
    elif scope_kind == "cohort":
        fields["cohort_id"] = str(COHORT_ID)
    fields.update(extra)
    return fields


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def test_pages_require_auth(monkeypatch) -> None:
    app = _app()
    c = TestClient(app, follow_redirects=False)
    for path in (
        f"{BASE}/",
        f"{BASE}/key/{KEY_ID}",
        f"{BASE}/cohort/{COHORT_ID}",
        f"{BASE}/all-active",
    ):
        r = c.get(path)
        assert r.status_code == 303
        assert r.headers["location"] == "/admin/login"
    r = c.post(f"{BASE}/inspect", data=_scope_fields("key"))
    assert r.status_code == 303


def test_dashboard_disabled_refuses_every_route(monkeypatch) -> None:
    app = _app(_settings(ENABLE_ADMIN_DASHBOARD=False))
    c = TestClient(app, follow_redirects=False)
    for path in (
        f"{BASE}/",
        f"{BASE}/key/{KEY_ID}",
        f"{BASE}/cohort/{COHORT_ID}",
        f"{BASE}/all-active",
    ):
        r = c.get(path)
        assert r.status_code == 404
    r = c.post(f"{BASE}/inspect", data=_scope_fields("key"))
    assert r.status_code == 404
    r = c.post(f"{BASE}/preview", data=_scope_fields("key", reason="x" * 10))
    assert r.status_code == 404
    r = c.post(f"{BASE}/apply", data={"csrf_token": CSRF})
    assert r.status_code == 404


def test_index_shows_three_explicit_scopes(client) -> None:
    r = client.get(f"{BASE}/")
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
    assert "One existing key" in r.text
    assert "One cohort" in r.text
    assert "Every active key (explicit)" in r.text
    assert "/admin/keys" in r.text
    assert "/admin/cohorts" in r.text
    assert f"{BASE}/all-active" in r.text
    assert "no implicit" in r.text


def test_key_scope_page_shows_bound_scope(client) -> None:
    r = client.get(f"{BASE}/key/{KEY_ID}")
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
    assert str(KEY_ID) in r.text
    assert 'name="scope" value="key"' in r.text
    assert f'name="key_id" value="{KEY_ID}"' in r.text
    assert "key status: active" in r.text
    # Reason is required in HTML as well as the backend.
    assert 'id="preview-reason"' in r.text
    assert "required" in r.text.split('id="preview-reason"')[1].split(">")[0]


def test_key_scope_missing_key_404_with_recovery(client) -> None:
    r = client.get(f"{BASE}/key/{uuid.uuid4()}")
    assert r.status_code == 404
    assert "Gateway key not found." in r.text
    assert f'href="{BASE}/"' in r.text


def test_key_scope_non_canonical_uuid_404(client) -> None:
    # uuid.UUID shorthand (no dashes) is permissive; the shared canonical
    # grammar refuses it with the fixed 404.
    shorthand = str(KEY_ID).replace("-", "")
    r = client.get(f"{BASE}/key/{shorthand}")
    assert r.status_code == 404
    assert "Gateway key not found." in r.text
    assert shorthand not in r.text


def test_key_scope_alias_refused_before_render(client, monkeypatch) -> None:
    # The incoming session cookie EQUALS the key's canonical UUID: the
    # scope is a known incoming alias and is refused before any template
    # context (and never re-exposed via a link).
    client.cookies.set("slaif_admin_session", str(COOKIE_UUID_CANARY))
    r = client.get(f"{BASE}/key/{KEY_ID}")
    assert r.status_code == 400
    assert "known incoming authentication value" in r.text
    assert f'href="{BASE}/key/{KEY_ID}"' not in r.text
    assert f'href="{BASE}/"' in r.text
    client.cookies.set("slaif_admin_session", "sess")


def test_cohort_scope_page_and_negatives(client) -> None:
    r = client.get(f"{BASE}/cohort/{COHORT_ID}")
    assert r.status_code == 200
    assert str(COHORT_ID) in r.text
    assert 'name="scope" value="cohort"' in r.text
    assert "team-a" in r.text

    assert client.get(f"{BASE}/cohort/{uuid.uuid4()}").status_code == 404
    assert client.get(f"{BASE}/cohort/{str(COHORT_ID).replace('-', '')}").status_code == 404


def test_all_active_scope_page_is_explicit(client) -> None:
    r = client.get(f"{BASE}/all-active")
    assert r.status_code == 200
    assert "every key currently in the active state" in r.text
    assert 'name="key_id"' not in r.text
    assert 'name="cohort_id"' not in r.text
    assert 'name="scope" value="all_active"' in r.text


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------


def test_inspect_requires_csrf(client, service) -> None:
    r = client.post(f"{BASE}/inspect", data=_scope_fields("key", csrf_token="wrong"))
    assert r.status_code == 400
    assert "Invalid CSRF token." in r.text
    assert service.calls == []


def test_inspect_exact_service_call_is_read_only(client, service) -> None:
    service.summary = _summary(ReplayScope(key_id=KEY_ID))
    r = client.post(
        f"{BASE}/inspect",
        data=_scope_fields("key", created_from="2026-01-01T00:00:00Z"),
    )
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
    assert service.calls == [
        (
            "inspect",
            {
                "scope": ReplayScope(key_id=KEY_ID),
                "created_from": datetime(2026, 1, 1, tzinfo=UTC),
                "created_until": None,
            },
        )
    ]
    assert "model-x" in r.text
    assert str(ROUTE_ID) in r.text
    assert "3" in r.text
    # "Keys in scope" renders the NUMERIC aggregate (the Jinja
    # projection is keys_count, so the dict.keys builtin can never
    # leak into the page).
    keys_cell = (
        r.text.split("Keys in scope</dt>")[1].split("<dd>")[1].split("</dd>")[0]
    )
    assert keys_cell.strip() == "1 (1 active/valid)"
    assert "builtin method" not in r.text


def test_inspect_bad_scope_refused_with_fixed_entry(client, service) -> None:
    # Chosen kind without its ID.
    r = client.post(
        f"{BASE}/inspect", data={"csrf_token": CSRF, "scope": "key"}
    )
    assert r.status_code == 400
    assert "Choose exactly one replay maintenance scope" in r.text
    assert f'href="{BASE}/"' in r.text
    assert service.calls == []
    # Unknown scope kind.
    r = client.post(
        f"{BASE}/inspect",
        data={"csrf_token": CSRF, "scope": "everything"},
    )
    assert r.status_code == 400
    assert "Choose exactly one replay maintenance scope" in r.text
    # Malformed scope UUID (the shared canonical grammar refuses it).
    r = client.post(
        f"{BASE}/inspect",
        data=_scope_fields("key", key_id="not-a-uuid"),
    )
    assert r.status_code == 400
    assert "valid canonical UUID" in r.text
    assert service.calls == []
    # Conflicting scope members (kind=cohort with a key_id ALSO present):
    # the shared exactly-one law refuses the ambiguity; nothing is
    # silently dropped.
    r = client.post(
        f"{BASE}/inspect",
        data=_scope_fields("cohort", key_id=str(KEY_ID)),
    )
    assert r.status_code == 400
    assert "Exactly one scope is required" in r.text
    assert service.calls == []


def test_inspect_bad_time_bounds_refused(client, service) -> None:
    # Non-UTC offset.
    r = client.post(
        f"{BASE}/inspect",
        data=_scope_fields("key", created_from="2026-01-01T00:00:00+02:00"),
    )
    assert r.status_code == 400
    assert "explicit UTC timestamp" in r.text
    # Malformed.
    r = client.post(
        f"{BASE}/inspect", data=_scope_fields("key", created_from="not-a-time")
    )
    assert r.status_code == 400
    assert "ISO 8601 UTC timestamp" in r.text
    # from > until.
    r = client.post(
        f"{BASE}/inspect",
        data=_scope_fields(
            "key",
            created_from="2026-01-02T00:00:00Z",
            created_until="2026-01-01T00:00:00Z",
        ),
    )
    assert r.status_code == 400
    assert "Creation bounds must satisfy" in r.text
    # A valid scope still gets the scope recovery link.
    assert f'href="{BASE}/key/{KEY_ID}"' in r.text
    assert service.calls == []


def test_inspect_ceiling_refusal_fixed_message(client, service) -> None:
    service.summary = _summary(ReplayScope(key_id=KEY_ID))
    service.inspect_exc = ReplayMaintenanceError(
        "The maintenance scope exceeds the bounded ceiling "
        "(1000 keys / 50000 references). Narrow the scope or "
        "creation-time bounds and preview again.",
        error_code="replay_maintenance_oversize",
    )
    r = client.post(f"{BASE}/inspect", data=_scope_fields("key"))
    assert r.status_code == 400
    assert "bounded ceiling" in r.text
    assert f'href="{BASE}/key/{KEY_ID}"' in r.text


def test_inspect_requested_model_alias_withheld(client, service) -> None:
    summary = _summary(ReplayScope(key_id=KEY_ID))
    summary = SimpleNamespace(**vars(summary)) if hasattr(summary, "__dict__") else summary
    service.summary = SimpleNamespace(
        scope_text=summary.scope_text,
        now=summary.now,
        configured_ttl_seconds=summary.configured_ttl_seconds,
        keys=summary.keys,
        keys_active_or_valid=summary.keys_active_or_valid,
        references=summary.references,
        active_references=summary.active_references,
        expired_references=summary.expired_references,
        created_min=summary.created_min,
        created_max=summary.created_max,
        expiry_min=summary.expiry_min,
        expiry_max=summary.expiry_max,
        per_key=summary.per_key,
        route_model_groups=(
            ReplayRouteModelGroup(
                route_id=ROUTE_ID, requested_model=COOKIE_CANARY, references=3
            ),
        ),
        route_model_groups_total=1,
        route_model_groups_truncated=False,
        reasons=summary.reasons,
        note=summary.note,
    )
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    try:
        r = client.post(f"{BASE}/inspect", data=_scope_fields("key"))
        assert r.status_code == 200
        assert COOKIE_CANARY not in r.text
        assert "Withheld: matches a known credential value" in r.text
    finally:
        client.cookies.set("slaif_admin_session", "sess")


def test_inspect_scope_alias_refused_before_service(client, service) -> None:
    client.cookies.set("slaif_admin_session", str(COOKIE_UUID_CANARY))
    r = client.post(f"{BASE}/inspect", data=_scope_fields("key"))
    assert r.status_code == 400
    assert "known incoming authentication value" in r.text
    assert str(KEY_ID) not in r.text
    assert service.calls == []
    client.cookies.set("slaif_admin_session", "sess")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def _preview(client, service, **extra):
    ttl_raw = str(extra.get("ttl_seconds", "") or "")
    try:
        ttl = int(ttl_raw) if ttl_raw else 31536000
    except ValueError:
        ttl = 31536000
    service.plan = _plan(ReplayScope(key_id=KEY_ID), ttl=ttl)
    return client.post(f"{BASE}/preview", data=_scope_fields("key", **extra))


def test_preview_blank_ttl_uses_configured_default(client, service) -> None:
    r = _preview(client, service, reason="Extend replay refs for Q2 audit window")
    assert r.status_code == 200
    call = service.calls[0]
    assert call[0] == "preview"
    assert call[1]["ttl_seconds"] is None
    assert "configured default" in r.text
    assert "review_token" in r.text


def test_preview_explicit_ttl_passed(client, service) -> None:
    r = _preview(
        client,
        service,
        ttl_seconds="2592000",
        reason="Extend replay refs for Q2 audit window",
    )
    assert r.status_code == 200
    assert service.calls[0][1]["ttl_seconds"] == 2592000


def test_preview_ttl_refusals(client, service) -> None:
    # Router-level whole-number format refusals (fixed message + scope
    # recovery link; the shared service is never reached).
    for bad in ("12.5", "abc", "-5", "+5", "1e3"):
        r = _preview(
            client,
            service,
            ttl_seconds=bad,
            reason="Extend replay refs for Q2 audit window",
        )
        assert r.status_code == 400, (bad, r.status_code)
        assert "whole number of seconds" in r.text
        assert f'href="{BASE}/key/{KEY_ID}"' in r.text
    assert service.calls == []
    # The RANGE law is the real shared validator (Core authority): the
    # router passes clean integers through and the shared
    # validate_ttl_seconds refuses the out-of-range values.
    from slaif_gateway.services.codex_replay_maintenance import (
        validate_ttl_seconds,
    )

    assert validate_ttl_seconds(1) == 1
    assert validate_ttl_seconds(31536000) == 31536000
    for bad in (0, 31536001, -1):
        with pytest.raises(ReplayMaintenanceError) as exc:
            validate_ttl_seconds(bad)
        assert "1..31536000" in exc.value.safe_message
    with pytest.raises(ReplayMaintenanceError):
        validate_ttl_seconds("2592000")


def test_preview_include_expired_default_off_then_on(client, service) -> None:
    r = _preview(client, service, reason="Extend replay refs for Q2 audit window")
    assert r.status_code == 200
    assert service.calls[0][1]["include_expired"] is False
    r = _preview(
        client,
        service,
        include_expired="1",
        reason="Extend replay refs for Q2 audit window",
    )
    assert r.status_code == 200
    assert service.calls[1][1]["include_expired"] is True


def test_preview_reason_convention(client, service) -> None:
    # Required, nonblank.
    r = _preview(client, service, reason="")
    assert r.status_code == 400
    assert "nonblank audit reason" in r.text
    r = _preview(client, service, reason="     ")
    assert r.status_code == 400
    # Over the 512-character GUI bound.
    r = _preview(client, service, reason="x" * 513)
    assert r.status_code == 400
    assert "512" in r.text
    # Bounded nonblank Unicode is ACCEPTED and preserved verbatim.
    unicode_reason = "Étendre les références de lecture pour 213-a audit"
    r = _preview(client, service, reason=unicode_reason)
    assert r.status_code == 200
    assert unicode_reason in r.text
    # Leading spaces are legal and NEVER trimmed.
    padded = "  Extend replay refs for Q2 audit window  "
    r = _preview(client, service, reason=padded)
    assert r.status_code == 200
    token = r.text.split('name="review_token" value="')[1].split('"')[0]
    document = verify_replay_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    assert document["reason"] == padded


def test_preview_reason_alias_refused(client, service) -> None:
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    try:
        r = _preview(client, service, reason=COOKIE_CANARY)
        assert r.status_code == 400
        assert "known incoming authentication value" in r.text
        assert COOKIE_CANARY not in r.text
        assert service.calls == []
    finally:
        client.cookies.set("slaif_admin_session", "sess")


def test_preview_rendered_plan_size_bound_before_signing(client, service, monkeypatch) -> None:
    """The strict 32KiB bound on the RENDERED plan fires BEFORE any
    signing work: shrink the cap and the preview refuses with the fixed
    message and no token, while the service preview itself succeeded."""
    import slaif_gateway.api.admin_replay_maintenance as router_mod

    service.plan = _plan(ReplayScope(key_id=KEY_ID))
    monkeypatch.setattr(router_mod, "REPLAY_PLAN_MAX_BYTES", 100)
    r = _preview(client, service, reason="Extend replay refs for Q2 audit window")
    assert r.status_code == 400
    assert "The reviewed replay plan exceeds the bounded size." in r.text
    assert "review_token" not in r.text
    assert f'href="{BASE}/key/{KEY_ID}"' in r.text
    # The shared service preview DID run (read-only); signing never did.
    assert [name for name, _ in service.calls] == ["preview"]


def test_preview_review_doc_alias_refused_before_signing(client, service) -> None:
    # The signed scope UUID is a known incoming alias: refused before
    # the token is rendered.
    client.cookies.set("slaif_admin_session", str(COOKIE_UUID_CANARY))
    r = _preview(client, service, reason="Extend replay refs for Q2 audit window")
    assert r.status_code == 400
    assert "known incoming authentication value" in r.text
    assert "review_token" not in r.text
    assert f'href="{BASE}/"' in r.text
    assert not any(name == "apply" for name, _ in service.calls)
    client.cookies.set("slaif_admin_session", "sess")


def test_preview_signs_token_bound_to_actor_session(client, service) -> None:
    r = _preview(client, service, reason="Extend replay refs for Q2 audit window")
    assert r.status_code == 200
    token = r.text.split('name="review_token" value="')[1].split('"')[0]
    document = verify_replay_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    assert document["reason"] == "Extend replay refs for Q2 audit window"
    with pytest.raises(AdminReviewIntentError):
        verify_replay_review_token(
            admin_session_secret=_settings().ADMIN_SESSION_SECRET,
            token=token,
            admin_user_id=OTHER_ADMIN_ID,
            admin_session_id=SESSION_ID,
        )
    with pytest.raises(AdminReviewIntentError):
        verify_replay_review_token(
            admin_session_secret=_settings().ADMIN_SESSION_SECRET,
            token=token,
            admin_user_id=ADMIN_ID,
            admin_session_id=OTHER_SESSION_ID,
        )


# ---------------------------------------------------------------------------
# Review-intent helper (pure)
# ---------------------------------------------------------------------------


def test_replay_token_round_trip_verbatim_reason() -> None:
    doc = _review_doc(ReplayScope(key_id=KEY_ID), reason="  Extend refs - audit window  ")
    token = build_replay_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=doc,
    )
    out = verify_replay_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    assert out == doc


def test_replay_token_cross_purpose_refused() -> None:
    from tests.unit.test_admin_compatibility_212 import _module_review_doc

    compat_token = intent.build_compatibility_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    with pytest.raises(AdminReviewIntentError):
        verify_replay_review_token(
            admin_session_secret="s" * 40,
            token=compat_token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )
    replay_token = build_replay_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_review_doc(ReplayScope(key_id=KEY_ID)),
    )
    with pytest.raises(AdminReviewIntentError):
        intent.verify_compatibility_review_token(
            admin_session_secret="s" * 40,
            token=replay_token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )


def test_replay_token_build_refuses_bad_documents() -> None:
    kwargs = dict(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    # Unknown outer review keys.
    bad = _review_doc(ReplayScope(key_id=KEY_ID))
    bad["extra"] = 1
    with pytest.raises(AdminReviewIntentError):
        build_replay_review_token(review_document=bad, **kwargs)
    # Missing required plan field.
    missing = _review_doc(ReplayScope(key_id=KEY_ID))
    del missing["plan"]["ttl_seconds"]
    with pytest.raises(AdminReviewIntentError):
        build_replay_review_token(review_document=missing, **kwargs)
    # Non-integer plan field (type strictness).
    badtype = _review_doc(ReplayScope(key_id=KEY_ID))
    badtype["plan"]["ttl_seconds"] = "2592000"
    with pytest.raises(AdminReviewIntentError):
        build_replay_review_token(review_document=badtype, **kwargs)
    # Unknown plan field.
    unknown = _review_doc(ReplayScope(key_id=KEY_ID))
    unknown["plan"]["bogus"] = 1
    with pytest.raises(AdminReviewIntentError):
        build_replay_review_token(review_document=unknown, **kwargs)
    # Reason violations (the normal GUI convention: bounded nonblank
    # Unicode - there is NO 8-character minimum; "short" would be legal).
    for bad_reason in ("", "       ", "x" * 513):
        doc = _review_doc(ReplayScope(key_id=KEY_ID), reason=bad_reason)
        with pytest.raises(AdminReviewIntentError):
            build_replay_review_token(review_document=doc, **kwargs)


def test_replay_token_expired_and_tampered() -> None:
    now = datetime.now(UTC)
    token = build_replay_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_review_doc(ReplayScope(key_id=KEY_ID)),
        ttl_seconds=1,
        now=now,
    )
    with pytest.raises(AdminReviewIntentError) as exc:
        verify_replay_review_token(
            admin_session_secret="s" * 40,
            token=token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            now=now + timedelta(seconds=2),
        )
    assert "expired" in exc.value.message
    # Tampered body (one flipped base64 char) -> fixed invalid message.
    body, digest = token.rsplit(".", 1)
    flipped = ("A" if body[0] != "A" else "B") + body[1:]
    with pytest.raises(AdminReviewIntentError):
        verify_replay_review_token(
            admin_session_secret="s" * 40,
            token=flipped + "." + digest,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )
    # Wrong secret -> not authentic.
    with pytest.raises(AdminReviewIntentError) as exc2:
        verify_replay_review_token(
            admin_session_secret="t" * 40,
            token=token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )
    assert "not valid for this signed-in admin" in exc2.value.message


def test_replay_token_max_astral_unicode_reason_round_trip() -> None:
    # 512 astral characters consume 6,144 canonical JSON bytes under
    # ensure_ascii; the bounded envelope must still round-trip.
    reason = "\U0001F600" * 512
    doc = _review_doc(ReplayScope(key_id=KEY_ID), reason=reason)
    token = build_replay_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=doc,
    )
    out = verify_replay_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    assert out["reason"] == reason
    # 513 astral characters exceed the reason bound.
    doc2 = _review_doc(ReplayScope(key_id=KEY_ID), reason="\U0001F600" * 513)
    with pytest.raises(AdminReviewIntentError):
        build_replay_review_token(
            admin_session_secret="s" * 40,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            review_document=doc2,
        )


def test_replay_token_envelope_cap_enforced(monkeypatch) -> None:
    # A shrunk envelope budget proves the pre-signing cap fires with the
    # fixed too-large message (no allocation/signing side effects).
    monkeypatch.setattr(intent, "REPLAY_REVIEW_PLAN_MAX_BYTES", 100)
    with pytest.raises(AdminReviewIntentError) as exc:
        build_replay_review_token(
            admin_session_secret="s" * 40,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            review_document=_review_doc(ReplayScope(key_id=KEY_ID)),
        )
    assert "bounded review size" in exc.value.message


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _preview_token(client, service, **extra) -> str:
    r = _preview(client, service, **extra)
    assert r.status_code == 200, r.text[:500]
    return r.text.split('name="review_token" value="')[1].split('"')[0]


def _apply(client, token, **extra):
    fields = {"csrf_token": CSRF, "review_token": token, "confirm_apply": "1"}
    fields.update(extra)
    return client.post(f"{BASE}/apply", data=fields)


def test_apply_requires_confirmation(client, service) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    r = _apply(client, token, confirm_apply="")
    assert r.status_code == 400
    assert "Confirm the reviewed replay extension before applying it." in r.text
    # Verified canonical scope still gets the recovery link; no apply call.
    assert f'href="{BASE}/key/{KEY_ID}"' in r.text
    assert [name for name, _ in service.calls] == ["preview"]


def test_apply_exact_single_call_with_signed_facts(client, service) -> None:
    token = _preview_token(
        client,
        service,
        ttl_seconds="2592000",
        include_expired="1",
        reason="  Extend replay refs - verbatim reason  ",
    )
    service.result = ReplayExtendResult(
        applied=True,
        already_applied=False,
        updated_references=2,
        selected_keys=1,
        eligible_references=2,
        exclusion_counts={"expired_not_included": 1},
    )
    r = _apply(
        client,
        token,
        # Posted overrides must confer NO authority: the signed values
        # are the only ones that reach the shared service.
        reason="posted reason should be ignored",
        ttl_seconds="1",
        eligible_references="999",
        plan="{}",
    )
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
    names = [name for name, _ in service.calls]
    assert names.count("apply") == 1
    plan, kwargs = service.calls[-1]
    assert plan is not None
    assert kwargs["plan"].ttl_seconds == 2592000
    assert kwargs["plan"].include_expired is True
    assert kwargs["plan"].scope == ReplayScope(key_id=KEY_ID)
    assert kwargs["reason"] == "  Extend replay refs - verbatim reason  "
    assert kwargs["actor_admin_id"] == ADMIN_ID
    assert "Applied" in r.text
    assert "2 reference" in r.text


def test_apply_repeat_already_applied_truthful(client, service) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    service.result = ReplayExtendResult(
        applied=False,
        already_applied=True,
        updated_references=0,
        selected_keys=1,
        eligible_references=2,
        exclusion_counts={"expired_not_included": 1},
    )
    r = _apply(client, token)
    assert r.status_code == 200
    assert "Already applied" in r.text
    assert "nothing was written" in r.text
    assert "no audit record" in r.text
    assert service.calls[-1][0] == "apply"


def test_apply_noop_result_truthful(client, service) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    service.result = ReplayExtendResult(
        applied=False,
        already_applied=False,
        updated_references=0,
        selected_keys=1,
        eligible_references=0,
        exclusion_counts={"outside_lifetime": 1},
    )
    r = _apply(client, token)
    assert r.status_code == 200
    assert "No eligible change" in r.text
    assert "nothing was written" in r.text


def test_apply_expired_token_refused(client, service, monkeypatch) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    # Advance the shared clock past the 15-minute bound.
    now = datetime.now(UTC)
    monkeypatch.setattr(
        "slaif_gateway.api.admin_review_intent.datetime",
        type("FakeDT", (datetime,), {"now": classmethod(lambda cls, tz=None: now + timedelta(minutes=16))}),
    )
    r = _apply(client, token)
    assert r.status_code == 400
    assert "expired" in r.text
    # Invalid token -> fixed replay entry, no scope link.
    assert f'href="{BASE}/key/{KEY_ID}"' not in r.text
    assert f'href="{BASE}/"' in r.text
    assert [name for name, _ in service.calls] == ["preview"]


def test_apply_tampered_token_refused(client, service) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    body, digest = token.rsplit(".", 1)
    flipped = ("A" if body[0] != "A" else "B") + body[1:]
    r = _apply(client, flipped + "." + digest)
    assert r.status_code == 400
    # A decodable tampered body fails the HMAC check: fixed not-authentic
    # message (a non-decodable body fails the format check first).
    assert "not valid for this signed-in admin" in r.text
    assert [name for name, _ in service.calls] == ["preview"]


def test_apply_wrong_actor_refused(client, service, monkeypatch) -> None:
    token = build_replay_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        admin_user_id=OTHER_ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_review_doc(ReplayScope(key_id=KEY_ID)),
    )
    r = _apply(client, token)
    assert r.status_code == 400
    assert "not valid for this signed-in admin" in r.text
    assert [name for name, _ in service.calls] == []


def test_apply_cross_purpose_compatibility_token_refused(client, service) -> None:
    from tests.unit.test_admin_compatibility_212 import _module_review_doc

    token = intent.build_compatibility_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    r = _apply(client, token)
    assert r.status_code == 400
    assert "not valid for this signed-in admin" in r.text
    assert service.calls == []


def test_apply_stale_refused_with_fresh_preview_recovery(client, service) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    service.apply_exc = ReplayMaintenanceStaleError(
        "The reviewed replay maintenance pre-state no longer matches the "
        "live rows.",
        error_code="replay_maintenance_stale",
    )
    r = _apply(client, token)
    assert r.status_code == 400
    assert "no longer matches the live rows" in r.text
    assert "Preview the scope again" in r.text
    assert f'href="{BASE}/key/{KEY_ID}"' in r.text


def test_apply_generic_failure_unconfirmed(client, service) -> None:
    token = _preview_token(client, service, reason="Extend replay refs for Q2 audit window")
    service.apply_exc = RuntimeError("boom")
    r = _apply(client, token)
    assert r.status_code == 400
    assert "UNCONFIRMED" in r.text
    assert "cannot prove a rollback" in r.text
    assert "boom" not in r.text


def test_apply_alias_recheck_before_service(client, service) -> None:
    # Token signed with a reason that is ALSO the current incoming
    # session cookie: the apply-time recheck refuses BEFORE the shared
    # service is called.
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    token = build_replay_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_review_doc(ReplayScope(key_id=KEY_ID), reason=COOKIE_CANARY),
    )
    r = _apply(client, token)
    assert r.status_code == 400
    assert "known incoming authentication value" in r.text
    assert COOKIE_CANARY not in r.text
    assert service.calls == []
    client.cookies.set("slaif_admin_session", "sess")


def test_apply_scope_alias_gets_fixed_entry_not_scope_link(client, service) -> None:
    # The signed scope UUID itself is the incoming alias: refused, and
    # the scope is never re-exposed through a recovery URL.
    client.cookies.set("slaif_admin_session", str(COOKIE_UUID_CANARY))
    token = build_replay_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_review_doc(ReplayScope(key_id=KEY_ID)),
    )
    r = _apply(client, token)
    assert r.status_code == 400
    assert "known incoming authentication value" in r.text
    assert f'href="{BASE}/key/{KEY_ID}"' not in r.text
    assert f'href="{BASE}/"' in r.text
    assert service.calls == []
    client.cookies.set("slaif_admin_session", "sess")
