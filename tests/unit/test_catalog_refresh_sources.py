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

import hashlib
import gzip
import socket
import ssl
import time

import httpx
from httpx._content import IteratorByteStream

import pytest

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
    # Slow-DNS negative: each resolver call sleeps 0.35 s; the deadline is
    # 0.6 s. Two attempts fit (preflight resolves at ~0.0 and ~0.35 s),
    # the third reservation is refused BEFORE any later DNS/HTTP activity.
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
    assert calls["http"] == 2, "no HTTP request starts after the deadline"
    assert calls["dns"] == 2, "no later DNS after the deadline"
    assert wall < 2.0, f"wall time unbounded: {wall}"


def test_deadline_stops_slow_drip_mid_body() -> None:
    # Slow-drip negative: 1 KiB chunks every 0.2 s, deadline 0.6 s. The
    # read stops at the deadline (bounded wall time) and the consumed
    # chunks are charged.
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
    # only the 1 KiB raw reads actually delivered before expiry are
    # charged (a few of them, never the whole drip)
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
    assert result.attempts == 1, "preflight refusal: no retry loop, no connection"
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
