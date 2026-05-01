import asyncio
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, Cohort, Institution, Owner, UsageLedger
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin(database_url: str) -> dict[str, str]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-records-{suffix}@example.org",
                display_name="Records Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            usage_count = await session.scalar(select(func.count()).select_from(UsageLedger))
    await engine.dispose()
    return {
        "admin_email": admin.email,
        "admin_password": "correct horse battery staple",
        "usage_count": str(usage_count or 0),
    }


async def _record_counts(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        payload = {
            "institutions": int(await session.scalar(select(func.count()).select_from(Institution)) or 0),
            "cohorts": int(await session.scalar(select(func.count()).select_from(Cohort)) or 0),
            "owners": int(await session.scalar(select(func.count()).select_from(Owner)) or 0),
            "usage": int(await session.scalar(select(func.count()).select_from(UsageLedger)) or 0),
        }
    await engine.dispose()
    return payload


async def _load_record_state(
    database_url: str,
    *,
    institution_id: uuid.UUID,
    cohort_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        institution = await session.get(Institution, institution_id)
        cohort = await session.get(Cohort, cohort_id)
        owner = await session.get(Owner, owner_id)
        assert institution is not None
        assert cohort is not None
        assert owner is not None
        audit_rows = list((await session.execute(select(AuditLog).order_by(AuditLog.created_at.asc()))).scalars())
        payload = {
            "institution": institution,
            "cohort": cohort,
            "owner": owner,
            "audit_rows": audit_rows,
            "usage_count": int(await session.scalar(select(func.count()).select_from(UsageLedger)) or 0),
        }
    await engine.dispose()
    return payload


def _extract_detail_id(location: str) -> uuid.UUID:
    match = re.search(r"/admin/(?:institutions|cohorts|owners)/([^?]+)", location)
    assert match is not None
    return uuid.UUID(match.group(1))


def test_admin_record_mutation_forms_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    institution_name = f"Integration University {suffix}"
    updated_institution_name = f"Integration University Updated {suffix}"
    cohort_name = f"Integration Cohort {suffix}"
    updated_cohort_name = f"Integration Cohort Updated {suffix}"
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/institutions/new",
            data={"name": "Blocked", "csrf_token": "missing", "reason": "records update"},
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303

        login_page = client.get("/admin/login")
        csrf = _csrf_from_html(login_page.text)
        login = client.post(
            "/admin/login",
            data={
                "email": data["admin_email"],
                "password": data["admin_password"],
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        for path in ("/admin/institutions/new", "/admin/cohorts/new", "/admin/owners/new"):
            page = client.get(path)
            assert page.status_code == 200
            assert 'name="csrf_token"' in page.text
            assert 'name="reason"' in page.text

        institution_page = client.get("/admin/institutions/new")
        institution_csrf = _csrf_from_html(institution_page.text)
        create_institution = client.post(
            "/admin/institutions/new",
            data={
                "csrf_token": institution_csrf,
                "name": institution_name,
                "country": "SI",
                "notes": "safe institution note",
                "reason": "create prerequisite record",
            },
            follow_redirects=False,
        )
        assert create_institution.status_code == 303
        institution_id = _extract_detail_id(create_institution.headers["location"])

        edit_institution_page = client.get(f"/admin/institutions/{institution_id}/edit")
        edit_institution = client.post(
            f"/admin/institutions/{institution_id}/edit",
            data={
                "csrf_token": _csrf_from_html(edit_institution_page.text),
                "name": updated_institution_name,
                "country": "AT",
                "notes": "safe updated institution note",
                "reason": "update prerequisite record",
            },
            follow_redirects=False,
        )
        assert edit_institution.status_code == 303

        cohort_page = client.get("/admin/cohorts/new")
        create_cohort = client.post(
            "/admin/cohorts/new",
            data={
                "csrf_token": _csrf_from_html(cohort_page.text),
                "name": cohort_name,
                "description": "safe cohort note",
                "starts_at": "2026-01-01T00:00:00+00:00",
                "ends_at": "2026-02-01T00:00:00+00:00",
                "reason": "create prerequisite record",
            },
            follow_redirects=False,
        )
        assert create_cohort.status_code == 303
        cohort_id = _extract_detail_id(create_cohort.headers["location"])

        edit_cohort_page = client.get(f"/admin/cohorts/{cohort_id}/edit")
        edit_cohort = client.post(
            f"/admin/cohorts/{cohort_id}/edit",
            data={
                "csrf_token": _csrf_from_html(edit_cohort_page.text),
                "name": updated_cohort_name,
                "description": "safe updated cohort note",
                "starts_at": "2026-01-05T00:00:00+00:00",
                "ends_at": "2026-02-05T00:00:00+00:00",
                "reason": "update prerequisite record",
            },
            follow_redirects=False,
        )
        assert edit_cohort.status_code == 303

        owner_page = client.get("/admin/owners/new")
        create_owner = client.post(
            "/admin/owners/new",
            data={
                "csrf_token": _csrf_from_html(owner_page.text),
                "name": "Ada",
                "surname": "Lovelace",
                "email": f"owner-records-{uuid.uuid4().hex}@example.org",
                "institution_id": str(institution_id),
                "external_id": "safe-external-id",
                "notes": "safe owner note",
                "is_active": "true",
                "reason": "create prerequisite record",
            },
            follow_redirects=False,
        )
        assert create_owner.status_code == 303
        owner_id = _extract_detail_id(create_owner.headers["location"])

        edit_owner_page = client.get(f"/admin/owners/{owner_id}/edit")
        edit_owner = client.post(
            f"/admin/owners/{owner_id}/edit",
            data={
                "csrf_token": _csrf_from_html(edit_owner_page.text),
                "name": "Ada Updated",
                "surname": "Lovelace",
                "email": f"owner-records-updated-{uuid.uuid4().hex}@example.org",
                "institution_id": str(institution_id),
                "external_id": "safe-external-id-updated",
                "notes": "safe updated owner note",
                "is_active": "true",
                "reason": "update prerequisite record",
            },
            follow_redirects=False,
        )
        assert edit_owner.status_code == 303

        before_invalid = asyncio.run(_record_counts(migrated_postgres_url))
        invalid_email = client.post(
            "/admin/owners/new",
            data={
                "csrf_token": _csrf_from_html(client.get("/admin/owners/new").text),
                "name": "Invalid",
                "surname": "Email",
                "email": "not-an-email",
                "institution_id": str(institution_id),
                "external_id": "",
                "notes": "safe",
                "is_active": "true",
                "reason": "records update",
            },
        )
        missing_reason = client.post(
            "/admin/cohorts/new",
            data={
                "csrf_token": _csrf_from_html(client.get("/admin/cohorts/new").text),
                "name": "Missing Reason",
                "description": "safe",
                "starts_at": "",
                "ends_at": "",
                "reason": "",
            },
        )
        no_csrf = client.post(
            "/admin/institutions/new",
            data={
                "name": "No CSRF University",
                "country": "SI",
                "notes": "safe",
                "reason": "records update",
            },
        )
        after_invalid = asyncio.run(_record_counts(migrated_postgres_url))

        assert invalid_email.status_code == 400
        assert missing_reason.status_code == 400
        assert no_csrf.status_code == 400
        assert after_invalid == before_invalid

        combined = "\n".join(
            [
                client.get(f"/admin/institutions/{institution_id}").text,
                client.get(f"/admin/cohorts/{cohort_id}").text,
                client.get(f"/admin/owners/{owner_id}").text,
            ]
        )
        assert updated_institution_name in combined
        assert updated_cohort_name in combined
        assert "Ada Updated" in combined
        assert "token_hash" not in combined
        assert "encrypted_payload" not in combined
        assert "nonce" not in combined
        assert "password_hash" not in combined
        assert "slaif_admin_session" not in combined
        assert settings.OPENAI_UPSTREAM_API_KEY not in combined
        assert settings.OPENROUTER_API_KEY not in combined
        assert "plaintext gateway key" not in combined.lower()

    state = asyncio.run(
        _load_record_state(
            migrated_postgres_url,
            institution_id=institution_id,
            cohort_id=cohort_id,
            owner_id=owner_id,
        )
    )
    institution = state["institution"]
    cohort = state["cohort"]
    owner = state["owner"]
    audit_rows = state["audit_rows"]

    assert institution.name == updated_institution_name
    assert institution.country == "AT"
    assert cohort.name == updated_cohort_name
    assert owner.name == "Ada Updated"
    assert owner.institution_id == institution_id
    assert state["usage_count"] == int(data["usage_count"])

    record_actions = {
        "institution_created",
        "institution_updated",
        "cohort_created",
        "cohort_updated",
        "owner_created",
        "owner_updated",
    }
    record_audit_rows = [row for row in audit_rows if row.action in record_actions]
    audit_text = "\n".join(str(row.old_values) + str(row.new_values) + str(row.note) for row in record_audit_rows)
    assert "institution_created" in {row.action for row in record_audit_rows}
    assert "institution_updated" in {row.action for row in record_audit_rows}
    assert "cohort_created" in {row.action for row in record_audit_rows}
    assert "cohort_updated" in {row.action for row in record_audit_rows}
    assert "owner_created" in {row.action for row in record_audit_rows}
    assert "owner_updated" in {row.action for row in record_audit_rows}
    assert "token_hash" not in audit_text
    assert "encrypted_payload" not in audit_text
    assert "provider_api_key" not in audit_text
