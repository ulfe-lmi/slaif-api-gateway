from slaif_gateway.api.routing_errors import openai_error_from_route_resolution_error
from slaif_gateway.services.routing_errors import (
    ModelNotAllowedForKeyError,
    ModelNotFoundError,
    ProviderDisabledError,
    ProviderNotAllowedForKeyError,
    UnsupportedRouteMatchTypeError,
)


def test_route_resolution_errors_have_safe_metadata() -> None:
    errors = [
        ModelNotFoundError(),
        ProviderDisabledError(),
        ModelNotAllowedForKeyError(),
        ProviderNotAllowedForKeyError(),
        UnsupportedRouteMatchTypeError(),
    ]

    for error in errors:
        assert isinstance(error.status_code, int)
        assert isinstance(error.error_type, str)
        assert isinstance(error.error_code, str)
        assert isinstance(error.safe_message, str)


def test_openai_mapping_preserves_safe_metadata() -> None:
    error = ProviderDisabledError()

    mapped = openai_error_from_route_resolution_error(error)

    assert mapped.status_code == 403
    assert mapped.error_type == "permission_error"
    assert mapped.code == "provider_disabled"
    assert mapped.message == error.safe_message
