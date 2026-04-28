import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import Cohort, Institution, Owner
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_records(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-{uuid.uuid4()}@example.org",
                display_name="Integration Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            institution = await InstitutionsRepository(session).create_institution(
                name=f"SLAIF University {uuid.uuid4()}",
                country="SI",
                notes="safe institution note",
            )
            other_institution = await InstitutionsRepository(session).create_institution(
                name=f"Other University {uuid.uuid4()}",
                country="SI",
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"Workshop {uuid.uuid4()}",
                description="safe cohort description",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await OwnersRepository(session).create_owner(
                name="Ada",
                surname="Lovelace",
                email=f"owner-{uuid.uuid4()}@example.org",
                institution_id=institution.id,
                notes="safe owner note",
            )
            other_owner = await OwnersRepository(session).create_owner(
                name="Grace",
                surname="Hopper",
                email=f"other-{uuid.uuid4()}@example.org",
                institution_id=other_institution.id,
            )
            active_key = await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=f"public-{uuid.uuid4()}",
                token_hash="token_hash_must_not_render_" + uuid.uuid4().hex,
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                key_hint="sk-slaif-public-hint",
                cost_limit_eur=Decimal("12.000000000"),
                token_limit_total=1200,
                request_limit_total=120,
                allowed_models=["gpt-test"],
                allowed_endpoints=["/v1/chat/completions"],
                metadata_json={"allowed_providers": ["openai"]},
                created_by_admin_user_id=admin.id,
            )
            await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=f"other-{uuid.uuid4()}",
                token_hash="other_token_hash_must_not_render_" + uuid.uuid4().hex,
                owner_id=other_owner.id,
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                key_hint="sk-slaif-other-hint",
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
                "owner_id": owner.id,
                "owner_email": owner.email,
                "owner_name": f"{owner.name} {owner.surname}",
                "owner_updated_at": owner.updated_at,
                "institution_id": institution.id,
                "institution_name": institution.name,
                "institution_updated_at": institution.updated_at,
                "cohort_id": cohort.id,
                "cohort_name": cohort.name,
                "cohort_updated_at": cohort.updated_at,
                "public_key_id": active_key.public_key_id,
                "token_hash": active_key.token_hash,
            }
    await engine.dispose()
    return payload


async def _get_records(database_url: str, owner_id: uuid.UUID, institution_id: uuid.UUID, cohort_id: uuid.UUID):
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        owner = await session.get(Owner, owner_id)
        institution = await session.get(Institution, institution_id)
        cohort = await session.get(Cohort, cohort_id)
        assert owner is not None
        assert institution is not None
        assert cohort is not None
        payload = {
            "owner_updated_at": owner.updated_at,
            "institution_updated_at": institution.updated_at,
            "cohort_updated_at": cohort.updated_at,
        }
    await engine.dispose()
    return payload


def test_admin_records_readonly_pages(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_records(migrated_postgres_url))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        for path in ("/admin/owners", "/admin/institutions", "/admin/cohorts"):
            unauthenticated = client.get(path, follow_redirects=False)
            assert unauthenticated.status_code == 303
            assert unauthenticated.headers["location"] == "/admin/login"

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

        owners = client.get("/admin/owners")
        assert owners.status_code == 200
        assert data["owner_email"] in owners.text
        assert data["owner_name"] in owners.text
        assert data["institution_name"] in owners.text

        owner_filtered = client.get(
            "/admin/owners",
            params={
                "email": data["owner_email"],
                "institution_id": str(data["institution_id"]),
                "cohort_id": str(data["cohort_id"]),
            },
        )
        assert owner_filtered.status_code == 200
        assert data["owner_email"] in owner_filtered.text

        owner_detail = client.get(f"/admin/owners/{data['owner_id']}")
        assert owner_detail.status_code == 200
        assert data["owner_email"] in owner_detail.text
        assert data["public_key_id"] in owner_detail.text

        institutions = client.get("/admin/institutions")
        assert institutions.status_code == 200
        assert data["institution_name"] in institutions.text

        institution_filtered = client.get("/admin/institutions", params={"name": data["institution_name"]})
        assert institution_filtered.status_code == 200
        assert data["institution_name"] in institution_filtered.text

        institution_detail = client.get(f"/admin/institutions/{data['institution_id']}")
        assert institution_detail.status_code == 200
        assert data["institution_name"] in institution_detail.text
        assert data["public_key_id"] in institution_detail.text

        cohorts = client.get("/admin/cohorts")
        assert cohorts.status_code == 200
        assert data["cohort_name"] in cohorts.text

        cohort_filtered = client.get("/admin/cohorts", params={"name": data["cohort_name"], "active": "true"})
        assert cohort_filtered.status_code == 200
        assert data["cohort_name"] in cohort_filtered.text

        cohort_detail = client.get(f"/admin/cohorts/{data['cohort_id']}")
        assert cohort_detail.status_code == 200
        assert data["cohort_name"] in cohort_detail.text
        assert data["public_key_id"] in cohort_detail.text

        combined = "\n".join(
            [
                owners.text,
                owner_detail.text,
                institutions.text,
                institution_detail.text,
                cohorts.text,
                cohort_detail.text,
            ]
        )
        assert "token_hash" not in combined
        assert data["token_hash"] not in combined
        assert "encrypted_payload" not in combined
        assert "nonce" not in combined
        assert "password_hash" not in combined
        assert "slaif_admin_session" not in combined
        assert settings.OPENAI_UPSTREAM_API_KEY not in combined
        assert settings.OPENROUTER_API_KEY not in combined
        assert "prompt" not in combined.lower()
        assert "completion" not in combined.lower()

        assert client.get("/admin/owners/not-a-uuid").status_code == 404
        assert client.get(f"/admin/owners/{uuid.uuid4()}").status_code == 404
        assert client.get("/admin/institutions/not-a-uuid").status_code == 404
        assert client.get(f"/admin/institutions/{uuid.uuid4()}").status_code == 404
        assert client.get("/admin/cohorts/not-a-uuid").status_code == 404
        assert client.get(f"/admin/cohorts/{uuid.uuid4()}").status_code == 404

    after = asyncio.run(
        _get_records(
            migrated_postgres_url,
            data["owner_id"],
            data["institution_id"],
            data["cohort_id"],
        )
    )
    assert after["owner_updated_at"] == data["owner_updated_at"]
    assert after["institution_updated_at"] == data["institution_updated_at"]
    assert after["cohort_updated_at"] == data["cohort_updated_at"]
