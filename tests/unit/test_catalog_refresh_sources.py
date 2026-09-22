"""Unit tests for the 181 bounded official-source fetch layer (sources.py).

All traffic is served by ``httpx.MockTransport`` and every DNS lookup is an
injected resolver: no test performs a real network request. The tests pin
the security-relevant behavior: HTTPS-only approved-host allowlist,
credential/port rejection, public-destination guard, redirect re-validation
(every hop re-checked against the allowlist, bounded), bounded 429/5xx
retries, mid-stream body byte caps, encoding allowlist, URL deduplication,
collection budgets, and safe code-only failure outcomes.
"""

from __future__ import annotations

import hashlib
import socket

import httpx
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
    plan_catalog_specs,
    validate_source_url,
)

OR_URL = "https://openrouter.ai/api/v1/models"
PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
MODELS_MD_URL = "https://developers.openai.com/api/docs/models.md"
PAGE_URL = "https://developers.openai.com/api/docs/models/gpt-5.2.md"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

PUBLIC = "93.184.216.34"
PRIVATE = "192.168.1.10"


def _resolve(*ips: str):
    def resolve(host, port, proto=None):
        if not ips:
            raise OSError("nxdomain")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))
            for ip in ips
        ]

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


# --- URL validation (allowlist, scheme, credentials, port, path) -----------


def test_validate_source_url_approval_and_rejections() -> None:
    validate_source_url(OR_URL, provider="openrouter")
    validate_source_url("https://openrouter.ai:443/api/v1/models", provider="openrouter")
    validate_source_url(PRICING_URL, provider="openai")
    validate_source_url("https://openai.com/api/pricing.md", provider="openai")
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
        validate_source_url("https://openrouter.ai/api/v1/models", provider="openai")
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


# --- DNS public-destination guard ------------------------------------------


def test_private_or_failed_dns_is_a_safe_failure() -> None:
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        resolve=_resolve(PRIVATE),
    )
    assert result.ok is False and result.failure_code == "destination_not_public"
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        resolve=_resolve(),  # nxdomain
    )
    assert result.ok is False and result.failure_code == "dns_resolution_failed"
    # A resolver that returns an empty list is also a failure, never a pass.
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=b"{}")),
        _spec(),
        resolve=lambda host, port, proto=None: [],
    )
    assert result.ok is False and result.failure_code == "dns_resolution_failed"


# --- Successful retrieval records the measured outcome ---------------------


def test_ok_retrieval_records_outcome_status_bytes_and_digest() -> None:
    body = b'{"data": []}\n'
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
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
        _client(lambda request: httpx.Response(204)), _spec(), resolve=_ok()
    )
    assert result.ok is True and result.status == 204 and result.content == b""


# --- Redirects: bounded, relative-join, and re-validated -------------------


def test_relative_redirect_joins_and_stays_approved() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == OR_URL:
            return httpx.Response(301, headers={"location": "/api/v1/models?mirror=1"})
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is True
    assert result.redirects == 1
    assert result.final_url == "https://openrouter.ai/api/v1/models?mirror=1"
    assert len(calls) == 2


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
    result = fetch_source(client, _spec(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "url_host_not_approved"
    assert len(calls) == 1, "the unapproved target must never be requested"


def test_absolute_redirect_within_family_is_followed_and_recorded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OR_URL:
            return httpx.Response(
                301, headers={"location": "https://openrouter.ai/api/v1/models/new"}
            )
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is True and result.redirects == 1
    assert result.final_url == "https://openrouter.ai/api/v1/models/new"


def test_redirect_loop_is_bounded_and_missing_location_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            301, headers={"location": "https://openrouter.ai/api/v1/models"}
        )

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is False
    assert result.failure_code == "redirect_unbounded"
    assert result.redirects == src.MAX_REDIRECTS

    def no_location(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301)

    result = fetch_source(_client(no_location), _spec(), resolve=_ok())
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

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is True and result.attempts == 2


def test_429_beyond_retry_bound_fails_safe(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "300"})

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is False and result.failure_code == "rate_limited"
    assert result.attempts == 1  # an oversized retry-after is never waited on


def test_429_without_finite_retry_after_fails_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "soon"})

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is False and result.failure_code == "rate_limited"


def test_5xx_retries_bounded_times_then_fails_safe() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(503)

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is False and result.failure_code == "http_5xx"
    assert result.attempts == src.MAX_ATTEMPTS == hits["n"]


def test_5xx_then_success_records_attempts() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(502)
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is True and result.attempts == 2


def test_transport_error_retries_then_fails_safe() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] <= src.MAX_ATTEMPTS - 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, content=b'{"data": []}')

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is True and result.attempts == src.MAX_ATTEMPTS

    def always_down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = fetch_source(_client(always_down), _spec(), resolve=_ok())
    assert result.ok is False and result.failure_code == "transport_error"
    assert result.attempts == src.MAX_ATTEMPTS


# --- Body byte cap (mid-stream) and encoding allowlist ----------------------


def test_body_byte_cap_fails_mid_stream() -> None:
    big = b"x" * (64 * 1024 * 2)

    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=big)),
        _spec(max_bytes=64 * 1024),
        resolve=_ok(),
    )
    assert result.ok is False and result.failure_code == "body_too_large"
    assert result.content is None

    exact = b"y" * 64 * 1024
    result = fetch_source(
        _client(lambda request: httpx.Response(200, content=exact)),
        _spec(max_bytes=64 * 1024),
        resolve=_ok(),
    )
    assert result.ok is True and result.content == exact


def test_unexpected_encoding_fails_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"{}", headers={"content-encoding": "br"}
        )

    result = fetch_source(_client(handler), _spec(), resolve=_ok())
    assert result.ok is False and result.failure_code == "unexpected_encoding"


def test_status_outside_success_range_is_a_safe_code() -> None:
    result = fetch_source(
        _client(lambda request: httpx.Response(404)), _spec(), resolve=_ok()
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


# --- fetch_sources: dedupe, provenance, budgets ------------------------------


def test_fetch_sources_deduplicates_shared_urls() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=b'{"data": []}')

    spec_a = _spec()
    spec_b = _spec()  # same URL: shared retrieval, never re-fetched
    results = fetch_sources((spec_a, spec_b), client=_client(handler), resolve=_ok())
    assert len(results) == 2
    assert results[0].content == results[1].content
    assert hits["n"] == 1


def test_fetch_sources_seen_urls_replan_fails_closed() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=b'{"data": []}')

    client = _client(handler)
    phase1 = fetch_sources((_spec(),), client=client, resolve=_ok())
    assert phase1[0].ok is True
    # A URL already fetched in this invocation must never be re-planned by
    # the caller: that is a planner bug and fails closed with a safe code.
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(
            (_spec(),),
            client=client,
            resolve=_ok(),
            seen_urls={"https://openrouter.ai/api/v1/models"},
        )
    assert exc.value.code == "duplicate_url_planned"
    assert hits["n"] == 1, "no second network request for the re-planned URL"


def test_fetch_sources_budgets_block_collection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1024)

    many = tuple(_spec() for _ in range(src.MAX_COLLECTION_REQUESTS + 1))
    # Distinct URLs per spec: vary the path.
    many = tuple(
        SourceSpec(
            provider="openrouter",
            source_kind="openrouter_models_api",
            model="catalog",
            url=f"https://openrouter.ai/api/v1/models?page={i}",
            max_bytes=1024,
        )
        for i in range(src.MAX_COLLECTION_REQUESTS + 1)
    )
    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(many, client=_client(handler), resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"

    # Byte budget: one 4 MiB openrouter cap + a second full body exceeds 32 MiB
    # only with 32 bodies; use a tighter body to exceed the budget quickly.
    big = b"z" * (8 * 1024 * 1024)
    big_specs = tuple(
        SourceSpec(
            provider="openrouter",
            source_kind="openrouter_models_api",
            model="catalog",
            url=f"https://openrouter.ai/api/v1/models?big={i}",
            max_bytes=8 * 1024 * 1024,
        )
        for i in range(5)  # 5 x 8 MiB > 32 MiB
    )

    def handler_big(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    with pytest.raises(SourceFetchError) as exc:
        fetch_sources(big_specs, client=_client(handler_big), resolve=_ok())
    assert exc.value.code == "collection_budget_exhausted"


def test_new_client_bounded_timeouts_no_implicit_redirects() -> None:
    client = new_client()
    try:
        assert client.follow_redirects is False
        timeout = client.timeout
        assert timeout.read <= src.READ_TIMEOUT + 1
        assert timeout.connect <= src.CONNECT_TIMEOUT + 1
    finally:
        client.close()


def test_failed_retrieval_never_records_body_content() -> None:
    result = fetch_source(
        _client(lambda request: httpx.Response(404, content=b"secret")),
        _spec(),
        resolve=_ok(),
    )
    assert result.ok is False
    assert result.content is None
    assert result.content_sha256() is None
    assert result.failure_code == "http_404"
