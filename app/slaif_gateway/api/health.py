"""Health and readiness API routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from slaif_gateway.db.schema_status import check_schema_current

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.DATABASE_URL:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "not_configured",
                "redis": "not_required",
            },
        )

    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "not_initialized",
                "redis": "not_required",
            },
        )

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            schema_status = await check_schema_current(connection)
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "error",
                "redis": "not_required",
            },
        )

    if not schema_status.is_current:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "ok",
                "schema": schema_status.status,
                "alembic_current": schema_status.current_revision,
                "alembic_head": schema_status.head_revision,
                "redis": "not_required",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "database": "ok",
            "schema": "ok",
            "alembic_current": schema_status.current_revision,
            "alembic_head": schema_status.head_revision,
            "redis": "not_required",
        },
    )
