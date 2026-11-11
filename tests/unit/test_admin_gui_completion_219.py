"""Focused 219-a GUI completion seams (bounded calibration + changed guidance).

The whole-field guidance inventory stays in
tests/unit/test_admin_usability_inventory.py; this module covers only the
bounded seams changed by 219-a:

- the safe no-store calibration summary/proposal JSON attachment (typed
  projection, CLI-compatible value law, auth/gate/error paths, no writes);
- the non-rotating attachment CSRF contract: a download must not
  invalidate the still-displayed preview page's form token;
- the corrected preview-page copy and its current-data download link;
- rendered key-detail guidance associations (unique help ids, every
  aria-describedby target defined, rc-help span for the record choice);
- the create-page visual consolidation (policy source section before the
  guided request-policy selector).

All seams are preauthorized fakes at the service/CSRF boundary; no DB,
network, or browser is involved.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
)
from slaif_gateway.services.calibration_summary_service import (
    CalibrationSummaryError,
)
from tests.unit.test_admin_key_create_routes import _patch_options
from tests.unit.test_admin_keys_routes import (
    _admin_session,
    _admin_user,
    _app,
    _calibration_preview,
    _login,
    _trusted_detail,
)

_SUMMARY_PATH = "slaif_gateway.services.calibration_summary_service.CalibrationSummaryService.summarize_calibration_key_usage"
_GET_DETAIL = "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail"
_CREATE_TEMPLATE = (
    "slaif_gateway.services.key_template_service.KeyTemplateService.create_from_calibration_proposal"
)
_VALIDATE_SESSION = (
    "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session"
)
_REFRESH_CSRF = (
    "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token"
)
_VERIFY_CSRF = (
    "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token"
)


def _patch_get_detail(monkeypatch, key) -> None:
    async def get_key_detail(self, gateway_key_id):
        assert gateway_key_id == key.id
        return key

    monkeypatch.setattr(_GET_DETAIL, get_key_detail)


def test_calibration_summary_json_download_serves_typed_payload(monkeypatch) -> None:
    key = _trusted_detail()
    received: dict[str, object] = {}

    async def summarize_calibration_key_usage(self, **kwargs):
        received.update(kwargs)
        return _calibration_preview(key.id)

    monkeypatch.setattr(_SUMMARY_PATH, summarize_calibration_key_usage)
    _patch_get_detail(monkeypatch, key)
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(
        f"/admin/keys/{key.id}/calibration/summary.json",
        params={
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-02-01T00:00:00Z",
            "multiplier": "2.5",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="slaif-calibration-summary-{key.id}.json"'
    )
    assert "no-store" in response.headers["cache-control"]
    assert "no-cache" in response.headers["cache-control"]
    assert response.headers["pragma"] == "no-cache"
    # A GET attachment must not rotate or re-issue the session cookie.
    assert "set-cookie" not in {k.lower() for k in response.headers}

    # Same service and input validation as the preview, re-run at download:
    # ISO+Z datetimes become aware UTC, multiplier is a Decimal.
    assert received["gateway_key_id"] == key.id
    assert received["start_at"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert received["end_at"] == datetime(2026, 2, 1, tzinfo=UTC)
    assert received["multiplier"] == Decimal("2.5")

    payload = json.loads(response.text)
    assert set(payload) == {"summary", "proposal", "is_empty", "warnings"}
    assert payload["is_empty"] is False
    assert payload["warnings"] == []

    summary = payload["summary"]
    proposal = payload["proposal"]
    # CLI-compatible value law: UUIDs as text, Decimals as exact text,
    # datetimes as ISO-8601, tuples as JSON arrays.
    assert summary["gateway_key_id"] == str(key.id)
    assert summary["owner_email"] == "ada@example.org"
    assert summary["time_window_start"] is None
    assert summary["total_slaif_calculated_cost"] == "0.001000000"
    assert summary["observed_endpoints"] == ["/v1/chat/completions"]
    assert proposal["source_gateway_key_id"] == str(key.id)
    assert proposal["proposed_cost_limit_eur"] == "0.002000000"
    assert proposal["multiplier"] == "2"
    parsed_window = datetime.fromisoformat(proposal["source_time_window_start"])
    assert parsed_window.tzinfo is not None
    # No key material, provider credentials, or raw request content.
    assert "sk-provider-secret-placeholder" not in response.text
    assert "Authorization: Bearer" not in response.text
    assert "session_token" not in response.text
    assert response.text.endswith("\n")


def test_calibration_summary_json_download_gate_and_error_paths(monkeypatch) -> None:
    key = _trusted_detail()
    calls: list[object] = []
    created: list[object] = []

    async def summarize_calibration_key_usage(self, **kwargs):
        calls.append(kwargs)
        raise CalibrationSummaryError("Calibration window has no usage rows.")

    monkeypatch.setattr(_SUMMARY_PATH, summarize_calibration_key_usage)
    _patch_get_detail(monkeypatch, key)

    # Unauthenticated: straight redirect to login, service never touched.
    client = TestClient(_app())
    response = client.get(
        f"/admin/keys/{key.id}/calibration/summary.json",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert calls == []

    _login(monkeypatch, client)

    # Invalid key id in the path: safe 404 before any service call.
    response = client.get("/admin/keys/not-a-uuid/calibration/summary.json")
    assert response.status_code == 404
    assert calls == []

    # Unparseable multiplier: fixed 400.
    response = client.get(f"/admin/keys/{key.id}/calibration/summary.json", params={"multiplier": "abc"})
    assert response.status_code == 400
    assert "invalid decimal" in response.text

    # Domain summary error: safe fixed 400 message.
    response = client.get(f"/admin/keys/{key.id}/calibration/summary.json", params={"multiplier": "2"})
    assert response.status_code == 400
    assert "Calibration window has no usage rows." in response.text
    assert len(calls) == 1

    # The attachment is read-only: no template/key mutation path runs.
    assert created == []


def test_calibration_download_does_not_rotate_displayed_form_csrf(monkeypatch) -> None:
    key = _trusted_detail()
    state: dict[str, object] = {"issued": [], "current": None}
    admin_user = _admin_user()

    async def validate_admin_session(self, **kwargs):
        session = _admin_session(admin_user)
        return AdminSessionContext(admin_user=admin_user, admin_session=session)

    async def refresh_csrf_token(self, **kwargs):
        token = f"csrf-turn-{len(state['issued']) + 1}"
        state["issued"].append(token)
        state["current"] = token
        return token

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return bool(csrf_token) and csrf_token == state["current"]

    monkeypatch.setattr(_VALIDATE_SESSION, validate_admin_session)
    monkeypatch.setattr(_REFRESH_CSRF, refresh_csrf_token)
    monkeypatch.setattr(_VERIFY_CSRF, verify_session_csrf_token)

    created: list[dict[str, object]] = []
    template_id = uuid.uuid4()

    async def create_from_calibration_proposal(self, **kwargs):
        created.append(kwargs)
        return SimpleNamespace(template=SimpleNamespace(id=template_id))

    monkeypatch.setattr(_CREATE_TEMPLATE, create_from_calibration_proposal)

    async def summarize_calibration_key_usage(self, **kwargs):
        return _calibration_preview(key.id)

    monkeypatch.setattr(_SUMMARY_PATH, summarize_calibration_key_usage)
    _patch_get_detail(monkeypatch, key)

    client = TestClient(_app())
    client.cookies.set("slaif_admin_session", "session-plaintext")

    # 1) The rendered calibration page issues exactly one form token.
    response = client.get(f"/admin/keys/{key.id}/calibration")
    assert response.status_code == 200
    assert state["issued"] == ["csrf-turn-1"]
    assert 'name="csrf_token" value="csrf-turn-1"' in response.text

    # 2) The JSON download authenticates but must NOT rotate the token.
    download = client.get(
        f"/admin/keys/{key.id}/calibration/summary.json", params={"multiplier": "2"}
    )
    assert download.status_code == 200
    assert state["issued"] == ["csrf-turn-1"]
    assert state["current"] == "csrf-turn-1"

    # 3) The still-displayed form token must still validate: create
    # succeeds and redirects to the created template.
    response = client.post(
        f"/admin/keys/{key.id}/calibration/create-template",
        data={
            "csrf_token": "csrf-turn-1",
            "start_at": "",
            "end_at": "",
            "multiplier": "2",
            "template_name": "Workshop template",
            "template_description": "",
            "validity_days_default": "",
            "email_delivery_mode_default": "",
            "confirm_create_template": "true",
            "reason": "Reviewed calibration proposal",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/templates/{template_id}?message=template_created"
    )
    assert len(created) == 1
    assert created[0]["name"] == "Workshop template"
    assert created[0]["confirm_create_template"] is True
    assert state["issued"] == ["csrf-turn-1"]

    # 4) A token that was never issued is refused without any mutation.
    response = client.post(
        f"/admin/keys/{key.id}/calibration/create-template",
        data={
            "csrf_token": "csrf-never-issued",
            "template_name": "Never created",
            "confirm_create_template": "true",
            "reason": "Refused",
        },
    )
    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert len(created) == 1


def test_calibration_preview_page_links_current_data_download(monkeypatch) -> None:
    key = _trusted_detail()

    async def summarize_calibration_key_usage(self, **kwargs):
        assert kwargs["multiplier"] == Decimal("2")
        return _calibration_preview(key.id)

    monkeypatch.setattr(_SUMMARY_PATH, summarize_calibration_key_usage)
    monkeypatch.setattr(
        _VERIFY_CSRF,
        lambda self, admin_session, csrf_token: csrf_token == "dashboard-csrf",
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{key.id}/calibration/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-02-01T00:00:00Z",
            "multiplier": "2",
        },
    )

    assert response.status_code == 200
    # Honest copy: template creation IS supported on this page; only bulk
    # participant key creation remains future work.
    assert "bulk participant key creation remains future work" in response.text
    assert "Templates and recommendation execution are future work" not in response.text
    # The download reuses the SAME selected inputs (URL-encoded) and is
    # explicitly described as CURRENT data, not a frozen rendered copy.
    assert (
        'href="/admin/keys/'
        f"{key.id}/calibration/summary.json"
        "?start_at=2026-01-01T00%3A00%3A00Z"
        "&amp;end_at=2026-02-01T00%3A00%3A00Z"
        "&amp;multiplier=2\""
    ) in response.text
    assert "Download this preview's JSON" in response.text
    assert "not a frozen copy of this rendered preview" in response.text
    # The template-creation form and its linked help are still present.
    assert f'action="/admin/keys/{key.id}/calibration/create-template"' in response.text
    assert 'name="template_name"' in response.text
    assert 'name="confirm_create_template"' in response.text
    assert 'id="calibration-template-help"' in response.text
    assert "no-store" in response.headers["cache-control"]


def test_key_detail_guidance_ids_are_unique_and_linked(monkeypatch) -> None:
    key = _trusted_detail()
    _patch_get_detail(monkeypatch, key)
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}")
    assert response.status_code == 200
    html_text = response.text

    # Every rendered help id is unique on the page.
    help_ids = re.findall(r'\bid="([^"]*-help)"', html_text)
    assert len(help_ids) == len(set(help_ids))

    # Every aria-describedby target is defined on the rendered page.
    defined_ids = set(re.findall(r'\bid="([^"]+)"', html_text))
    describedby_refs = re.findall(r'aria-describedby="([^"]+)"', html_text)
    assert describedby_refs, "expected guidance associations on the detail page"
    for ref in describedby_refs:
        for token in ref.split():
            assert token in defined_ids, f"unlinked guidance target: {token}"

    # Every rendered -help element is actually linked to at least one
    # control (no orphaned help paragraphs).
    referenced = {token for ref in describedby_refs for token in ref.split()}
    for help_id in set(help_ids):
        assert help_id in referenced, f"orphaned help id: {help_id}"

    # The record-choice destination-ID field carries its own linked help.
    assert (
        '<span class="rc-help" id="key-ext-tool-dest-help">' in html_text
    )


def test_key_create_policy_source_precedes_guided_selector(monkeypatch) -> None:
    _patch_options(monkeypatch)
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get("/admin/keys/create")
    assert response.status_code == 200
    html_text = response.text

    # Visual consolidation: the short Policy Source section is presented
    # BEFORE the long guided request-policy selector.
    source_pos = html_text.index('id="create-policy-source-heading"')
    guided_pos = html_text.index('id="create-policy-heading"')
    assert source_pos < guided_pos

    # The guided selector keeps its single-source submission surface and
    # the new owner/cohort choices carry linked unique-ID help.
    assert 'data-policy-selector-surface' in html_text
    for help_id in ("create-owner-help", "create-cohort-help"):
        assert f'id="{help_id}"' in html_text
        assert f'aria-describedby="{help_id}"' in html_text
