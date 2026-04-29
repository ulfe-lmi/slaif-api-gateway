"""Startup-time operator warnings for risky production settings."""

from __future__ import annotations

import os

import structlog

from slaif_gateway.config import Settings, looks_like_real_upstream_openai_key

logger = structlog.get_logger(__name__)


def emit_startup_configuration_warnings(settings: Settings) -> None:
    """Log actionable warnings for intentionally risky production exposure settings."""
    if settings.APP_ENV.lower() != "production":
        return

    if settings.ENABLE_METRICS:
        _warn_for_metrics_exposure(settings)

    _warn_for_openai_api_key_boundary(settings)

    if settings.readyz_include_details():
        logger.warning(
            "Production readiness details are enabled; /readyz may expose schema/runtime "
            "status and should be internal or allowlisted.",
            setting="READYZ_INCLUDE_DETAILS",
            mitigation="Restrict /readyz with an internal network or reverse proxy allowlist.",
        )


def _warn_for_openai_api_key_boundary(settings: Settings) -> None:
    client_key = os.getenv("OPENAI_API_KEY")
    if not client_key:
        return
    if looks_like_real_upstream_openai_key(
        client_key,
        gateway_prefixes=settings.get_gateway_key_accepted_prefixes(),
    ):
        return
    logger.warning(
        "OPENAI_API_KEY is reserved for OpenAI-compatible clients, not the gateway "
        "upstream OpenAI provider secret.",
        setting="OPENAI_API_KEY",
        mitigation="Use OPENAI_UPSTREAM_API_KEY for the server-side upstream OpenAI key.",
    )


def _warn_for_metrics_exposure(settings: Settings) -> None:
    if settings.METRICS_PUBLIC_IN_PRODUCTION:
        logger.warning(
            "Production metrics are explicitly configured as public; restrict /metrics with "
            "an internal network, reverse proxy allowlist, or admin authentication.",
            setting="METRICS_PUBLIC_IN_PRODUCTION",
            mitigation="Set METRICS_PUBLIC_IN_PRODUCTION=false and protect /metrics.",
        )
        return

    if settings.METRICS_REQUIRE_AUTH is False:
        logger.warning(
            "Production metrics authentication is explicitly disabled; /metrics may be "
            "publicly reachable.",
            setting="METRICS_REQUIRE_AUTH",
            mitigation="Set METRICS_REQUIRE_AUTH=true or use METRICS_ALLOWED_IPS.",
        )
