"""ASGI app entrypoint for the SLAIF API Gateway."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from slaif_gateway import metrics as metrics_module
from slaif_gateway.api.admin import router as admin_router
from slaif_gateway.api.admin_provider_route_configuration import (
    router as admin_provider_route_configuration_router,
)
from slaif_gateway.api.admin_key_batch import router as admin_key_batch_router
from slaif_gateway.api.admin_key_clone import router as admin_key_clone_router
from slaif_gateway.api.admin_record_choices import router as admin_record_choices_router
from slaif_gateway.api.admin_operations import router as admin_operations_router
from slaif_gateway.api.branding import router as branding_router
from slaif_gateway.api.errors import (
    OpenAICompatibleError,
    http_exception_handler,
    openai_compatible_error_handler,
    request_validation_exception_handler,
)
from slaif_gateway.api.health import router as health_router
from slaif_gateway.api.metrics import router as metrics_router
from slaif_gateway.api.middleware import MetricsMiddleware, RequestIdMiddleware
from slaif_gateway.api.request_capture import install_request_capture
from slaif_gateway.api.request_diagnostics import install_request_diagnostics
from slaif_gateway.api.openai_compat import router as openai_compat_router
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.lifespan import build_lifespan
from slaif_gateway.logging import configure_logging
from slaif_gateway.modules.clients.codex_0162 import bootstrap_codex_compatibility_profile
from slaif_gateway.modules.servers.upstream_llm.profiles import bootstrap_upstream_llm_profiles
from slaif_gateway.startup_warnings import emit_startup_configuration_warnings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_settings = settings or get_settings()
    configure_logging(app_settings)
    emit_startup_configuration_warnings(app_settings)
    codex_profile = bootstrap_codex_compatibility_profile(
        app_settings.CODEX_COMPATIBILITY_PROFILE_FILE
    )
    upstream_llm_profiles = bootstrap_upstream_llm_profiles(app_settings.UPSTREAM_LLM_PROFILES_FILE)

    @asynccontextmanager
    async def app_lifespan(app: FastAPI):
        try:
            async with build_lifespan(app_settings)(app):
                yield
        finally:
            metrics_module.cleanup_multiproc_metrics()

    app = FastAPI(title="SLAIF API Gateway", lifespan=app_lifespan)
    app.state.settings = app_settings
    app.state.codex_0162_profile = codex_profile
    app.state.upstream_llm_profiles = upstream_llm_profiles
    app.state.db_engine = None
    app.state.db_sessionmaker = None
    app.state.redis_client = None

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/admin/static", StaticFiles(directory=str(static_dir)), name="admin_static")

    app.add_middleware(MetricsMiddleware)
    install_request_diagnostics(app, app_settings)
    app.add_middleware(RequestIdMiddleware, settings=app_settings)
    install_request_capture(app, app_settings)

    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.include_router(health_router)
    app.include_router(metrics_router)
    # Fixed-literal routers (branding, record-choices lookup) register before admin so their literals win over dynamic admin paths.
    app.include_router(branding_router)
    app.include_router(admin_record_choices_router)
    app.include_router(admin_router)
    # 208-a: purpose-bound reviewed key-clone routes (one-way helper reuse;
    # admin.py does not import this router).
    app.include_router(admin_key_clone_router)
    # 209-a: reviewed key-configuration batch routes under the unambiguous
    # /admin/key-batch prefix (one-way helper reuse; no reverse import).
    app.include_router(admin_key_batch_router)
    # Reviewed route configuration + provider preparation (210-a): the
    # focused router reuses admin.py helpers one-way (admin.py does not
    # import this router).
    app.include_router(admin_provider_route_configuration_router)
    # 211-a: operations GUI (content-free request diagnostics + safe
    # process-configuration inspection); one-way helper reuse from admin.py.
    app.include_router(admin_operations_router)
    app.include_router(openai_compat_router)

    return app


app = create_app()
