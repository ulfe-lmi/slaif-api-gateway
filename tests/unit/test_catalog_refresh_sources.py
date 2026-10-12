"""Unit tests for the 181 bounded official-source fetch layer (sources.py).

All traffic is served by ``httpx.MockTransport`` and every DNS lookup is an
injected resolver: no test performs a real network request. The tests pin
the security-relevant behavior: HTTPS-only approved-host allowlist, exact
path-family pinning (181-f F2: no query/fragment/path expansion),
credential/port rejection, public-destination guard INCLUDING mixed
answer sets, the vetted-connection binding (AP-F2: the ACTUAL connection
primitive is intercepted - numeric vetted destinations, original hostname
SNI, verified certificate policy, proxy/redirect/reuse/spec-cache bypass
fail-closed), redirect re-validation, bounded 429/5xx retries, mid-stream
body byte caps, identity-only transfer encoding with no pre-refusal
expansion (AP-F3), and the ONE whole-invocation attempt/byte/deadline
budget with the cross-phase outcome cache (AP-F1) - all with safe
code-only failure outcomes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import gzip
import socket
import ssl
import time

import httpx
from httpx._content import IteratorByteStream

import pytest

from slaif_gateway.services.catalog_refresh import source_transport as st
from slaif_gateway.services.catalog_refresh import sources as src
from slaif_gateway.services.catalog_refresh.sources import (
    SourceFetchError,
    SourceSpec,
    ecb_spec,
    fetch_source,
    fetch_sources,
    model_page_spec,
    new_client,
    new_acquisition_context,
    plan_catalog_specs,
    validate_source_url,
)
from httpcore._backends.sync import SyncStream

from slaif_gateway.services.catalog_refresh.source_transport import (
    VettedNetworkBackend,
)

OR_URL = "https://openrouter.ai/api/v1/models"
PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
MODELS_MD_URL = "https://developers.openai.com/api/docs/models.md"
PAGE_URL = "https://developers.openai.com/api/docs/models/gpt-5.2.md"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

PUBLIC = "93.184.216.34"
PRIVATE = "192.168.1.10"
LOOPBACK = "127.0.0.1"


def _ctx(**kw):
    return new_acquisition_context(**kw)


def _ainfo(ip: str):
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


def _resolve(*ips: str):
    def resolve(host, port, proto=None):
        if not ips:
            raise OSError("nxdomain")
        return [_ainfo(ip) for ip in ips]

    return resolve


def _ok(resolve=PUBLIC):
    return _resolve(resolve)


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        headers={"User-Agent": src.USER_AGENT, "Accept": "*/*"},
    )


def _spec(url: str = OR_URL, max_bytes: int = 64 * 1024) -> SourceSpec:
    return SourceSpec(
        provider="openrouter",
        source_kind="openrouter_models_api",
        model="catalog",
        url=url,
        max_bytes=max_bytes,
    )


def _page_spec(slug: str) -> SourceSpec:
    return model_page_spec("openai", slug)


def _refusing_create_connection(calls: list):
    def fake(address, timeout=None, source_address=None, **kwargs):
        calls.append(address)
        raise ConnectionRefusedError("test boundary: no real connection")

    return fake


# --- URL validation (allowlist, scheme, credentials, port, path families) ---


def test_validate_source_url_approval_and_rejections() -> None:
    validate_source_url(OR_URL, provider="openrouter")
    validate_source_url("https://openrouter.ai:443/api/v1/models", provider="openrouter")
    validate_source_url(PRICING_URL, provider="openai")
    validate_source_url(MODELS_MD_URL, provider="openai")
    validate_source_url(PAGE_URL, provider="openai")
    validate_source_url(ECB_URL, provider="ecb")
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url("http://openrouter.ai/api/v1/models", provider="openrouter")
    assert exc.value.code == "url_not_https"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url(
            "https://user:pass@openrouter.ai/api/v1/models", provider="openrouter"
        )
    assert exc.value.code == "url_credentials"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url("https://evil.example.com/models", provider="openrouter")
    assert exc.value.code == "url_host_not_approved"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url(OR_URL, provider="openai")
    assert exc.value.code == "url_host_not_approved"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url("https://openrouter.ai:8443/api/v1/models", provider="openrouter")
    assert exc.value.code == "url_nondefault_port"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url("https://openrouter.ai", provider="openrouter")
    assert exc.value.code == "url_missing_path"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url(OR_URL, provider="ecb")
    assert exc.value.code == "url_host_not_approved"


def test_validate_source_url_exact_path_families_only() -> None:
    # 181-f (F2): no arbitrary same-host path/query/fragment expansion.
    cases = [
        (OR_URL + "?mirror=1", "openrouter", "openrouter_models_api", "url_query_forbidden"),
        (OR_URL + "/new", "openrouter", "openrouter_models_api", "url_path_not_approved"),
        ("https://openrouter.ai/steal", "openrouter", None, "url_path_not_approved"),
        ("https://openai.com/api/pricing.md", "openai", None, "url_path_not_approved"),
        (PRICING_URL + "#section", "openai", "openai_pricing_docs", "url_fragment_forbidden"),
        (
            "https://developers.openai.com/api/docs/models/a/b.md",
            "openai",
            "docs_page",
            "url_path_not_approved",
        ),
        (
            "https://developers.openai.com/api/docs/models/../../etc.md",
            "openai",
            "docs_page",
            "url_path_not_approved",
        ),
        (
            "https://developers.openai.com/api/docs/models/%252Fetc.md",
            "openai",
            "docs_page",
            "model_page_slug_invalid",
        ),
        (
            "https://developers.openai.com/api/docs/models/%2F.md",
            "openai",
            "docs_page",
            "model_page_slug_invalid",
        ),
        # kind mismatch: a registered path of a DIFFERENT kind is drift
        (MODELS_MD_URL, "openai", "openai_pricing_docs", "url_path_kind_mismatch"),
        (
            "https://www.ecb.europa.eu/stats/eurofxref/other.xml",
            "ecb",
            "ecb_reference_xml",
            "url_path_not_approved",
        ),
    ]
    for url, provider, kind, want in cases:
        with pytest.raises(SourceFetchError) as exc:
            validate_source_url(url, provider=provider, source_kind=kind)
        assert exc.value.code == want, url
    # legitimate registry URLs still validate, including quoted slugs
    validate_source_url(
        "https://developers.openai.com/api/docs/models/meta%2Fllama-3.1%3Afree.md",
        provider="openai",
        source_kind="docs_page",
    )


# --- DNS public-destination guard (incl. mixed answer sets) -----------------


def test_private_or_failed_dns_is_a_safe_failure() -> None:
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        context=_ctx(),
        resolve=_resolve(PRIVATE),
    )
    assert result.ok is False and result.failure_code == "destination_not_public"
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        context=_ctx(),
        resolve=_resolve(),  # nxdomain
    )
    assert result.ok is False and result.failure_code == "dns_resolution_failed"
    # A resolver that returns an empty list is also a failure, never a pass.
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        context=_ctx(),
        resolve=lambda host, port, proto=None: [],
    )
    assert result.ok is False and result.failure_code == "dns_resolution_failed"


def test_mixed_public_and_loopback_answer_set_is_refused() -> None:
    def mixed(host, port, proto=None):
        return [_ainfo(PUBLIC), _ainfo(LOOPBACK)]

    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        context=_ctx(),
        resolve=mixed,
    )
    assert result.ok is False
    assert result.failure_code == "destination_mixed_or_not_public"
    # an all-public multi-address answer set is fine
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        context=_ctx(),
        resolve=_resolve(PUBLIC, "93.184.216.35"),
    )
    assert result.ok is True


# --- Successful retrieval records the measured outcome ---------------------


def test_ok_retrieval_records_outcome_status_bytes_and_digest() -> None:
    body = b'{"data": []}\n'
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is True
    assert result.status == 200
    assert result.content == body
    assert len(result.content) == len(body)
    assert result.content_sha256() == hashlib.sha256(body).hexdigest()
    assert result.final_url is None
    assert result.attempts == 1 and result.redirects == 0
    assert result.failure_code is None
    assert seen[0].headers["user-agent"] == src.USER_AGENT
    # A 204 is a successful transport retrieval of an (empty) body: the
    # emptiness is caught by the deterministic parser downstream, not here.
    result = fetch_source(
        _client(lambda request: httpx.Response(204)), _spec(),
        context=_ctx(), resolve=_ok(),
    )
    assert result.ok is True and result.status == 204 and result.content == b""


# --- Redirects: bounded, re-validated, drift fails closed -------------------


def test_redirect_to_unapproved_host_is_refused_not_followed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == OR_URL:
            return httpx.Response(
                302, headers={"location": "https://evil.example.com/steal"}
            )
        return httpx.Response(200, content=b'{"data": []}')

    client = _client(handler)
    result = fetch_source(client, _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "url_host_not_approved"
    assert len(calls) == 1, "the unapproved target must never be requested"


def test_redirect_query_drift_is_refused_not_followed() -> None:
    # 181-f (F2): the family has no query members - a 3xx adding one is
    # unsupported drift, refused before any second request.
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == OR_URL:
            return httpx.Response(301, headers={"location": "/api/v1/models?mirror=1"})
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "url_query_forbidden"
    assert len(calls) == 1, "the drifted target must never be requested"


def test_redirect_path_drift_is_refused_not_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OR_URL:
            return httpx.Response(
                301, headers={"location": "https://openrouter.ai/api/v1/models/new"}
            )
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "url_path_not_approved"


def test_redirect_kind_drift_is_refused() -> None:
    # pricing.md -> models.md is a cross-kind substitution: refused.
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == PRICING_URL:
            return httpx.Response(301, headers={"location": MODELS_MD_URL})
        return httpx.Response(200, content=b"# Pricing")

    spec = SourceSpec(
        provider="openai",
        source_kind="openai_pricing_docs",
        model="catalog",
        url=PRICING_URL,
        max_bytes=512 * 1024,
    )
    result = fetch_source(
        _client(handler), spec, context=_ctx(), resolve=_ok()
    )
    assert result.ok is False
    assert result.failure_code == "url_path_kind_mismatch"


def test_redirect_loop_is_bounded_and_missing_location_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            301, headers={"location": "https://openrouter.ai/api/v1/models"}
        )

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "redirect_unbounded"
    assert result.redirects == src.MAX_REDIRECTS

    def no_location(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301)

    result = fetch_source(_client(no_location), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False and result.failure_code == "redirect_missing_location"


# --- 429 and 5xx: bounded retries with safe terminal codes ------------------


def test_429_with_finite_retry_after_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is True and result.attempts == 2


def test_429_beyond_retry_bound_fails_safe(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "300"})

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False and result.failure_code == "rate_limited"
    assert result.attempts == 1  # an oversized retry-after is never waited on


def test_429_without_finite_retry_after_fails_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "soon"})

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False and result.failure_code == "rate_limited"


def test_5xx_retries_bounded_times_then_fails_safe() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(503)

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False and result.failure_code == "http_5xx"
    assert result.attempts == src.MAX_ATTEMPTS == hits["n"]


def test_5xx_then_success_records_attempts() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(502)
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is True and result.attempts == 2


def test_transport_error_retries_then_fails_safe() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] <= src.MAX_ATTEMPTS - 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is True and result.attempts == src.MAX_ATTEMPTS

    def always_down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = fetch_source(_client(always_down), _spec(), context=_ctx(), resolve=_ok())
    assert result.ok is False and result.failure_code == "transport_error"
    assert result.attempts == src.MAX_ATTEMPTS


# --- Body byte cap (mid-stream) and identity-only encoding ------------------


def test_body_byte_cap_fails_mid_stream() -> None:
    big = b"x" * (64 * 1024 * 2)

    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=big)),
        _spec(max_bytes=64 * 1024),
        context=_ctx(),
        resolve=_ok(),
    )
    assert result.ok is False and result.failure_code == "body_too_large"
    assert result.content is None

    exact = b"y" * 64 * 1024
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=exact)),
        _spec(max_bytes=64 * 1024),
        context=_ctx(),
        resolve=_ok(),
    )
    assert result.ok is True and result.content == exact


def test_content_length_header_is_never_trusted_for_the_cap() -> None:
    # Header claims 10 bytes; the stream actually delivers 200. The cap
    # (100) is enforced on the ACTUAL stream, not the header.
    result = fetch_source(
        _client(
            lambda request: httpx.Response(
                200, content=b"x" * 200, headers={"content-length": "10"}
            )
        ),
        _spec(max_bytes=100),
        context=_ctx(),
        resolve=_ok(),
    )
    assert result.ok is False and result.failure_code == "body_too_large"


def test_unexpected_encoding_fails_safe_before_any_read() -> None:
    touched = {"read": False}

    def body():
        touched["read"] = True
        yield b"{}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=IteratorByteStream(body()),
            headers={"content-encoding": "br"},
        )

    context = _ctx()
    result = fetch_source(_client(handler), _spec(), context=context, resolve=_ok())
    assert result.ok is False and result.failure_code == "unexpected_encoding"
    assert touched["read"] is False, "the stream must never be read on refusal"
    assert context.bytes_remaining == src.MAX_COLLECTION_BYTES


def test_gzip_is_refused_before_any_expansion() -> None:
    # AP-F3 reproducer of the 181-c probe: a real streaming gzip body that
    # would expand to 8 MiB. The production code must refuse BEFORE any
    # decoding/expansion: the stream is never touched, nothing is charged.
    wire = gzip.compress(b"\x00" * (8 * 1024 * 1024))
    assert len(wire) < 64 * 1024  # small on the wire, 8 MiB expanded
    touched = {"read": False}

    def body():
        touched["read"] = True
        yield wire

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=IteratorByteStream(body()),
            headers={
                "content-encoding": "gzip",
                "content-length": str(len(wire)),
            },
        )

    context = _ctx()
    result = fetch_source(
        _client(handler), _spec(max_bytes=256), context=context, resolve=_ok()
    )
    assert result.ok is False and result.failure_code == "unexpected_encoding"
    assert touched["read"] is False, "no expansion before refusal"
    assert context.bytes_remaining == src.MAX_COLLECTION_BYTES
    assert result.content is None


def test_partial_stream_failure_consumes_bytes_and_fails_safe() -> None:
    def gen():
        yield b"y" * src._CHUNK_SIZE
        raise httpx.ReadError("stream cut")

    context = _ctx()
    result = fetch_source(
        _client(
            lambda request: httpx.Response(200, stream=IteratorByteStream(gen()))
        ),
        _spec(max_bytes=1024 * 1024),
        context=context,
        resolve=_ok(),
    )
    assert result.ok is False and result.failure_code == "transport_error"
    # each of the 3 retried attempts consumed (and was charged for) its
    # interrupted chunk - failures never refund
    assert result.attempts == src.MAX_ATTEMPTS
    assert context.bytes_remaining == (
        src.MAX_COLLECTION_BYTES - src.MAX_ATTEMPTS * src._CHUNK_SIZE
    )


def test_status_outside_success_range_is_a_safe_code() -> None:
    result = fetch_source(
        _client(lambda request: httpx.Response(404)), _spec(),
        context=_ctx(), resolve=_ok(),
    )
    assert result.ok is False and result.failure_code == "http_404"


# --- Spec planning and model-page slugs --------------------------------------


def test_plan_catalog_specs_covers_selected_providers() -> None:
    specs = plan_catalog_specs(("openrouter",))
    assert [(s.url, s.source_kind) for s in specs] == [(OR_URL, "openrouter_models_api")]
    specs = plan_catalog_specs(("openai",))
    assert [(s.url, s.source_kind) for s in specs] == [
        (PRICING_URL, "openai_pricing_docs"),
        (MODELS_MD_URL, "openai_models_docs"),
    ]
    specs = plan_catalog_specs(("openai", "openrouter"))
    assert len(specs) == 3
    assert ecb_spec().url == ECB_URL
    with pytest.raises(SourceFetchError) as exc:
        plan_catalog_specs(("anthropic",))
    assert exc.value.code == "unknown_provider"


def test_model_page_slug_is_quoted_model_identity() -> None:
    spec = model_page_spec("openai", "gpt-5.2")
    assert spec.url == PAGE_URL
    assert spec.required is False
    spec = model_page_spec("openai", "meta/llama-3.1:free")
    assert spec.url.endswith("/models/meta%2Fllama-3.1%3Afree.md")
    with pytest.raises(SourceFetchError) as exc:
        model_page_spec("openai", "../etc/passwd")
    assert exc.value.code == "model_page_slug_invalid"


# --- AP-F1: ONE whole-invocation budget and cross-phase cache ---------------


def test_one_attempt_budget_spans_fetch_calls_no_reset() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=b'{"data": []}')

    client = _client(handler)
    context = _ctx(max_attempts=4)
    slugs = [f"budget-model-{i}" for i in range(5)]
    # Four fetch calls, one spec each: the SAME context carries the
    # allowance across all of them (4 attempts = exactly 4 requests).
    for i in range(4):
        results = fetch_sources(
            (_page_spec(slugs[i]),), client=client, context=context, resolve=_ok()
        )
        assert results[0].ok is True
    assert hits["n"] == 4
    # The fifth call: the pre-attempt reservation fails - no reset.
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((_page_spec(slugs[4]),), client=client, context=context, resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"
    assert hits["n"] == 4, "no HTTP request after exhaustion"


def test_one_byte_budget_spans_fetch_calls_no_reset() -> None:
    body = b"z" * 1024
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=body)

    client = _client(handler)
    context = _ctx(max_bytes=3 * 1024)

    def small_spec(slug: str) -> SourceSpec:
        return SourceSpec(
            provider="openai",
            source_kind="docs_page",
            model=slug,
            url=f"https://developers.openai.com/api/docs/models/{slug}.md",
            max_bytes=1024,
            required=False,
        )

    slugs = [f"byte-model-{i}" for i in range(4)]
    for i in range(3):
        results = fetch_sources(
            (small_spec(slugs[i]),), client=client, context=context, resolve=_ok()
        )
        assert results[0].ok is True
    assert hits["n"] == 3
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(
            (small_spec(slugs[3]),), client=client, context=context, resolve=_ok()
        )
    assert exc.value.code == "collection_budget_exhausted"
    assert hits["n"] == 3, "no HTTP request after exhaustion"


def test_failed_body_read_consumes_budget_and_blocks_next_spec() -> None:
    # 2 MiB collection budget; a 1 MiB spec whose body is 1 MiB + one
    # chunk: the failed read consumes 17 chunks (no refund), leaving less
    # than the next spec's cap can cover.
    body = b"x" * (1024 * 1024 + src._CHUNK_SIZE)
    context = _ctx(max_bytes=2 * 1024 * 1024)
    client = _client(lambda request: httpx.Response(200, content=body))

    def capped_spec(slug: str) -> SourceSpec:
        return SourceSpec(
            provider="openai",
            source_kind="docs_page",
            model=slug,
            url=f"https://developers.openai.com/api/docs/models/{slug}.md",
            max_bytes=1024 * 1024,
            required=False,
        )

    results = fetch_sources(
        (capped_spec("fail-one"),), client=client, context=context, resolve=_ok()
    )
    assert results[0].ok is False
    assert results[0].failure_code == "body_too_large"
    consumed = 17 * src._CHUNK_SIZE
    assert context.bytes_remaining == 2 * 1024 * 1024 - consumed
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(
            (capped_spec("fail-two"),), client=client, context=context, resolve=_ok()
        )
    assert exc.value.code == "collection_budget_exhausted"


def test_attempts_are_counted_per_real_http_request() -> None:
    # One redirect hop + one 5xx retry + one success = 4 real requests
    # = 4 attempts charged, recorded as spec attempts 3.
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(301, headers={"location": OR_URL})
        if hits["n"] == 2:
            return httpx.Response(503)
        return httpx.Response(200, content=b'{"data": []}')

    context = _ctx(max_attempts=4)
    result = fetch_sources((_spec(),), client=_client(handler), context=context, resolve=_ok())
    assert result[0].ok is True and result[0].attempts == 3
    assert context.attempts_remaining == 1, "every hop and retry is charged (4 of 4 used)"


def test_cross_phase_cache_reuses_success_and_failure() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=b'{"data": []}')

    client = _client(handler)
    context = _ctx()
    spec = _spec()
    phase1 = fetch_sources((spec,), client=client, context=context, resolve=_ok())
    phase2 = fetch_sources((spec,), client=client, context=context, resolve=_ok())
    assert hits["n"] == 1, "the cached success is never re-fetched"
    assert phase2[0] is phase1[0], "same result: no new retrieval-time claim"

    # failures are cached too
    def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    context2 = _ctx()
    page = _page_spec("missing-model")
    r1 = fetch_sources((page,), client=_client(not_found), context=context2, resolve=_ok())
    r2 = fetch_sources((page,), client=_client(not_found), context=context2, resolve=_ok())
    assert r1[0].ok is False and r1[0].failure_code == "http_404"
    assert r2[0] is r1[0]


def test_cache_identity_mismatch_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"data": []}')

    client = _client(handler)
    context = _ctx()
    spec_a = _spec()
    fetch_sources((spec_a,), client=client, context=context, resolve=_ok())
    # Same URL, different registry identity: a planner bug, fails closed.
    spec_b = SourceSpec(
        provider="openrouter",
        source_kind="openrouter_models_api",
        model="other-model",
        url=spec_a.url,
        max_bytes=spec_a.max_bytes,
    )
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((spec_b,), client=client, context=context, resolve=_ok())
    assert exc.value.code == "duplicate_url_planned"


# --- AP-F1: finite deadline negatives (real, bounded wall time) -------------


def test_deadline_stops_slow_dns_before_later_network() -> None:
    # Slow-DNS negative (injected-seam level, 181-h R1): each resolver
    # call sleeps 0.35 s; the collection target is 0.6 s. Attempt 1
    # resolves at ~0.35 s and its single 503 HTTP request is charged;
    # the 5xx retry's preflight resolves at ~0.70 s, AFTER the target -
    # and NO second HTTP request starts after expiry (the cooperative
    # checkpoint runs between the resolver and the next action).
    # Collection-level exhaustion propagates. The in-process resolver is
    # ordinary and cannot be cancelled MID-sleep (documented R1 limit);
    # the elapsed-time cutoff for the operator workflow is the standard
    # watchdog (H3).
    calls = {"dns": 0, "http": 0}

    def slow_public(host, port, proto=None):
        calls["dns"] += 1
        time.sleep(0.35)
        return [_ainfo(PUBLIC)]

    def handler(request: httpx.Request) -> httpx.Response:
        calls["http"] += 1
        return httpx.Response(503)

    started = time.monotonic()
    with pytest.raises(SourceFetchError) as exc:
        fetch_source(
            _client(handler), _spec(),
            context=_ctx(deadline_seconds=0.6), resolve=slow_public,
        )
    wall = time.monotonic() - started
    assert exc.value.code == "acquisition_deadline_exceeded"
    assert calls["http"] == 1, "no HTTP request starts after the deadline"
    assert calls["dns"] == 2, "the retry preflight ran; nothing later did"
    assert wall < 2.0, f"wall time unbounded: {wall}"


def test_deadline_stops_slow_drip_mid_body() -> None:
    # Slow-drip negative: 1 KiB chunks every 0.2 s, collection target
    # 0.6 s. The read stops at the target (bounded wall time) and every
    # RETURNED chunk is charged, including the one that arrives after
    # expiry (181-h R2).
    def drip():
        for _ in range(64):
            yield b"d" * 1024
            time.sleep(0.2)

    context = _ctx(deadline_seconds=0.6)
    started = time.monotonic()
    with pytest.raises(SourceFetchError) as exc:
        fetch_source(
            _client(lambda request: httpx.Response(200, content=drip())),
            _spec(max_bytes=1024 * 1024),
            context=context,
            resolve=_ok(),
        )
    wall = time.monotonic() - started
    assert exc.value.code == "acquisition_deadline_exceeded"
    assert wall < 2.0, f"wall time unbounded: {wall}"
    charged = src.MAX_COLLECTION_BYTES - context.bytes_remaining
    # the delivered 1 KiB chunks are charged, including at most one
    # late-returned chunk (a few of them, never the whole drip)
    assert 2 * 1024 <= charged <= 5 * 1024, f"charged={charged}"


def test_retry_sleep_is_deadline_bounded_and_no_http_after_expiry() -> None:
    # 429 with Retry-After: 30 s, deadline 0.5 s. The sleep is bounded by
    # the deadline; when it expires, NO second HTTP request is started.
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "30"})
        return httpx.Response(200, content=b'{"data": []}')

    started = time.monotonic()
    with pytest.raises(SourceFetchError) as exc:
        fetch_source(
            _client(handler), _spec(),
            context=_ctx(deadline_seconds=0.5), resolve=_ok(),
        )
    wall = time.monotonic() - started
    assert exc.value.code == "acquisition_deadline_exceeded"
    assert hits["n"] == 1, "no later HTTP after the deadline"
    assert wall < 1.5, f"retry sleep not deadline-bounded: {wall}"


# --- AP-F2: vetted-connection binding through the production client --------


def test_new_client_binds_actual_connection_to_vetted_numeric_destination() -> None:
    calls: list = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(socket, "create_connection", _refusing_create_connection(calls))
    try:
        client = new_client(resolve=_ok())
        try:
            result = fetch_source(
                client, _spec(), context=_ctx(), resolve=_ok()
            )
        finally:
            client.close()
    finally:
        monkey.undo()
    assert result.ok is False
    assert result.failure_code == "destination_connect_failed"
    assert result.attempts == src.MAX_ATTEMPTS
    assert len(calls) == src.MAX_ATTEMPTS
    # The ACTUAL connection primitive was asked for the vetted PUBLIC
    # NUMERIC destination (and nothing else) on every attempt.
    assert all(addr == (PUBLIC, 443) for addr in calls)


def test_tls_keeps_original_hostname_sni_and_verified_policy() -> None:
    wrapped: list = []
    sockets: list = []
    # A fresh unconnected AF_INET socket per attempt: TCP options work,
    # and the spy refuses the handshake before any I/O happens on it.
    def fresh_socket(*args, **kwargs):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockets.append(sock)
        return sock

    monkey = pytest.MonkeyPatch()
    monkey.setattr(socket, "create_connection", fresh_socket)

    def spy_wrap(self_ctx, sock, server_hostname=None, *args, **kwargs):
        wrapped.append((self_ctx.check_hostname, self_ctx.verify_mode, server_hostname))
        raise ssl.SSLError("test boundary: no real handshake")

    monkey.setattr(ssl.SSLContext, "wrap_socket", spy_wrap)
    calls: list = []
    try:
        client = new_client(resolve=_ok())
        try:
            result = fetch_source(
                client, _spec(), context=_ctx(), resolve=_ok()
            )
        finally:
            client.close()
    finally:
        monkey.undo()
        for sock in sockets:
            sock.close()
    # Safe failure from the refused handshake...
    assert result.ok is False
    assert result.failure_code == "transport_error"
    assert result.attempts == src.MAX_ATTEMPTS
    # ...while the REAL production TLS path was exercised with the
    # ORIGINAL hostname as SNI and the verified certificate policy.
    assert len(wrapped) == src.MAX_ATTEMPTS
    for check_hostname, verify_mode, server_hostname in wrapped:
        assert server_hostname == "openrouter.ai"
        assert check_hostname is True
        assert verify_mode == ssl.CERT_REQUIRED
    assert all(addr == (PUBLIC, 443) for addr in calls)


def test_mixed_dns_answer_set_refused_before_any_connection() -> None:
    def mixed(host, port, proto=None):
        return [_ainfo(PUBLIC), _ainfo(LOOPBACK)]

    calls: list = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(socket, "create_connection", _refusing_create_connection(calls))
    try:
        client = new_client(resolve=mixed)
        try:
            result = fetch_source(
                client, _spec(), context=_ctx(), resolve=mixed
            )
        finally:
            client.close()
    finally:
        monkey.undo()
    assert result.ok is False
    assert result.failure_code == "destination_mixed_or_not_public"
    assert result.attempts == 0, "preflight refusal: no request sent, no retry loop, no connection"
    assert calls == [], "the mixed answer set never reaches a connection"


def test_rebinding_between_preflight_and_connect_is_refused() -> None:
    # The preflight sees a public address; the connect-time resolution
    # (the one that is bound) sees loopback. The connection must be
    # refused - preflight vetting alone is not a fix.
    state = {"n": 0}

    def rebinding(host, port, proto=None):
        state["n"] += 1
        if state["n"] % 2 == 1:
            return [_ainfo(PUBLIC)]
        # connect-time answer: the vetted public address rebound alongside
        # a loopback one - the mixed set must be refused as a whole.
        return [_ainfo(PUBLIC), _ainfo(LOOPBACK)]

    calls: list = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(socket, "create_connection", _refusing_create_connection(calls))
    try:
        client = new_client(resolve=rebinding)
        try:
            result = fetch_source(
                client, _spec(), context=_ctx(), resolve=rebinding
            )
        finally:
            client.close()
    finally:
        monkey.undo()
    assert result.ok is False
    assert result.failure_code == "destination_mixed_or_not_public"
    assert calls == [], "never connected to the rebound (loopback) address"


def test_environment_proxy_is_never_used() -> None:
    calls: list = []
    monkey = pytest.MonkeyPatch()
    monkey.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    monkey.setenv("HTTP_PROXY", "http://127.0.0.1:9999")
    monkey.setattr(socket, "create_connection", _refusing_create_connection(calls))
    try:
        client = new_client(resolve=_ok())
        assert client.trust_env is False
        try:
            result = fetch_source(
                client, _spec(), context=_ctx(), resolve=_ok()
            )
        finally:
            client.close()
    finally:
        monkey.undo()
    assert result.ok is False
    assert result.failure_code == "destination_connect_failed"
    # A proxy would connect to 127.0.0.1:9999; the recorded targets prove
    # direct vetted connections only.
    assert len(calls) == src.MAX_ATTEMPTS
    assert all(addr == (PUBLIC, 443) for addr in calls)


def test_spec_cache_reuse_makes_no_second_connection() -> None:
    calls: list = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(socket, "create_connection", _refusing_create_connection(calls))
    try:
        client = new_client(resolve=_ok())
        try:
            context = _ctx()
            r1 = fetch_sources(
                (_spec(),), client=client, context=context, resolve=_ok()
            )
            r2 = fetch_sources(
                (_spec(),), client=client, context=context, resolve=_ok()
            )
        finally:
            client.close()
    finally:
        monkey.undo()
    assert r1[0].ok is False
    assert r2[0] is r1[0], "cached failure reused: no new retrieval"
    assert len(calls) == src.MAX_ATTEMPTS, "no second connection for the cached URL"


def test_production_pool_only_connects_through_vetted_backend() -> None:
    client = new_client(resolve=_ok())
    try:
        # The pool's network backend is the ONLY connection path inside
        # the acquisition client: reuse, retries, and redirects all open
        # new connections through it, so none can bypass the vetted
        # destination decision.
        backend = client._transport._pool._network_backend
        assert isinstance(backend, VettedNetworkBackend)
    finally:
        client.close()


def test_unix_domain_sockets_are_forbidden_by_the_backend() -> None:
    backend = VettedNetworkBackend(resolve=_ok())
    with pytest.raises(SourceFetchError) as exc:
        backend.connect_unix_socket("/tmp/forbidden.sock")
    assert exc.value.code == "uds_forbidden"


# --- fetch_sources: dedupe, provenance, budgets ------------------------------


def test_fetch_sources_deduplicates_shared_urls() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=b'{"data": []}')

    spec_a = _spec()
    spec_b = _spec()  # same URL: shared retrieval, never re-fetched
    results = fetch_sources(
        (spec_a, spec_b), client=_client(handler), context=_ctx(), resolve=_ok()
    )
    assert len(results) == 2
    assert results[0].content == results[1].content
    assert hits["n"] == 1


def test_fetch_sources_budgets_block_collection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1024)

    # Attempt budget: 129 distinct page URLs exhaust 128 attempts.
    many = tuple(_page_spec(f"many-{i}") for i in range(src.MAX_COLLECTION_REQUESTS + 1))
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(many, client=_client(handler), context=_ctx(), resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"

    # Byte budget: five 8 MiB bodies exceed the 32 MiB collection cap.
    big = b"z" * (8 * 1024 * 1024)

    def handler_big(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    big_specs = tuple(
        SourceSpec(
            provider="openai",
            source_kind="docs_page",
            model=f"big-{i}",
            url=f"https://developers.openai.com/api/docs/models/big-{i}.md",
            max_bytes=8 * 1024 * 1024,
        )
        for i in range(5)  # 5 x 8 MiB > 32 MiB
    )
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(
            big_specs, client=_client(handler_big), context=_ctx(), resolve=_ok()
        )
    assert exc.value.code == "collection_budget_exhausted"


def test_new_client_bounded_timeouts_no_implicit_redirects() -> None:
    client = new_client()
    try:
        assert client.follow_redirects is False
        assert client.trust_env is False, "no environment proxies or implicit config"
        assert client.headers["accept-encoding"] == "identity"
        timeout = client.timeout
        assert timeout.read <= src.READ_TIMEOUT + 1
        assert timeout.connect <= src.CONNECT_TIMEOUT + 1
    finally:
        client.close()


def test_failed_retrieval_never_records_body_content() -> None:
    result = fetch_source(
        _client(lambda request: httpx.Response(404, content=b"secret")),
        _spec(),
        context=_ctx(),
        resolve=_ok(),
    )
    assert result.ok is False
    assert result.content is None
    assert result.content_sha256() is None
    assert result.failure_code == "http_404"


# --- 181-g: G1-G6 regressions (strategic negative probes) -------------------


class _FakeSock:
    """Minimal socket double for the backend connect seam tests."""

    def __init__(self, recv_side=None, send_side=None):
        self.recv_calls: list[int] = []
        self.send_calls = 0
        self.closed = False
        self.timeouts: list[float | None] = []
        self._recv_side = recv_side
        self._send_side = send_side

    def settimeout(self, value: float | None) -> None:
        self.timeouts.append(value)

    def setsockopt(self, *args: object) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def recv(self, n: int) -> bytes:
        self.recv_calls.append(n)
        return self._recv_side(n) if self._recv_side is not None else b""

    def send(self, data: bytes) -> int:
        self.send_calls += 1
        if self._send_side is not None:
            return self._send_side(data)
        return len(data)


# --- 181-h R1: cooperative target at application checkpoints ----------------


def test_expired_dns_preflight_stops_before_http() -> None:
    # G1 (injected-seam level; documented limit: the in-process test
    # seam cannot be killed mid-call, so the deadline is re-checked
    # between the resolver and the next action): NO HTTP request starts
    # after expiry.
    calls = {"http": 0}

    def slow_public(host, port, proto=None):
        time.sleep(0.05)
        return [_ainfo(PUBLIC)]

    def handler(request: httpx.Request) -> httpx.Response:
        calls["http"] += 1
        return httpx.Response(200, content=b"[]")

    ctx = _ctx(deadline_seconds=0.02)
    started = time.monotonic()
    with pytest.raises(SourceFetchError) as exc:
        fetch_source(_client(handler), _spec(), context=ctx, resolve=slow_public)
    wall = time.monotonic() - started
    assert exc.value.code == "acquisition_deadline_exceeded"
    assert calls["http"] == 0, "no HTTP request starts after expired DNS"
    assert wall < 0.05 + 0.25, f"wall time unbounded: {wall}"


# --- G2: overflow debited in full, exhaustion terminal ----------------------


def test_overflow_chunk_is_debited_and_exhaustion_is_terminal() -> None:
    # G2 (exact probe case): 256 budget, chunks 200+100. The overflow
    # chunk is DEBITED in full (honest -44 deficit, never a refund) and
    # the invocation is terminally exhausted: the later 50-byte fetch is
    # refused BEFORE its handler runs.
    ctx = _ctx(max_bytes=256)
    hits = {"a": 0, "b": 0}

    def handler_a(request: httpx.Request) -> httpx.Response:
        hits["a"] += 1
        return httpx.Response(
            200,
            content=IteratorByteStream(iter([b"x" * 200, b"y" * 100])),
            headers={"content-type": "application/json"},
        )

    def handler_b(request: httpx.Request) -> httpx.Response:
        hits["b"] += 1
        return httpx.Response(200, content=b"z" * 50)

    spec_a = _spec(max_bytes=256)
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((spec_a,), client=_client(handler_a), context=ctx, resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"
    assert ctx.bytes_remaining == -44, "all 300 consumed bytes debited (256-300)"
    assert ctx.exhausted is True

    with pytest.raises(SourceFetchError) as exc2:
        fetch_sources(
            (_page_spec("gpt-5.2"),), client=_client(handler_b), context=ctx, resolve=_ok()
        )
    assert exc2.value.code == "collection_budget_exhausted"
    assert hits["a"] == 1
    assert hits["b"] == 0, "terminal exhaustion blocks the later fetch before its handler"


def test_failed_read_bytes_are_never_refunded() -> None:
    # G2: bytes consumed before a mid-stream failure stay charged (no
    # refund); the finite retry re-reads and the crossing debit
    # terminates the invocation. 256 budget, 200+failure, retry 200 ->
    # an honest -144 deficit, and the later fetch is refused pre-handler.
    ctx = _ctx(max_bytes=256)
    hits = {"n": 0, "b": 0}

    def failing(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1

        def gen():
            yield b"x" * 200
            raise OSError("test boundary: reset")

        return httpx.Response(200, content=IteratorByteStream(gen()))

    spec_a = _spec(max_bytes=256)
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((spec_a,), client=_client(failing), context=ctx, resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"
    assert hits["n"] == 2, "finite retry re-reads; both consumed amounts debited"
    assert ctx.bytes_remaining == -144, "200+200 consumed of 256, no refund of failed bytes"
    assert ctx.exhausted is True

    def handler_b(request: httpx.Request) -> httpx.Response:
        hits["b"] += 1
        return httpx.Response(200, content=b"z" * 100)

    with pytest.raises(SourceFetchError) as exc2:
        fetch_sources(
            (_page_spec("gpt-5.2"),), client=_client(handler_b), context=ctx, resolve=_ok()
        )
    assert exc2.value.code == "collection_budget_exhausted"
    assert hits["b"] == 0, "terminal exhaustion blocks the later fetch before its handler"


def test_charge_and_reserve_refuse_after_terminal_exhaustion() -> None:
    # G2 (accounting seam): the crossing debit records the full honest
    # deficit; charge AND reserve refuse thereafter (no leftover credit).
    ctx = _ctx(max_bytes=256)
    ctx.charge_body_bytes(200)
    assert ctx.bytes_remaining == 56
    with pytest.raises(SourceFetchError) as exc:
        ctx.charge_body_bytes(100)
    assert exc.value.code == "collection_budget_exhausted"
    assert ctx.bytes_remaining == -44, "the crossing chunk is debited in full"
    assert ctx.exhausted is True
    with pytest.raises(SourceFetchError) as exc:
        ctx.charge_body_bytes(1)
    assert exc.value.code == "collection_budget_exhausted"
    with pytest.raises(SourceFetchError) as exc:
        ctx.reserve_attempt()
    assert exc.value.code == "collection_budget_exhausted"


def test_deadline_failure_does_not_hide_consumed_bytes() -> None:
    # G2/R2: 200 bytes are returned, then the stream stalls past the
    # 0.1 s target and 10 MORE bytes are returned after expiry. The
    # deadline failure aborts the run, but the LATE-RETURNED bytes are
    # debited first (210 of 256 charged, 46 remain - not the old 56).
    ctx = _ctx(max_bytes=256, deadline_seconds=0.1)

    def stalling(request: httpx.Request) -> httpx.Response:
        def gen():
            yield b"x" * 200
            time.sleep(0.3)
            yield b"y" * 10

        return httpx.Response(200, content=IteratorByteStream(gen()))

    spec_a = _spec(max_bytes=256)
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((spec_a,), client=_client(stalling), context=ctx, resolve=_ok())
    assert exc.value.code == "acquisition_deadline_exceeded"
    assert ctx.bytes_remaining == 46, "the late-returned 10 bytes are debited before the deadline failure (210 charged)"


# --- 181-h R2: returned chunks debited BEFORE deadline/overflow failure ------


def test_late_returned_chunk_after_expiry_is_debited_not_omitted() -> None:
    # 181-h R2 (exact G negative): 256 budget; 200 bytes are returned,
    # the context expires, then 100 MORE bytes are returned. The actual
    # 300 processed bytes are ALL charged (remaining -44, terminally
    # exhausted); the safe code may be deadline or budget, but the late
    # 100 bytes must not be omitted (the old 56-credit retention is
    # gone).
    ctx = _ctx(max_bytes=256)

    def late(request: httpx.Request) -> httpx.Response:
        def gen():
            yield b"x" * 200
            ctx.deadline = time.monotonic() - 1.0
            yield b"y" * 100

        return httpx.Response(200, content=IteratorByteStream(gen()))

    spec_a = _spec(max_bytes=256)
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((spec_a,), client=_client(late), context=ctx, resolve=_ok())
    assert exc.value.code in (
        "acquisition_deadline_exceeded",
        "collection_budget_exhausted",
    )
    assert ctx.bytes_remaining == -44, "all 300 returned bytes debited (256-300)"
    assert ctx.exhausted is True, "the crossing debit is terminal"


def test_expired_context_charges_returned_bytes_before_deadline_failure() -> None:
    # 181-h R2 (charge seam): already-consumed bytes passed to the
    # charge layer CANNOT vanish just because the collection target has
    # passed: the debit happens first, then the deadline failure.
    ctx = _ctx(max_bytes=256, deadline_seconds=0)
    with pytest.raises(SourceFetchError) as exc:
        ctx.charge_body_bytes(100)
    assert exc.value.code == "acquisition_deadline_exceeded"
    assert ctx.bytes_remaining == 156, "the returned 100 bytes are debited, not hidden"


def test_cross_phase_exhaustion_blocks_later_request_before_it_starts() -> None:
    # 181-h R2 (cross-phase reuse): terminal exhaustion from a failed
    # crossing read blocks the LATER spec before any new request is
    # sent (no post-exhaustion request, no leftover credit).
    ctx = _ctx(max_bytes=256)
    hits = {"n": 0}

    def failing(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1

        def gen():
            yield b"x" * 200
            yield b"y" * 100  # crosses 256: debited in full, terminal

        return httpx.Response(200, content=IteratorByteStream(gen()))

    with pytest.raises(SourceFetchError) as exc:
        fetch_sources((_spec(max_bytes=256),), client=_client(failing), context=ctx, resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"
    assert ctx.exhausted is True

    def later(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=b"z" * 10)

    with pytest.raises(SourceFetchError) as exc2:
        fetch_sources((_page_spec("gpt-5.2"),), client=_client(later), context=ctx, resolve=_ok())
    assert exc2.value.code == "collection_budget_exhausted"
    assert hits["n"] == 1, "no post-exhaustion request reaches the handler"


# --- 181-h H1: custom DNS worker / deadline-stream machinery absent ----------


def test_custom_dns_worker_and_deadline_stream_machinery_is_absent() -> None:
    # 181-h AP-H1: the removed 181-g machinery (custom DNS child process,
    # kill/reap lifecycle, deadline-wrapped stream, context binding) must
    # be ABSENT, while the small numeric connect-time vetting adapter and
    # the standard transport surface remain.
    import inspect

    for name in (
        "_spawn_resolver",
        "_resolve_default_bounded",
        "_RESOLVER_SCRIPT",
        "DeadlineStream",
        "DNS_REAP_TIMEOUT_SECONDS",
        "ACQUISITION_DNS_CAP_SECONDS",
        "resolve_vetted_public_destination",
    ):
        assert not hasattr(st, name), f"removed machinery still present: {name}"
    for cls in (st.VettedHTTPTransport, st.VettedNetworkBackend):
        params = inspect.signature(cls.__init__).parameters
        assert "deadline" not in params, f"{cls.__name__} still takes a deadline binding"
    assert not hasattr(src, "bind_acquisition_to_client"), "binding seam must be absent"
    # the retained, standard surface
    assert hasattr(st, "vet_public_destination")
    assert hasattr(st, "VettedNetworkBackend")
    assert hasattr(st, "VettedHTTPTransport")


# --- G3: global-unicast classification at the actual socket decision -------


@pytest.mark.parametrize(
    "ip",
    [
        "100.64.0.1",  # RFC 6598 shared address space (the probe case)
        "100.127.255.255",  # RFC 6598 upper edge
        "192.0.2.1",  # TEST-NET-1
        "198.18.0.1",  # benchmarking
        "224.0.0.1",  # multicast
        "240.0.0.1",  # reserved 240/4
        "2001:db8::1",  # IPv6 documentation
        "fe80::1",  # link-local
        "ff02::1",  # multicast
        "::ffff:100.64.0.1",  # IPv4-mapped CGNAT
    ],
)
def test_non_global_unicast_destination_refused_at_connect(
    ip: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = VettedNetworkBackend(resolve=_resolve(ip))
    calls: list = []

    def refusing(address, timeout=None, source_address=None, **kwargs):
        calls.append(address)
        raise AssertionError(f"must never connect to non-global {ip}")

    monkeypatch.setattr(socket, "create_connection", refusing)
    with pytest.raises(SourceFetchError) as exc:
        backend.connect_tcp("openrouter.ai", 443, timeout=1.0)
    assert exc.value.code == "destination_not_public"
    assert calls == [], "the non-global answer set never reaches a connection"


def test_mixed_answer_set_refused_as_a_whole_at_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # G3: a mixed answer set (one global, one CGNAT) is refused as a
    # WHOLE at the connect decision - never filtered to its public
    # member.
    backend = VettedNetworkBackend(resolve=_resolve(PUBLIC, "100.64.0.1"))
    calls: list = []

    def refusing(address, timeout=None, source_address=None, **kwargs):
        calls.append(address)
        raise AssertionError("mixed set must be refused before any connection")

    monkeypatch.setattr(socket, "create_connection", refusing)
    with pytest.raises(SourceFetchError) as exc:
        backend.connect_tcp("openrouter.ai", 443, timeout=1.0)
    assert exc.value.code == "destination_mixed_or_not_public"
    assert calls == [], "the mixed set is never filtered to its public member"


@pytest.mark.parametrize(
    "ip",
    [
        "93.184.216.34",
        "8.8.8.8",
        "2606:4700:4700::1111",
        "::ffff:93.184.216.34",
    ],
)
def test_global_unicast_destination_connects_numerically(
    ip: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # G3: legitimate global-unicast destinations (v4, v6, mapped) are
    # connected to the vetted NUMERIC destination.
    backend = VettedNetworkBackend(resolve=_resolve(ip))
    calls: list = []
    sock = _FakeSock()

    def fake_connect(address, timeout=None, source_address=None, **kwargs):
        calls.append(address)
        return sock

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    stream = backend.connect_tcp("openrouter.ai", 443, timeout=1.0)
    try:
        assert calls == [(ip, 443)], "connects only to the vetted numeric destination"
        assert isinstance(stream, SyncStream)
    finally:
        stream.close()
    assert sock.closed


# --- G4: safe rejected URL provenance ---------------------------------------


@pytest.mark.parametrize(
    ("location", "code"),
    [
        (
            "https://synthetic-user:synthetic-password@developers.openai.com"
            "/api/docs/models/a.md?token=synthetic-token",
            "url_credentials",
        ),
        (
            "https://developers.openai.com/api/docs/models/a.md?token=synthetic-token",
            "url_query_forbidden",
        ),
        (
            "https://developers.openai.com/api/docs/models/a.md#synthetic-token",
            "url_fragment_forbidden",
        ),
        (
            "https://evil.example.com/api/docs/models/a.md",
            "url_host_not_approved",
        ),
    ],
)
def test_rejected_redirect_target_never_reaches_final_url(location: str, code: str) -> None:
    # G4 (exact probe case, plus query/fragment/host/malformed-port
    # variants): the rejected raw target never leaves the loop variable -
    # final_url is the last VALIDATED safe URL (None when it is the
    # requested URL), and no synthetic marker survives serialization.
    spec = _page_spec("gpt-5.2")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == spec.url
        return httpx.Response(302, headers={"location": location})

    result = fetch_source(_client(handler), spec, context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == code
    assert result.final_url is None, "only a validated safe URL (or absent) is recorded"
    text = repr(dataclasses.asdict(result))
    for marker in ("synthetic-user", "synthetic-password", "synthetic-token"):
        assert marker not in text, f"rejected target leaked into provenance: {marker}"


def test_malformed_numeric_redirect_location_refused_at_revalidation() -> None:
    # G6 (redirect level): an OUT-OF-RANGE numeric port parses through
    # httpx's own redirect bookkeeping, so our re-validation is the
    # decision point: the exact safe code applies, provenance stays clean.
    spec = _page_spec("gpt-5.2")
    location = "https://developers.openai.com:99999/api/docs/models/a.md"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": location})

    result = fetch_source(_client(handler), spec, context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "url_nondefault_port"
    assert result.final_url is None
    assert "99999" not in repr(dataclasses.asdict(result))


def test_malformed_redirect_location_fails_safely_without_escaping() -> None:
    # G6 (redirect level): a NON-NUMERIC port cannot be parsed by httpx's
    # own redirect bookkeeping, which refuses it (RemoteProtocolError)
    # BEFORE our manual re-validation. The failure is still deterministic
    # and safe: the httpx error is caught, the SAFE code is recorded, no
    # ValueError escapes, and no raw target text reaches provenance.
    spec = _page_spec("gpt-5.2")
    location = "https://developers.openai.com:not-a-port/api/docs/models/a.md"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": location})

    result = fetch_source(_client(handler), spec, context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "transport_error", "safe code, no escaping exception"
    assert result.final_url is None
    assert "not-a-port" not in repr(dataclasses.asdict(result))


def test_redirect_to_encoded_traversal_page_is_refused_safely() -> None:
    # G5 (redirect level): a 302 whose target only decodes to a
    # traversal slug is refused with the safe slug code; provenance stays
    # clean.
    spec = _page_spec("gpt-5.2")
    location = (
        "https://developers.openai.com/api/docs/models/a%2F..%2F..%2Fprivate.md"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": location})

    result = fetch_source(_client(handler), spec, context=_ctx(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "model_page_slug_invalid"
    assert result.final_url is None
    assert "private" not in repr(dataclasses.asdict(result))


# --- G5: traversal and ambiguous URL encodings --------------------------------


@pytest.mark.parametrize(
    "slug",
    [
        "a%2F..%2F..%2Fprivate",  # the probe case: encoded traversal
        "%2e%2e%2fsecret",  # encoded dot segments
        "..%2Fsecret",  # raw dot + encoded separator
        "a%2F..%2Fb",  # traversal inside the ID
        "a%5Cb",  # backslash escape
        "%252Fetc",  # double/ambiguous percent escape
        "a%00b",  # control character
        "a%2F%2Fb",  # empty part (double separator)
        "..%2F..%2Fetc%2Fpasswd",
    ],
)
def test_encoded_traversal_and_ambiguous_slugs_refused(slug: str) -> None:
    url = f"https://developers.openai.com/api/docs/models/{slug}.md"
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url(url, provider="openai")
    assert exc.value.code == "model_page_slug_invalid"


@pytest.mark.parametrize(
    "slug",
    [
        "gpt-4o",
        "gpt-5.2",
        "vendor%2Fmodel",
        "meta%2Fllama-3.1%3Afree",  # legitimate namespaced ID with tag
        "chat%2D4o",
    ],
)
def test_legitimate_quoted_model_ids_preserved(slug: str) -> None:
    url = f"https://developers.openai.com/api/docs/models/{slug}.md"
    validate_source_url(url, provider="openai")  # must not raise


def test_model_page_spec_applies_same_slug_admission() -> None:
    # G5: generated specs get the SAME safe slug admission as supplied
    # or redirected URLs.
    with pytest.raises(SourceFetchError) as exc:
        model_page_spec("openai", "a/../../private")
    assert exc.value.code == "model_page_slug_invalid"
    with pytest.raises(SourceFetchError) as exc:
        model_page_spec("openai", "%2Fetc")
    assert exc.value.code == "model_page_slug_invalid"
    with pytest.raises(SourceFetchError) as exc:
        model_page_spec("openai", "a%2F..%2Fb")
    assert exc.value.code == "model_page_slug_invalid"
    spec = model_page_spec("openai", "openai/gpt-4o")
    assert spec.url == (
        "https://developers.openai.com/api/docs/models/openai%2Fgpt-4o.md"
    )


# --- G6: safe malformed URL/port handling ------------------------------------


@pytest.mark.parametrize(
    ("url", "code"),
    [
        (
            "https://developers.openai.com:not-a-port/api/docs/models/a.md",
            "url_nondefault_port",
        ),
        (
            "https://developers.openai.com:99999/api/docs/pricing.md",
            "url_nondefault_port",
        ),
        (
            "https://[::1/api/docs/pricing.md",
            "url_host_not_approved",
        ),
    ],
)
def test_malformed_authority_and_port_fail_with_safe_codes(url: str, code: str) -> None:
    # G6 (exact probe case, plus out-of-range and malformed brackets):
    # malformed untrusted URLs fail with the SAFE code, never an uncaught
    # ValueError or raw text.
    with pytest.raises(SourceFetchError) as exc:
        validate_source_url(url, provider="openai")
    assert exc.value.code == code


def test_explicit_default_port_still_accepted() -> None:
    validate_source_url(
        "https://developers.openai.com:443/api/docs/pricing.md", provider="openai"
    )
