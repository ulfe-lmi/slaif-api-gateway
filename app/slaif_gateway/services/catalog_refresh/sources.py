"""Objective 181 (C2): trusted, bounded acquisition of authoritative sources.

This module owns the ONLY live network path of the catalog refresh
subsystem. It is deliberately narrow:

- a fixed registry of official provider/publisher source families with
  exact host allowlists (no arbitrary URLs from model/source text);
- HTTPS only, no credentials in URLs, default port only;
- a DNS guard that refuses loopback/private/link-local/reserved
  destinations (checked before every request, including redirects);
- manual, bounded, re-validated redirects;
- bounded concurrency, request count, per-body bytes (enforced on the
  actual decoded stream, not Content-Length) and total collection bytes;
- finite 429/Retry-After handling and at most one retry on 5xx/transport
  failure;
- full provenance (requested/final URL, retrieval UTC time, status,
  content type, bytes, SHA-256) and safe code-only failures (never raw
  response bodies or secret-bearing exception text).

Retrieval time is never publication time. The retrieved bytes are data:
they are parsed by the registered deterministic parsers and never
executed, interpreted as HTML authority, or treated as configuration.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx

# --- source registry (fixed official families) -------------------------------

USER_AGENT = "slaif-gateway-catalog-collector/181 (+https://github.com/ulfe-lmi/slaif-api-gateway)"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENAI_PRICING_MD_URL = "https://developers.openai.com/api/docs/pricing.md"
OPENAI_MODELS_MD_URL = "https://developers.openai.com/api/docs/models.md"
OPENAI_MODEL_PAGE_URL = "https://developers.openai.com/api/docs/models/{slug}.md"
ECB_DAILY_XML_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# Exact host families per publisher (suffix-free exact hosts). Redirects
# may only land on the same family's approved hosts and are re-validated
# hop by hop.
OPENROUTER_HOSTS: frozenset[str] = frozenset({"openrouter.ai"})
OPENAI_HOSTS: frozenset[str] = frozenset({"openai.com", "developers.openai.com"})
ECB_HOSTS: frozenset[str] = frozenset({"www.ecb.europa.eu", "data-api.ecb.europa.eu"})

_PROVIDER_HOSTS: dict[str, frozenset[str]] = {
    "openrouter": OPENROUTER_HOSTS,
    "openai": OPENAI_HOSTS,
    "ecb": ECB_HOSTS,
}

# Per-body byte caps (decoded). Content-Length alone is not protection:
# the stream is counted chunk by chunk and aborted past the cap.
MAX_BODY_BYTES = {
    ("openrouter", "openrouter_models_api"): 4 * 1024 * 1024,
    ("openai", "openai_pricing_docs"): 512 * 1024,
    ("openai", "openai_models_docs"): 512 * 1024,
    ("openai", "docs_page"): 256 * 1024,
    ("ecb", "ecb_reference_xml"): 1 * 1024 * 1024,
}

# Collection-wide budgets.
MAX_COLLECTION_REQUESTS = 128
MAX_COLLECTION_BYTES = 32 * 1024 * 1024
MAX_CONCURRENCY = 4
MAX_REDIRECTS = 3
MAX_ATTEMPTS = 3  # initial + at most two retries (5xx/transport, or 429)
MAX_RETRY_AFTER_SECONDS = 30.0
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0
_CHUNK_SIZE = 64 * 1024
_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class SourceFetchError(Exception):
    """Safe, code-only acquisition failure. Never carries raw content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SourceSpec:
    """One planned retrieval from the official source registry."""

    provider: str
    source_kind: str
    model: str  # source record model part (catalog marker, pair, or slug)
    url: str
    max_bytes: int
    required: bool = True


@dataclass(frozen=True)
class RetrievalResult:
    """Measured outcome of one retrieval attempt sequence."""

    spec: SourceSpec
    ok: bool
    final_url: str | None
    retrieved_at: datetime
    status: int | None
    content_type: str | None
    content: bytes | None
    attempts: int
    redirects: int
    failure_code: str | None = None

    def content_sha256(self) -> str | None:
        if self.content is None:
            return None
        return hashlib.sha256(self.content).hexdigest()


def source_family_hosts(provider: str) -> frozenset[str]:
    try:
        return _PROVIDER_HOSTS[provider]
    except KeyError as exc:
        raise SourceFetchError("unknown_provider") from exc


def validate_source_url(url: str, *, provider: str) -> None:
    """Fail-closed URL validation against the source family's host set."""
    hosts = source_family_hosts(provider)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise SourceFetchError("url_not_https")
    if parsed.username is not None or parsed.password is not None:
        raise SourceFetchError("url_credentials")
    host = (parsed.hostname or "").lower()
    if not host or host not in hosts:
        raise SourceFetchError("url_host_not_approved")
    if parsed.port is not None and parsed.port != 443:
        raise SourceFetchError("url_nondefault_port")
    if not parsed.path:
        raise SourceFetchError("url_missing_path")


def _is_public_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def guard_public_destination(
    host: str,
    *,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> None:
    """Refuse destinations that resolve only to non-public addresses.

    Checked before every request and every redirect hop. Test transports
    may inject a resolver; a resolver failure is itself a safe failure.
    """
    try:
        results = resolve(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise SourceFetchError("dns_resolution_failed") from None
    if not results:
        raise SourceFetchError("dns_resolution_failed")
    public = any(_is_public_ip(item[4][0]) for item in results)
    if not public:
        raise SourceFetchError("destination_not_public")


def plan_catalog_specs(providers: tuple[str, ...]) -> list[SourceSpec]:
    """Phase-1 specs: one whole-catalog snapshot per selected provider.

    OpenAI additionally gets the pricing document and the model-docs index
    (identity/links only; per-model pages are phase 2). The ECB daily XML
    is planned by the collector only when a non-EUR proposal needs FX.
    """
    specs: list[SourceSpec] = []
    for provider in sorted(providers):
        if provider == "openrouter":
            specs.append(
                SourceSpec(
                    provider="openrouter",
                    source_kind="openrouter_models_api",
                    model="catalog",
                    url=OPENROUTER_MODELS_URL,
                    max_bytes=MAX_BODY_BYTES[("openrouter", "openrouter_models_api")],
                )
            )
        elif provider == "openai":
            specs.append(
                SourceSpec(
                    provider="openai",
                    source_kind="openai_pricing_docs",
                    model="catalog",
                    url=OPENAI_PRICING_MD_URL,
                    max_bytes=MAX_BODY_BYTES[("openai", "openai_pricing_docs")],
                )
            )
            specs.append(
                SourceSpec(
                    provider="openai",
                    source_kind="openai_models_docs",
                    model="catalog",
                    url=OPENAI_MODELS_MD_URL,
                    max_bytes=MAX_BODY_BYTES[("openai", "openai_models_docs")],
                )
            )
        else:
            raise SourceFetchError("unknown_provider")
    return specs


def model_page_spec(provider: str, model_id: str) -> SourceSpec:
    """Phase-2 spec: one official per-model doc page.

    The slug is the model ID itself (URL-quoted) — never derived from
    fetched content, so a renamed page cannot silently bind to the wrong
    model (the page's own ``Model ID:`` line must still match).
    """
    if provider != "openai":
        raise SourceFetchError("unknown_provider")
    if not _SLUG_PATTERN.fullmatch(model_id):
        raise SourceFetchError("model_page_slug_invalid")
    return SourceSpec(
        provider="openai",
        source_kind="docs_page",
        model=model_id,
        url=OPENAI_MODEL_PAGE_URL.format(slug=httpx.QueryParams({"s": model_id}).keys() and _quote_slug(model_id)),
        max_bytes=MAX_BODY_BYTES[("openai", "docs_page")],
        required=False,
    )


def _quote_slug(slug: str) -> str:
    from urllib.parse import quote

    return quote(slug, safe="")


def ecb_spec() -> SourceSpec:
    return SourceSpec(
        provider="ecb",
        source_kind="ecb_reference_xml",
        model="EUR-USD",
        url=ECB_DAILY_XML_URL,
        max_bytes=MAX_BODY_BYTES[("ecb", "ecb_reference_xml")],
    )


def _read_bounded(response: httpx.Response, cap: int) -> bytes:
    """Decode the response stream chunk by chunk; abort past the cap."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes(chunk_size=_CHUNK_SIZE):
        total += len(chunk)
        if total > cap:
            raise SourceFetchError("body_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _failed(
    spec: SourceSpec,
    *,
    current_url: str,
    last_status: int | None,
    attempts: int,
    redirects: int,
    code: str,
) -> RetrievalResult:
    return RetrievalResult(
        spec=spec,
        ok=False,
        final_url=current_url if current_url != spec.url else None,
        retrieved_at=datetime.now(UTC),
        status=last_status,
        content_type=None,
        content=None,
        attempts=attempts,
        redirects=redirects,
        failure_code=code,
    )


def fetch_source(
    client: httpx.Client,
    spec: SourceSpec,
    *,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> RetrievalResult:
    """Fetch one spec with bounded redirects, retries, and byte caps.

    Every outcome is a safe code-only result: transport errors, host
    rejections, status codes, oversized bodies and unexpected encodings
    never leak raw response bytes or exception text.
    """
    current_url = spec.url
    redirects = 0
    attempts = 0
    last_status: int | None = None
    while True:
        attempts += 1
        # The full allowlist check applies to EVERY attempted URL, including
        # each redirect target: a 3xx to another host (relative or absolute)
        # is re-validated before the next request, never blindly followed.
        try:
            validate_source_url(current_url, provider=spec.provider)
        except SourceFetchError as exc:
            return _failed(
                spec,
                current_url=current_url,
                last_status=last_status,
                attempts=attempts,
                redirects=redirects,
                code=exc.code,
            )
        try:
            guard_public_destination(
                urlparse(current_url).hostname or "", resolve=resolve
            )
        except SourceFetchError as exc:
            return _failed(
                spec,
                current_url=current_url,
                last_status=last_status,
                attempts=attempts,
                redirects=redirects,
                code=exc.code,
            )
        try:
            with client.stream(
                "GET", current_url, follow_redirects=False
            ) as response:
                last_status = response.status_code
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        return _failed(
                            spec, current_url=current_url, last_status=last_status,
                            attempts=attempts, redirects=redirects,
                            code="redirect_missing_location",
                        )
                    if redirects >= MAX_REDIRECTS:
                        return _failed(
                            spec, current_url=current_url, last_status=last_status,
                            attempts=attempts, redirects=redirects,
                            code="redirect_unbounded",
                        )
                    # Relative locations resolve against the current URL
                    # (RFC 3986); the joined URL is re-validated on the
                    # next loop iteration like every other attempt.
                    next_url = urljoin(current_url, location)
                    redirects += 1
                    current_url = next_url
                    continue
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    finite: float | None = None
                    if retry_after is not None:
                        try:
                            finite = float(retry_after)
                        except ValueError:
                            finite = None
                    if (
                        finite is not None
                        and 0 <= finite <= MAX_RETRY_AFTER_SECONDS
                        and attempts < MAX_ATTEMPTS
                    ):
                        import time

                        time.sleep(min(finite, MAX_RETRY_AFTER_SECONDS))
                        continue
                    return _failed(
                        spec, current_url=current_url, last_status=last_status,
                        attempts=attempts, redirects=redirects, code="rate_limited",
                    )
                if 500 <= response.status_code < 600:
                    if attempts < MAX_ATTEMPTS:
                        continue
                    return _failed(
                        spec, current_url=current_url, last_status=last_status,
                        attempts=attempts, redirects=redirects, code="http_5xx",
                    )
                if 200 <= response.status_code < 300:
                    encoding = (
                        response.headers.get("content-encoding") or "identity"
                    ).lower()
                    if encoding not in {"identity", "gzip", "deflate"}:
                        return _failed(
                            spec, current_url=current_url, last_status=last_status,
                            attempts=attempts, redirects=redirects,
                            code="unexpected_encoding",
                        )
                    content_type = response.headers.get("content-type")
                    if content_type is not None and len(content_type) > 256:
                        return _failed(
                            spec, current_url=current_url, last_status=last_status,
                            attempts=attempts, redirects=redirects,
                            code="header_too_large",
                        )
                    try:
                        body = _read_bounded(response, spec.max_bytes)
                    except SourceFetchError as exc:
                        return _failed(
                            spec, current_url=current_url, last_status=last_status,
                            attempts=attempts, redirects=redirects, code=exc.code,
                        )
                    return RetrievalResult(
                        spec=spec,
                        ok=True,
                        final_url=(
                            current_url if current_url != spec.url else None
                        ),
                        retrieved_at=datetime.now(UTC),
                        status=last_status,
                        content_type=(
                            content_type[:256] if content_type else None
                        ),
                        content=body,
                        attempts=attempts,
                        redirects=redirects,
                    )
                return _failed(
                    spec, current_url=current_url, last_status=last_status,
                    attempts=attempts, redirects=redirects,
                    code=f"http_{response.status_code}",
                )
        except (httpx.HTTPError, OSError):
            if attempts < MAX_ATTEMPTS:
                continue
            return _failed(
                spec, current_url=current_url, last_status=last_status,
                attempts=attempts, redirects=redirects, code="transport_error",
            )


def fetch_sources(
    specs: tuple[SourceSpec, ...],
    *,
    client: httpx.Client,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
    seen_urls: set[str] | None = None,
) -> list[RetrievalResult]:
    """Fetch all specs with collection-wide budgets and URL deduplication.

    ``seen_urls`` deduplicates shared snapshots across phases: a URL
    already fetched in this invocation is never fetched twice (the 444
    model payload is one retrieval, never one per model). Duplicate specs
    share the first retrieval's result bytes.
    """
    budget_requests = [MAX_COLLECTION_REQUESTS]
    budget_bytes = [MAX_COLLECTION_BYTES]
    seen = seen_urls if seen_urls is not None else set()
    cache: dict[str, RetrievalResult] = {}
    results: dict[str, RetrievalResult] = {}
    for spec in specs:
        if spec.url in cache:
            results[spec.url] = cache[spec.url]
            continue
        if spec.url in seen:
            # Planned but already fetched earlier in this invocation.
            raise SourceFetchError("duplicate_url_planned")
        if budget_requests[0] <= 0 or budget_bytes[0] < spec.max_bytes:
            raise SourceFetchError("collection_budget_exhausted")
        result = fetch_source(client, spec, resolve=resolve)
        cache[spec.url] = result
        results[spec.url] = result
        seen.add(spec.url)
        budget_requests[0] -= 1
        if result.ok and result.content is not None:
            budget_bytes[0] -= len(result.content)
    return [results[spec.url] for spec in specs]


def new_client() -> httpx.Client:
    """Production client: bounded timeouts, no implicit redirects."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=CONNECT_TIMEOUT, pool=CONNECT_TIMEOUT),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=MAX_CONCURRENCY, max_keepalive_connections=MAX_CONCURRENCY),
    )
