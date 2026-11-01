"""211-a GUI operations (unit): content-free request diagnostics + safe
process-configuration inspection.

Fake-persistence ASGI/Jinja seams over the real admin app (the typed
diagnostics service is faked at the module seam; the real router,
templates, shared record-choice macro/JS contract, and the real
configuration-inspection service run):

- typed found / ambiguous / overflow / not-found / store-unavailable /
  disabled outcomes, with a wire-200 ``stream_failure`` rendered
  visibly as a failure and unavailable historical module identity
  explicitly "not recorded";
- input canaries: credential-shaped and known-incoming-alias (current
  cookie) lookup values, picker queries, and selected values are refused
  or withheld — never echoed in HTML, JSON, redirects, or hidden fields;
- output canaries: retained choices, found-record fields, Codex identity
  facts, upstream identity/selector strings, and operator revision text
  that equal an incoming alias for THIS request are withheld without
  mutating stored facts or canonical snapshots;
- auth/CSRF/confirmation/reason denials (303 without a session, 400 on
  CSRF, fixed refusals with no service call, bounded reason law);
- cleanup: the service call carries actor/reason/count (asserted against
  the mocked store: one call, 0-delete audited once, 1000-delete "another
  run may be needed", unconfirmed-failure wording); the REAL one-audit-row
  and atomic-rollback proofs are the native PG module's;
- process configuration: exact 45 allowlist, API-scope wording, visible
  M-token / grouped-quantity formatting with raw sort keys and exact raw
  titles, startup profile snapshot (file changes later are not re-read),
  version/revision honesty, and no environment dump.

No database, no network, no credential loading; the shared service and
repository law is not re-proved here. The handlers perform no logging of
submitted values at all, so the canaries are asserted on every rendered
surface (HTML body, hidden fields, redirect targets, JSON bodies).
"""

from __future__ import annotations

import os
import json
import uuid
from html import unescape
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway import __version__
from slaif_gateway.api import admin_operations as ops
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.modules.servers.upstream_llm import profiles as llm_profiles
from slaif_gateway.schemas.request_diagnostics import (
    DIAGNOSTIC_LOOKUP_BOUND,
    DiagnosticsCleanupResult,
    DiagnosticsNamespace,
    DiagnosticsStatus,
    DiagnosticDisambiguationCandidate,
    DiagnosticIdChoice,
    DiagnosticIdChoiceResult,
    DiagnosticLookupOutcome,
    DiagnosticLookupResult,
    RequestDiagnosticRecord,
)
from slaif_gateway.services.admin_session_service import AdminSessionService
from slaif_gateway.services.configuration_inspection import (
    API_PROCESS_LIMITATIONS,
    CONFIG_INSPECTION_ALLOWLIST,
    INSPECTION_LIMITATIONS,
    PROCESS_SCOPES,
    inspect_process_configuration,
    setting_meaning,
)
from tests.unit.test_admin_key_actions_routes import _app, _settings

ADMIN_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
SESSION_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
CSRF = "dashboard-csrf"
NOW = datetime.now(UTC)

# Recognized credential shape (prefix-accepted gateway key).
CRED_CANARY = "sk-slaif-0123456789abcdefcanary"
# Opaque incoming credential value (fits the safe ID grammar): carried as
# the current admin session cookie in the alias canaries.
COOKIE_CANARY = "SESSCANARYcookie123opaque"


def _record(**overrides: Any) -> RequestDiagnosticRecord:
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        gateway_request_id="gw-11111111-2222-3333-4444-555555555555",
        client_request_id="client-1",
        client_id_unavailable_reason=None,
        method="POST",
        endpoint_template="/v1/chat/completions",
        occurred_at=NOW,
        http_status=200,
        stream_outcome="stream_failure",
        source="classifier",
        reason_code="rejection",
        error_code="field_too_large",
        error_param="messages[0].content",
        positions={"line": 3, "namespace_index": 2},
        counts={
            "count": 5,
            "max_output_tokens": 1_500_000,
            "context_window_tokens": 1_050_000,
        },
        limits={
            "max_input_tokens": 900_000,
            "absolute_max_output_tokens": 2_000_000,
        },
        gateway_key_id=uuid.uuid4(),
        route_id=uuid.uuid4(),
        route_pattern="/v1/chat/completions",
        deployment_revision=None,
        estimated_input_tokens=12,
        output_allowance_tokens=1_500_000,
        context_window_tokens=1_050_000,
        replay_error_code=None,
        recorded_at=NOW,
    )
    base.update(overrides)
    return RequestDiagnosticRecord(**base)


class _State:
    """Per-test fake diagnostics service + call record."""

    def __init__(self) -> None:
        self.status_result = DiagnosticsStatus(
            recording_enabled=True,
            retention_seconds=604800,
            max_records=1_000_000,
            write_timeout_ms=100,
            store_available=True,
            retained_records=2,
            oldest_occurred_at=NOW - timedelta(days=2),
            newest_occurred_at=NOW,
        )
        self.lookup_result: DiagnosticLookupResult | Exception = DiagnosticLookupResult(
            outcome=DiagnosticLookupOutcome.NOT_FOUND,
            namespace=DiagnosticsNamespace.ANY,
        )
        self.choices_result: DiagnosticIdChoiceResult | Exception = (
            DiagnosticIdChoiceResult(choices=(), cutoff=NOW, store_available=True)
        )
        self.cleanup_result: DiagnosticsCleanupResult | Exception = (
            DiagnosticsCleanupResult(deleted_count=3, store_available=True)
        )
        self.resolve_calls: list[tuple[str, DiagnosticsNamespace]] = []
        self.choices_calls: list[dict[str, Any]] = []
        self.cleanup_calls: list[dict[str, Any]] = []

    async def status(self) -> DiagnosticsStatus:
        if isinstance(self.status_result, Exception):
            raise self.status_result
        return self.status_result

    async def resolve(self, lookup_id: str, *, namespace: DiagnosticsNamespace):
        self.resolve_calls.append((lookup_id, namespace))
        if isinstance(self.lookup_result, Exception):
            raise self.lookup_result
        return self.lookup_result

    async def lookup_choices(self, *, namespace, query=None, selected=()):
        self.choices_calls.append(
            {"namespace": namespace, "query": query, "selected": tuple(selected)}
        )
        if isinstance(self.choices_result, Exception):
            raise self.choices_result
        return self.choices_result

    async def cleanup_audited(self, *, actor_admin_user_id, reason):
        self.cleanup_calls.append(
            {"actor_admin_user_id": actor_admin_user_id, "reason": reason}
        )
        if isinstance(self.cleanup_result, Exception):
            raise self.cleanup_result
        return self.cleanup_result


@pytest.fixture()
def state() -> _State:
    return _State()


@pytest.fixture()
def client(monkeypatch, state: _State) -> TestClient:
    app = _app()
    app.state.upstream_llm_profiles = {}
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
    monkeypatch.setattr(ops, "_diagnostics_service", lambda request: state)
    tc = TestClient(app)
    tc.cookies.set("slaif_admin_session", "session-plaintext")
    return tc


def _lookup(client: TestClient, **extra: Any) -> TestClient:
    return client


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def test_index_lists_both_operations(client: TestClient) -> None:
    response = client.get("/admin/operations/")
    assert response.status_code == 200
    assert "/admin/operations/diagnostics" in response.text
    assert "/admin/operations/process-configuration" in response.text


def test_diagnostics_page_renders_status_lookup_and_cleanup(
    client: TestClient,
) -> None:
    response = client.get("/admin/operations/diagnostics")
    assert response.status_code == 200
    assert "Enabled" in response.text
    assert "604800 seconds" in response.text
    # The ONE integrated picker control (kind-specific POST lookup).
    assert "diagnostic_request_id" in response.text
    assert 'name="lookup_id"' in response.text
    assert 'name="lookup_namespace"' in response.text
    assert "data-initial-options" in response.text
    # Associated help on the actual controls.
    assert "lookup-id-help" in response.text
    assert "lookup-namespace-help" in response.text
    assert "cleanup-confirm-help" in response.text
    # no-store on the rendered diagnostics page
    assert response.headers["cache-control"].startswith("no-store")


def test_diagnostics_page_unauthenticated_is_303_no_html(
    client: TestClient,
) -> None:
    client.cookies.clear()
    response = client.get(
        "/admin/operations/diagnostics", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


# ---------------------------------------------------------------------------
# Lookup outcomes
# ---------------------------------------------------------------------------


def test_lookup_found_renders_safe_facts_and_visible_failures(
    client: TestClient, state: _State,
) -> None:
    state.lookup_result = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.FOUND,
        namespace=DiagnosticsNamespace.ANY,
        record=_record(),
        match_count=1,
    )
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "gw-x", "lookup_namespace": "any"},
    )
    assert response.status_code == 200
    assert state.resolve_calls == [("gw-x", DiagnosticsNamespace.ANY)]
    # wire-200 stream_failure is visibly a failure
    assert "stream FAILED" in response.text
    assert "this is a failure, not a success" in response.text
    # readable labelled numeric facts (no dict reprs)
    assert "line: 3 · namespace_index: 2" in response.text
    assert "max_output_tokens: 1.5M tokens (1,500,000)" in response.text
    assert "max_input_tokens: 0.9M tokens (900,000)" in response.text
    # every token-named key renders M tokens (visible), not a raw count
    assert "context_window_tokens: 1.05M tokens (1,050,000)" in response.text
    assert "absolute_max_output_tokens: 2M tokens (2,000,000)" in response.text
    assert "{'count':" not in response.text
    assert "{'max_input_tokens':" not in response.text
    # token facts: visible M + exact raw detail
    assert 'title="1,050,000 tokens"' in response.text
    # unavailable historical module identity: explicitly not recorded
    assert "Deployment revision</dt><dd>not recorded</dd>" in response.text
    # explicit client module identity row (no current-key inference)
    assert "Client module identity" in response.text


def test_lookup_ambiguous_renders_candidate_table(client: TestClient, state: _State) -> None:
    state.lookup_result = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.AMBIGUOUS,
        namespace=DiagnosticsNamespace.ANY,
        match_count=120,
        candidates=(
            DiagnosticDisambiguationCandidate(
                gateway_request_id="gw-a",
                occurred_at=NOW,
                matched_namespace="client",
            ),
            DiagnosticDisambiguationCandidate(
                gateway_request_id="gw-b",
                occurred_at=NOW,
                matched_namespace="gateway",
            ),
        ),
        overflow=True,
    )
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "dup", "lookup_namespace": "any"},
    )
    assert response.status_code == 200
    assert "120 retained row(s)" in response.text
    assert "narrow the namespace" in response.text
    assert "gw-a" in response.text and "gw-b" in response.text
    # per-candidate server-rendered resolve forms (gateway namespace)
    assert 'name="lookup_id" value="gw-a"' in response.text
    assert 'name="lookup_namespace" value="gateway"' in response.text


def test_lookup_not_found_and_unavailable(client: TestClient, state: _State) -> None:
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "missing", "lookup_namespace": "any"},
    )
    assert "No retained record matches" in response.text

    state.lookup_result = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.UNAVAILABLE,
        namespace=DiagnosticsNamespace.ANY,
        reason="store_unavailable",
    )
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "missing", "lookup_namespace": "any"},
    )
    assert "store is unavailable" in response.text


def test_lookup_namespace_scoping(client: TestClient, state: _State) -> None:
    client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "x", "lookup_namespace": "client"},
    )
    assert state.resolve_calls == [("x", DiagnosticsNamespace.CLIENT)]


# ---------------------------------------------------------------------------
# Input canaries (refusal / withholding, no echo anywhere)
# ---------------------------------------------------------------------------


def test_lookup_credential_shaped_id_refused_without_echo(
    client: TestClient, state: _State,
) -> None:
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": CRED_CANARY,
              "lookup_namespace": "any"},
    )
    assert response.status_code == 200
    assert state.resolve_calls == []  # never reaches the service
    assert CRED_CANARY not in response.text
    assert "No retained record matches" in response.text


def test_lookup_current_cookie_alias_refused_without_echo(
    client: TestClient, state: _State,
) -> None:
    # The opaque cookie value fits the safe ID grammar: the grammar alone
    # is insufficient; the incoming-alias guard must withhold it.
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": COOKIE_CANARY,
              "lookup_namespace": "any"},
    )
    assert state.resolve_calls == []
    assert COOKIE_CANARY not in response.text
    assert "No retained record matches" in response.text


def test_lookup_prefill_ignores_unsafe_values(client: TestClient, state: _State) -> None:
    response = client.get(
        "/admin/operations/diagnostics?lookup="
        f"{_urllib_quote(CRED_CANARY)}&namespace=any"
    )
    assert CRED_CANARY not in response.text
    # safe prefill is applied
    response = client.get(
        "/admin/operations/diagnostics?lookup=gw-pre&namespace=client"
    )
    assert 'value="gw-pre"' in response.text


def _urllib_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value)


def test_lookup_blank_is_form_error(client: TestClient, state: _State) -> None:
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "  ", "lookup_namespace": "any"},
    )
    assert state.resolve_calls == []
    assert "Enter a diagnostic request ID." in response.text


# ---------------------------------------------------------------------------
# Picker POST lookup (kind-specific): transport, bounds, aliases
# ---------------------------------------------------------------------------


def _choices_payload(**extra: Any) -> dict[str, Any]:
    payload = {
        "csrf_token": CSRF,
        "kind": "diagnostic_request_id",
        "namespace": "any",
    }
    payload.update(extra)
    return payload


def test_choices_returns_bounded_safe_json(client: TestClient, state: _State) -> None:
    state.choices_result = DiagnosticIdChoiceResult(
        choices=(
            DiagnosticIdChoice(id="c-1", namespace="client", recorded_at=NOW),
            DiagnosticIdChoice(id="gw-2", namespace="gateway", recorded_at=NOW),
        ),
        cutoff=NOW - timedelta(days=7),
        store_available=True,
    )
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(q="c", selected=["c-1"]),
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
    body = response.json()
    assert body["kind"] == "diagnostic_request_id"
    assert body["limit"] == DIAGNOSTIC_LOOKUP_BOUND == 100
    assert body["store_available"] is True
    assert {c["id"] for c in body["choices"]} == {"c-1", "gw-2"}
    assert state.choices_calls[-1] == {
        "namespace": DiagnosticsNamespace.ANY, "query": "c", "selected": ("c-1",)
    }
    # the query is never echoed
    assert "c-1" in body["choices"][0]["id"]


def test_choices_query_never_echoed(client: TestClient, state: _State) -> None:
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(q="querycanary-xyz"),
    )
    assert response.status_code == 200
    assert "querycanary-xyz" not in response.text


def test_choices_query_over_bound_refused(client: TestClient, state: _State) -> None:
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(q="q" * 201),
    )
    assert response.status_code == 400
    assert "200" in response.json()["detail"]
    assert response.headers["cache-control"].startswith("no-store")
    assert state.choices_calls == []


def test_choices_selected_raw_count_bound_before_dedup(
    client: TestClient, state: _State,
) -> None:
    # 101 IDENTICAL submitted values must be refused at the raw repeat
    # count (before cleaning/dedup), not after.
    data = _choices_payload()
    data["selected"] = ["c-1"] * 101
    response = client.post("/admin/operations/diagnostics/choices", data=data)
    assert response.status_code == 400
    assert state.choices_calls == []
    # exactly 100 is accepted
    data["selected"] = ["c-1"] * 100
    response = client.post("/admin/operations/diagnostics/choices", data=data)
    assert response.status_code == 200


def test_choices_selected_value_bound_from_service(client: TestClient, state: _State) -> None:
    state.choices_result = ValueError("choice_selected_over_bound")
    data = _choices_payload()
    data["selected"] = [f"c-{i}" for i in range(101)]
    response = client.post("/admin/operations/diagnostics/choices", data=data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Too many selected values."


def test_choices_unsafe_selected_value_refused(client: TestClient, state: _State) -> None:
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(selected=["bad value!"]),
    )
    assert response.status_code == 400
    assert state.choices_calls == []


def test_choices_known_alias_query_and_selected_refused(
    client: TestClient, state: _State,
) -> None:
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(q=COOKIE_CANARY),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Search value withheld."
    assert COOKIE_CANARY not in response.text
    assert state.choices_calls == []
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(selected=[COOKIE_CANARY]),
    )
    assert response.status_code == 400
    assert state.choices_calls == []


def test_choices_retained_alias_value_withheld_from_output(
    client: TestClient, state: _State,
) -> None:
    # Output-side: a RETAINED choice equal to the current incoming cookie
    # is withheld from the JSON (input checks alone are insufficient).
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    state.choices_result = DiagnosticIdChoiceResult(
        choices=(
            DiagnosticIdChoice(id=COOKIE_CANARY, namespace="client", recorded_at=NOW),
            DiagnosticIdChoice(id="c-ok", namespace="client", recorded_at=NOW),
        ),
        cutoff=NOW,
        store_available=True,
    )
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert COOKIE_CANARY not in response.text
    assert {c["id"] for c in body["choices"]} == {"c-ok"}


def test_choices_store_unavailable_is_distinct_503(client: TestClient, state: _State) -> None:
    state.choices_result = DiagnosticIdChoiceResult(
        choices=(), cutoff=NOW, store_available=False
    )
    response = client.post(
        "/admin/operations/diagnostics/choices", data=_choices_payload()
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Diagnostics store unavailable."
    assert response.headers["cache-control"].startswith("no-store")


def test_choices_unknown_kind_and_invalid_namespace(
    client: TestClient, state: _State,
) -> None:
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(kind="owner"),
    )
    assert response.status_code == 400
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(namespace="bogus"),
    )
    assert response.status_code == 400


def test_choices_auth_and_csrf(client: TestClient, state: _State) -> None:
    # unauthenticated: 303 login (no JSON, no echo, no-store)
    client.cookies.clear()
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["cache-control"].startswith("no-store")
    client.cookies.set("slaif_admin_session", "session-plaintext")
    # wrong CSRF: fixed 400 JSON, no-store, no service call
    response = client.post(
        "/admin/operations/diagnostics/choices",
        data=_choices_payload(csrf_token="wrong"),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid CSRF token."
    assert response.headers["cache-control"].startswith("no-store")
    assert state.choices_calls == []


# ---------------------------------------------------------------------------
# Lookup auth/CSRF
# ---------------------------------------------------------------------------


def test_lookup_auth_and_csrf_denials(client: TestClient, state: _State) -> None:
    client.cookies.clear()
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "x", "lookup_namespace": "any"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set("slaif_admin_session", "session-plaintext")
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": "wrong", "lookup_id": "x", "lookup_namespace": "any"},
    )
    assert response.status_code == 400
    assert state.resolve_calls == []
    # invalid namespace: fixed safe 400
    response = client.post(
        "/admin/operations/diagnostics/lookup",
        data={"csrf_token": CSRF, "lookup_id": "x", "lookup_namespace": "bogus"},
    )
    assert response.status_code == 400
    assert "Invalid namespace." in response.text


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def test_cleanup_success_audited_once_with_actor_and_reason(
    client: TestClient, state: _State,
) -> None:
    state.cleanup_result = DiagnosticsCleanupResult(deleted_count=3, store_available=True)
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": "nightly drain"},
    )
    assert response.status_code == 200
    assert state.cleanup_calls == [
        {"actor_admin_user_id": ADMIN_ID, "reason": "nightly drain"}
    ]
    assert "deleted 3 expired" in response.text


def test_cleanup_zero_delete_audited_once(client: TestClient, state: _State) -> None:
    state.cleanup_result = DiagnosticsCleanupResult(deleted_count=0, store_available=True)
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": "sweep"},
    )
    assert len(state.cleanup_calls) == 1
    assert "deleted 0 expired" in response.text


def test_cleanup_batch_limit_note(client: TestClient, state: _State) -> None:
    state.cleanup_result = DiagnosticsCleanupResult(deleted_count=1000, store_available=True)
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": "sweep"},
    )
    assert "another run may be needed" in response.text


def test_cleanup_unconfirmed_failure_wording(client: TestClient, state: _State) -> None:
    state.cleanup_result = DiagnosticsCleanupResult(
        deleted_count=0, store_available=False, reason="store_unavailable"
    )
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": "sweep"},
    )
    assert "outcome unconfirmed" in response.text
    assert "Nothing was deleted" not in response.text
    assert "diagnostics_expired_cleanup" in response.text


def test_cleanup_denials(client: TestClient, state: _State) -> None:
    # no confirmation: no service call
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "reason": "x"},
    )
    assert state.cleanup_calls == []
    assert "Confirm the cleanup" in response.text
    # blank reason
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": "   "},
    )
    assert state.cleanup_calls == []
    assert "reason is required" in response.text
    # over-bound reason: fixed message, no service call
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": "r" * 513},
    )
    assert state.cleanup_calls == []
    assert "r" * 513 not in response.text
    # wrong CSRF
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": "wrong", "confirm": "1", "reason": "x"},
    )
    assert response.status_code == 400
    assert state.cleanup_calls == []


def test_cleanup_reason_incoming_alias_refused_before_service(
    client: TestClient, state: _State,
) -> None:
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1", "reason": COOKIE_CANARY},
    )
    assert state.cleanup_calls == []
    assert "Reason withheld" in response.text
    assert COOKIE_CANARY not in response.text
    # embedded alias in a longer reason is withheld as well
    response = client.post(
        "/admin/operations/diagnostics/cleanup",
        data={"csrf_token": CSRF, "confirm": "1",
              "reason": f"drain {COOKIE_CANARY} tail"},
    )
    assert state.cleanup_calls == []
    assert "Reason withheld" in response.text


# ---------------------------------------------------------------------------
# Process configuration page
# ---------------------------------------------------------------------------


def test_process_configuration_45_allowlist_and_api_scope(
    client: TestClient,
) -> None:
    response = client.get("/admin/operations/process-configuration")
    assert response.status_code == 200
    # HTML-autoescaped copy: the visible text is asserted decoded, so a
    # legitimate &#39; (e.g. "process's") does not break exact wording.
    html = unescape(response.text)
    # exact 45 allowlist, every name present
    assert html.count("data-sort-value=") >= 45
    for name in CONFIG_INSPECTION_ALLOWLIST:
        assert f"<code>{name}</code>" in html
    # API scope wording (not the CLI copy)
    assert "CURRENT API process" in html
    assert "CURRENT CLI process" not in html
    # API limitations list rendered
    for item in API_PROCESS_LIMITATIONS:
        assert item in html
    for item in INSPECTION_LIMITATIONS:
        if item in API_PROCESS_LIMITATIONS:
            continue  # shared verbatim wording, present by design
        assert item not in html
    assert f"<code>{__version__}</code>" in html
    # no environment dump: non-allowlisted env names never appear
    for env_name in ("DATABASE_URL", "REDIS_URL", "ADMIN_SESSION_SECRET",
                     "GATEWAY_KEY_PREFIX", "SMTP_HOST"):
        assert env_name not in html
    # revision honesty when undeclared
    assert "not recorded" in html


def test_process_configuration_visible_quantity_formatting(
    client: TestClient,
) -> None:
    settings = _settings(
        DEFAULT_MAX_OUTPUT_TOKENS=1_500_000,
        HARD_MAX_OUTPUT_TOKENS=1_500_000,
        DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=900_000,
        LAZY_THROTTLING_MAX_WAIT_SECONDS=120,
    )
    app = _app(settings)
    app.state.upstream_llm_profiles = {}
    admin_user = AdminUser(
        id=ADMIN_ID, email="a@e.org", display_name="A",
        password_hash="h", role="admin", is_active=True,
    )
    admin_session = AdminSession(
        id=SESSION_ID, admin_user_id=ADMIN_ID, session_token_hash="s",
        csrf_token_hash="c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        from slaif_gateway.services.admin_session_service import (
            AdminSessionContext,
        )

        return AdminSessionContext(
            admin_user=admin_user, admin_session=admin_session
        )

    tc = TestClient(app)
    tc.cookies.set("slaif_admin_session", "session-plaintext")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AdminSessionService, "validate_admin_session",
                   validate_admin_session)
        mp.setattr(AdminSessionService, "verify_session_csrf_token",
                   lambda self, row, tok: tok == CSRF)

        async def _refresh_1(self, admin_session_id=None):
            return CSRF

        mp.setattr(AdminSessionService, "refresh_csrf_token", _refresh_1)

        async def _noop(*a, **kw):  # pragma: no cover - not called
            return None

        mp.setattr(ops, "_diagnostics_service", lambda request: _State())
        response = tc.get("/admin/operations/process-configuration")
    assert response.status_code == 200
    html = response.text
    # visible M tokens for token quantities (not only a tooltip)
    assert "1.5M tokens" in html
    assert "0.9M tokens/minute" in html
    # grouped display for other numeric quantities
    assert "120</td>" in html or ">120<" in html
    # exact raw values stay as sort keys and titles
    assert 'data-sort-value="1500000"' in html
    assert 'title="1500000 tokens"' in html
    assert 'title="900000 tokens/minute or none"' in html


def test_process_configuration_profile_snapshot_startup_only(
    client: TestClient, tmp_path: Path,
) -> None:
    profile_file = tmp_path / "profiles-211.json"
    profile_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "unit-profile",
                        "revision": 7,
                        "instruction_placement": "preserve",
                        "tool_encoding": "preserve",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # Explicit safe mode: the loader refuses group/world-writable
    # external profile files (umask here is 0002, so 0664 would be
    # rejected).
    os.chmod(profile_file, 0o644)
    settings = _settings(UPSTREAM_LLM_PROFILES_FILE=str(profile_file))
    app = _app(settings)
    # The file changes AFTER startup: the page must still show the
    # startup-validated snapshot (never re-read at request time).
    profile_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "unit-profile",
                        "revision": 8,
                        "instruction_placement": "preserve",
                        "tool_encoding": "native_vllm",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(profile_file, 0o644)
    try:
        admin_user = AdminUser(
            id=ADMIN_ID, email="a@e.org", display_name="A",
            password_hash="h", role="admin", is_active=True,
        )
        admin_session = AdminSession(
            id=SESSION_ID, admin_user_id=ADMIN_ID, session_token_hash="s",
            csrf_token_hash="c",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        admin_session.admin_user = admin_user

        async def validate_admin_session(self, **kwargs):
            from slaif_gateway.services.admin_session_service import (
                AdminSessionContext,
            )

            return AdminSessionContext(
                admin_user=admin_user, admin_session=admin_session
            )

        tc = TestClient(app)
        tc.cookies.set("slaif_admin_session", "session-plaintext")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(AdminSessionService, "validate_admin_session",
                       validate_admin_session)
            mp.setattr(AdminSessionService, "verify_session_csrf_token",
                       lambda self, row, tok: tok == CSRF)

            async def _refresh_2(self, admin_session_id=None):
                return CSRF

            mp.setattr(AdminSessionService, "refresh_csrf_token", _refresh_2)
            response = tc.get("/admin/operations/process-configuration")
    finally:
        llm_profiles.load_profiles.cache_clear()
        llm_profiles.bootstrap_upstream_llm_profiles("")

    assert response.status_code == 200
    html = response.text
    # startup snapshot: revision 7 + preserve/preserve
    assert "<td><code>unit-profile</code></td>" in html
    assert "revision 7" not in html  # revision is a plain number cell
    assert "<td data-sort-value=\"7\">7</td>" in html
    assert "native_vllm" not in html  # the later file change is not re-read
    # the exact JSON selector object (version / profile / revision / sha256)
    import re

    match = re.search(r'<code>(\{.*?\})</code>', html, flags=re.DOTALL)
    assert match is not None
    selector = json.loads(match.group(1))
    assert set(selector) == {"version", "profile", "revision", "sha256"}
    assert selector["version"] == 1
    assert selector["profile"] == "unit-profile"
    assert selector["revision"] == 7


def test_process_configuration_revision_withheld_for_alias(
    client: TestClient,
) -> None:
    settings = _settings(
        REQUEST_CAPTURE_DEPLOYED_REVISION=COOKIE_CANARY,
        REQUEST_CAPTURE_REVISION_PROVENANCE="safe-provenance",
    )
    app = _app(settings)
    app.state.upstream_llm_profiles = {}
    admin_user = AdminUser(
        id=ADMIN_ID, email="a@e.org", display_name="A",
        password_hash="h", role="admin", is_active=True,
    )
    admin_session = AdminSession(
        id=SESSION_ID, admin_user_id=ADMIN_ID, session_token_hash="s",
        csrf_token_hash="c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user
    tc = TestClient(app)
    tc.cookies.set("slaif_admin_session", COOKIE_CANARY)
    with pytest.MonkeyPatch.context() as mp:
        async def validate_admin_session(self, **kwargs):
            from slaif_gateway.services.admin_session_service import (
                AdminSessionContext,
            )

            return AdminSessionContext(
                admin_user=admin_user, admin_session=admin_session
            )

        mp.setattr(AdminSessionService, "validate_admin_session",
                   validate_admin_session)
        mp.setattr(AdminSessionService, "verify_session_csrf_token",
                   lambda self, row, tok: tok == CSRF)

        async def _refresh_3(self, admin_session_id=None):
            return CSRF

        mp.setattr(AdminSessionService, "refresh_csrf_token", _refresh_3)
        response = tc.get("/admin/operations/process-configuration")
    assert response.status_code == 200
    # the cookie value is withheld from the revision display
    assert COOKIE_CANARY not in response.text
    # the safe provenance still renders
    assert "safe-provenance" in response.text


# ---------------------------------------------------------------------------
# Service-layer units (no HTTP)
# ---------------------------------------------------------------------------


def test_configuration_inspection_scopes_and_cli_default_unchanged() -> None:
    settings = _settings()
    cli = inspect_process_configuration(settings)
    api = inspect_process_configuration(settings, process_scope="api")
    assert PROCESS_SCOPES == ("cli", "api")
    cli_config = cli["config"]
    api_config = api["config"]
    # CLI keeps the exact existing wording
    assert cli_config["limitations"][0] == (
        "snapshot is the CURRENT CLI process's cached Settings, not live "
        "API/worker state"
    )
    assert "this command" in cli_config["limitations"][-1]
    # API uses its local wording (no CLI copy)
    assert api_config["limitations"][0] == (
        "snapshot is the CURRENT API process's cached Settings, not "
        "worker/scheduler or reverse-proxy state"
    )
    assert not any("CLI" in item for item in api_config["limitations"])
    # same 45 values/sources in both scopes
    assert len(cli_config["settings"]) == len(api_config["settings"]) == 45
    for name in CONFIG_INSPECTION_ALLOWLIST:
        assert cli_config["settings"][name]["value"] == (
            api_config["settings"][name]["value"]
        )
    with pytest.raises(ValueError, match="unknown_process_scope"):
        inspect_process_configuration(settings, process_scope="worker")
    # corrected consumer-accurate meanings
    assert "scalar string input" in setting_meaning(
        "RESPONSES_MAX_INPUT_TEXT_BYTES"
    )[1]
    assert "before decoding" in setting_meaning("CHAT_MAX_FILE_DATA_BYTES")[1]
    assert "text-part bytes" in setting_meaning(
        "CHAT_MAX_MESSAGE_CONTENT_BYTES"
    )[1]
    assert setting_meaning("NOT_A_SETTING") is None
