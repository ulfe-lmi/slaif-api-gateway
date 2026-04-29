import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AuditLog
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_user(database_url: str, *, email: str, password: str) -> uuid.UUID:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            repo = AdminUsersRepository(session)
            admin_user = await repo.create_admin_user(
                email=email,
                display_name="Integration Admin",
                password_hash=hash_admin_password(password),
                role="admin",
                is_active=True,
            )
            admin_user_id = admin_user.id
    await engine.dispose()
    return admin_user_id


async def _get_sessions(database_url: str, admin_user_id: uuid.UUID) -> list[AdminSession]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(AdminSession)
            .where(AdminSession.admin_user_id == admin_user_id)
            .order_by(AdminSession.created_at.asc())
        )
        rows = list(result.scalars().all())
    await engine.dispose()
    return rows


async def _session_count(database_url: str, admin_user_id: uuid.UUID) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(AdminSession).where(AdminSession.admin_user_id == admin_user_id)
        )
        count = int(result.scalar_one())
    await engine.dispose()
    return count


async def _audit_rows(database_url: str, *, actions: tuple[str, ...], email: str | None = None) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        statement = select(AuditLog).where(AuditLog.action.in_(actions))
        if email is not None:
            statement = statement.where(AuditLog.new_values["email"].as_string() == email)
        result = await session.execute(statement.order_by(AuditLog.created_at.asc()))
        rows = list(result.scalars().all())
    await engine.dispose()
    return rows


async def _age_login_audits(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                update(AuditLog)
                .where(AuditLog.action.in_(("admin_login_failed", "admin_login_rate_limited")))
                .values(created_at=datetime.now(UTC) - timedelta(hours=2))
            )
    await engine.dispose()


async def _expire_session(database_url: str, admin_session_id: uuid.UUID) -> None:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                update(AdminSession)
                .where(AdminSession.id == admin_session_id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1), revoked_at=None)
            )
    await engine.dispose()


def test_admin_web_auth_session_and_csrf_flow(migrated_postgres_url: str) -> None:
    email = f"admin-{uuid.uuid4()}@example.org"
    password = "correct horse battery staple"
    admin_user_id = asyncio.run(_create_admin_user(migrated_postgres_url, email=email, password=password))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        login_page = client.get("/admin/login")
        assert login_page.status_code == 200
        login_csrf = _csrf_from_html(login_page.text)

        wrong_password = client.post(
            "/admin/login",
            data={"email": email, "password": "wrong", "csrf_token": login_csrf},
        )
        assert wrong_password.status_code == 401
        assert "Invalid email or password." in wrong_password.text
        assert email not in wrong_password.text
        assert asyncio.run(_session_count(migrated_postgres_url, admin_user_id)) == 0

        login_page = client.get("/admin/login")
        login_csrf = _csrf_from_html(login_page.text)
        login_response = client.post(
            "/admin/login",
            data={"email": email, "password": password, "csrf_token": login_csrf},
            follow_redirects=False,
        )
        assert login_response.status_code == 303
        assert login_response.headers["location"] == "/admin"
        set_cookie = login_response.headers["set-cookie"]
        assert "slaif_admin_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "secure" not in set_cookie.lower()

        session_cookie = client.cookies.get("slaif_admin_session")
        assert session_cookie
        sessions = asyncio.run(_get_sessions(migrated_postgres_url, admin_user_id))
        assert len(sessions) == 1
        admin_session = sessions[0]
        assert admin_session.session_token_hash.startswith("sha256:")
        assert session_cookie not in admin_session.session_token_hash
        assert admin_session.revoked_at is None

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert "Dashboard Foundation" in dashboard.text
        assert "password_hash" not in dashboard.text
        assert session_cookie not in dashboard.text
        logout_csrf = _csrf_from_html(dashboard.text)

        logout_response = client.post(
            "/admin/logout",
            data={"csrf_token": logout_csrf},
            follow_redirects=False,
        )
        assert logout_response.status_code == 303
        assert logout_response.headers["location"] == "/admin/login"
        assert "slaif_admin_session=" in logout_response.headers["set-cookie"]
        assert "Max-Age=0" in logout_response.headers["set-cookie"]

        revoked_session = asyncio.run(_get_sessions(migrated_postgres_url, admin_user_id))[0]
        assert revoked_session.revoked_at is not None
        assert client.get("/admin", follow_redirects=False).status_code == 303

        login_page = client.get("/admin/login")
        login_csrf = _csrf_from_html(login_page.text)
        second_login = client.post(
            "/admin/login",
            data={"email": email, "password": password, "csrf_token": login_csrf},
            follow_redirects=False,
        )
        assert second_login.status_code == 303
        second_session_cookie = client.cookies.get("slaif_admin_session")
        second_session = asyncio.run(_get_sessions(migrated_postgres_url, admin_user_id))[-1]
        asyncio.run(_expire_session(migrated_postgres_url, second_session.id))

        expired_response = client.get("/admin", follow_redirects=False)
        assert expired_response.status_code == 303
        assert expired_response.headers["location"] == "/admin/login"
        assert second_session_cookie not in expired_response.text


def test_admin_login_rate_limit_blocks_brute_force_attempts(migrated_postgres_url: str) -> None:
    email = f"admin-{uuid.uuid4()}@example.org"
    password = "correct horse battery staple"
    admin_user_id = asyncio.run(_create_admin_user(migrated_postgres_url, email=email, password=password))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        ADMIN_LOGIN_MAX_FAILED_ATTEMPTS=3,
        ADMIN_LOGIN_WINDOW_SECONDS=1800,
        ADMIN_LOGIN_LOCKOUT_SECONDS=1800,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        for _ in range(3):
            login_page = client.get("/admin/login")
            login_csrf = _csrf_from_html(login_page.text)
            wrong_password = client.post(
                "/admin/login",
                data={"email": email.upper(), "password": "wrong", "csrf_token": login_csrf},
            )
            assert wrong_password.status_code == 401
            assert "Invalid email or password." in wrong_password.text
            assert email not in wrong_password.text
            assert "wrong" not in wrong_password.text

        assert asyncio.run(_session_count(migrated_postgres_url, admin_user_id)) == 0

        login_page = client.get("/admin/login")
        login_csrf = _csrf_from_html(login_page.text)
        blocked = client.post(
            "/admin/login",
            data={"email": email, "password": password, "csrf_token": login_csrf},
            follow_redirects=False,
        )
        assert blocked.status_code == 429
        assert "Too many failed login attempts. Try again later." in blocked.text
        assert email not in blocked.text
        assert password not in blocked.text
        assert asyncio.run(_session_count(migrated_postgres_url, admin_user_id)) == 0

        audit_rows = asyncio.run(
            _audit_rows(
                migrated_postgres_url,
                actions=("admin_login_failed", "admin_login_rate_limited"),
                email=email,
            )
        )
        assert [row.action for row in audit_rows].count("admin_login_failed") == 3
        assert [row.action for row in audit_rows].count("admin_login_rate_limited") >= 1
        audit_dump = " ".join(
            str(value)
            for row in audit_rows
            for value in (row.old_values, row.new_values, row.note, row.user_agent)
        )
        assert password not in audit_dump
        assert "password_hash" not in audit_dump
        assert "slaif_admin_session" not in audit_dump
        assert audit_rows[0].new_values["email"] == email

        asyncio.run(_age_login_audits(migrated_postgres_url))
        login_page = client.get("/admin/login")
        login_csrf = _csrf_from_html(login_page.text)
        successful = client.post(
            "/admin/login",
            data={"email": email, "password": password, "csrf_token": login_csrf},
            follow_redirects=False,
        )

        assert successful.status_code == 303
        assert successful.headers["location"] == "/admin"
        assert asyncio.run(_session_count(migrated_postgres_url, admin_user_id)) == 1
