from __future__ import annotations

import inspect

import slaif_gateway.cli.usage as usage_cli
import slaif_gateway.services.usage_report_service as usage_service


MODULES = (usage_cli, usage_service)


def test_usage_modules_do_not_import_provider_clients_or_adapters() -> None:
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
            assert marker not in source


def test_usage_modules_do_not_import_dashboard_smtp_celery_or_fastapi_routes() -> None:
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


def test_usage_service_is_read_only_and_does_not_call_external_services() -> None:
    source = inspect.getsource(usage_service)
    forbidden = (
        ".commit(",
        ".add(",
        "create_async_engine",
        "get_sessionmaker",
        "httpx",
        "requests",
        "aiohttp",
        "urllib.request",
    )

    for marker in forbidden:
        assert marker not in source


def test_usage_cli_output_fields_do_not_include_secret_or_content_fields() -> None:
    forbidden = (
        "prompt_content",
        "completion_content",
        "request_body",
        "response_body",
        "token_hash",
        "provider_api_key",
        "plaintext_key",
        "encrypted_payload",
        "nonce",
        "password_hash",
        "SLAIF_API_KEY",
        "SLAIF_BASE_URL",
    )

    for module in MODULES:
        source = inspect.getsource(module)
        for marker in forbidden:
            assert marker not in source
