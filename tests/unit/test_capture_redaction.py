"""Focused regressions for the pure request-capture masker (objective 191, R5).

These pin the two short-auth-source cases called out in review (explicit
credential fields must mask their source value regardless of length) plus the
identifier-preservation invariant. The broader corpus is exercised by the
independent strategic probe; full unit coverage is added with the rest of the
facility.
"""

from __future__ import annotations

from urllib.parse import unquote_to_bytes

from slaif_gateway.utils.capture_redaction import redact_capture_request

_PREFIXES = ("sk-slaif-",)


def _key(public_id: str = "pubid12345678901", secret: str = "s" * 43) -> str:
    return f"sk-slaif-{public_id}.{secret}"


def test_short_query_credential_field_is_masked() -> None:
    result = redact_capture_request(
        path=b"/v1/responses",
        query=b"api_key=abc",
        headers=[],
        body=b"{}",
        accepted_prefixes=_PREFIXES,
    )
    assert b"abc" not in result.query
    assert b"[REDACTED]" in unquote_to_bytes(result.query.decode("latin-1"))
    assert result.secrets_masked >= 1


def test_short_json_credential_field_is_masked_with_copies() -> None:
    result = redact_capture_request(
        path=b"/v1/responses",
        query=b"",
        headers=[],
        body=b'{"password":"xyz","input":"value xyz repeated"}',
        accepted_prefixes=_PREFIXES,
    )
    assert b'"password":"xyz"' not in result.body
    assert b"[REDACTED]" in result.body
    # Known copies of the explicit credential value are masked too.
    assert b"xyz" not in result.body


def test_identifier_fields_are_preserved() -> None:
    result = redact_capture_request(
        path=b"/v1/responses",
        query=b"session=abc",
        headers=[],
        body=b'{"session_id":"abc","nonce":"xyz","signature":"sig"}',
        accepted_prefixes=_PREFIXES,
    )
    assert b"session=abc" in result.query
    assert b'"session_id":"abc"' in result.body
    assert b'"nonce":"xyz"' in result.body
    assert b'"signature":"sig"' in result.body
    assert result.secrets_masked == 0


def test_recognized_gateway_bearer_yields_hint_not_secret() -> None:
    key = _key()
    body = ('{"input":"see ' + key + '"}').encode()
    result = redact_capture_request(
        path=b"/v1/responses",
        query=b"",
        headers=[("authorization", f"Bearer {key}".encode())],
        body=body,
        accepted_prefixes=_PREFIXES,
    )
    assert result.recognized_hint == "sk-slaif-pubid123\u2026***"
    assert key.encode() not in result.body
    assert result.recognized_hint.encode() in result.body
    assert result.recognized_hint.encode() in result.headers[0][1]


def test_non_secret_body_is_byte_identical() -> None:
    body = b'{"input":"The password manager is great but I forgot my password once"}'
    result = redact_capture_request(
        path=b"/v1/responses",
        query=b"",
        headers=[],
        body=body,
        accepted_prefixes=_PREFIXES,
    )
    assert result.body == body
    assert result.secrets_masked == 0
