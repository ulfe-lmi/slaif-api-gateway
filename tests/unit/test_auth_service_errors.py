from __future__ import annotations

import inspect

from slaif_gateway.services.auth_service import (
    GatewayKeyDigestMismatchError,
    GatewayKeyExpiredError,
    GatewayKeyNotFoundError,
    GatewayKeyNotYetValidError,
    GatewayKeyRevokedError,
    GatewayKeySuspendedError,
    InvalidAuthorizationSchemeError,
    MalformedGatewayKeyError,
    MissingAuthorizationError,
    MissingTokenHmacSecretError,
)

_DISALLOWED_IMPORT_TERMS = ("openai", "openrouter", "aiosmtplib", "celery", "fastapi")
_DISALLOWED_DB_TERMS = ("commit(", "sessionmaker", "create_async_engine")


def test_domain_auth_error_metadata_defaults() -> None:
    assert MissingAuthorizationError().status_code == 401
    assert MissingAuthorizationError().error_type == "authentication_error"
    assert InvalidAuthorizationSchemeError().error_code == "invalid_authorization_scheme"
    assert MalformedGatewayKeyError().error_code == "malformed_gateway_key"
    assert GatewayKeyNotFoundError().error_code == "gateway_key_not_found"
    assert GatewayKeyDigestMismatchError().error_code == "gateway_key_invalid_digest"
    assert GatewayKeySuspendedError().status_code == 403
    assert GatewayKeyRevokedError().status_code == 403
    assert GatewayKeyExpiredError().error_code == "gateway_key_expired"
    assert GatewayKeyNotYetValidError().error_code == "gateway_key_not_yet_valid"
    assert MissingTokenHmacSecretError().status_code == 500


def test_auth_service_module_safety_constraints() -> None:
    import slaif_gateway.services.auth_service as auth_service_module

    source = inspect.getsource(auth_service_module)
    import_lines = [
        line.strip().lower()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]

    for line in import_lines:
        for term in _DISALLOWED_IMPORT_TERMS:
            assert term not in line, f"forbidden import term '{term}' in auth_service: {line}"

    lowered_source = source.lower()
    for term in _DISALLOWED_DB_TERMS:
        assert term not in lowered_source

    assert "last_used_at" not in lowered_source
    assert "plaintext_key" not in lowered_source
