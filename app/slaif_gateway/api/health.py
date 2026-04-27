"""Health and readiness API routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    return {
        "status": "ok",
        "database": "not_configured",
        "redis": "not_configured",
    }
