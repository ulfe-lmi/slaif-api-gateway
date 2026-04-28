from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from slaif_gateway.services.email_templates import GatewayKeyEmailContext, render_gateway_key_email


def test_gateway_key_email_rendering_includes_openai_compatible_instructions() -> None:
    body = render_gateway_key_email(
        GatewayKeyEmailContext(
            owner_name="Ada",
            owner_surname="Lovelace",
            owner_email="ada@example.org",
            plaintext_gateway_key="sk-slaif-public.once-only-secret",
            api_base_url="https://api.ulfe.slaif.si",
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=datetime(2026, 2, 1, tzinfo=UTC),
            institution_name="SLAIF",
            cohort_name="Workshop",
            cost_limit_eur=Decimal("10.00"),
            token_limit_total=1000,
            request_limit_total=20,
        )
    )

    assert 'export OPENAI_API_KEY="sk-slaif-public.once-only-secret"' in body
    assert 'export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"' in body
    assert "from openai import OpenAI" in body
    assert "client = OpenAI()" in body
    assert "Valid from: 2026-01-01T00:00:00+00:00" in body
    assert "Valid until: 2026-02-01T00:00:00+00:00" in body
    assert "Cost limit EUR: 10.00" in body
    assert "Token limit: 1000" in body
    assert "Request limit: 20" in body


def test_gateway_key_email_rendering_excludes_storage_and_provider_material() -> None:
    body = render_gateway_key_email(
        GatewayKeyEmailContext(
            owner_name="Ada",
            owner_surname="Lovelace",
            owner_email="ada@example.org",
            plaintext_gateway_key="sk-slaif-public.once-only-secret",
            api_base_url="https://api.ulfe.slaif.si/v1",
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )

    assert "OPENAI_UPSTREAM_API_KEY" not in body
    assert "OPENROUTER_API_KEY" not in body
    assert "token_hash" not in body
    assert "encrypted_payload" not in body
    assert "nonce" not in body
