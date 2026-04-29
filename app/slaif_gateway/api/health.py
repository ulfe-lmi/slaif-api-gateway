"""Health and readiness API routes."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from slaif_gateway.config import Settings
from slaif_gateway.db.schema_status import check_schema_current

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    redis_status = await _redis_status(request, settings)
    if settings is None or not settings.DATABASE_URL:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "not_configured",
                "redis": redis_status,
            },
        )

    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "not_initialized",
                "redis": redis_status,
            },
        )

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            schema_status = await check_schema_current(connection)
            provider_secret_status = (
                await _provider_secret_status(connection, settings, schema_status.is_current)
                if settings is not None and settings.APP_ENV.lower() == "production"
                else None
            )
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "error",
                "redis": redis_status,
            },
        )

    if not schema_status.is_current or redis_status == "error":
        return JSONResponse(
            status_code=503,
            content=_readyz_database_content(
                status="not_ready",
                database="ok",
                schema=schema_status.status,
                redis=redis_status,
                settings=settings,
                current_revision=schema_status.current_revision,
                head_revision=schema_status.head_revision,
                provider_secret_status=None,
            ),
        )

    ready = provider_secret_status is None or provider_secret_status.status != "missing"
    return JSONResponse(
        status_code=200 if ready else 503,
        content=_readyz_database_content(
            status="ok" if ready else "not_ready",
            database="ok",
            schema="ok",
            redis=redis_status,
            settings=settings,
            current_revision=schema_status.current_revision,
            head_revision=schema_status.head_revision,
            provider_secret_status=provider_secret_status,
        ),
    )


async def _redis_status(request: Request, settings: Settings | None) -> str:
    if settings is None or not settings.ENABLE_REDIS_RATE_LIMITS:
        return "not_required"

    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        return "error"

    try:
        await redis_client.ping()
    except Exception:  # noqa: BLE001
        return "error"
    return "ok"


def _readyz_database_content(
    *,
    status: str,
    database: str,
    schema: str,
    redis: str,
    settings: Settings | None,
    current_revision: str | None,
    head_revision: str | None,
    provider_secret_status: "ProviderSecretReadiness | None" = None,
) -> dict[str, str | None]:
    content: dict[str, str | None] = {
        "status": status,
        "database": database,
        "schema": schema,
        "redis": redis,
    }
    if settings is not None and settings.readyz_include_details():
        content["alembic_current"] = current_revision
        content["alembic_head"] = head_revision
    if provider_secret_status is not None:
        content["provider_secrets"] = provider_secret_status.status
        if settings is not None and settings.readyz_include_details() and provider_secret_status.missing_env_vars:
            content["missing_provider_secret_env_vars"] = ",".join(provider_secret_status.missing_env_vars)
    return content


class ProviderSecretReadiness:
    def __init__(self, *, status: str, missing_env_vars: tuple[str, ...] = ()) -> None:
        self.status = status
        self.missing_env_vars = missing_env_vars


async def _provider_secret_status(
    connection,
    settings: Settings | None,
    schema_is_current: bool,
) -> ProviderSecretReadiness:
    if not schema_is_current:
        return ProviderSecretReadiness(status="not_checked")

    result = await connection.execute(
        text(
            "SELECT api_key_env_var FROM provider_configs "
            "WHERE enabled = true ORDER BY provider ASC"
        )
    )
    rows = result.mappings().all()
    missing_env_vars = tuple(
        sorted(
            {
                str(row["api_key_env_var"])
                for row in rows
                if row.get("api_key_env_var")
                and not _provider_secret_env_var_is_configured(str(row["api_key_env_var"]), settings)
            }
        )
    )
    if missing_env_vars:
        return ProviderSecretReadiness(status="missing", missing_env_vars=missing_env_vars)
    return ProviderSecretReadiness(status="ok")


def _provider_secret_env_var_is_configured(env_var: str, settings: Settings | None) -> bool:
    if os.getenv(env_var):
        return True
    settings_value = getattr(settings, env_var, None) if settings is not None else None
    return isinstance(settings_value, str) and bool(settings_value.strip())
