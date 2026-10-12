"""Objective 181 (C2, hardened in 181-f): trusted, bounded acquisition of
authoritative sources.

This module owns the ONLY live network path of the catalog refresh
subsystem. It is deliberately narrow:

- a fixed registry of official provider/publisher source families with
  exact host AND exact path families (no arbitrary URLs, paths, queries,
  fragments, or ports from model/source text);
- HTTPS only, no credentials in URLs, default port only;
- a DNS guard that refuses loopback/private/link-local/reserved
  destinations AND mixed public/non-public answer sets (checked before
  every request, including redirects), plus connection-time vetting in
  the transport binding (``source_transport``) so the actual TCP
  connection always lands on the vetted public numeric destination with
  the original hostname, SNI, and verified certificate policy;
- manual, bounded, re-validated redirects;
- ONE collection-owned :class:`AcquisitionContext` per invocation that
  carries a finite attempt budget, a finite body-byte budget, a
  cooperative whole-invocation 120-second collection target (181-h R1,
  human-approved: application checkpoints, not an in-library hard
  bound), and the cross-phase URL outcome cache (181-f F1: no second
  fetch phase can reset any allowance; failed, interrupted, and
  overflow reads consume the byte budget and are never refunded;
  every RETURNED chunk is debited before any deadline/overflow failure,
  including chunks that arrive after the target has passed - 181-h R2);
- bounded concurrency, request count, per-body bytes (enforced on
  the returned application body stream, not Content-Length) and total
  collection bytes;
- identity-only transfer encoding (``Accept-Encoding: identity``; any
  other Content-Encoding is refused BEFORE any decoding/expansion, and
  bodies are read with ``iter_raw`` so no decoder is ever constructed);
- finite 429/Retry-After handling (the wait is bounded by the
  remaining collection target and checkpointed after the wait) and at
  most two retries on 5xx/transport failure;
- full provenance (requested/final URL, retrieval UTC time, status,
  content type, bytes, SHA-256) and safe code-only failures (never raw
  response bodies or secret-bearing exception text).

Retrieval time is never publication time. The retrieved bytes are data:
they are parsed by the registered deterministic parsers and never
executed, interpreted as HTML authority, or treated as configuration.
"""

from __future__ import annotations

import hashlib
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

# --- source registry (fixed official families) -------------------------------

USER_AGENT = "slaif-gateway-catalog-collector/181 (+https://github.com/ulfe-lmi/slaif-api-gateway)"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENAI_PRICING_MD_URL = "https://developers.openai.com/api/docs/pricing.md"
OPENAI_MODELS_MD_URL = "https://developers.openai.com/api/docs/models.md"
OPENAI_MODEL_PAGE_URL = "https://developers.openai.com/api/docs/models/{slug}.md"
ECB_DAILY_XML_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# Exact host families per publisher (suffix-free exact hosts).
OPENROUTER_HOSTS: frozenset[str] = frozenset({"openrouter.ai"})
OPENAI_HOSTS: frozenset[str] = frozenset({"openai.com", "developers.openai.com"})
ECB_HOSTS: frozenset[str] = frozenset({"www.ecb.europa.eu", "data-api.ecb.europa.eu"})

# Exact path families per (provider, source_kind). A registry URL is the
# exact family member: no query, no fragment, no credentials, no
# non-default port, no same-host path expansion (181-f F2).
OPENROUTER_MODELS_PATH = "/api/v1/models"
OPENAI_PRICING_MD_PATH = "/api/docs/pricing.md"
OPENAI_MODELS_MD_PATH = "/api/docs/models.md"
OPENAI_MODEL_DOC_PREFIX = "/api/docs/models/"
OPENAI_MODEL_DOC_SUFFIX = ".md"
ECB_DAILY_XML_PATH = "/stats/eurofxref/eurofxref-daily.xml"

_PROVIDER_HOSTS: dict[str, frozenset[str]] = {
    "openrouter": OPENROUTER_HOSTS,
    "openai": OPENAI_HOSTS,
    "ecb": ECB_HOSTS,
}

# Per-body byte caps (returned application body bytes; identity transfer, see below).
# Content-Length alone is not protection: the stream is counted chunk by
# chunk and aborted past the cap.
MAX_BODY_BYTES = {
    ("openrouter", "openrouter_models_api"): 4 * 1024 * 1024,
    ("openai", "openai_pricing_docs"): 512 * 1024,
    ("openai", "openai_models_docs"): 512 * 1024,
    ("openai", "docs_page"): 256 * 1024,
    ("ecb", "ecb_reference_xml"): 1 * 1024 * 1024,
}

# Collection-wide budgets (181-f F1: one context per invocation).
MAX_COLLECTION_REQUESTS = 128
MAX_COLLECTION_BYTES = 32 * 1024 * 1024
# Cooperative whole-invocation collection target (181-h R1,
# human-approved): application checkpoints between attempts, after every
# returned body chunk, at phase boundaries, and around the 429 retry
# wait stop BEFORE new application activity once this instant has
# passed. It is NOT a hard total elapsed bound: blocking DNS/library
# operations and a continuous slow stream can exceed it, and the
# documented operator watchdog (``timeout --kill-after=5 300``) is the
# elapsed-time cutoff for the read-only collect command.
ACQUISITION_DEADLINE_SECONDS = 120.0
MAX_CONCURRENCY = 4
MAX_REDIRECTS = 3
MAX_ATTEMPTS = 3  # initial + at most two retries (5xx/transport, or 429)
MAX_RETRY_AFTER_SECONDS = 30.0
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0
_CHUNK_SIZE = 64 * 1024
# G5 (181-g): the model-page slug is the URL-QUOTED model ID. After ONE
# decode it may be a plain ID or a namespaced ID (plain parts separated
# by single encoded slashes, e.g. ``vendor%2Fmodel``). Dot segments,
# empty parts, encoded separators that introduce traversal,
# backslash/control variants, and double/ambiguous percent-escapes are
# all refused; the fixed official path families are NOT widened.
# Part alphabet: the plain model-ID alphabet plus ":" for legitimate
# namespaced IDs (vendor/model:tag, as in the provider catalogs) - the
# first character must stay alphanumeric.
_SLUG_PART_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SLUG_MAX_PARTS = 32
_SLUG_MAX_TOTAL = 200


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


@dataclass
class AcquisitionContext:
    """One collection-owned finite budget for a whole collection run.

    181-f (F1): created ONCE before acquisition starts (by
    ``collect_bundle`` unless the caller supplies one programmatically)
    and passed through every fetch phase, redirect, and retry. A second
    ``fetch_sources`` call with the same context never resets any
    allowance.

    - ``deadline``: absolute ``time.monotonic()`` instant - the
      cooperative whole-invocation collection target (181-h R1):
      application checkpoints (before each new request, after every
      returned body chunk, at phase boundaries, and around the 429
      wait) refuse to start new activity once it has passed. It is not
      enforced inside library operations; a blocking DNS lookup or a
      continuous slow stream can exceed it (documented).
    - ``attempts_remaining``: the budget RESERVES one unit per attempted
      fetch iteration (conservatively, before pre-validation); the
      ``RetrievalResult.attempts`` metadata records only requests
      ACTUALLY sent, so rejected preflight/redirect validation is never
      counted as a sent request.
    - ``bytes_remaining``: RETURNED application body chunks on 2xx
      responses - successful reads, interrupted/failed reads, and
      overflow chunks alike. Every returned chunk is debited BEFORE any
      deadline/overflow failure (181-h R2: a chunk that arrives after
      the target has passed is still counted). Failures never refund.
    - ``cache``: one URL's success OR failure is cached across phases
      within the invocation; cached results are reused without new
      retrieval-time claims, duplicate network, or budget expenditure.

    Caller-supplied JSON never owns this context; only the collection
    (or a programmatic test/smoke caller) constructs it.
    """

    deadline: float
    attempts_remaining: int
    bytes_remaining: int
    cache: dict[str, RetrievalResult] = field(default_factory=dict)
    # G2 (181-g): once the byte budget is crossed by a consumed chunk,
    # the invocation is TERMINALLY exhausted: the crossing (and later)
    # chunks are still debited (``bytes_remaining`` goes negative - an
    # honest deficit, never a refund) and no later attempt, read, or
    # phase may use any leftover credit.
    exhausted: bool = False

    def check_deadline(self) -> None:
        if time.monotonic() >= self.deadline:
            raise SourceFetchError("acquisition_deadline_exceeded")

    def remaining_seconds(self) -> float:
        return self.deadline - time.monotonic()

    def reserve_attempt(self) -> None:
        """Reserve ONE real HTTP request; refuse past the deadline, on
        terminal exhaustion, or when no attempt budget remains
        (collection-level failure)."""
        self.check_deadline()
        if self.exhausted or self.attempts_remaining <= 0:
            raise SourceFetchError("collection_budget_exhausted")
        self.attempts_remaining -= 1

    def charge_body_bytes(self, n: int) -> None:
        """Charge consumed body bytes (no refunds).

        Every RETURNED chunk is debited BEFORE any deadline/overflow
        failure (181-h R2): a chunk that arrives after the collection
        target has passed is still counted - the consumed bytes never
        vanish - and the deadline check follows the debit. An overflow
        chunk (``n`` greater than the remaining budget) is debited in
        full (the honest deficit is kept in ``bytes_remaining``) and
        the invocation is marked terminally exhausted BEFORE the
        failure propagates, so later attempts, reads, and fetch phases
        cannot use leftover credit.
        """
        if self.exhausted:
            raise SourceFetchError("collection_budget_exhausted")
        if n > self.bytes_remaining:
            self.bytes_remaining -= n  # negative deficit, honestly kept
            self.exhausted = True
            raise SourceFetchError("collection_budget_exhausted")
        self.bytes_remaining -= n
        if self.bytes_remaining < 0:
            self.exhausted = True
        self.check_deadline()  # AFTER the debit: consumed bytes never vanish

    def cache_lookup(self, spec: SourceSpec) -> RetrievalResult | None:
        """Reuse a cached success OR failure for this URL, revalidating
        the planned spec's registry identity first."""
        cached = self.cache.get(spec.url)
        if cached is None:
            return None
        planned = (
            spec.provider,
            spec.source_kind,
            spec.model,
            spec.max_bytes,
            spec.required,
        )
        stored = (
            cached.spec.provider,
            cached.spec.source_kind,
            cached.spec.model,
            cached.spec.max_bytes,
            cached.spec.required,
        )
        if planned != stored:
            raise SourceFetchError("duplicate_url_planned")
        # Defense in depth: the cached URL must still be registry-valid.
        validate_source_url(
            spec.url, provider=spec.provider, source_kind=spec.source_kind
        )
        return cached

    def cache_store(self, spec: SourceSpec, result: RetrievalResult) -> None:
        self.cache[spec.url] = result


def new_acquisition_context(
    *,
    deadline_seconds: float = ACQUISITION_DEADLINE_SECONDS,
    max_attempts: int = MAX_COLLECTION_REQUESTS,
    max_bytes: int = MAX_COLLECTION_BYTES,
) -> AcquisitionContext:
    """Create the one collection-owned budget for this invocation."""
    return AcquisitionContext(
        deadline=time.monotonic() + deadline_seconds,
        attempts_remaining=max_attempts,
        bytes_remaining=max_bytes,
    )


def source_family_hosts(provider: str) -> frozenset[str]:
    try:
        return _PROVIDER_HOSTS[provider]
    except KeyError as exc:
        raise SourceFetchError("unknown_provider") from exc


def _validate_slug_text(raw_segment: str, decoded: str) -> None:
    """Safe slug admission for the model-page segment (181-g G5).

    ``raw_segment`` is the single path segment exactly as it appears in
    the URL (no raw ``/`` - that is checked by the caller); ``decoded``
    is its ONE-pass percent-decoding. Rules (fail closed):

    - no backslash or control character in the RAW segment;
    - no double/ambiguous percent-escape: after ONE decode the text
      must contain no ``%`` (``%25xx``-style ambiguity is refused);
    - the decoded text splits into at most ``_SLUG_MAX_PARTS`` parts on
      ``/`` (encoded separators); no empty part and no dot segment
      (``.``/``..``) - encoded traversal is refused;
    - every part matches ``_SLUG_PART_PATTERN`` (plain ID alphabet) and
      the decoded total is bounded.

    Legitimate URL-quoted model IDs - plain IDs and valid namespaced
    IDs such as ``vendor%2Fmodel`` - are preserved.
    """
    if "\\" in raw_segment or any(c < " " or c == "\x7f" for c in raw_segment):
        raise SourceFetchError("model_page_slug_invalid")
    if "%" in decoded:
        raise SourceFetchError("model_page_slug_invalid")
    if len(decoded) > _SLUG_MAX_TOTAL:
        raise SourceFetchError("model_page_slug_invalid")
    parts = decoded.split("/")
    if len(parts) > _SLUG_MAX_PARTS:
        raise SourceFetchError("model_page_slug_invalid")
    for part in parts:
        if part in ("", ".", ".."):
            raise SourceFetchError("model_page_slug_invalid")
        if not _SLUG_PART_PATTERN.fullmatch(part):
            raise SourceFetchError("model_page_slug_invalid")


def _validate_path_family(
    path: str, *, provider: str, source_kind: str | None
) -> None:
    """Exact path-family check (181-f F2).

    Only the registered path families are accepted; everything else
    (arbitrary same-host paths, traversal segments, encoded ambiguity)
    fails closed. Query and fragment are rejected by the caller before
    this runs.
    """
    if provider == "openrouter":
        if path != OPENROUTER_MODELS_PATH:
            raise SourceFetchError("url_path_not_approved")
        if source_kind not in (None, "openrouter_models_api"):
            raise SourceFetchError("url_path_kind_mismatch")
    elif provider == "openai":
        if path == OPENAI_PRICING_MD_PATH:
            if source_kind not in (None, "openai_pricing_docs"):
                raise SourceFetchError("url_path_kind_mismatch")
        elif path == OPENAI_MODELS_MD_PATH:
            if source_kind not in (None, "openai_models_docs"):
                raise SourceFetchError("url_path_kind_mismatch")
        elif (
            path.startswith(OPENAI_MODEL_DOC_PREFIX)
            and path.endswith(OPENAI_MODEL_DOC_SUFFIX)
            and len(path) > len(OPENAI_MODEL_DOC_PREFIX) + len(OPENAI_MODEL_DOC_SUFFIX)
        ):
            if source_kind not in (None, "docs_page"):
                raise SourceFetchError("url_path_kind_mismatch")
            # The single path segment is the URL-quoted model ID: a
            # legitimate registry page URL never contains a raw "/" in
            # the segment (namespaced IDs keep their separator encoded
            # as %2F), so a raw separator is path drift, not a slug -
            # reject it before any decoding. Decode ONCE, then apply
            # the safe slug admission (G5): dot segments, encoded
            # traversal, double/ambiguous escapes, and backslash or
            # control variants fail closed; valid namespaced IDs are
            # preserved.
            segment = path[
                len(OPENAI_MODEL_DOC_PREFIX) : -len(OPENAI_MODEL_DOC_SUFFIX)
            ]
            if "/" in segment:
                raise SourceFetchError("url_path_not_approved")
            _validate_slug_text(segment, unquote(segment))
        else:
            raise SourceFetchError("url_path_not_approved")
    elif provider == "ecb":
        if path != ECB_DAILY_XML_PATH:
            raise SourceFetchError("url_path_not_approved")
        if source_kind not in (None, "ecb_reference_xml"):
            raise SourceFetchError("url_path_kind_mismatch")
    else:
        raise SourceFetchError("unknown_provider")


def validate_source_url(
    url: str,
    *,
    provider: str,
    source_kind: str | None = None,
) -> None:
    """Fail-closed URL validation against the source family.

    Applied before the first request AND on every redirect hop and every
    cache reuse: HTTPS only, no credentials, exact approved host,
    default port only, no query, no fragment, and the exact registered
    path family for the provider (and source kind, when given).
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        # Malformed untrusted URL (bad authority/brackets): fail closed
        # with a safe code, never an uncaught exception or raw text.
        raise SourceFetchError("url_host_not_approved") from None
    if parsed.scheme != "https":
        raise SourceFetchError("url_not_https")
    if parsed.username is not None or parsed.password is not None:
        raise SourceFetchError("url_credentials")
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:
        # Malformed authority (e.g. broken IPv6 brackets).
        raise SourceFetchError("url_host_not_approved") from None
    if not host or host not in source_family_hosts(provider):
        raise SourceFetchError("url_host_not_approved")
    try:
        port = parsed.port
    except ValueError:
        # Nonnumeric or out-of-range port (G6): a malformed untrusted
        # port is treated like any non-default port - refused safely.
        raise SourceFetchError("url_nondefault_port") from None
    if port is not None and port != 443:
        raise SourceFetchError("url_nondefault_port")
    if not parsed.path:
        raise SourceFetchError("url_missing_path")
    if parsed.query:
        raise SourceFetchError("url_query_forbidden")
    if parsed.fragment:
        raise SourceFetchError("url_fragment_forbidden")
    _validate_path_family(parsed.path, provider=provider, source_kind=source_kind)


def guard_public_destination(
    host: str,
    *,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> tuple[str, ...]:
    """Preflight destination vetting: refuse non-global-unicast or
    MIXED answers.

    Runs before every request and every redirect hop and returns the
    vetted global-unicast numeric destinations (provenance). It is an
    early safe failure, not the binding: the ACTUAL connection is
    vetted again at connect time inside
    ``source_transport.VettedNetworkBackend`` (a preflight lookup
    followed by an independent client resolution is not a fix - the
    connect-time answer set is the one that is bound). The lookup is
    ordinary and in-process (trusted host/resolver, 181-h R1); the
    caller re-checks the collection target before the next action, so
    a slow lookup that consumes the remaining target stops all later
    network activity.
    """
    from slaif_gateway.services.catalog_refresh.source_transport import (
        vet_public_destination,
    )

    return vet_public_destination(host, resolve=resolve)


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


def _quote_slug(slug: str) -> str:
    return quote(slug, safe="")


def model_page_spec(provider: str, model_id: str) -> SourceSpec:
    """Phase-2 spec: one official per-model doc page.

    The slug is the model ID itself (URL-quoted) — never derived from
    fetched content, so a renamed page cannot silently bind to the wrong
    model (the page's own ``Model ID:`` line must still match).
    """
    if provider != "openai":
        raise SourceFetchError("unknown_provider")
    # Equivalent safe slug admission (G5) for GENERATED specs: the
    # model ID (decoded form) must pass the same rules as a supplied
    # or redirected URL, so a fetched or supplied ID cannot mint a
    # traversal or ambiguous page URL.
    _validate_slug_text(model_id, model_id)
    return SourceSpec(
        provider="openai",
        source_kind="docs_page",
        model=model_id,
        url=OPENAI_MODEL_PAGE_URL.format(slug=_quote_slug(model_id)),
        max_bytes=MAX_BODY_BYTES[("openai", "docs_page")],
        required=False,
    )


def ecb_spec() -> SourceSpec:
    return SourceSpec(
        provider="ecb",
        source_kind="ecb_reference_xml",
        model="EUR-USD",
        url=ECB_DAILY_XML_URL,
        max_bytes=MAX_BODY_BYTES[("ecb", "ecb_reference_xml")],
    )


def _read_bounded(
    response: httpx.Response,
    cap: int,
    *,
    context: AcquisitionContext,
) -> bytes:
    """Read the identity-encoded body chunk by chunk; abort past cap.

    The content-encoding header has already been checked to be absent
    or ``identity`` (anything else fails before this is reached), so
    the production live-stream path iterates the stream as returned
    (NO decoder is ever constructed and no compressed bytes are ever
    expanded). The collection target is checked COOPERATIVELY
    (181-h R1): once BEFORE the first body pull (the headers may
    already have consumed the target) and after every processed
    chunk, so the read stops before the next chunk is requested once
    a checkpoint observes expiry. A continuous slow stream between
    checkpoints can exceed the target - the per-operation read
    timeout bounds inactivity, not total elapsed time (documented
    R1 limit; no mid-stream cancellation is claimed).

    Pre-buffered responses (``httpx.Response(content=...)`` bodies, as
    produced by test mock transports - the production stream path never
    pre-buffers) are served from the exact buffered body bytes in the
    same accounting. EVERY RETURNED application body chunk is charged
    to the collection byte budget at the moment it is consumed (live
    path: per returned chunk; buffered path: per bounded buffer
    slice), BEFORE the per-spec cap check - so failed, interrupted,
    and overflow reads consume budget and are never refunded. A
    returned chunk arriving after the collection target has passed is
    still debited FIRST, and only then does the target failure
    propagate (181-h R2: the consumed bytes never vanish). The counts
    are application body chunks, not exact network/TLS/header byte
    quotas. ``Content-Length`` is never consulted.
    """
    chunks: list[bytes] = []
    total = 0

    def charge_and_check(n: int) -> None:
        nonlocal total
        context.charge_body_bytes(n)
        total += n
        if total > cap:
            raise SourceFetchError("body_too_large")

    buffered = getattr(response, "_content", None)
    if buffered is not None:
        # Pre-buffered response (httpx buffers Response(content=...)
        # bodies at construction; the production live-stream path never
        # takes this branch). The buffer holds exactly the body bytes;
        # serve it in bounded slices with the same accounting. Slice
        # sizes are limited by the REMAINING collection byte budget
        # where practical (G2): a crossing read can then exceed the
        # budget only by at most that bounded slice, and the charge
        # layer debits it and terminates the invocation.
        context.check_deadline()  # headers may have consumed the target
        i = 0
        while i < len(buffered):
            n = min(_CHUNK_SIZE, len(buffered) - i)
            if context.bytes_remaining > 0:
                n = min(n, max(1, context.bytes_remaining))
            chunk = buffered[i : i + n]
            charge_and_check(len(chunk))
            chunks.append(chunk)
            i += n
    else:
        # Live network stream: stop before the FIRST body pull if the
        # headers already consumed the collection target (181-h R1).
        context.check_deadline()
        # Every RETURNED chunk is then charged as it is consumed - the
        # debit happens BEFORE any deadline/overflow failure (181-h
        # R2), and the cooperative checkpoint after processing stops
        # the read BEFORE the next chunk is requested once the target
        # has passed.
        for raw in response.stream:
            if raw:
                charge_and_check(len(raw))
                chunks.append(raw)
            context.check_deadline()
    return b"".join(chunks)


def _failed(
    spec: SourceSpec,
    *,
    current_url: str,
    last_safe_url: str,
    last_status: int | None,
    attempts: int,
    redirects: int,
    code: str,
) -> RetrievalResult:
    """Safe-code failure result.

    G4 (181-g): ``final_url`` records only the LAST VALIDATED SAFE URL
    (the rejected raw target - e.g. one carrying credentials, query,
    or an unapproved host - never leaves the loop variable and is
    never persisted in provenance, metadata, or error text).
    """
    return RetrievalResult(
        spec=spec,
        ok=False,
        final_url=last_safe_url if last_safe_url != spec.url else None,
        retrieved_at=datetime.now(UTC),
        status=last_status,
        content_type=None,
        content=None,
        attempts=attempts,
        redirects=redirects,
        failure_code=code,
    )


def _collection_level(exc: SourceFetchError) -> bool:
    """Exhaustion of the shared budget/deadline aborts the WHOLE
    collection (no later spec can make progress); everything else is a
    per-spec safe outcome."""
    return exc.code in (
        "collection_budget_exhausted",
        "acquisition_deadline_exceeded",
    )


def _source_cause(exc: BaseException) -> SourceFetchError | None:
    """Find a SourceFetchError in the exception cause chain (the
    transport binding raises it from inside the HTTP client stack)."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, SourceFetchError):
            return current
        current = current.__cause__ or current.__context__
    return None


def fetch_source(
    client: httpx.Client,
    spec: SourceSpec,
    *,
    context: AcquisitionContext,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> RetrievalResult:
    """Fetch one spec with bounded redirects, retries, caps, and budget.

    Every outcome is a safe code-only result: transport errors, host/path
    rejections, destination vetting failures, status codes, oversized
    bodies, and unexpected encodings never leak raw response bytes or
    exception text.

    Attempt accounting (181-f F1, metadata clarified in 181-h H2): one
    REAL HTTP request sent is one recorded attempt - the initial
    request, each redirect hop, each 429 wait, and each 5xx/transport
    retry; rejected preflight/redirect validation is NOT counted as a
    sent request (the shared budget still conservatively reserves one
    unit per attempted iteration before pre-validation). The
    collection target is checkpointed at every decision point (before
    each new request, during the body read, around the 429 wait), so
    an expired target stops all later network activity (181-h R1).
    Collection-level exhaustion (attempts, bytes, target) raises out of
    this function to BLOCK the whole run; per-spec failures return.
    """
    current_url = spec.url
    # G4: the last VALIDATED SAFE URL - rejected redirect targets never
    # leave this loop variable (never persisted in provenance).
    last_safe_url = spec.url
    redirects = 0
    # Requests ACTUALLY sent (initial request, each redirect hop, each
    # 429 wait, each 5xx/transport retry): the recorded ``attempts``
    # metadata. The shared budget additionally RESERVES one unit per
    # attempted iteration before pre-validation (conservative);
    # rejected preflight/redirect validation never counts as a sent
    # request (181-h H2).
    sent = 0
    last_status: int | None = None
    while True:
        # Reserve BEFORE the request: deadline + one attempt from the
        # one shared, whole-invocation budget (conservative, pre-
        # validation).
        context.reserve_attempt()
        # The full allowlist check applies to EVERY attempted URL,
        # including each redirect target: a 3xx to another host, path
        # family, or query is re-validated before the next request,
        # never blindly followed.
        try:
            validate_source_url(
                current_url, provider=spec.provider, source_kind=spec.source_kind
            )
        except SourceFetchError as exc:
            return _failed(
                spec,
                current_url=current_url,
                last_safe_url=last_safe_url,
                last_status=last_status,
                attempts=sent,
                redirects=redirects,
                code=exc.code,
            )
        last_safe_url = current_url
        try:
            guard_public_destination(
                urlparse(current_url).hostname or "", resolve=resolve
            )
        except SourceFetchError as exc:
            # Collection-level exhaustion (deadline/budget) aborts the
            # WHOLE invocation - no per-spec masking.
            if _collection_level(exc):
                raise
            return _failed(
                spec,
                current_url=current_url,
                last_safe_url=last_safe_url,
                last_status=last_status,
                attempts=sent,
                redirects=redirects,
                code=exc.code,
            )
        # Cooperative checkpoint (181-h R1): stop BEFORE the HTTP
        # request after a slow (blocking, in-process) DNS lookup that
        # consumed the remaining collection target.
        context.check_deadline()
        # Ordinary per-operation timeouts (connect/write/pool 10 s,
        # read 30 s) are owned by the client; there is no clamped
        # per-request deadline (181-h R1).
        sent += 1
        try:
            with client.stream(
                "GET",
                current_url,
                follow_redirects=False,
            ) as response:
                last_status = response.status_code
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        return _failed(
                            spec, current_url=current_url,
                            last_safe_url=last_safe_url,
                            last_status=last_status,
                            attempts=sent, redirects=redirects,
                            code="redirect_missing_location",
                        )
                    if redirects >= MAX_REDIRECTS:
                        return _failed(
                            spec, current_url=current_url,
                            last_safe_url=last_safe_url,
                            last_status=last_status,
                            attempts=sent, redirects=redirects,
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
                        and sent < MAX_ATTEMPTS
                    ):
                        # The wait consumes the shared deadline: never
                        # sleep past it, and a deadline that expires
                        # during/after the wait stops the next attempt.
                        wait = min(
                            finite, MAX_RETRY_AFTER_SECONDS, context.remaining_seconds()
                        )
                        if wait > 0:
                            time.sleep(wait)
                        context.check_deadline()
                        continue
                    return _failed(
                        spec, current_url=current_url,
                        last_safe_url=last_safe_url,
                        last_status=last_status,
                        attempts=sent, redirects=redirects, code="rate_limited",
                    )
                if 500 <= response.status_code < 600:
                    if sent < MAX_ATTEMPTS:
                        continue
                    return _failed(
                        spec, current_url=current_url,
                        last_safe_url=last_safe_url,
                        last_status=last_status,
                        attempts=sent, redirects=redirects, code="http_5xx",
                    )
                if 200 <= response.status_code < 300:
                    # F3: identity-only transfer. Any non-identity
                    # Content-Encoding is refused BEFORE any decoding or
                    # expansion (the body stream is never read).
                    encoding = (
                        response.headers.get("content-encoding") or "identity"
                    ).lower()
                    if encoding != "identity":
                        return _failed(
                            spec, current_url=current_url,
                            last_safe_url=last_safe_url,
                            last_status=last_status,
                            attempts=sent, redirects=redirects,
                            code="unexpected_encoding",
                        )
                    content_type = response.headers.get("content-type")
                    if content_type is not None and len(content_type) > 256:
                        return _failed(
                            spec, current_url=current_url,
                            last_safe_url=last_safe_url,
                            last_status=last_status,
                            attempts=sent, redirects=redirects,
                            code="header_too_large",
                        )
                    try:
                        body = _read_bounded(
                            response, spec.max_bytes, context=context
                        )
                    except SourceFetchError as exc:
                        if _collection_level(exc):
                            raise
                        return _failed(
                            spec, current_url=current_url,
                            last_safe_url=last_safe_url,
                            last_status=last_status,
                            attempts=sent, redirects=redirects, code=exc.code,
                        )
                    return RetrievalResult(
                        spec=spec,
                        ok=True,
                        final_url=(
                            last_safe_url if last_safe_url != spec.url else None
                        ),
                        retrieved_at=datetime.now(UTC),
                        status=last_status,
                        content_type=(
                            content_type[:256] if content_type else None
                        ),
                        content=body,
                        attempts=sent,
                        redirects=redirects,
                    )
                return _failed(
                    spec, current_url=current_url,
                    last_safe_url=last_safe_url,
                    last_status=last_status,
                    attempts=sent, redirects=redirects,
                    code=f"http_{response.status_code}",
                )
        except SourceFetchError as exc:
            # Connect-time destination vetting / budget failures raised
            # from inside the transport binding.
            if _collection_level(exc):
                raise
            if sent < MAX_ATTEMPTS:
                continue
            return _failed(
                spec, current_url=current_url,
                last_safe_url=last_safe_url,
                last_status=last_status,
                attempts=sent, redirects=redirects, code=exc.code,
            )
        except (httpx.HTTPError, OSError) as exc:
            cause = _source_cause(exc)
            if cause is not None and _collection_level(cause):
                raise cause
            code = cause.code if cause is not None else "transport_error"
            if sent < MAX_ATTEMPTS:
                continue
            return _failed(
                spec, current_url=current_url,
                last_safe_url=last_safe_url,
                last_status=last_status,
                attempts=sent, redirects=redirects, code=code,
            )


def fetch_sources(
    specs: tuple[SourceSpec, ...],
    *,
    client: httpx.Client,
    context: AcquisitionContext,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> list[RetrievalResult]:
    """Fetch all specs under ONE shared acquisition context.

    The context (created before acquisition starts, 181-f F1) carries
    the finite attempt/byte budgets, the monotonic deadline, and the
    cross-phase URL outcome cache. Calling this function a second time
    with the SAME context continues the SAME invocation: no allowance is
    reset and no cached URL is fetched twice (its success OR failure is
    reused after revalidating the planned spec's registry identity).

    Before each uncached spec, the remaining budgets must cover its full
    per-body cap and at least one attempt; otherwise the collection
    fails closed (``collection_budget_exhausted``) - partial progress
    never silently continues past an un-coverable spec.
    """
    results: dict[str, RetrievalResult] = {}
    for spec in specs:
        context.check_deadline()
        cached = context.cache_lookup(spec)
        if cached is not None:
            results[spec.url] = cached
            continue
        if (
            context.exhausted
            or context.attempts_remaining < 1
            or context.bytes_remaining < spec.max_bytes
        ):
            raise SourceFetchError("collection_budget_exhausted")
        result = fetch_source(
            client, spec, context=context, resolve=resolve
        )
        context.cache_store(spec, result)
        results[spec.url] = result
    return [results[spec.url] for spec in specs]


def new_client(
    *,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> httpx.Client:
    """Production client: vetted-connection transport, identity transfer,
    bounded timeouts, no implicit redirects, no environment proxies.

    The transport binds every real TCP connection to the vetted
    global-unicast numeric destination (original hostname, SNI, and
    verified certificate policy intact) and disables environment
    proxies and other implicit network configuration
    (``trust_env=False``). Timeouts are the ordinary httpx per-
    operation values (connect/write/pool 10 s, read 30 s); the
    whole-invocation cooperation (target checkpoints, operator
    watchdog) lives in ``sources`` and the documented collect workflow
    (181-h R1).
    """
    from slaif_gateway.services.catalog_refresh.source_transport import (
        VettedHTTPTransport,
    )

    return httpx.Client(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        },
        timeout=httpx.Timeout(
            connect=CONNECT_TIMEOUT,
            read=READ_TIMEOUT,
            write=CONNECT_TIMEOUT,
            pool=CONNECT_TIMEOUT,
        ),
        follow_redirects=False,
        trust_env=False,
        transport=VettedHTTPTransport(
            resolve=resolve,
            limits=httpx.Limits(
                max_connections=MAX_CONCURRENCY,
                max_keepalive_connections=MAX_CONCURRENCY,
            ),
        ),
    )
