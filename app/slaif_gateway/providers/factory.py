"""Provider adapter factory."""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from slaif_gateway.config import CLIENT_GATEWAY_KEY_ENV_VAR, Settings
from slaif_gateway.modules.contracts import DEFAULT_CLIENT_MODULE_ID
from slaif_gateway.modules.servers.registry import (
    build_server_adapter,
    ensure_client_server_pair,
    resolve_server_module,
)
from slaif_gateway.providers.base import ProviderAdapter
from slaif_gateway.providers.errors import MissingProviderApiKeyError, ProviderConfigurationError

_DEFAULT_OPENAI_API_KEY_ENV_VAR = "OPENAI_UPSTREAM_API_KEY"
_DEFAULT_OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"


def get_provider_adapter(provider: object, settings: Settings) -> ProviderAdapter:
    """Return an adapter for a configured provider or resolved route."""
    normalized = _provider_name(provider)
    provider_kind = _provider_kind(provider)
    route_capabilities = _first_attr(provider, "capabilities", "route_capabilities")
    descriptor = resolve_server_module(normalized, provider_kind, route_capabilities)
    ensure_client_server_pair(DEFAULT_CLIENT_MODULE_ID, descriptor.module_id)

    base_url = _provider_base_url(provider)
    api_key_env_var = _provider_api_key_env_var(provider) or _default_api_key_env_var(normalized)
    if descriptor.module_id == "facial_scoring" and api_key_env_var != "FACIAL_SCORING_API_KEY":
        raise ProviderConfigurationError(
            "Facial scoring requires the FACIAL_SCORING_API_KEY environment variable",
            provider=normalized,
            error_code="invalid_provider_configuration",
        )
    api_key = _provider_api_key(api_key_env_var, settings=settings, provider=normalized)
    timeout_seconds = _provider_timeout_seconds(provider)
    max_retries = _provider_max_retries(provider)

    if descriptor.module_id == "facial_scoring":
        if not base_url:
            raise ProviderConfigurationError(
                "Native module provider requires a base URL",
            provider=normalized,
            error_code="invalid_provider_configuration",
        )
        _validate_module_base_url(base_url)
    elif descriptor.module_id in {"openai-compatible", "local-coding-v1"}:
        if not base_url:
            raise ProviderConfigurationError(
                "OpenAI-compatible server module requires a base URL",
                provider=normalized,
                error_code="invalid_provider_configuration",
            )
        _validate_generic_base_url(base_url)
    elif base_url:
        # The built-in provider descriptors accept an operator-selected base
        # URL; their adapters retain the existing URL validation/behavior.
        pass

    return build_server_adapter(
        descriptor,
        settings,
        provider_name=normalized,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries or 0,
        route_capabilities=(
            route_capabilities if isinstance(route_capabilities, dict) else None
        ),
    )


def _provider_name(provider: object) -> str:
    raw_provider = provider if isinstance(provider, str) else getattr(provider, "provider", None)
    if not isinstance(raw_provider, str):
        raise ProviderConfigurationError(
            "Unsupported provider configured for route",
            error_code="unsupported_provider",
        )
    return raw_provider.strip().lower()


def _provider_base_url(provider: object) -> str | None:
    base_url = _first_attr(provider, "provider_base_url", "base_url")
    return base_url.strip() if isinstance(base_url, str) and base_url.strip() else None


def _provider_kind(provider: object) -> str | None:
    value = _first_attr(provider, "provider_kind", "kind")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _provider_api_key_env_var(provider: object) -> str | None:
    env_var = _first_attr(provider, "provider_api_key_env_var", "api_key_env_var")
    return env_var.strip() if isinstance(env_var, str) and env_var.strip() else None


def _provider_timeout_seconds(provider: object) -> int | None:
    timeout_seconds = _first_attr(provider, "provider_timeout_seconds", "timeout_seconds")
    return timeout_seconds if isinstance(timeout_seconds, int) and timeout_seconds > 0 else None


def _provider_max_retries(provider: object) -> int | None:
    max_retries = _first_attr(provider, "provider_max_retries", "max_retries")
    return max_retries if isinstance(max_retries, int) and max_retries >= 0 else None


def _first_attr(provider: object, *names: str) -> object:
    if isinstance(provider, str):
        return None
    for name in names:
        value = getattr(provider, name, None)
        if value is not None:
            return value
    return None


def _default_api_key_env_var(provider: str) -> str | None:
    if provider == "openai":
        return _DEFAULT_OPENAI_API_KEY_ENV_VAR
    if provider == "openrouter":
        return _DEFAULT_OPENROUTER_API_KEY_ENV_VAR
    if provider == "facial_scoring":
        return "FACIAL_SCORING_API_KEY"
    return None


def _provider_api_key(api_key_env_var: str | None, *, settings: Settings, provider: str) -> str:
    if not api_key_env_var:
        raise MissingProviderApiKeyError(provider=provider)

    if api_key_env_var == CLIENT_GATEWAY_KEY_ENV_VAR or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", api_key_env_var
    ):
        raise ProviderConfigurationError(
            "Provider API key environment variable name is invalid",
            provider=provider,
            error_code="invalid_provider_configuration",
        )

    value = os.getenv(api_key_env_var)
    if value:
        return value

    settings_value = getattr(settings, api_key_env_var, None)
    if isinstance(settings_value, str) and settings_value:
        return settings_value

    raise MissingProviderApiKeyError(
        f"Provider API key is not configured for environment variable {api_key_env_var}",
        provider=provider,
    )


def _validate_generic_base_url(value: str) -> None:
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as exc:
        raise ProviderConfigurationError(
            "Generic OpenAI-compatible base URL is invalid",
            error_code="invalid_provider_configuration",
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise ProviderConfigurationError(
            "Generic OpenAI-compatible base URL is invalid",
            error_code="invalid_provider_configuration",
        )


def _validate_module_base_url(value: str) -> None:
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as exc:
        raise ProviderConfigurationError(
            "Native module base URL is invalid",
            error_code="invalid_provider_configuration",
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise ProviderConfigurationError(
            "Native module base URL is invalid",
            error_code="invalid_provider_configuration",
        )
