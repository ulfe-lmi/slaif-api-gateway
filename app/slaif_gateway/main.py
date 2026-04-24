"""ASGI app entrypoint for the SLAIF API Gateway."""

from fastapi import FastAPI

app = FastAPI(title="SLAIF API Gateway")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {
        "status": "ok",
        "database": "not_configured",
        "redis": "not_configured",
    }


@app.get("/v1/models")
def list_models() -> dict[str, object]:
    return {"object": "list", "data": []}
