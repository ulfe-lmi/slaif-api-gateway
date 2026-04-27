"""Provider adapter domain errors with safe metadata only."""

from __future__ import annotations

from slaif_gateway.schemas.providers import ProviderErrorDiagnostic


class ProviderError(Exception):
    """Base provider adapter error.

    Provider errors must not carry provider API keys, gateway keys, client
    Authorization headers, or full raw upstream error bodies.
    """

    status_code: int = 502
    error_type: str = "server_error"
    error_code: str = "provider_error"
    message: str = "Provider request failed"

    def __init__(
        self,
        safe_message: str | None = None,
        *,
        provider: str | None = None,
        upstream_status_code: int | None = None,
        status_code: int | None = None,
        error_type: str | None = None,
        error_code: str | None = None,
        diagnostic: ProviderErrorDiagnostic | None = None,
    ) -> None:
        self.safe_message = safe_message or self.message
        self.provider = provider
        self.upstream_status_code = upstream_status_code
        self.diagnostic = diagnostic
        self.status_code = status_code if status_code is not None else self.__class__.status_code
        self.error_type = error_type or self.__class__.error_type
        self.error_code = error_code or self.__class__.error_code
        super().__init__(self.safe_message)


class ProviderConfigurationError(ProviderError):
    status_code = 500
    error_code = "provider_configuration_error"
    message = "Provider is not configured correctly"


class MissingProviderApiKeyError(ProviderConfigurationError):
    error_code = "missing_provider_api_key"
    message = "Provider API key is not configured"


class ProviderRequestError(ProviderError):
    status_code = 502
    error_code = "provider_request_error"
    message = "Provider request failed"


class ProviderHTTPError(ProviderError):
    status_code = 502
    error_code = "provider_http_error"
    message = "Provider returned an error"


class ProviderTimeoutError(ProviderRequestError):
    status_code = 504
    error_code = "provider_timeout"
    message = "Provider request timed out"


class ProviderResponseParseError(ProviderError):
    status_code = 502
    error_code = "provider_response_parse_error"
    message = "Provider returned an invalid response"


class UnsupportedProviderEndpointError(ProviderConfigurationError):
    error_code = "unsupported_provider_endpoint"
    message = "Provider endpoint is not supported"
