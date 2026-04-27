from __future__ import annotations

import inspect

from slaif_gateway.cli import quota as quota_cli
from slaif_gateway.services import reservation_reconciliation


def test_reconciliation_service_does_not_import_network_or_background_modules() -> None:
    source = inspect.getsource(reservation_reconciliation)

    forbidden = (
        "providers.",
        "OpenAI",
        "OpenRouter",
        "httpx",
        "SMTP",
        "aiosmtplib",
        "celery",
        "redis",
        "dashboard",
        "fastapi",
    )
    for term in forbidden:
        assert term not in source


def test_quota_cli_does_not_call_providers_or_expose_secret_fields() -> None:
    source = inspect.getsource(quota_cli)

    forbidden = (
        "providers.",
        "OpenAI",
        "OpenRouter",
        "httpx",
        "token_hash",
        "plaintext_key",
        "provider_api_key",
        "encrypted_payload",
        "nonce",
    )
    for term in forbidden:
        assert term not in source
