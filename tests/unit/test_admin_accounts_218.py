"""218-a: privileged administrator account management (G17).

Unit/ASGI coverage:

- shared AdminService reset law (fresh row lock BEFORE mutation,
  transactional target-session revocation, exact actor/target/reason
  audit, rollback precondition on audit failure, offline-CLI audit
  shape) and AdminSessionService login ordering (locked fresh read
  BEFORE password verification);
- the /admin/accounts router over the REAL app + REAL Jinja templates
  with fake DB seams: dashboard-off gate, session auth, SERVER-side
  persisted superadmin gate, CSRF, bounded validation BEFORE Argon2id,
  no-echo alias refusals, URL-bound reset target, duplicate/fault
  outcomes, self-reset logout, and FULL-BODY + captured-LOG secret
  canaries (complete password/confirmation, session token, provider
  secret, password hash never appear anywhere in HTML/JSON/logs).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
    AdminSessionService,
)
from slaif_gateway.services.admin_service import AdminService
from slaif_gateway.services.record_errors import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from slaif_gateway.utils.passwords import hash_admin_password, verify_admin_password

SESSION_COOKIE = "slaif_admin_session"
SESSION_TOKEN = "session-canary-218-token"
PASSWORD = "Canary-Pw-218-!xQ"
CONFIRMATION = "Canary-Pw-218-!xQ"
# Independent opaque synthetic provider secret: it must NOT reuse the
# configured gateway key prefix, so the canary can never be mistaken for
# (or accidentally refused as) an incoming gateway-key alias.
PROVIDER_SECRET = "provider-canary-secret-218-opaque"
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$Q1$canaryhashvalue"

# This venv's TestClient host scope: a cookie delivered by a server
# Set-Cookie header is stored under this domain, and the app's own
# delete-cookie header only clears same-scope jar entries. Seeding the
# fixture cookie with this scope mirrors a real browser cookie that the
# server itself set at login.
COOKIE_DOMAIN = "testserver.local"


# ---------------------------------------------------------------------------
# Shared fakes (service level; no DB)
# ---------------------------------------------------------------------------


class _FakeSessionsRepo:
    def __init__(self, sessions: list[AdminSession] | None = None) -> None:
        self.sessions = list(sessions or [])
        self.calls: list[tuple[uuid.UUID, datetime]] = []

    async def revoke_all_sessions_for_admin(
        self, admin_user_id: uuid.UUID, *, revoked_at: datetime
    ) -> int:
        self.calls.append((admin_user_id, revoked_at))
        count = 0
        for session in self.sessions:
            if session.admin_user_id == admin_user_id and session.revoked_at is None:
                session.revoked_at = revoked_at
                count += 1
        return count


class _FakeAudit:
    def __init__(self, fail: bool = False) -> None:
        self.rows: list[dict[str, object]] = []
        self.fail = fail

    async def add_audit_log(self, **kwargs: object):
        if self.fail:
            raise RuntimeError("audit store unavailable")
        self.rows.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), **kwargs)

    async def get_latest_admin_login_lockout(self, **kwargs: object) -> object:
        return None

    async def count_recent_admin_login_failures(self, **kwargs: object) -> int:
        return 0


def _admin_user(
    *,
    email: str = "admin@example.org",
    role: str = "admin",
    password_hash: str | None = None,
) -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email=email,
        display_name="Admin " + email.split("@")[0],
        password_hash=password_hash or ARGON2_HASH,
        role=role,
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _session_for(user: AdminUser) -> AdminSession:
    session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=user.id,
        session_token_hash="sha256:row",
        csrf_token_hash="sha256:row",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.admin_user = user
    return session


class _UsersRepo:
    """In-memory AdminUsersRepository stand-in with a call ledger."""

    def __init__(self, users: list[AdminUser]) -> None:
        self.by_id = {user.id: user for user in users}
        self.events: list[str] = []
        self.locked_override: object = ...  # sentinel: default = by_id lookup

    async def get_admin_user_by_email(self, email: str) -> AdminUser | None:
        for user in self.by_id.values():
            if user.email == email:
                return user
        return None

    async def get_admin_user_by_id(self, admin_user_id: uuid.UUID) -> AdminUser | None:
        return self.by_id.get(admin_user_id)

    async def get_admin_user_for_update(self, admin_user_id: uuid.UUID) -> AdminUser | None:
        self.events.append(f"lock:{admin_user_id}")
        if self.locked_override is not ...:
            return self.locked_override
        return self.by_id.get(admin_user_id)

    async def set_admin_password_hash(
        self, admin_user_id: uuid.UUID, password_hash: str
    ) -> bool:
        self.events.append(f"sethash:{admin_user_id}")
        user = self.by_id.get(admin_user_id)
        if user is None:
            return False
        user.password_hash = password_hash
        return True

    async def set_last_login_at(
        self, admin_user_id: uuid.UUID, timestamp: datetime
    ) -> None:
        user = self.by_id.get(admin_user_id)
        if user is not None:
            user.last_login_at = timestamp

    async def create_admin_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        role: str = "admin",
        is_active: bool = True,
    ) -> AdminUser:
        self.events.append(f"create:{email}")
        user = AdminUser(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )
        self.by_id[user.id] = user
        return user

    async def list_admin_users(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[AdminUser]:
        rows = sorted(self.by_id.values(), key=lambda u: u.created_at, reverse=True)
        return rows[offset : offset + limit]


def _service(
    *,
    users: list[AdminUser],
    sessions: list[AdminSession] | None = None,
    audit_fail: bool = False,
):
    users_repo = _UsersRepo(users)
    sessions_repo = _FakeSessionsRepo(sessions)
    audit = _FakeAudit(fail=audit_fail)
    service = AdminService(
        admin_users_repository=users_repo,  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
        admin_sessions_repository=sessions_repo,  # type: ignore[arg-type]
    )
    return service, users_repo, sessions_repo, audit


# ---------------------------------------------------------------------------
# Shared service law (Phase 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_locks_then_revokes_and_audits_actor_target_reason() -> None:
    actor = _admin_user(email="root@example.org", role="superadmin")
    target = _admin_user(email="target@example.org")
    target_sessions = [_session_for(target), _session_for(target)]
    bystander = _admin_user(email="other@example.org")
    bystander_session = _session_for(bystander)
    service, users_repo, sessions_repo, audit = _service(
        users=[actor, target, bystander],
        sessions=[*target_sessions, bystander_session],
    )

    new_hash = "argon2-new-hash"
    result = await service.reset_admin_password(
        admin_user_id_or_email=target.email,
        password_hash=new_hash,
        actor_admin_id=actor.id,
        reason="stolen credentials",
        ip_address="203.0.113.7",
        user_agent="test-agent",
    )

    # Lock strictly BEFORE the hash mutation; revocation and audit after.
    assert users_repo.events == [
        f"lock:{target.id}",
        f"sethash:{target.id}",
    ]
    assert sessions_repo.calls and sessions_repo.calls[0][0] == target.id
    assert result.id == target.id
    assert result.password_hash == new_hash
    # ALL target sessions revoked; the unrelated user's session untouched.
    assert all(s.revoked_at is not None for s in target_sessions)
    assert bystander_session.revoked_at is None
    # Exact actor/target/reason audit.
    assert audit.rows[-1]["action"] == "admin_user_password_reset"
    assert audit.rows[-1]["admin_user_id"] == actor.id
    assert audit.rows[-1]["entity_id"] == target.id
    assert audit.rows[-1]["new_values"] == {
        "password_changed": True,
        "revoked_count": 2,
        "reason": "stolen credentials",
    }
    assert audit.rows[-1]["ip_address"] == "203.0.113.7"
    assert audit.rows[-1]["user_agent"] == "test-agent"


@pytest.mark.asyncio
async def test_reset_offline_cli_shape_keeps_honest_provenance() -> None:
    target = _admin_user(email="target@example.org")
    service, _users_repo, sessions_repo, audit = _service(
        users=[target], sessions=[_session_for(target)]
    )

    await service.reset_admin_password(
        admin_user_id_or_email=str(target.id), password_hash="argon2-new"
    )

    # Offline CLI: no actor, no reason, no ip/ua - the audit row records
    # no authenticated actor (honest offline provenance), and the shared
    # session revocation still happens.
    assert audit.rows[-1]["admin_user_id"] is None
    assert audit.rows[-1]["new_values"] == {
        "password_changed": True,
        "revoked_count": 1,
    }
    assert audit.rows[-1]["ip_address"] is None
    assert audit.rows[-1]["user_agent"] is None
    assert sessions_repo.calls[0][0] == target.id


@pytest.mark.asyncio
async def test_reset_uses_fresh_locked_row_not_stale_snapshot() -> None:
    stale = _admin_user(email="target@example.org", password_hash="argon2-stale")
    fresh = AdminUser(
        id=stale.id,
        email=stale.email,
        display_name=stale.display_name,
        password_hash="argon2-fresh",
        role=stale.role,
        is_active=True,
    )
    service, users_repo, _sessions_repo, audit = _service(users=[stale])
    users_repo.by_id[stale.id] = fresh  # "committed elsewhere" newer row
    users_repo.locked_override = fresh  # locked read returns the fresh row

    await service.reset_admin_password(
        admin_user_id_or_email=stale.email, password_hash="argon2-new"
    )

    assert fresh.password_hash == "argon2-new"
    assert audit.rows[-1]["entity_id"] == fresh.id


@pytest.mark.asyncio
async def test_reset_audit_failure_propagates_for_transaction_rollback() -> None:
    target = _admin_user(email="target@example.org")
    service, _users_repo, _sessions_repo, _audit = _service(
        users=[target], audit_fail=True
    )

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        await service.reset_admin_password(
            admin_user_id_or_email=target.email,
            password_hash="argon2-new",
            actor_admin_id=target.id,
            reason="x",
        )
    # The exception propagates to the caller's transaction scope, which
    # rolls the hash + revocation back (proven natively in the PG
    # integration module); the service itself must not swallow it.


@pytest.mark.asyncio
async def test_create_audits_actor_reason_and_keeps_offline_shape() -> None:
    actor = _admin_user(email="root@example.org", role="superadmin")
    service, users_repo, _sessions_repo, audit = _service(users=[actor])

    created = await service.create_admin_user(
        email="New@Example.ORG",
        display_name="  New Admin  ",
        password_hash=ARGON2_HASH,
        is_superadmin=True,
        actor_admin_id=actor.id,
        reason="onboarding",
    )
    assert created.email == "new@example.org"
    assert created.display_name == "New Admin"
    assert created.role == "superadmin"
    assert audit.rows[-1]["action"] == "admin_user_created"
    assert audit.rows[-1]["admin_user_id"] == actor.id
    assert audit.rows[-1]["new_values"]["reason"] == "onboarding"

    # Offline CLI shape: no actor/reason keys at all (byte-identical
    # audit to the pre-218 CLI behavior).
    await service.create_admin_user(
        email="cli@example.org",
        display_name="CLI Admin",
        password_hash=ARGON2_HASH,
    )
    row = audit.rows[-1]
    assert row["admin_user_id"] is None
    assert "reason" not in row["new_values"]
    assert row["new_values"] == {
        "email": "cli@example.org",
        "display_name": "CLI Admin",
        "role": "admin",
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_create_duplicate_email_refused_before_write() -> None:
    existing = _admin_user(email="dup@example.org")
    service, users_repo, _sessions_repo, _audit = _service(users=[existing])

    with pytest.raises(DuplicateRecordError):
        await service.create_admin_user(
            email="DUP@example.org", display_name="Dup", password_hash=ARGON2_HASH
        )
    assert not any(event.startswith("create:") for event in users_repo.events)


@pytest.mark.asyncio
async def test_list_admin_users_passes_offset() -> None:
    users = [
        _admin_user(email=f"u{i}@example.org") for i in range(3)
    ]
    service, _users_repo, _sessions_repo, _audit = _service(users=users)
    rows = await service.list_admin_users(limit=2, offset=1)
    assert len(rows) == 2


def _login_service(users_repo: _UsersRepo, user: AdminUser):
    audit = _FakeAudit()
    sessions_repo = _FakeSessionsRepo()
    service = AdminSessionService(
        settings=Settings(
            APP_ENV="test",
            ADMIN_SESSION_SECRET="s" * 40,
            ADMIN_SESSION_TTL_SECONDS=60,
        ),
        admin_users_repository=users_repo,  # type: ignore[arg-type]
        admin_sessions_repository=sessions_repo,  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
    )
    return service


@pytest.mark.asyncio
async def test_login_locks_row_before_verifying_and_uses_fresh_hash() -> None:
    # REAL Argon2id hashes: the shared verifier only returns False for a
    # valid-but-mismatching hash (corrupt/non-Argon2 rows are a
    # pre-existing data-integrity condition outside this order).
    old_hash, new_hash = hash_admin_password("old"), hash_admin_password("new")
    stale = _admin_user(email="target@example.org", password_hash=old_hash)
    fresh = AdminUser(
        id=stale.id,
        email=stale.email,
        display_name=stale.display_name,
        password_hash=new_hash,
        role=stale.role,
        is_active=True,
    )
    users_repo = _UsersRepo([stale])
    users_repo.by_id[stale.id] = fresh
    users_repo.locked_override = fresh
    service = _login_service(users_repo, stale)

    # The superseded password must NOT authenticate against the fresh
    # locked hash; the new password does.
    from slaif_gateway.services.admin_session_service import AdminAuthenticationError

    with pytest.raises(AdminAuthenticationError):
        await service.authenticate_admin(email="target@example.org", password="old")
    result = await service.authenticate_admin(email="target@example.org", password="new")
    assert result.id == fresh.id
    # The lock happened before any verification (event ledger ordering).
    assert users_repo.events == [f"lock:{fresh.id}"] * 2


# ---------------------------------------------------------------------------
# Router (REAL app + REAL Jinja; fake DB seams)
# ---------------------------------------------------------------------------


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
        "ADMIN_SESSION_SECRET": "s" * 40,
        "OPENAI_UPSTREAM_API_KEY": PROVIDER_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None) -> object:
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _account_row(
    *,
    email: str = "admin@example.org",
    role: str = "admin",
    last_login_at: datetime | None = None,
) -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email=email,
        display_name="Display " + email.split("@")[0],
        password_hash=ARGON2_HASH,
        role=role,
        is_active=True,
        created_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
        last_login_at=last_login_at,
        updated_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
    )


def _login(monkeypatch, client: TestClient, user: AdminUser) -> None:
    session = _session_for(user)

    async def fake_validate(self, **kwargs):
        return AdminSessionContext(admin_user=user, admin_session=session)

    async def fake_refresh(self, **kwargs):
        return "csrf-218"

    def fake_verify(self, admin_session, csrf_token):
        return csrf_token == "csrf-218"

    monkeypatch.setattr(
        AdminSessionService, "validate_admin_session", fake_validate
    )
    monkeypatch.setattr(AdminSessionService, "refresh_csrf_token", fake_refresh)
    monkeypatch.setattr(
        AdminSessionService, "verify_session_csrf_token", fake_verify
    )
    client.cookies.set(SESSION_COOKIE, SESSION_TOKEN, domain=COOKIE_DOMAIN)


def _patch_admin_service(
    monkeypatch,
    *,
    list_rows: list[AdminUser] | None = None,
    create: object = None,
    reset: object = None,
    get: object = None,
) -> dict[str, object]:
    """Patch the AdminService class methods the router calls.

    ``create``/``reset``/``get`` may be an Exception (raise) or a value
    (return). Returns the call ledger.
    """
    seen: dict[str, object] = {}

    async def fake_list(self, **kwargs):
        seen["list"] = kwargs
        assert list_rows is not None
        return list_rows

    async def fake_create(self, **kwargs):
        seen["create"] = kwargs
        if isinstance(create, BaseException):
            raise create
        return create

    async def fake_reset(self, **kwargs):
        seen["reset"] = kwargs
        if isinstance(reset, BaseException):
            raise reset
        return reset

    async def fake_get(self, value):
        seen.setdefault("get", []).append(value)
        if isinstance(get, BaseException):
            raise get
        return get

    monkeypatch.setattr(AdminService, "list_admin_users", fake_list)
    monkeypatch.setattr(AdminService, "create_admin_user", fake_create)
    monkeypatch.setattr(AdminService, "reset_admin_password", fake_reset)
    monkeypatch.setattr(AdminService, "get_admin_user", fake_get)
    return seen


def _client(monkeypatch, user: AdminUser) -> TestClient:
    client = TestClient(_app())
    _login(monkeypatch, client, user)
    return client


def test_dashboard_off_gate_returns_404() -> None:
    client = TestClient(_app(_settings(ENABLE_ADMIN_DASHBOARD=False)))
    assert client.get("/admin/accounts").status_code == 404
    assert client.get("/admin/accounts/create").status_code == 404
    assert client.get("/admin/accounts/reset").status_code == 404


def test_list_unauthenticated_redirects_to_login() -> None:
    client = TestClient(_app())
    response = client.get("/admin/accounts", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_list_normal_admin_forbidden_not_login_redirect(monkeypatch) -> None:
    user = _admin_user(email="admin@example.org", role="admin")
    client = _client(monkeypatch, user)

    response = client.get("/admin/accounts")

    assert response.status_code == 403
    assert "superadmin" in response.text
    assert "row-ordinal" not in response.text
    # The same server-side gate applies to the action forms.
    assert client.get("/admin/accounts/create").status_code == 403
    assert client.get("/admin/accounts/reset", params={"admin_id": str(user.id)}).status_code == 403


def test_list_viewer_forbidden(monkeypatch) -> None:
    user = _admin_user(email="viewer@example.org", role="viewer")
    client = _client(monkeypatch, user)
    assert client.get("/admin/accounts").status_code == 403


def test_list_superadmin_renders_safe_metadata_and_navigation(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    rows = [
        _account_row(email="a@example.org", role="superadmin", last_login_at=datetime(2026, 3, 1, tzinfo=UTC)),
        _account_row(email="b@example.org", role="admin"),
    ]
    seen = _patch_admin_service(monkeypatch, list_rows=rows)
    client = _client(monkeypatch, root)

    response = client.get("/admin/accounts", params={"limit": 50, "offset": 0})

    assert response.status_code == 200
    assert seen["list"] == {"limit": 51, "offset": 0}  # cap+1 fetch
    body = response.text
    for row in rows:
        assert row.email in body
        assert "Reset password" in body
        assert f"/admin/accounts/reset?admin_id={row.id}" in body
    assert "Never" in body  # missing last login renders as missing
    # No hashes, session tokens, or secrets anywhere in the body.
    assert "argon2" not in body
    assert ARGON2_HASH not in body
    assert SESSION_TOKEN not in body
    assert PROVIDER_SECRET not in body
    # Structural guards.
    assert 'role="region"' in body and 'tabindex="0"' in body
    assert "data-ordinal" in body
    assert "data-sortable" in body
    # Honest navigation: 2 fetched <= page size -> no next page.
    assert "No more rows" in body
    assert "Beginning" in body


def test_list_full_page_is_not_has_more_but_cap_plus_one_is(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    client = _client(monkeypatch, root)

    # Exactly limit rows fetched: a full page is NOT "more".
    _patch_admin_service(monkeypatch, list_rows=[_account_row(email=f"p{i}@e.org") for i in range(2)])
    body = client.get("/admin/accounts", params={"limit": 2, "offset": 0}).text
    assert "No more rows" in body

    # limit+1 fetched: honest "more" with the preserved navigation URL.
    _patch_admin_service(monkeypatch, list_rows=[_account_row(email=f"q{i}@e.org") for i in range(3)])
    body = client.get("/admin/accounts", params={"limit": 2, "offset": 2}).text
    assert 'href="/admin/accounts?limit=2&amp;offset=4"' in body
    assert "Rows 3" in body  # continued first ordinal (offset 2 + 1)


def test_create_get_renders_linked_field_help(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    _patch_admin_service(monkeypatch, list_rows=[])
    client = _client(monkeypatch, root)

    body = client.get("/admin/accounts/create").text

    # Every visible control carries a real aria-describedby link to an
    # existing non-empty help element with a unique id.
    for control_id in (
        "create-email-help",
        "create-display-name-help",
        "create-password-help",
        "create-password-confirmation-help",
        "create-role-help",
        "create-confirm-help",
        "create-superadmin-confirm-help",
        "create-reason-help",
    ):
        assert f'id="{control_id}"' in body, control_id
        assert f'aria-describedby="{control_id}"' in body, control_id
    assert 'name="role"' in body
    assert "<select name=\"role\"" in body
    # No password value can ever be prefilled.
    assert 'value="' + PASSWORD not in body
    # No hidden bootstrap: the form POSTs to the same origin.
    assert 'action="/admin/accounts/create"' in body


def _create_post(client: TestClient, **overrides) -> object:
    data = {
        "email": "new@example.org",
        "display_name": "New Admin",
        "password": PASSWORD,
        "password_confirmation": CONFIRMATION,
        "role": "admin",
        "confirm_create": "1",
        "confirm_superadmin": "",
        "reason": "routine coverage",
        "csrf_token": "csrf-218",
    }
    data.update(overrides)
    return client.post("/admin/accounts/create", data=data, follow_redirects=False)


def test_create_happy_redirects_and_hashes_with_actor(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="new@example.org"))
    client = _client(monkeypatch, root)

    response = _create_post(client, email="  NEW@Example.ORG  ", display_name="  New Admin  ")

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/accounts?message=admin_account_created"
    kwargs = seen["create"]
    assert kwargs["email"] == "new@example.org"
    assert kwargs["display_name"] == "New Admin"
    assert kwargs["is_superadmin"] is False
    assert kwargs["actor_admin_id"] == root.id
    assert kwargs["reason"] == "routine coverage"
    assert kwargs["password_hash"].startswith("$argon2id$")
    assert verify_admin_password(PASSWORD, str(kwargs["password_hash"]))


def test_create_superadmin_records_privileged_choice(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="x@example.org"))
    client = _client(monkeypatch, root)

    response = _create_post(client, role="superadmin", confirm_superadmin="1")

    assert response.status_code == 303
    assert seen["create"]["is_superadmin"] is True


@pytest.mark.asyncio
async def _assert_no_hash(monkeypatch) -> None:
    """hash_admin_password must not run for refused submissions."""
    import slaif_gateway.api.admin_accounts as router_mod

    async def boom(*args, **kwargs):
        raise AssertionError("Argon2id must not run for a refused submission")

    monkeypatch.setattr(router_mod, "hash_admin_password", boom)


def test_create_requires_explicit_confirmation_even_for_ordinary_admin(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))
    client = _client(monkeypatch, root)
    import slaif_gateway.api.admin_accounts as router_mod
    monkeypatch.setattr(
        router_mod,
        "hash_admin_password",
        lambda value: (_ for _ in ()).throw(AssertionError("no hashing")),
    )

    response = _create_post(client, confirm_create="")

    assert response.status_code == 400
    assert "explicit confirmation" in response.text
    assert "create" not in seen


def test_create_superadmin_requires_privileged_acknowledgement(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))
    client = _client(monkeypatch, root)
    import slaif_gateway.api.admin_accounts as router_mod
    monkeypatch.setattr(
        router_mod,
        "hash_admin_password",
        lambda value: (_ for _ in ()).throw(AssertionError("no hashing")),
    )

    response = _create_post(client, role="superadmin", confirm_superadmin="")

    assert response.status_code == 400
    assert "privileged" in response.text
    assert "create" not in seen


def test_create_browsed_role_value_is_not_an_authority(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))
    client = _client(monkeypatch, root)
    import slaif_gateway.api.admin_accounts as router_mod
    monkeypatch.setattr(
        router_mod,
        "hash_admin_password",
        lambda value: (_ for _ in ()).throw(AssertionError("no hashing")),
    )

    response = _create_post(client, role="operator")

    assert response.status_code == 400
    assert "create" not in seen


@pytest.mark.parametrize(
    "password,confirmation",
    [
        ("", ""),
        (PASSWORD * 11, "mismatched"),
        (PASSWORD, PASSWORD + "x"),
    ],
    ids=["empty", "over-cap-mismatch", "mismatch"],
)
def test_create_password_law_refuses_before_hash(monkeypatch, password, confirmation) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))
    client = _client(monkeypatch, root)
    import slaif_gateway.api.admin_accounts as router_mod
    monkeypatch.setattr(
        router_mod,
        "hash_admin_password",
        lambda value: (_ for _ in ()).throw(AssertionError("no hashing")),
    )

    response = _create_post(client, password=password, password_confirmation=confirmation)

    assert response.status_code == 400
    assert "create" not in seen
    # The complete submitted secret values are never echoed in the error
    # re-render: check BOTH nonempty distinct canaries (the shared law has
    # no minimum length, so only empty/over-cap/mismatch refuse).
    for secret in (password, confirmation):
        if secret:
            assert secret not in response.text


def test_create_accepts_short_matching_password_shared_nonempty_law(monkeypatch) -> None:
    """The shared hashing law is nonempty (no GUI minimum): a short but
    matching password is accepted and hashed with its EXACT bytes."""
    root = _admin_user(email="root@example.org", role="superadmin")
    short_password = "Ab-1xQ"
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))
    client = _client(monkeypatch, root)

    response = _create_post(
        client, password=short_password, password_confirmation=short_password
    )

    assert response.status_code == 303
    kwargs = seen["create"]
    assert kwargs["password_hash"] != short_password  # only the hash persists
    assert verify_admin_password(short_password, str(kwargs["password_hash"]))


def test_create_alias_fields_refused_without_echo_in_full_body(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))
    client = _client(monkeypatch, root)
    import slaif_gateway.api.admin_accounts as router_mod
    monkeypatch.setattr(
        router_mod,
        "hash_admin_password",
        lambda value: (_ for _ in ()).throw(AssertionError("no hashing")),
    )

    # display_name equals the incoming session-cookie value (a known
    # incoming authentication value).
    response = _create_post(client, display_name=SESSION_TOKEN)
    assert response.status_code == 400
    assert "create" not in seen
    assert SESSION_TOKEN not in response.text  # full-body no-echo

    # reason equals the incoming session-cookie value.
    response = _create_post(client, reason=SESSION_TOKEN)
    assert response.status_code == 400
    assert SESSION_TOKEN not in response.text

    # An EARLIER error branch (bad role) must still withhold tainted
    # email/name/reason values from the re-render.
    response = _create_post(
        client,
        role="operator",
        email=SESSION_TOKEN,
        display_name=SESSION_TOKEN,
        reason=SESSION_TOKEN,
    )
    assert response.status_code == 400
    assert SESSION_TOKEN not in response.text


def test_create_duplicate_record_error_answers_fixed_409(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    _patch_admin_service(monkeypatch, create=DuplicateRecordError("Admin user", "email"))
    client = _client(monkeypatch, root)

    response = _create_post(client)

    assert response.status_code == 409
    assert "already exists" in response.text
    assert PASSWORD not in response.text
    assert "argon2" not in response.text
    assert "IntegrityError" not in response.text
    assert "psycopg" not in response.text and "asyncpg" not in response.text


def test_create_integrity_race_recheck_decides_honest_outcome(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    client = _client(monkeypatch, root)
    race_error = IntegrityError("INSERT", {}, RuntimeError("duplicate key value violates unique constraint \"admin_users_email_key\""))

    # Raced commit of the SAME email: the known duplicate condition.
    _patch_admin_service(monkeypatch, create=race_error, get=_account_row(email="new@example.org"))
    response = _create_post(client)
    assert response.status_code == 409
    assert "already exists" in response.text
    assert "admin_users_email_key" not in response.text

    # A DIFFERENT integrity fault: honest unconfirmed outcome, no
    # rollback promise, no raw SQL text.
    _patch_admin_service(monkeypatch, create=race_error, get=RecordNotFoundError("Admin user"))
    response = _create_post(client)
    assert response.status_code == 500
    assert "could not be confirmed" in response.text
    assert "nothing was committed" not in response.text
    assert "duplicate key" not in response.text


def test_create_unexpected_fault_fixed_unconfirmed_and_log_canary(monkeypatch, capsys) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    _patch_admin_service(
        monkeypatch,
        create=RuntimeError(f"boom {PASSWORD} {ARGON2_HASH}"),
    )
    client = _client(monkeypatch, root)

    response = _create_post(client)

    assert response.status_code == 500
    assert "could not be confirmed" in response.text
    captured = capsys.readouterr()
    # Full-body + captured-LOG canaries: the fault must not leak the
    # exception text (carrying the password/hash) into the response or
    # the captured logs (stdout structured logs or stderr).
    assert PASSWORD not in response.text
    assert ARGON2_HASH not in response.text
    assert PASSWORD not in captured.out
    assert ARGON2_HASH not in captured.out
    assert PASSWORD not in captured.err
    assert ARGON2_HASH not in captured.err
    assert "boom" not in captured.out


def test_create_wrong_csrf_refused_before_effects(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    seen = _patch_admin_service(monkeypatch, create=_account_row(email="n@example.org"))

    async def fake_validate(self, **kwargs):
        session = _session_for(root)
        return AdminSessionContext(admin_user=root, admin_session=session)

    async def fake_refresh(self, **kwargs):
        return "csrf-218"

    def fake_verify(self, admin_session, csrf_token):
        return False  # CSRF mismatch

    client = TestClient(_app())
    monkeypatch.setattr(AdminSessionService, "validate_admin_session", fake_validate)
    monkeypatch.setattr(AdminSessionService, "refresh_csrf_token", fake_refresh)
    monkeypatch.setattr(AdminSessionService, "verify_session_csrf_token", fake_verify)
    client.cookies.set(SESSION_COOKIE, SESSION_TOKEN)

    response = _create_post(client)

    assert response.status_code == 400
    assert "Invalid CSRF token" in response.text
    assert "create" not in seen


# --- reset form -------------------------------------------------------------


def _reset_get(client: TestClient, target: AdminUser) -> object:
    return client.get("/admin/accounts/reset", params={"admin_id": str(target.id)})


def _reset_post(
    client: TestClient, target: AdminUser, **overrides: object
) -> object:
    data = {
        "admin_id": str(target.id),
        "password": PASSWORD,
        "password_confirmation": CONFIRMATION,
        "confirm_reset": "1",
        "reason": "compromised account",
        "csrf_token": "csrf-218",
    }
    headers = overrides.pop("headers", None)
    data.update(overrides)  # type: ignore[arg-type]
    return client.post(  # type: ignore[arg-type]
        f"/admin/accounts/reset?admin_id={target.id}",
        data=data,  # type: ignore[arg-type]
        headers=headers,  # type: ignore[arg-type]
        follow_redirects=False,
    )


def test_reset_get_renders_server_identity_bound_form(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org", role="superadmin")
    _patch_admin_service(monkeypatch, get=target)
    client = _client(monkeypatch, root)

    body = _reset_get(client, target).text

    assert target.email in body
    assert "superadmin" in body
    # URL-bound form action + hidden canonical target.
    assert f'action="/admin/accounts/reset?admin_id={target.id}"' in body
    assert f'name="admin_id" value="{target.id}"' in body
    # Session-revocation consequence explained BEFORE confirmation.
    assert "signs out ALL of its existing console sessions" in body
    # Linked field help on every visible control.
    for control_id in (
        "reset-password-help",
        "reset-password-confirmation-help",
        "reset-confirm-help",
        "reset-reason-help",
    ):
        assert f'id="{control_id}"' in body, control_id
        assert f'aria-describedby="{control_id}"' in body, control_id
    # No secrets.
    assert ARGON2_HASH not in body and SESSION_TOKEN not in body and PROVIDER_SECRET not in body


def test_reset_get_self_reset_shows_own_session_consequence(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    root.created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
    _patch_admin_service(monkeypatch, get=root)
    client = _client(monkeypatch, root)

    body = _reset_get(client, root).text

    assert "your own account" in body
    assert f'action="/admin/accounts/reset?admin_id={root.id}"' in body


def test_reset_get_missing_or_invalid_target(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    client = _client(monkeypatch, root)

    _patch_admin_service(monkeypatch, get=RecordNotFoundError("Admin user"))
    missing = client.get("/admin/accounts/reset", params={"admin_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    assert "no longer exists" in missing.text

    invalid = client.get("/admin/accounts/reset")
    assert invalid.status_code == 400
    assert "Select an administrator account" in invalid.text


def test_reset_happy_redirects_and_audits_with_masked_ua(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    seen = _patch_admin_service(monkeypatch, get=target, reset=target)
    client = _client(monkeypatch, root)

    response = _reset_post(client, target, headers={"user-agent": "clean-ua-218"})

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/accounts?message=admin_password_reset"
    kwargs = seen["reset"]
    assert kwargs["admin_user_id_or_email"] == str(target.id)
    assert kwargs["actor_admin_id"] == root.id
    assert kwargs["reason"] == "compromised account"
    assert verify_admin_password(PASSWORD, str(kwargs["password_hash"]))
    # The audit User-Agent is the pure-masker output: clean ASCII
    # metadata passes through EXACTLY.
    assert kwargs["user_agent"] == "clean-ua-218"


def test_reset_audit_ua_masks_embedded_cookie_alias(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    seen = _patch_admin_service(monkeypatch, get=target, reset=target)
    client = _client(monkeypatch, root)

    # ASCII UA embedding the session-cookie value (a known incoming
    # authentication value).
    response = _reset_post(
        client, target, headers={"user-agent": f"agent {SESSION_TOKEN} tail"}
    )

    assert response.status_code == 303
    forwarded_ua = seen["reset"]["user_agent"]
    assert forwarded_ua is not None
    assert SESSION_TOKEN not in str(forwarded_ua)  # no raw alias persisted


def test_reset_self_reset_redirects_safe_login_and_clears_cookie(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    _patch_admin_service(monkeypatch, get=root, reset=root)
    client = _client(monkeypatch, root)

    response = _reset_post(client, root)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login?message=admin_password_reset_self"
    set_cookie = response.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE}=" in set_cookie
    assert "Max-Age=0" in set_cookie or "Expires=Thu, 01 Jan 1970" in set_cookie
    # Secret-free outcome: the flash is fixed text, no password/hash.
    assert PASSWORD not in response.text
    assert ARGON2_HASH not in response.text

    # The safe login page renders the fixed secret-free flash.
    login_body = client.get("/admin/login?message=admin_password_reset_self").text
    assert "Your password was reset" in login_body
    assert PASSWORD not in login_body


def test_reset_target_mismatch_refused_before_any_effect(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    other = _account_row(email="other@example.org")
    seen = _patch_admin_service(monkeypatch, get=target, reset=target)
    client = _client(monkeypatch, root)

    # Form bound to `target`'s URL, hidden field claiming `other`.
    response = client.post(
        f"/admin/accounts/reset?admin_id={target.id}",
        data={
            "admin_id": str(other.id),
            "password": PASSWORD,
            "password_confirmation": CONFIRMATION,
            "confirm_reset": "1",
            "reason": "x",
            "csrf_token": "csrf-218",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "no longer matches" in response.text
    assert "get" not in seen and "reset" not in seen

    # Missing URL target is refused even with a valid hidden field.
    response = client.post(
        "/admin/accounts/reset",
        data={
            "admin_id": str(target.id),
            "password": PASSWORD,
            "password_confirmation": CONFIRMATION,
            "confirm_reset": "1",
            "reason": "x",
            "csrf_token": "csrf-218",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "reset" not in seen


def test_reset_requires_confirmation_and_matching_passwords(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    seen = _patch_admin_service(monkeypatch, get=target, reset=target)
    client = _client(monkeypatch, root)
    import slaif_gateway.api.admin_accounts as router_mod
    monkeypatch.setattr(
        router_mod,
        "hash_admin_password",
        lambda value: (_ for _ in ()).throw(AssertionError("no hashing")),
    )

    response = _reset_post(client, target, confirm_reset="")
    assert response.status_code == 400
    assert "reset" not in seen

    response = _reset_post(client, target, password_confirmation=CONFIRMATION + "x")
    assert response.status_code == 400
    assert "do not match exactly" in response.text
    assert "reset" not in seen
    # The complete secrets are never echoed in the error re-render.
    assert PASSWORD not in response.text
    assert CONFIRMATION + "x" not in response.text
    # The server-refetched target identity is still displayed on the
    # validation-recovery re-render.
    assert target.email in response.text
    assert f'name="admin_id" value="{target.id}"' in response.text


def test_reset_missing_target_answers_404(monkeypatch) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    _patch_admin_service(monkeypatch, get=target, reset=RecordNotFoundError("Admin user"))
    client = _client(monkeypatch, root)

    response = _reset_post(client, target)

    assert response.status_code == 404
    assert "no longer exists" in response.text
    assert PASSWORD not in response.text


def test_reset_fault_path_fixed_unconfirmed_no_raw_text(monkeypatch, capsys) -> None:
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    _patch_admin_service(
        monkeypatch,
        get=target,
        reset=RuntimeError(f"commit failed {PASSWORD} {ARGON2_HASH}"),
    )
    client = _client(monkeypatch, root)

    response = _reset_post(client, target)

    assert response.status_code == 500
    body = response.text
    assert "could not be confirmed" in body
    assert "nothing was committed" not in body
    assert "unchanged" not in body
    assert PASSWORD not in body
    assert ARGON2_HASH not in body
    captured = capsys.readouterr()
    assert PASSWORD not in captured.out
    assert ARGON2_HASH not in captured.out
    assert PASSWORD not in captured.err
    assert ARGON2_HASH not in captured.err


def test_full_bodies_and_logs_canary_across_surfaces(monkeypatch, capsys) -> None:
    """Complete bodies (every collected response, INCLUDING the 400
    validation re-renders) + captured logs (stdout structured logs and
    stderr) across representative 218 surfaces must never carry the
    canary secrets."""
    root = _admin_user(email="root@example.org", role="superadmin")
    target = _account_row(email="target@example.org")
    rows = [target, _account_row(email="second@example.org")]
    _patch_admin_service(
        monkeypatch, list_rows=rows, get=target, create=target, reset=target
    )
    client = _client(monkeypatch, root)

    responses = [
        ("list", client.get("/admin/accounts")),
        ("create-form", client.get("/admin/accounts/create")),
        ("create-validation-400", _create_post(client, confirm_create="")),
        ("create-success", _create_post(client)),
        ("reset-form", _reset_get(client, target)),
        ("reset-validation-400", _reset_post(client, target, confirm_reset="")),
        ("reset-success", _reset_post(client, target)),
    ]
    by_name = {name: response for name, response in responses}
    # Explicit expected status/outcome checks for every collected response.
    assert by_name["list"].status_code == 200
    assert target.email in by_name["list"].text
    assert by_name["create-form"].status_code == 200
    assert by_name["create-validation-400"].status_code == 400
    assert by_name["create-success"].status_code == 303
    assert by_name["create-success"].headers["location"] == (
        "/admin/accounts?message=admin_account_created"
    )
    assert by_name["reset-form"].status_code == 200
    assert by_name["reset-validation-400"].status_code == 400
    assert by_name["reset-success"].status_code == 303
    assert by_name["reset-success"].headers["location"] == (
        "/admin/accounts?message=admin_password_reset"
    )

    # ALL collected bodies (success, redirect, and error re-renders alike).
    bodies = "\n".join(response.text for _name, response in responses)
    captured = capsys.readouterr()
    logs = captured.out + "\n" + captured.err

    for secret in (PASSWORD, CONFIRMATION, SESSION_TOKEN, PROVIDER_SECRET, ARGON2_HASH):
        assert secret not in bodies, secret
        assert secret not in logs, secret
