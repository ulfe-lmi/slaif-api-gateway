"""212-a GUI Codex compatibility management (unit).

Fake-persistence ASGI/Jinja seams over the real admin app (the shared
Codex migration service and its repositories are faked at the module
seam where a test needs router logic only; the REAL shared Core law -
reason validation, frozen edges, identity checks, and the optional
active-tuple apply guard - runs unpatched with fake key/audit rows in
the law tests; the real HMAC review-intent helpers sign/verify every
token):

- pages: auth (303), no-store, Choose-a-key entry, ordinal-first
  qualification projection with canonical artifact links gated exactly
  like the existing route-detail handler, startup data identity
  distinct from qualification/upstream selectors, validated preset
  table, and explicit unavailable states;
- presets: exact loader bytes on the authenticated private no-store
  export, read auth that does NOT rotate the origin page CSRF and does
  NOT even touch the session last-seen stamp (touch=False), and the
  known-incoming-alias refusal (display withheld, export refused,
  canonical bytes never rewritten);
- key page: exact pin projection, finite pin-derived options (no
  rollback/migrate offered outside the Core's frozen edges), withheld
  pins re-exposed NOWHERE (no hidden raw values, no options);
- review: the shared Core reason law on the ORIGINAL string (8-200
  printable ASCII, non-whitespace, leading space legal and never
  trimmed), known-alias/credential-shape refusals BEFORE any row read,
  rollback expected-source = the key's current pin selector (the CLI's
  from-target), a source-as-target form value refused, legal-edge but
  wrong-source identity mismatch, migrate pin binding, the intended
  unavailable-active-profile guard, same-revision different-digest
  refusal, and no domain/audit writes on any dry run;
- apply: wrong CSRF / missing confirmation / wrong key / expired /
  tampered / cross-actor / wrong-purpose token refusals, the exact
  one-tuple-plus-one-audit apply, the already_at_target no-write
  repeat, the apply-worker active-registry drift refusal through the
  real shared guard, and the reviewed-bounded-facts alias recheck at
  apply time.

No database, no network, no credential loading. The native PG module
proves the real transaction/audit/preservation law; the browser module
proves the real operator flow.
"""

from __future__ import annotations

import inspect
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api import admin as admin_api
from slaif_gateway.api import admin_compatibility as compat
from slaif_gateway.api.admin_review_intent import (
    build_compatibility_review_token,
)
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE_ID
from slaif_gateway.modules.codex_profile_data import list_codex_presets
from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
    AdminSessionService,
)
from slaif_gateway.services.codex_module_upgrade import (
    CODEX_0149_V4_CLIENT_MODULE,
    UPGRADE_TARGET_CLIENT_MODULES,
    CodexModuleUpgradeResult,
)
from slaif_gateway.services.codex_qualification import CodexQualificationResult
from tests.unit.test_admin_key_actions_routes import _app

ADMIN_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
SESSION_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
KEY_ID = uuid.UUID("cccccccc-0000-4000-8000-000000000003")
OTHER_KEY_ID = uuid.UUID("dddddddd-0000-4000-8000-000000000004")
CSRF = "compat-csrf"

PIN_0149_V4 = dict(CODEX_0149_V4_CLIENT_MODULE)
PIN_0149_V5 = dict(UPGRADE_TARGET_CLIENT_MODULES["0149-v5"])
PIN_0162_V1 = dict(UPGRADE_TARGET_CLIENT_MODULES["0162-v1"])
PIN_0162_V2 = dict(UPGRADE_TARGET_CLIENT_MODULES["0162-v2"])
PIN_0162_V2_MOD = {
    "id": CODEX_0162_CLIENT_MODULE_ID,
    "version": "2",
    "fixture_sha256": PIN_0162_V2["fixture_sha256"],
}

# Opaque incoming credential value (fits a hex-ish grammar): carried as
# the current admin session cookie in the alias canaries.
COOKIE_CANARY = "SESSCANARYcookie123opaque"
CRED_CANARY = "sk-slaif-0123456789abcdefcanary"

BASE = "/admin/operations/compatibility"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def touch_log() -> list[bool | None]:
    return []


@pytest.fixture()
def client(monkeypatch, touch_log) -> TestClient:
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
        touch_log.append(kwargs.get("touch", True))
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
    tc = TestClient(app, follow_redirects=False)
    tc.cookies.set("slaif_admin_session", "session-plaintext")
    return tc


def _key_row(pin: dict[str, str] | None) -> SimpleNamespace:
    metadata: dict[str, Any] = {}
    if pin is not None:
        metadata = {"responses_policy": {"client_module": dict(pin)}}
    return SimpleNamespace(id=KEY_ID, metadata_json=metadata)


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def add_audit_log(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


class FakeKeys:
    def __init__(self, key: SimpleNamespace | None) -> None:
        self.key = key
        self.reads = 0

    async def get_gateway_key_for_update(self, key_id: uuid.UUID):
        self.reads += 1
        if self.key is not None and self.key.id == key_id:
            return self.key
        return None


@pytest.fixture()
def core(monkeypatch) -> SimpleNamespace:
    """Real shared Core law, fake key/audit rows at the repository seam."""
    state = SimpleNamespace(keys=None, audit=FakeAudit(), key=None, key_reads=0)

    class _Keys(FakeKeys):
        async def get_gateway_key_for_update(self, key_id):  # noqa: D102
            state.key_reads += 1
            if state.key is not None and state.key.id == key_id:
                return state.key
            return None

    state.keys = _Keys(None)
    monkeypatch.setattr(compat, "GatewayKeysRepository", lambda session: state.keys)
    monkeypatch.setattr(compat, "AuditRepository", lambda session: state.audit)
    return state


def _qualification_result(
    *,
    ready: bool,
    profile_id: str | None = "slaif-codex-0.147-v1",
    metadata_version: int | None = 1,
    client_module_id: str | None = "codex-0.149-responses-v1",
    client_module_version: str | None = "4",
    reasons: tuple[str, ...] = (),
    route_id: uuid.UUID | None = None,
) -> CodexQualificationResult:
    return CodexQualificationResult(
        state="protocol_qualified" if ready else "not_ready",
        requested_model="gpt-5.6-sol",
        provider="openai",
        endpoint="/v1/responses",
        route_id=route_id or uuid.uuid4(),
        paired_route_id=None,
        reason_codes=reasons,
        profile_version=metadata_version,
        cli_version="0.147.0" if ready else None,
        profile=None,
        catalog_source=None,
        wire_api=None,
        real_provider_e2e=None,
        profile_id=profile_id if ready else None,
        metadata_version=metadata_version,
        provider_kind="openai" if ready else None,
        provider_display_name=None,
        client_module_id=client_module_id if ready else None,
        client_module_version=client_module_version if ready else None,
        client_module_fixture_sha256=None,
    )


@pytest.fixture()
def qual(monkeypatch) -> SimpleNamespace:
    state = SimpleNamespace(results=[])

    class _Qual:
        async def inspect(self, **_kw):
            return list(state.results)

    monkeypatch.setattr(compat, "_qualification_service", lambda session: _Qual())
    monkeypatch.setattr(compat, "render_codex_profile", _fake_render)
    return state


def _fake_render(base_url: str, profile_id: str | None = None):
    # Link-decision facts mirror the canonical handler's render exactly.
    return SimpleNamespace(
        profile_config_self_contained=False,
        model_catalog_json=None,
    )


def _review_post(
    client: TestClient,
    value: str,
    reason: str,
    *,
    pin_selector: str = "",
    from_version: str = "",
    from_digest: str = "",
    csrf: str = CSRF,
    key_id: uuid.UUID = KEY_ID,
) -> Any:
    return client.post(
        f"{BASE}/key/{key_id}/review",
        data={
            "csrf_token": csrf,
            "operation_target": value,
            "reason": reason,
            "pin_selector": pin_selector,
            "from_version": from_version,
            "from_digest": from_digest,
        },
    )


def _token_from(response: Any) -> str:
    return response.text.split('name="review_token" value="', 1)[1].split('"', 1)[0]


def _apply_post(
    client: TestClient,
    token: str,
    *,
    confirm: str = "1",
    csrf: str = CSRF,
    key_id: uuid.UUID = KEY_ID,
) -> Any:
    return client.post(
        f"{BASE}/key/{key_id}/apply",
        data={
            "csrf_token": csrf,
            "review_token": token,
            "confirm_apply": confirm,
        },
    )


def _module_review_doc(
    *,
    operation: str,
    expected_source: str,
    target: str,
    key_id: uuid.UUID = KEY_ID,
    reason: str = "unit reviewed migration",
) -> dict[str, Any]:
    return {
        "operation": operation,
        "gateway_key_id": str(key_id),
        "expected_source": expected_source,
        "target": target,
        "reason": reason,
        "source_tuple": dict(
            UPGRADE_TARGET_CLIENT_MODULES[expected_source]
            if expected_source in UPGRADE_TARGET_CLIENT_MODULES
            else CODEX_0149_V4_CLIENT_MODULE
        ),
        "target_tuple": dict(
            UPGRADE_TARGET_CLIENT_MODULES[target]
            if target in UPGRADE_TARGET_CLIENT_MODULES
            else CODEX_0149_V4_CLIENT_MODULE
        ),
    }


def _settings_secret() -> str:
    from tests.unit.test_admin_key_actions_routes import _settings

    return _settings().ADMIN_SESSION_SECRET


# ---------------------------------------------------------------------------
# Pages and auth
# ---------------------------------------------------------------------------


def test_index_unauthenticated_is_303(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get(f"{BASE}/")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert "Choose a key" not in response.text


def test_index_renders_projection_entries_and_no_store(
    client: TestClient, qual: SimpleNamespace
) -> None:
    ready_route = uuid.uuid4()
    unready_route = uuid.uuid4()
    qual.results = [
        _qualification_result(ready=True, route_id=ready_route),
        _qualification_result(
            ready=False,
            route_id=unready_route,
            reasons=("pricing_missing_responses",),
        ),
    ]
    response = client.get(f"{BASE}/")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    # Choose-a-key entry (existing key workflow owns selection/search).
    assert 'href="/admin/keys"' in response.text
    # Qualification projection with ordinal column and exact reasons.
    assert 'data-ordinal' in response.text
    assert str(ready_route) in response.text
    assert str(unready_route) in response.text
    assert "pricing_missing_responses" in response.text
    # Canonical artifact links on the READY row only (base + profile, no
    # catalog for the fake non-self-contained artifact).
    assert (
        f"/admin/routes/{ready_route}/codex-profile/profile" in response.text
    )
    assert f"/admin/routes/{ready_route}/codex-profile/base" in response.text
    assert f"/admin/routes/{ready_route}/codex-profile/catalog" not in response.text
    assert f"/admin/routes/{unready_route}/codex-profile" not in response.text
    # Startup data identity section is explicit.
    assert "API startup data identity" in response.text
    # Preset table with inspect/download links.
    assert f"{BASE}/preset/codex-0.163.0/download" in response.text
    # No filesystem paths leak to the browser.
    assert "app/slaif_gateway" not in response.text
    assert "resources/" not in response.text


def test_index_unavailable_projection_is_explicit(
    client: TestClient, qual: SimpleNamespace
) -> None:
    class _Boom:
        async def inspect(self, **_kw):
            raise RuntimeError("db down")

    qual.results = None
    import slaif_gateway.api.admin_compatibility as module

    module._qualification_service = lambda session: _Boom()
    response = client.get(f"{BASE}/")
    assert response.status_code == 200
    assert "qualification projection is unavailable" in response.text
    assert "No declared Codex routes." not in response.text


def test_index_preset_facts_alias_withheld(client: TestClient, qual) -> None:
    # A real registered preset's DIGEST equal to a known incoming
    # credential is withheld from the index display; the preset links
    # remain and the canonical export bytes are unchanged.
    qual.results = []
    name, _path, profile = list(list_codex_presets())[0]
    digest = str(profile.to_facts().get("digest"))
    response = client.get(f"{BASE}/", headers={"X-API-Key": digest})
    assert response.status_code == 200
    assert digest not in response.text
    assert "Withheld: matches a known credential value" in response.text
    assert f"{BASE}/preset/{name}/download" in response.text


def test_index_preset_name_alias_no_href_reexposure(
    client: TestClient, qual
) -> None:
    # A preset NAME equal to a known incoming credential: withheld in
    # the cell AND never re-exposed through the Inspect/Download hrefs.
    qual.results = []
    name, _path, _profile = list(list_codex_presets())[0]
    response = client.get(f"{BASE}/", headers={"X-API-Key": name})
    assert response.status_code == 200
    assert name not in response.text
    assert f"preset/{name}" not in response.text
    assert "Withheld: matches a known credential value" in response.text


def test_index_qualification_alias_withheld(client: TestClient, qual) -> None:
    # Requested model equal to a known incoming credential: withheld,
    # route link intact.
    route = uuid.uuid4()
    qual.results = [_qualification_result(ready=True, route_id=route)]
    response = client.get(f"{BASE}/", headers={"X-API-Key": "gpt-5.6-sol"})
    assert response.status_code == 200
    assert "gpt-5.6-sol" not in response.text
    assert "Withheld: matches a known credential value" in response.text
    assert f"/admin/routes/{route}" in response.text

    # A route ID equal to a known incoming credential: the link and the
    # canonical artifact links are dropped entirely, not just the text.
    response = client.get(f"{BASE}/", headers={"X-API-Key": str(route)})
    assert response.status_code == 200
    assert f"href=\"/admin/routes/{route}\"" not in response.text
    assert f"/admin/routes/{route}/codex-profile" not in response.text
    assert "Withheld: matches a known credential value" in response.text


# ---------------------------------------------------------------------------
# Presets: exact export, non-rotating no-touch auth, alias refusal
# ---------------------------------------------------------------------------


def test_preset_page_renders_facts_document_and_no_paths(
    client: TestClient,
) -> None:
    response = client.get(f"{BASE}/preset/codex-0.163.0")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    # The exact validated document is rendered (Jinja-escaped).
    assert "schema_version" in response.text
    assert "namespace_rules" in response.text
    assert "64 KiB" in response.text
    assert ".json" not in response.headers.get("content-disposition", "")
    # Bounded safe facts, no CLI filesystem paths.
    assert "app/slaif_gateway" not in response.text


def test_preset_download_exact_bytes_no_store_no_touch(
    client: TestClient, touch_log: list,
) -> None:
    from slaif_gateway.modules.codex_profile_data import read_codex_preset

    before = list(touch_log)
    response = client.get(f"{BASE}/preset/codex-0.163.0/download")
    assert response.status_code == 200
    assert response.content == read_codex_preset("codex-0.163.0").encode()
    assert response.headers["content-disposition"] == (
        'attachment; filename="codex-0.163.0.json"'
    )
    assert response.headers["cache-control"].startswith("no-store")
    # Fully read-only: the ONLY session validation for this download used
    # touch=False (no last-seen write) and no CSRF refresh happened.
    assert touch_log[len(before):] == [False]


def test_preset_download_unauthenticated_303_no_store(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get(f"{BASE}/preset/codex-0.163.0/download")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert response.headers["cache-control"].startswith("no-store")


def test_attachment_context_touch_default_preserved() -> None:
    # The new keyword defaults to True: existing call sites keep the old
    # (touch) behavior; only the 212 download opts into touch=False.
    signature = inspect.signature(admin_api._admin_attachment_context)
    assert signature.parameters["touch"].default is True


def test_preset_unknown_name_404(client: TestClient) -> None:
    assert (
        client.get(f"{BASE}/preset/not-a-preset").status_code == 404
    )
    assert (
        client.get(f"{BASE}/preset/not-a-preset/download").status_code == 404
    )


def test_preset_canary_withheld_display_and_refused_export(
    client: TestClient, monkeypatch
) -> None:
    document = json.dumps(
        {"schema_version": 2, "revision": 9, "marker": COOKIE_CANARY}
    )
    profile = SimpleNamespace(
        to_facts=lambda: {"revision": "9", "digest": "d" * 64}
    )

    def fake_list():
        return (("canary-preset", Path("/tmp/unused"), profile),)

    monkeypatch.setattr(compat, "read_codex_preset", lambda name: document)
    monkeypatch.setattr(compat, "list_codex_presets", fake_list)
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)

    page = client.get(f"{BASE}/preset/canary-preset")
    assert page.status_code == 200
    assert COOKIE_CANARY not in page.text
    assert "withheld" in page.text

    download = client.get(f"{BASE}/preset/canary-preset/download")
    assert download.status_code == 403
    assert COOKIE_CANARY not in download.text
    assert "refused" in download.text


# ---------------------------------------------------------------------------
# Key page: pin projection, finite options, withheld-pin safety
# ---------------------------------------------------------------------------


@pytest.fixture()
def key_detail(monkeypatch) -> SimpleNamespace:
    state = SimpleNamespace(pin=None)

    class _Detail:
        id = KEY_ID
        public_key_id = "sk-slaif-public1"
        computed_display_status = "active"
        owner_display_name = "Owner"
        owner_email = None
        key_prefix = "sk-slaif-"

        @property
        def responses_policy(self):
            if state.pin is None:
                return {"client_module": {}}
            return {"client_module": dict(state.pin)}

    async def get_key_detail(self, key_id):
        return _Detail()

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService"
        ".get_key_detail",
        get_key_detail,
    )
    return state


def _key_page(client: TestClient) -> Any:
    return client.get(f"{BASE}/key/{KEY_ID}")


def test_key_page_unauthenticated_and_unknown_uuid(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get(f"{BASE}/key/{KEY_ID}").status_code == 303
    client.cookies.set("slaif_admin_session", "session-plaintext")
    assert client.get(f"{BASE}/key/not-a-uuid").status_code == 404


def test_key_page_0149v4_offers_exact_two_upgrades(
    client: TestClient, key_detail: SimpleNamespace
) -> None:
    key_detail.pin = PIN_0149_V4
    response = _key_page(client)
    assert response.status_code == 200
    # Exact current pin, read-only.
    assert PIN_0149_V4["fixture_sha256"] in response.text
    assert "0149-v4" in response.text
    # Finite options: ONLY the two legal upgrades from 0149-v4.
    assert "module_upgrade:0149-v5" in response.text
    assert "module_upgrade:0162-v1" in response.text
    assert "module_rollback" not in response.text
    assert "migrate:" not in response.text
    # Hidden bounded facts carry the exact pin.
    assert 'name="pin_selector" value="0149-v4"' in response.text
    assert f'name="from_digest" value="{PIN_0149_V4["fixture_sha256"]}"' in response.text
    assert 'name="from_version" value="4"' in response.text
    # Bounded field help on the actual controls.
    assert "operation-target-help" in response.text
    assert "migration-reason-help" in response.text
    assert "8&ndash;200" in response.text or "8-200" in response.text


def test_key_page_0162v2_offers_rollback_and_migrate(
    client: TestClient, key_detail: SimpleNamespace
) -> None:
    key_detail.pin = PIN_0162_V2_MOD
    response = _key_page(client)
    assert response.status_code == 200
    assert "module_rollback:0162-v1" in response.text
    assert "migrate:active" in response.text
    assert "migrate:0162-v1" in response.text
    assert "migrate:0162-v2" in response.text
    # 0149-v4 is NOT a legal destination from 0162-v2.
    assert "module_rollback:0149-v4" not in response.text
    assert "module_upgrade" not in response.text


def test_key_page_no_pin_is_explicit(
    client: TestClient, key_detail: SimpleNamespace
) -> None:
    key_detail.pin = None
    response = _key_page(client)
    assert response.status_code == 200
    assert "No readable client-module binding" in response.text
    assert 'name="operation_target"' not in response.text


def test_key_page_withheld_pin_reexposed_nowhere(
    client: TestClient, key_detail: SimpleNamespace
) -> None:
    key_detail.pin = {
        "id": PIN_0149_V4["id"],
        "version": "4",
        "fixture_sha256": COOKIE_CANARY,
    }
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    response = _key_page(client)
    assert response.status_code == 200
    assert COOKIE_CANARY not in response.text
    # Withheld binding: no form at all - no options, NO hidden raw values.
    assert 'name="operation_target"' not in response.text
    assert 'name="from_digest"' not in response.text
    assert 'name="pin_selector"' not in response.text
    assert 'name="from_version"' not in response.text


# ---------------------------------------------------------------------------
# Review: shared Core reason law, alias guards, edges, migrate binding
# ---------------------------------------------------------------------------


def test_review_reason_too_short_refused_by_core_law(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0149_V4)
    response = _review_post(
        client,
        "module_upgrade:0149-v5",
        "short",
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "8-200 printable ASCII" in response.text
    # The Core reason law rejects BEFORE the row is read.
    assert core.key_reads == 0
    assert core.audit.entries == []


def test_review_reason_all_whitespace_refused(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0149_V4)
    response = _review_post(
        client,
        "module_upgrade:0149-v5",
        "        ",
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "8-200 printable ASCII" in response.text
    assert core.key_reads == 0


def test_review_reason_leading_space_preserved_verbatim(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0149_V4)
    original = " leading-space-reason-ok"
    response = _review_post(
        client,
        "module_upgrade:0149-v5",
        original,
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert response.status_code == 200
    assert "Dry run complete" in response.text
    # The ORIGINAL (untrimmed) reason is what the review binds and what
    # the apply persists: round-trip through the signed token.
    assert response.text.split(">Audit reason (verbatim, never trimmed)</dt>")[1]
    token = _token_from(response)
    apply = _apply_post(client, token)
    assert apply.status_code == 200
    assert "Applied" in apply.text
    assert core.audit.entries == [
        {
            "action": "codex_client_module_upgraded",
            "entity_type": "gateway_key",
            "entity_id": KEY_ID,
            "admin_user_id": ADMIN_ID,
            "old_values": {"client_module": PIN_0149_V4},
            "new_values": {"client_module": PIN_0149_V5},
            "note": original,
        }
    ]
    assert core.key.metadata_json["responses_policy"]["client_module"] == PIN_0149_V5


def test_review_reason_known_alias_refused_before_row_read(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0149_V4)
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    response = _review_post(
        client,
        "module_upgrade:0149-v5",
        COOKIE_CANARY,
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "matches a known incoming authentication value" in response.text
    assert COOKIE_CANARY not in response.text
    assert core.key_reads == 0
    assert core.audit.entries == []


def test_review_reason_credential_shape_refused(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0149_V4)
    response = _review_post(
        client,
        "module_upgrade:0149-v5",
        CRED_CANARY,
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert response.status_code == 400
    assert CRED_CANARY not in response.text
    assert core.key_reads == 0


def test_review_rollback_expected_source_is_current_pin(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V5)
    calls: list[dict[str, Any]] = []

    async def spy_mutate(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID,
            status="dry_run",
            action=kwargs["action"],
            source_module=PIN_0149_V5,
            target_module=PIN_0149_V4,
            changed=False,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_mutate)
    response = _review_post(
        client,
        "module_rollback:0149-v4",
        "rollback reviewed reason",
        pin_selector="0149-v5",
        from_version="5",
        from_digest=PIN_0149_V5["fixture_sha256"],
    )
    assert response.status_code == 200
    # The Core receives expected_source = the CURRENT pin (0149-v5) and
    # target = the destination (0149-v4): never a self-edge.
    assert calls[0]["expected_source"] == "0149-v5"
    assert calls[0]["target"] == "0149-v4"
    assert calls[0]["action"] == "codex_client_module_rolled_back"


def test_review_source_as_target_form_value_refused(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0149_V5)
    response = _review_post(
        client,
        "module_rollback:0149-v5",
        "rollback reviewed reason",
        pin_selector="0149-v5",
        from_version="5",
        from_digest=PIN_0149_V5["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "Choose a reviewed migration operation and target." in response.text
    assert core.key_reads == 0


def test_review_legal_edge_wrong_source_identity_mismatch(
    client: TestClient, core: SimpleNamespace
) -> None:
    # 0149-v4 -> 0162-v2 is not a legal edge: the 0162-v2 upgrade expects
    # the 0162-v1 source, so the Core's identity check must refuse.
    core.key = _key_row(PIN_0149_V4)
    response = _review_post(
        client,
        "module_upgrade:0162-v2",
        "hop reviewed reason",
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "does not match the expected source tuple" in response.text
    assert core.audit.entries == []
    assert core.key.metadata_json["responses_policy"]["client_module"] == PIN_0149_V4


def test_review_migrate_dry_run_binds_exact_pin(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0162_V2_MOD)
    response = _review_post(
        client,
        "migrate:0162-v1",
        "migrate reviewed reason",
        pin_selector="0162-v2",
        from_version="2",
        from_digest=PIN_0162_V2_MOD["fixture_sha256"],
    )
    assert response.status_code == 200
    assert "Dry run complete" in response.text
    # Exact frozen 0162-v1 target identity is displayed.
    assert PIN_0162_V1["fixture_sha256"] in response.text
    assert core.audit.entries == []
    assert core.key.metadata_json["responses_policy"]["client_module"] == (
        PIN_0162_V2_MOD
    )


def test_review_migrate_posted_digest_alias_refused(
    client: TestClient, core: SimpleNamespace
) -> None:
    core.key = _key_row(PIN_0162_V2_MOD)
    client.cookies.set("slaif_admin_session", COOKIE_CANARY)
    response = _review_post(
        client,
        "migrate:0162-v1",
        "migrate reviewed reason",
        pin_selector="0162-v2",
        from_version="2",
        from_digest=COOKIE_CANARY,
    )
    assert response.status_code == 400
    assert "reviewed source identity was withheld" in response.text
    assert COOKIE_CANARY not in response.text
    assert core.key_reads == 0


def test_review_migrate_unavailable_active_profile_denied(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    # The registry resolves an active module whose identity is NOT the
    # 0.162 compatibility module: the intended Core guard must fire
    # (valid auth/CSRF; not the generic None-source fallback).
    core.key = _key_row(PIN_0162_V2_MOD)
    monkeypatch.setattr(
        "slaif_gateway.services.codex_module_upgrade.get_client_module",
        lambda _module_id: SimpleNamespace(
            module_id="some-other-module",
            module_version="9",
            fixture_sha256="e" * 64,
        ),
    )
    response = _review_post(
        client,
        "migrate:active",
        "migrate active reviewed",
        pin_selector="0162-v2",
        from_version="2",
        from_digest=PIN_0162_V2_MOD["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "The active Codex profile module is unavailable." in response.text
    assert core.audit.entries == []


def test_review_migrate_same_revision_different_digest_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    # Active resolves to the SAME revision (2) with a DIFFERENT digest:
    # a profile change requires a revision change.
    core.key = _key_row(PIN_0162_V2_MOD)
    monkeypatch.setattr(
        "slaif_gateway.services.codex_module_upgrade.get_client_module",
        lambda _module_id: SimpleNamespace(
            module_id=CODEX_0162_CLIENT_MODULE_ID,
            module_version="2",
            fixture_sha256="f" * 64,
        ),
    )
    response = _review_post(
        client,
        "migrate:active",
        "migrate active reviewed",
        pin_selector="0162-v2",
        from_version="2",
        from_digest=PIN_0162_V2_MOD["fixture_sha256"],
    )
    assert response.status_code == 400
    assert "A profile change requires a profile revision change." in response.text
    assert core.audit.entries == []


# ---------------------------------------------------------------------------
# Apply: token security + exact mutation + drift + idempotency
# ---------------------------------------------------------------------------


def _review_then_token(
    client: TestClient, core: SimpleNamespace, doc: dict[str, Any]
) -> str:
    return build_compatibility_review_token(
        admin_session_secret=_settings_secret(),
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=doc,
    )


def test_apply_wrong_csrf_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    response = _apply_post(client, token, csrf="wrong-csrf")
    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert calls == []
    assert core.audit.entries == []


def test_apply_missing_confirmation_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    response = _apply_post(client, token, confirm="")
    assert response.status_code == 400
    assert "Confirm the reviewed migration" in response.text
    assert calls == []


def test_apply_wrong_key_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    response = _apply_post(client, token, key_id=OTHER_KEY_ID)
    assert response.status_code == 400
    assert "not valid for this signed-in admin" in response.text
    assert calls == []


def test_apply_expired_token_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    token = build_compatibility_review_token(
        admin_session_secret=_settings_secret(),
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=_module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
        ttl_seconds=1,
        now=datetime.now(UTC) - timedelta(seconds=2),
    )
    response = _apply_post(client, token)
    assert response.status_code == 400
    assert calls == []


def test_apply_tampered_token_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    body, separator, digest = token.rpartition(".")
    flipped = ("A" if body[-1] != "A" else "B") + body[:-1]
    response = _apply_post(client, f"{flipped}.{digest}")
    assert response.status_code == 400
    assert calls == []


def test_apply_cross_actor_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    other_admin = uuid.uuid4()
    token = build_compatibility_review_token(
        admin_session_secret=_settings_secret(),
        admin_user_id=other_admin,
        admin_session_id=SESSION_ID,
        review_document=_module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    response = _apply_post(client, token)
    assert response.status_code == 400
    assert "not valid for this signed-in admin" in response.text
    assert calls == []


def test_apply_wrong_purpose_token_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    # A validly signed token whose signed purpose is NOT the
    # compatibility purpose must be refused: the purpose is part of the
    # signed payload, and the compatibility verifier is closed to its own
    # purpose only.
    import base64

    from slaif_gateway.api.admin_review_intent import (
        REVIEW_INTENT_TTL_SECONDS,
        _canonical_json,
        _digest,
    )

    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    secret = _settings_secret()
    payload = {
        "purpose": "admin.key-clone.review.v1",
        "admin_user_id": str(ADMIN_ID),
        "admin_session_id": str(SESSION_ID),
        "expires_at": (
            datetime.now(UTC) + timedelta(seconds=REVIEW_INTENT_TTL_SECONDS)
        ).isoformat(),
        "review": _module_review_doc(
            operation="module_upgrade",
            expected_source="0149-v4",
            target="0149-v5",
        ),
    }
    encoded = _canonical_json(payload)
    token = base64.urlsafe_b64encode(encoded).decode("ascii") + "." + _digest(
        secret, encoded
    )
    response = _apply_post(client, token)
    assert response.status_code == 400
    assert calls == []


def test_apply_updates_binding_and_exactly_one_audit(
    client: TestClient, core: SimpleNamespace
) -> None:
    row = _key_row(PIN_0149_V4)
    row.metadata_json = {
        "responses_policy": {"client_module": dict(PIN_0149_V4), "version": 1},
        "other": "sentinel",
    }
    core.key = row
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade",
            expected_source="0149-v4",
            target="0149-v5",
            reason="apply audit reason",
        ),
    )
    response = _apply_post(client, token)
    assert response.status_code == 200
    assert "Applied" in response.text
    assert "codex_client_module_upgraded" in response.text
    # ONLY the client_module tuple changed; everything else preserved.
    assert row.metadata_json["other"] == "sentinel"
    assert row.metadata_json["responses_policy"]["version"] == 1
    assert row.metadata_json["responses_policy"]["client_module"] == PIN_0149_V5
    assert len(core.audit.entries) == 1
    entry = core.audit.entries[0]
    assert entry["action"] == "codex_client_module_upgraded"
    assert entry["admin_user_id"] == ADMIN_ID
    assert entry["note"] == "apply audit reason"
    assert entry["old_values"] == {"client_module": PIN_0149_V4}
    assert entry["new_values"] == {"client_module": PIN_0149_V5}


def test_apply_repeat_already_at_target_no_write_no_audit(
    client: TestClient, core: SimpleNamespace
) -> None:
    # The key already carries the target identity (e.g. another
    # authorized action reached it): the exact repeat is the Core's
    # accepted no-op with no write and no audit.
    core.key = _key_row(PIN_0149_V5)
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    response = _apply_post(client, token)
    assert response.status_code == 200
    assert "Already at target" in response.text
    assert "nothing was written" in response.text
    assert "no audit record" in response.text
    assert core.key.metadata_json["responses_policy"]["client_module"] == PIN_0149_V5
    assert core.audit.entries == []


def test_apply_active_registry_drift_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    # Review binds the active tuple (revision 3, digest A); the apply
    # worker's registry resolves a DIFFERENT tuple (revision 3, digest B):
    # the shared expected-target guard must refuse before any mutation.
    core.key = _key_row(PIN_0162_V2_MOD)

    def active_module(digest: str) -> SimpleNamespace:
        return SimpleNamespace(
            module_id=CODEX_0162_CLIENT_MODULE_ID,
            module_version="3",
            fixture_sha256=digest,
        )

    digest_a = "a" * 64
    digest_b = "b" * 64
    monkeypatch.setattr(
        "slaif_gateway.services.codex_module_upgrade.get_client_module",
        lambda _module_id: active_module(digest_a),
    )
    review = _review_post(
        client,
        "migrate:active",
        "migrate active reviewed",
        pin_selector="0162-v2",
        from_version="2",
        from_digest=PIN_0162_V2_MOD["fixture_sha256"],
    )
    assert review.status_code == 200
    token = _token_from(review)
    monkeypatch.setattr(
        "slaif_gateway.services.codex_module_upgrade.get_client_module",
        lambda _module_id: active_module(digest_b),
    )
    response = _apply_post(client, token)
    assert response.status_code == 400
    assert "The active Codex profile identity changed" in response.text
    assert core.key.metadata_json["responses_policy"]["client_module"] == (
        PIN_0162_V2_MOD
    )
    assert core.audit.entries == []


def test_review_target_tuple_alias_refused_before_signing(
    client: TestClient, core: SimpleNamespace
) -> None:
    # The incoming request carries the TARGET fixture digest as a
    # credential (X-API-Key): the review must refuse BEFORE signing or
    # rendering - no token, no echo, no row mutation.
    core.key = _key_row(PIN_0149_V4)
    response = client.post(
        f"{BASE}/key/{KEY_ID}/review",
        data={
            "csrf_token": CSRF,
            "operation_target": "module_upgrade:0149-v5",
            "reason": "tuple alias reviewed",
            "pin_selector": "0149-v4",
            "from_version": "4",
            "from_digest": PIN_0149_V4["fixture_sha256"],
        },
        headers={"X-API-Key": PIN_0149_V5["fixture_sha256"]},
    )
    assert response.status_code == 400
    assert PIN_0149_V5["fixture_sha256"] not in response.text
    assert "match a known incoming authentication value" in response.text
    assert 'name="review_token"' not in response.text
    assert core.audit.entries == []
    assert core.key.metadata_json["responses_policy"]["client_module"] == (
        PIN_0149_V4
    )


def test_review_source_tuple_alias_refused(
    client: TestClient, core: SimpleNamespace
) -> None:
    # The SOURCE tuple value is the incoming credential: same refusal.
    core.key = _key_row(PIN_0149_V4)
    response = client.post(
        f"{BASE}/key/{KEY_ID}/review",
        data={
            "csrf_token": CSRF,
            "operation_target": "module_upgrade:0149-v5",
            "reason": "tuple alias reviewed",
            "pin_selector": "0149-v4",
            "from_version": "4",
            "from_digest": PIN_0149_V4["fixture_sha256"],
        },
        headers={"X-API-Key": PIN_0149_V4["fixture_sha256"]},
    )
    assert response.status_code == 400
    assert PIN_0149_V4["fixture_sha256"] not in response.text
    assert 'name="review_token"' not in response.text
    assert core.audit.entries == []


def test_apply_tuple_alias_change_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    # Review is clean (no alias in the review request); the APPLY request
    # now carries the target digest as a credential: refuse BEFORE the
    # Core call or any audit write, with no echo in the outcome.
    core.key = _key_row(PIN_0149_V4)
    review = _review_post(
        client,
        "module_upgrade:0149-v5",
        "apply time tuple canary",
        pin_selector="0149-v4",
        from_version="4",
        from_digest=PIN_0149_V4["fixture_sha256"],
    )
    assert review.status_code == 200
    token = _token_from(review)
    # Only now replace the mutation seam: the review above must run the
    # real dry run so the token signs genuine Core facts.
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    response = client.post(
        f"{BASE}/key/{KEY_ID}/apply",
        data={
            "csrf_token": CSRF,
            "review_token": token,
            "confirm_apply": "1",
        },
        headers={"X-API-Key": PIN_0149_V5["fixture_sha256"]},
    )
    assert response.status_code == 400
    assert PIN_0149_V5["fixture_sha256"] not in response.text
    assert "matches a known incoming authentication value" in response.text
    assert calls == []
    assert core.audit.entries == []
    assert core.key.metadata_json["responses_policy"]["client_module"] == (
        PIN_0149_V4
    )


def test_apply_reviewed_reason_now_alias_refused(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)
    calls: list[dict[str, Any]] = []

    async def spy_apply(**kwargs: Any):
        calls.append(kwargs)
        return CodexModuleUpgradeResult(
            gateway_key_id=KEY_ID, status="applied", action="codex_client_module_upgraded",
            source_module=PIN_0149_V4, target_module=PIN_0149_V5, changed=True,
        )

    monkeypatch.setattr(compat, "mutate_codex_client_module", spy_apply)
    reason = "apply time alias reason"
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade",
            expected_source="0149-v4",
            target="0149-v5",
            reason=reason,
        ),
    )
    # This APPLY request now carries the reviewed reason as an incoming
    # authentication value (the session cookie): refuse before persisting.
    client.cookies.set("slaif_admin_session", reason)
    response = _apply_post(client, token)
    assert response.status_code == 400
    assert "matches a known incoming authentication value" in response.text
    assert reason not in response.text
    assert calls == []


def test_apply_generic_failure_is_unconfirmed_wording(
    client: TestClient, core: SimpleNamespace, monkeypatch
) -> None:
    core.key = _key_row(PIN_0149_V4)

    async def boom(**_kwargs: Any):
        raise RuntimeError("commit ack lost")

    monkeypatch.setattr(compat, "mutate_codex_client_module", boom)
    token = _review_then_token(
        client,
        core,
        _module_review_doc(
            operation="module_upgrade", expected_source="0149-v4", target="0149-v5"
        ),
    )
    response = _apply_post(client, token)
    assert response.status_code == 400
    assert "UNCONFIRMED" in response.text
    assert "audit log" in response.text
    assert "The review is unchanged" not in response.text
