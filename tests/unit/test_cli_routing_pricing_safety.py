from __future__ import annotations

import inspect

import slaif_gateway.cli.fx as fx_cli
import slaif_gateway.cli.pricing as pricing_cli
import slaif_gateway.cli.providers as providers_cli
import slaif_gateway.cli.routes as routes_cli
import slaif_gateway.services.fx_rate_service as fx_service
import slaif_gateway.services.model_route_service as route_service
import slaif_gateway.services.pricing_rule_service as pricing_service
import slaif_gateway.services.provider_config_service as provider_service


MODULES = (
    providers_cli,
    routes_cli,
    pricing_cli,
    fx_cli,
    provider_service,
    route_service,
    pricing_service,
    fx_service,
)


def test_cli_config_modules_do_not_import_provider_clients_or_adapters() -> None:
    forbidden = (
        "from openai",
        "import openai",
        "openrouter",
        "slaif_gateway.providers",
        "ProviderAdapter",
        "get_provider_adapter",
    )

    for module in MODULES:
        source = inspect.getsource(module)
        for marker in forbidden:
            if marker == "openrouter" and module is provider_service:
                continue
            assert marker not in source


def test_cli_config_modules_do_not_call_internet_or_external_pricing_fx() -> None:
    forbidden = (
        "httpx",
        "requests",
        "aiohttp",
        "urllib.request",
        "fetch",
        "live pricing",
        "external FX",
    )

    for module in MODULES:
        source = inspect.getsource(module)
        for marker in forbidden:
            assert marker not in source


def test_cli_config_modules_do_not_import_dashboard_smtp_celery_or_fastapi_routes() -> None:
    forbidden = (
        "celery",
        "aiosmtplib",
        "SMTP",
        "FastAPI",
        "APIRouter",
        "slaif_gateway.api",
        "slaif_gateway.admin",
    )

    for module in MODULES:
        source = inspect.getsource(module)
        for marker in forbidden:
            assert marker not in source


def test_cli_config_modules_do_not_log_or_print_secret_fields() -> None:
    forbidden = (
        "token_hash",
        "password_hash",
        "encrypted_payload",
        "nonce",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY=",
        "SLAIF_API_KEY",
        "SLAIF_BASE_URL",
    )

    for module in MODULES:
        source = inspect.getsource(module)
        for marker in forbidden:
            assert marker not in source
