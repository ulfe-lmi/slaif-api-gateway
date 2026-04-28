import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_records import (
    AdminCohortDetail,
    AdminCohortListRow,
    AdminInstitutionDetail,
    AdminInstitutionListRow,
    AdminOwnerDetail,
    AdminOwnerListRow,
    AdminRelatedKeySummary,
)
from slaif_gateway.services.admin_records_dashboard import AdminRecordNotFoundError
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


def _admin_user() -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )


def _admin_session(admin_user: AdminUser) -> AdminSession:
    session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.admin_user = admin_user
    return session


def _login(monkeypatch, client: TestClient) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")


def _key_summary() -> AdminRelatedKeySummary:
    return AdminRelatedKeySummary(
        id=uuid.uuid4(),
        public_key_id="public-record-key",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_email="ada@example.org",
        status="active",
        computed_display_status="active",
        valid_until=datetime.now(UTC) + timedelta(days=1),
    )


def _owner() -> AdminOwnerDetail:
    row = AdminOwnerListRow(
        id=uuid.uuid4(),
        name="Ada",
        surname="Lovelace",
        display_name="Ada Lovelace",
        email="ada@example.org",
        institution_id=uuid.uuid4(),
        institution_name="SLAIF University",
        is_active=True,
        key_count=2,
        active_key_count=1,
        created_at=datetime.now(UTC) - timedelta(days=2),
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )
    return AdminOwnerDetail(
        **asdict(row),
        external_id="external-safe-id",
        notes="safe owner note",
        anonymized_at=None,
        recent_keys=(_key_summary(),),
    )


def _institution() -> AdminInstitutionDetail:
    row = AdminInstitutionListRow(
        id=uuid.uuid4(),
        name="SLAIF University",
        country="SI",
        owner_count=2,
        key_count=3,
        active_key_count=1,
        created_at=datetime.now(UTC) - timedelta(days=3),
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )
    return AdminInstitutionDetail(**asdict(row), notes="safe institution note", recent_keys=(_key_summary(),))


def _cohort() -> AdminCohortDetail:
    row = AdminCohortListRow(
        id=uuid.uuid4(),
        name="Spring Workshop",
        description="safe cohort description",
        starts_at=datetime.now(UTC) - timedelta(days=1),
        ends_at=datetime.now(UTC) + timedelta(days=30),
        owner_count=2,
        key_count=3,
        active_key_count=1,
        created_at=datetime.now(UTC) - timedelta(days=3),
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )
    return AdminCohortDetail(**asdict(row), recent_keys=(_key_summary(),))


def test_admin_record_routes_redirect_when_unauthenticated() -> None:
    client = TestClient(_app())

    for path in ("/admin/owners", "/admin/institutions", "/admin/cohorts"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_admin_owner_routes_return_html_and_accept_filters(monkeypatch) -> None:
    owner = _owner()
    seen: dict[str, object] = {}

    async def list_owners(self, **kwargs):
        seen.update(kwargs)
        return [owner]

    async def get_owner_detail(self, owner_id):
        assert owner_id == owner.id
        return owner

    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_owners",
        list_owners,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_owner_detail",
        get_owner_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(
        "/admin/owners",
        params={
            "email": owner.email,
            "institution_id": str(owner.institution_id),
            "cohort_id": str(uuid.uuid4()),
            "limit": "25",
            "offset": "5",
        },
    )
    detail = client.get(f"/admin/owners/{owner.id}")

    assert response.status_code == 200
    assert detail.status_code == 200
    assert "Owners" in response.text
    assert "Owner Detail" in detail.text
    assert owner.email in response.text
    assert owner.display_name in detail.text
    assert seen["email"] == owner.email
    assert seen["institution_id"] == owner.institution_id
    assert seen["limit"] == 25
    assert seen["offset"] == 5


def test_admin_institution_routes_return_html_and_accept_filters(monkeypatch) -> None:
    institution = _institution()
    seen: dict[str, object] = {}

    async def list_institutions(self, **kwargs):
        seen.update(kwargs)
        return [institution]

    async def get_institution_detail(self, institution_id):
        assert institution_id == institution.id
        return institution

    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_institutions",
        list_institutions,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_institution_detail",
        get_institution_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get("/admin/institutions", params={"name": "slaif", "limit": "20", "offset": "2"})
    detail = client.get(f"/admin/institutions/{institution.id}")

    assert response.status_code == 200
    assert detail.status_code == 200
    assert "Institutions" in response.text
    assert "Institution Detail" in detail.text
    assert institution.name in response.text
    assert institution.name in detail.text
    assert seen["name"] == "slaif"
    assert seen["limit"] == 20
    assert seen["offset"] == 2


def test_admin_cohort_routes_return_html_and_accept_filters(monkeypatch) -> None:
    cohort = _cohort()
    seen: dict[str, object] = {}

    async def list_cohorts(self, **kwargs):
        seen.update(kwargs)
        return [cohort]

    async def get_cohort_detail(self, cohort_id):
        assert cohort_id == cohort.id
        return cohort

    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_cohorts",
        list_cohorts,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_cohort_detail",
        get_cohort_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get("/admin/cohorts", params={"name": "spring", "active": "true", "limit": "10", "offset": "1"})
    detail = client.get(f"/admin/cohorts/{cohort.id}")

    assert response.status_code == 200
    assert detail.status_code == 200
    assert "Cohorts" in response.text
    assert "Cohort Detail" in detail.text
    assert cohort.name in response.text
    assert cohort.name in detail.text
    assert seen["name"] == "spring"
    assert seen["active"] is True
    assert seen["limit"] == 10
    assert seen["offset"] == 1


def test_admin_record_missing_or_invalid_ids_are_safe(monkeypatch) -> None:
    async def missing(self, record_id):
        raise AdminRecordNotFoundError("missing")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_owner_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_institution_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_cohort_detail",
        missing,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    assert client.get("/admin/owners/not-a-uuid").status_code == 404
    assert client.get(f"/admin/owners/{uuid.uuid4()}").status_code == 404
    assert client.get("/admin/institutions/not-a-uuid").status_code == 404
    assert client.get(f"/admin/institutions/{uuid.uuid4()}").status_code == 404
    assert client.get("/admin/cohorts/not-a-uuid").status_code == 404
    assert client.get(f"/admin/cohorts/{uuid.uuid4()}").status_code == 404


def test_admin_record_list_invalid_uuid_filters_are_safe(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get("/admin/owners", params={"institution_id": "not-a-uuid"})

    assert response.status_code == 400
    assert "Invalid filter." in response.text
