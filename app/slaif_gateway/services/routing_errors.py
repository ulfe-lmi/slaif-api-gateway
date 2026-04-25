"""Domain errors for model route resolution."""

from __future__ import annotations


class RouteResolutionError(Exception):
    """Base domain error for safe route resolution failures."""

    status_code = 400
    error_type = "invalid_request_error"
    error_code = "route_resolution_error"
    message = "Unable to resolve model route"

    def __init__(self, message: str | None = None) -> None:
        self.safe_message = message or self.message
        super().__init__(self.safe_message)


class ModelNotFoundError(RouteResolutionError):
    status_code = 404
    error_code = "model_not_found"
    message = "The requested model is not supported"


class ModelRouteDisabledError(RouteResolutionError):
    status_code = 403
    error_type = "permission_error"
    error_code = "model_route_disabled"
    message = "The requested model route is disabled"


class ProviderDisabledError(RouteResolutionError):
    status_code = 403
    error_type = "permission_error"
    error_code = "provider_disabled"
    message = "Provider is disabled for the requested model"


class ModelNotAllowedForKeyError(RouteResolutionError):
    status_code = 403
    error_type = "permission_error"
    error_code = "model_not_allowed_for_key"
    message = "The requested model is not allowed for this key"


class ProviderNotAllowedForKeyError(RouteResolutionError):
    status_code = 403
    error_type = "permission_error"
    error_code = "provider_not_allowed_for_key"
    message = "The resolved provider is not allowed for this key"


class AmbiguousRouteError(RouteResolutionError):
    status_code = 500
    error_type = "server_error"
    error_code = "ambiguous_route"
    message = "Multiple routes matched with identical precedence"


class UnsupportedRouteMatchTypeError(RouteResolutionError):
    status_code = 500
    error_type = "server_error"
    error_code = "unsupported_route_match_type"
    message = "Route has an unsupported match_type"
