import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import AdminSessionContext


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
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _login(monkeypatch, client: TestClient, *, valid_csrf: str = "dashboard-csrf") -> AdminUser:
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return valid_csrf

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == valid_csrf

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def _institution_form(**overrides) -> dict[str, str]:
    values = {
        "csrf_token": "dashboard-csrf",
        "name": "SLAIF University",
        "country": "SI",
        "notes": "safe note",
        "reason": "records update",
    }
    values.update(overrides)
    return values


def _cohort_form(**overrides) -> dict[str, str]:
    values = {
        "csrf_token": "dashboard-csrf",
        "name": "Spring Workshop",
        "description": "safe cohort",
        "starts_at": "2026-01-01T00:00:00+00:00",
        "ends_at": "2026-02-01T00:00:00+00:00",
        "reason": "records update",
    }
    values.update(overrides)
    return values


def _owner_form(**overrides) -> dict[str, str]:
    values = {
        "csrf_token": "dashboard-csrf",
        "name": "Ada",
        "surname": "Lovelace",
        "email": "ada@example.org",
        "institution_id": "",
        "external_id": "external-safe",
        "notes": "safe note",
        "is_active": "true",
        "reason": "records update",
    }
    values.update(overrides)
    return values


def _patch_empty_institutions(monkeypatch) -> None:
    async def list_institutions(self, **kwargs):
        return []

    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_institutions",
        list_institutions,
    )


def test_record_create_get_requires_login() -> None:
    client = TestClient(_app())

    for path in ("/admin/institutions/new", "/admin/cohorts/new", "/admin/owners/new"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_record_create_get_renders_csrf_and_reason(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)
    _patch_empty_institutions(monkeypatch)

    for path in ("/admin/institutions/new", "/admin/cohorts/new", "/admin/owners/new"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'name="csrf_token" value="dashboard-csrf"' in response.text
        assert 'name="reason"' in response.text
        assert "token_hash" not in response.text


def test_institution_create_requires_csrf_and_reason_before_service(monkeypatch) -> None:
    called = False

    async def create_institution(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.institution_service.InstitutionService.create_institution",
        create_institution,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    no_csrf = client.post("/admin/institutions/new", data=_institution_form(csrf_token=""))
    no_reason = client.post("/admin/institutions/new", data=_institution_form(reason=""))

    assert no_csrf.status_code == 400
    assert no_reason.status_code == 400
    assert called is False


def test_record_create_rejects_invalid_fields_before_service(monkeypatch) -> None:
    called: list[str] = []

    async def create_institution(self, **kwargs):
        called.append("institution")

    async def create_cohort(self, **kwargs):
        called.append("cohort")

    async def create_owner(self, **kwargs):
        called.append("owner")

    monkeypatch.setattr(
        "slaif_gateway.services.institution_service.InstitutionService.create_institution",
        create_institution,
    )
    monkeypatch.setattr("slaif_gateway.services.cohort_service.CohortService.create_cohort", create_cohort)
    monkeypatch.setattr("slaif_gateway.services.owner_service.OwnerService.create_owner", create_owner)
    _patch_empty_institutions(monkeypatch)
    client = TestClient(_app())
    _login(monkeypatch, client)

    institution = client.post("/admin/institutions/new", data=_institution_form(notes="sk-real-looking-secret"))
    cohort = client.post("/admin/cohorts/new", data=_cohort_form(ends_at="2025-01-01T00:00:00+00:00"))
    owner = client.post("/admin/owners/new", data=_owner_form(email="not-an-email"))

    assert institution.status_code == 400
    assert cohort.status_code == 400
    assert owner.status_code == 400
    assert called == []


def test_valid_record_create_calls_services_with_actor_and_reason(monkeypatch) -> None:
    seen: dict[str, dict[str, object]] = {}
    institution_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    async def create_institution(self, **kwargs):
        seen["institution"] = kwargs
        return SimpleNamespace(id=institution_id)

    async def create_cohort(self, **kwargs):
        seen["cohort"] = kwargs
        return SimpleNamespace(id=cohort_id)

    async def create_owner(self, **kwargs):
        seen["owner"] = kwargs
        return SimpleNamespace(id=owner_id)

    monkeypatch.setattr(
        "slaif_gateway.services.institution_service.InstitutionService.create_institution",
        create_institution,
    )
    monkeypatch.setattr("slaif_gateway.services.cohort_service.CohortService.create_cohort", create_cohort)
    monkeypatch.setattr("slaif_gateway.services.owner_service.OwnerService.create_owner", create_owner)
    _patch_empty_institutions(monkeypatch)
    client = TestClient(_app())
    admin_user = _login(monkeypatch, client)

    institution = client.post("/admin/institutions/new", data=_institution_form(), follow_redirects=False)
    cohort = client.post("/admin/cohorts/new", data=_cohort_form(), follow_redirects=False)
    owner = client.post("/admin/owners/new", data=_owner_form(), follow_redirects=False)

    assert institution.headers["location"] == f"/admin/institutions/{institution_id}?message=institution_created"
    assert cohort.headers["location"] == f"/admin/cohorts/{cohort_id}?message=cohort_created"
    assert owner.headers["location"] == f"/admin/owners/{owner_id}?message=owner_created"
    assert seen["institution"]["actor_admin_id"] == admin_user.id
    assert seen["cohort"]["actor_admin_id"] == admin_user.id
    assert seen["owner"]["actor_admin_id"] == admin_user.id
    assert seen["owner"]["email"] == "ada@example.org"
    assert seen["owner"]["reason"] == "records update"


def test_record_edit_posts_call_services(monkeypatch) -> None:
    seen: dict[str, dict[str, object]] = {}
    institution_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    async def update_institution(self, record_id, **kwargs):
        seen["institution"] = {"record_id": record_id, **kwargs}
        return SimpleNamespace(id=record_id)

    async def update_cohort(self, record_id, **kwargs):
        seen["cohort"] = {"record_id": record_id, **kwargs}
        return SimpleNamespace(id=record_id)

    async def update_owner(self, record_id, **kwargs):
        seen["owner"] = {"record_id": record_id, **kwargs}
        return SimpleNamespace(id=record_id)

    monkeypatch.setattr(
        "slaif_gateway.services.institution_service.InstitutionService.update_institution",
        update_institution,
    )
    monkeypatch.setattr("slaif_gateway.services.cohort_service.CohortService.update_cohort", update_cohort)
    monkeypatch.setattr("slaif_gateway.services.owner_service.OwnerService.update_owner", update_owner)
    _patch_empty_institutions(monkeypatch)
    client = TestClient(_app())
    _login(monkeypatch, client)

    institution = client.post(
        f"/admin/institutions/{institution_id}/edit",
        data=_institution_form(name="Updated University"),
        follow_redirects=False,
    )
    cohort = client.post(
        f"/admin/cohorts/{cohort_id}/edit",
        data=_cohort_form(name="Updated Workshop"),
        follow_redirects=False,
    )
    owner = client.post(
        f"/admin/owners/{owner_id}/edit",
        data=_owner_form(name="Updated"),
        follow_redirects=False,
    )

    assert institution.headers["location"] == f"/admin/institutions/{institution_id}?message=institution_updated"
    assert cohort.headers["location"] == f"/admin/cohorts/{cohort_id}?message=cohort_updated"
    assert owner.headers["location"] == f"/admin/owners/{owner_id}?message=owner_updated"
    assert seen["institution"]["name"] == "Updated University"
    assert seen["cohort"]["name"] == "Updated Workshop"
    assert seen["owner"]["name"] == "Updated"
