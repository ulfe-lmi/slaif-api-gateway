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


def _key_summary() -> AdminRelatedKeySummary:
    return AdminRelatedKeySummary(
        id=uuid.uuid4(),
        public_key_id="public-safe-record-key",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_email="ada@example.org",
        status="active",
        computed_display_status="active",
        valid_until=datetime.now(UTC) + timedelta(days=1),
    )


def _records():
    owner_row = AdminOwnerListRow(
        id=uuid.uuid4(),
        name="Ada",
        surname="Lovelace",
        display_name="Ada Lovelace",
        email="ada@example.org",
        institution_id=uuid.uuid4(),
        institution_name="SLAIF University",
        is_active=True,
        key_count=1,
        active_key_count=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    institution_row = AdminInstitutionListRow(
        id=owner_row.institution_id,
        name="SLAIF University",
        country="SI",
        owner_count=1,
        key_count=1,
        active_key_count=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    cohort_row = AdminCohortListRow(
        id=uuid.uuid4(),
        name="Spring Workshop",
        description="safe cohort description",
        starts_at=datetime.now(UTC) - timedelta(days=1),
        ends_at=datetime.now(UTC) + timedelta(days=10),
        owner_count=1,
        key_count=1,
        active_key_count=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return (
        AdminOwnerDetail(
            **asdict(owner_row),
            external_id="external-safe-id",
            notes="safe owner note",
            anonymized_at=None,
            recent_keys=(_key_summary(),),
        ),
        AdminInstitutionDetail(
            **asdict(institution_row),
            notes="safe institution note",
            recent_keys=(_key_summary(),),
        ),
        AdminCohortDetail(**asdict(cohort_row), recent_keys=(_key_summary(),)),
    )


def test_admin_record_pages_render_only_safe_metadata(monkeypatch) -> None:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-that-must-not-render",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)
    app.state.db_sessionmaker = _FakeSessionmaker()
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
    owner, institution, cohort = _records()

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    async def list_owners(self, **kwargs):
        return [owner]

    async def get_owner_detail(self, owner_id):
        return owner

    async def list_institutions(self, **kwargs):
        return [institution]

    async def get_institution_detail(self, institution_id):
        return institution

    async def list_cohorts(self, **kwargs):
        return [cohort]

    async def get_cohort_detail(self, cohort_id):
        return cohort

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_owners",
        list_owners,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_owner_detail",
        get_owner_detail,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_institutions",
        list_institutions,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_institution_detail",
        get_institution_detail,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_cohorts",
        list_cohorts,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.get_cohort_detail",
        get_cohort_detail,
    )
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "session-token-must-not-render")

    combined = "\n".join(
        [
            client.get("/admin/owners").text,
            client.get(f"/admin/owners/{owner.id}").text,
            client.get("/admin/institutions").text,
            client.get(f"/admin/institutions/{institution.id}").text,
            client.get("/admin/cohorts").text,
            client.get(f"/admin/cohorts/{cohort.id}").text,
        ]
    )

    assert owner.email in combined
    assert institution.name in combined
    assert cohort.name in combined
    assert "public-safe-record-key" in combined
    assert "password_hash_must_not_render" not in combined
    assert "session_hash_must_not_render" not in combined
    assert "session-token-must-not-render" not in combined
    assert settings.ADMIN_SESSION_SECRET not in combined
    assert settings.OPENAI_UPSTREAM_API_KEY not in combined
    assert settings.OPENROUTER_API_KEY not in combined
    assert "token_hash" not in combined
    assert "encrypted_payload" not in combined
    assert "nonce" not in combined
    assert "plaintext gateway key" not in combined.lower()
    assert "prompt text must not render" not in combined
    assert "completion text must not render" not in combined
