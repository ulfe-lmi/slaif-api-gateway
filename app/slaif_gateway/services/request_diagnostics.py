"""Shared service for the content-free request-failure diagnostics facility.

The service is the typed boundary: it accepts only a finite set of known,
safe facts, projects them to bounded typed record fields (unsafe or unknown
free-form values become explicitly unavailable), enforces the whole-record
8 KiB serialized payload cap, and performs every write in an independent,
bounded, best-effort transaction that can never change the original request
outcome, admission, accounting, or cancellation.

Content-free projection rules (work order 201-a, privacy section):

* ``source`` / ``reason_code`` / ``error_code`` / ``replay_error_code`` must
  be members of a small, reviewed finite vocabulary (the existing shared
  classifier facts, the existing additional-tools taxonomy reasons, and the
  fixed codes emitted by the narrow observation hooks).  Anything else is
  explicitly unavailable (``None``), never stored.
* ``error_param`` must match a strict bounded path grammar (1-8 components;
  each component a lowercase identifier, an identifier with one numeric
  index, or a bare numeric index) AND the joined path must fit the 64-byte
  ``error_param`` column.  Anything else — including an overlong path made
  of only known components — is unavailable (the other failure facts are
  preserved; the whole record is never dropped).
* ``positions`` may only carry the known classifier index names
  (``namespace_index`` / ``tool_index`` / ``line`` / ``column`` / ``pos``)
  with bounded integer values.
* ``counts`` / ``limits`` may only carry the closed numeric key vocabulary
  with bounded non-negative integers.
* A complete incoming authentication secret (custom gateway prefixes,
  bearer, cookie/session, proxy credentials, X-API-Key) must never be stored
  as a client request ID, even embedded inside a larger ID.  Detection
  reuses the pure capture-redaction discovery and masking helpers, so a
  client ID equal to or containing a known secret is omitted with the fixed
  reason ``secret_alias``.

No request/response body, prompt, tool argument/result, media URL,
reasoning, provider payload, header value, or raw path variable is ever
persisted by this facility.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slaif_gateway.config import Settings
from slaif_gateway.db.models import utcnow
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.request_diagnostics import RequestDiagnosticsRepository
from slaif_gateway.schemas.request_diagnostics import (
    DIAGNOSTIC_LOOKUP_BOUND,
    DIAGNOSTIC_MAX_RECORD_BYTES,
    DIAGNOSTIC_STREAM_OUTCOMES,
    DiagnosticDisambiguationCandidate,
    DiagnosticLookupOutcome,
    DiagnosticLookupResult,
    DiagnosticIdChoice,
    DiagnosticIdChoiceResult,
    DiagnosticsCleanupResult,
    DiagnosticsNamespace,
    DiagnosticsStatus,
    DiagnosticsWriteOutcome,
    RequestDiagnosticRecord,
)
from slaif_gateway.utils.capture_redaction import (
    CaptureRedactionError,
    build_capture_masker,
    collect_incoming_secrets,
)
from slaif_gateway.utils.redaction import redact_text

# Bounded picker-search query length (server-side; matches the shared
# record-choices query bound; the endpoint refuses longer bodies).
DIAGNOSTIC_CHOICE_QUERY_MAX_LENGTH = 200
# Bounded picker hydration: at most this many retained point checks.
DIAGNOSTIC_CHOICE_SELECTED_MAX = DIAGNOSTIC_LOOKUP_BOUND

DIAGNOSTICS_SCOPE_STATE_KEY = "slaif.request_diagnostics"

# -- bounded, finite, safe patterns ------------------------------------------

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SAFE_PATTERN_RE = re.compile(r"^[A-Za-z0-9._:/{}*?-]{1,128}$")
_SAFE_METHOD_RE = re.compile(r"^[A-Z]{1,16}$")
# Safe operator revision charset (commits, tags, PEP 440/git-describe
# revisions such as ``2026.10.29-rc1+build.7``); anything else is
# recorded as unavailable rather than dropping the whole record.
_SAFE_REVISION_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")
_HTTP_STATUS_CODE_RE = re.compile(r"^[0-9]{3}$")
_PARAM_WORD_RE = re.compile(r"^[a-z_][a-z0-9_]{0,31}$")
_PARAM_INDEXED_RE = re.compile(r"^\[([0-9]{1,7})\]$")
_BARE_INDEX_RE = re.compile(r"^[0-9]{1,7}$")
_MAX_PARAM_INDEX = 1_000_000
# The error_param column is VARCHAR(64); an overlong path of known
# components must be projected to unavailable instead of making the
# PostgreSQL insert fail and dropping the whole diagnostic.
_ERROR_PARAM_MAX_LENGTH = 64

# Finite, reviewed param component vocabulary: the known path components of
# the five required failure classes and the taxonomy/schema classifier paths.
# Numeric indices (``input[3]``) are preserved; any path containing an
# unknown component is explicitly unavailable, never stored.
_KNOWN_PARAM_COMPONENTS = frozenset(
    {
        # taxonomy / client-tools paths
        "input",
        "tools",
        "function",
        "functions",
        "namespace",
        "name",
        "type",
        "role",
        "id",
        "description",
        "parameters",
        "custom",
        # route-limit rejection params
        "model",
        "instructions",
        "max_output_tokens",
        # core request fields (schema / endpoint paths)
        "content",
        "text",
        "tool_choice",
        "parallel_tool_calls",
        "previous_response_id",
        "response_format",
        "store",
        "stream",
        "stream_options",
        "metadata",
        "encrypted_content",
        "call_id",
        "output",
        "temperature",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "audio",
        "session",
        "messages",
    }
)

# -- reviewed finite vocabularies --------------------------------------------
# Unknown values become explicitly unavailable (``None``); the set is small
# and reviewed on purpose (five required failure classes, auth/schema errors,
# existing classifier and taxonomy facts).  It is NOT an exhaustive
# cross-project error catalog.

# Sources that may appear in a retained diagnostic record.
_KNOWN_SOURCES = frozenset(
    {
        "local_error",  # shared local-error classifier (api/errors.py)
        "codex_additional_tools_taxonomy",  # shared taxonomy classifier
        "chat_completions_accounting_finalization",  # existing capture source
        "responses_route_limits",  # narrow route-limit observation hook
        "responses_stream_failure",  # narrow stream-boundary observation hook
    }
)

# Existing additional-tools taxonomy reasons (codex_0162 classifier).
_TAXONOMY_REASONS = frozenset(
    {
        "additional_tools_not_a_nonempty_list",
        "namespace_name_invalid",
        "namespace_name_unapproved",
        "namespace_not_object",
        "too_many_namespaces",
        "too_many_tools_per_namespace",
        "too_many_total_tools",
        "tool_name_duplicate",
        "tool_name_not_allowed",
        "tool_not_object",
        "tool_type_invalid",
        "tools_not_a_nonempty_list",
        "unapproved_namespace_set",
    }
)

# Fixed local-classifier reasons plus the reviewed fixed codes of the five
# required failure classes (endpoint/model/capability denial, unsupported
# function tools, context rejection, replay rejection, unsupported streaming
# event after HTTP 200) and auth/schema/quota errors.
_REQUIRED_ERROR_CODES = frozenset(
    {
        # authentication / schema
        "authentication_failed",
        "invalid_authorization_scheme",
        "malformed_gateway_key",
        "missing_authorization",
        "gateway_key_invalid_digest",
        "gateway_key_revoked",
        "gateway_key_suspended",
        "gateway_key_expired",
        "gateway_key_not_found",
        "validation_error",
        # endpoint / model / capability denial
        "endpoint_not_allowed",
        "model_not_found",
        "model_not_allowed_for_key",
        "provider_not_allowed_for_key",
        "model_route_disabled",
        "responses_function_tool_capability_not_supported",
        "responses_custom_tool_capability_not_supported",
        "responses_codex_client_tools_invalid",
        "responses_codex_streaming_tool_events_not_allowed",
        # route-limit (context / output / input) rejection
        "responses_codex_limits_invalid",
        "output_token_limit_exceeded",
        "input_token_limit_exceeded",
        "responses_codex_context_window_exceeded",
        # replay rejection (actual fixed codes only; counts are never invented)
        "responses_codex_replay_reference_not_found",
        "responses_codex_replay_route_mismatch",
        "responses_codex_replay_hmac_unavailable",
        "responses_codex_replay_persistence_failed",
        # unsupported streaming event after HTTP 200 and stream failures
        "responses_stream_event_not_supported",
        "responses_stream_provider_failure",
        "streaming_live_burn_limit_exceeded",
        "responses_stream_usage_missing",
        "client_disconnected",
        # quota / rate
        "quota_limit_exceeded",
        "rate_limited",
        "request_rate_limit_exceeded",
        "token_rate_limit_exceeded",
        "concurrency_rate_limit_exceeded",
    }
)

_FIXED_LOCAL_REASONS = frozenset(
    {
        "local_rejection",
        "request_validation",
        "http_error",
        "taxonomy_rejected",
    }
)

# reason_code: fixed classifier reasons or a reviewed required code.
_KNOWN_REASON_CODES = _TAXONOMY_REASONS | _FIXED_LOCAL_REASONS | _REQUIRED_ERROR_CODES
# replay_error_code: only the fixed replay codes are genuinely known.
_KNOWN_REPLAY_ERROR_CODES = frozenset(
    {
        "responses_codex_replay_reference_not_found",
        "responses_codex_replay_route_mismatch",
        "responses_codex_replay_hmac_unavailable",
        "responses_codex_replay_persistence_failed",
    }
)

# Known classifier index names for the bounded ``positions`` object.
_KNOWN_POSITION_KEYS = frozenset({"namespace_index", "tool_index", "line", "column", "pos"})
_MAX_POSITION_VALUE = 1_000_000
# Closed numeric key vocabulary for the bounded ``counts`` / ``limits`` maps.
_KNOWN_FACT_MAP_KEYS = frozenset(
    {
        "count",
        "limit",
        "observed",
        "absolute_max_output_tokens",
        "max_output_tokens",
        "max_input_tokens",
        "context_window_tokens",
    }
)
_MAX_FACT_MAP_VALUE = 1_000_000_000

# Fields the strict scope-state projection accepts.  Unknown keys are a
# projection error at the service boundary, never stored.
_KNOWN_FACT_FIELDS = frozenset(
    {
        "gateway_request_id",
        "client_request_id",
        "method",
        "endpoint_template",
        "occurred_at",
        "http_status",
        "stream_outcome",
        "source",
        "reason_code",
        "error_code",
        "error_param",
        "positions",
        "counts",
        "limits",
        "gateway_key_id",
        "route_id",
        "route_pattern",
        "deployment_revision",
        "estimated_input_tokens",
        "output_allowance_tokens",
        "context_window_tokens",
        "replay_error_code",
        "recorded_at",
    }
)

# -- client-ID secret-alias masking bounds ------------------------------------
# The alias masker is built from bounded header-derived secrets only (never
# the body): at most 32 values, each at most 512 bytes.
_MAX_CREDENTIAL_VALUES = 32
_MAX_CREDENTIAL_BYTES = 512
_CLIENT_ID_MASK_REPLACEMENT = b"[REDACTED]"


class DiagnosticsProjectionError(ValueError):
    """Fixed-reason error for facts that cannot be safely projected.

    The message is a stable reason code; it never contains request content.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# -- ASGI scope-state channel ----------------------------------------------


def record_scope_diagnostics(scope: dict[str, Any], **fields: object) -> None:
    """Merge bounded, content-free diagnostic facts onto per-request scope.

    Only known fact fields are accepted (unknown keys are ignored so a stray
    hook can never leak content into the channel or poison the record).
    ``None`` values are ignored so multiple best-effort hooks (stream-failure
    boundaries, route facts) can contribute disjoint fields to the same
    record.  Never raises.
    """
    try:
        state = scope.setdefault("state", {})
        if not isinstance(state, dict):
            return
        current = state.get(DIAGNOSTICS_SCOPE_STATE_KEY)
        if not isinstance(current, dict):
            current = {}
        for key, value in fields.items():
            if value is not None and key in _KNOWN_FACT_FIELDS:
                current[key] = value
        state[DIAGNOSTICS_SCOPE_STATE_KEY] = current
    except Exception:  # noqa: BLE001 - observability must never affect the request
        pass


def get_scope_diagnostics(scope: dict[str, Any]) -> dict[str, Any] | None:
    """Return the merged per-request diagnostic facts, or ``None``."""
    try:
        state = scope.get("state")
        if not isinstance(state, dict):
            return None
        current = state.get(DIAGNOSTICS_SCOPE_STATE_KEY)
        return dict(current) if isinstance(current, dict) else None
    except Exception:  # noqa: BLE001 - observability must never affect the request
        return None


# -- strict projection -------------------------------------------------------


def _safe_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value in _KNOWN_SOURCES:
        return value
    return None


def _safe_reason_code(value: Any) -> str | None:
    if isinstance(value, str) and value in _KNOWN_REASON_CODES:
        return value
    return None


def _safe_error_code(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value in _REQUIRED_ERROR_CODES:
        return value
    if _HTTP_STATUS_CODE_RE.fullmatch(value):
        return value
    return None


def _safe_replay_error_code(value: Any) -> str | None:
    if isinstance(value, str) and value in _KNOWN_REPLAY_ERROR_CODES:
        return value
    return None


def _safe_param_component(component: str) -> bool:
    """Finite known component, optionally with one bounded numeric index."""
    if _BARE_INDEX_RE.fullmatch(component):
        return int(component) <= _MAX_PARAM_INDEX
    word = component
    index = None
    if component.endswith("]") and "[" in component:
        head, _, tail = component.partition("[")
        if not tail.endswith("]") or "[" in tail[:-1] or "]" in tail[:-1]:
            return False
        index = tail[:-1]
        word = head
    if not _PARAM_WORD_RE.fullmatch(word) or word not in _KNOWN_PARAM_COMPONENTS:
        return False
    if index is None:
        return True
    if not _PARAM_INDEXED_RE.fullmatch("[" + index + "]"):
        return False
    return int(index) <= _MAX_PARAM_INDEX


def _safe_error_param(value: Any) -> str | None:
    """Finite known path components within the 64-char column bound.

    Any other form — unknown components, bad indices, or an overlong joined
    path — is unavailable (``None``); the remaining failure facts survive.
    """
    if not isinstance(value, str) or not value:
        return None
    parts = value.split(".")
    if not 1 <= len(parts) <= 8:
        return None
    if any(not part or not _safe_param_component(part) for part in parts):
        return None
    if len(value) > _ERROR_PARAM_MAX_LENGTH:
        return None
    return value


def _safe_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _safe_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _safe_positions(value: Any) -> dict[str, int] | None:
    """Only the known classifier index names with bounded values."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    out: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key not in _KNOWN_POSITION_KEYS:
            continue
        number = _safe_int(item, minimum=0, maximum=_MAX_POSITION_VALUE)
        if number is not None:
            out[key] = number
    return out or None


def _safe_fact_map(value: Any) -> dict[str, int] | None:
    """Closed key vocabulary with bounded non-negative integers."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    out: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key not in _KNOWN_FACT_MAP_KEYS:
            continue
        number = _safe_int(item, minimum=0, maximum=_MAX_FACT_MAP_VALUE)
        if number is not None:
            out[key] = number
    return out or None


def build_client_id_masker(
    scope: dict[str, Any], *, accepted_prefixes: Sequence[str]
) -> tuple[Callable[[bytes], bytes] | None, bool]:
    """Build the bounded pure masker for client-ID secret-alias detection.

    Returns ``(masker_or_None, complete)``.  Reuses the pure
    capture-redaction discovery (credential headers: Authorization bearer
    plus gateway secret suffix, proxy-authorization including Bearer,
    cookies, X-API-Key and the other known credential headers; plus known
    credential query parameters from the scope query string, which is used
    in memory only and never stored) and the pure single-pass bytes masker.
    No body buffering: the scope carries headers/query only.

    Bounded to 32 values of at most 512 bytes each with a fixed replacement
    token.  When discovery is incomplete — more distinct credential values
    than the bound, a value above the size bound, or a masker construction
    error — ``complete`` is ``False`` and the caller must FAIL CLOSED (omit
    the client ID); it must never silently mask only a subset.  Values are
    never logged, stored, or returned; only the masker callable is.
    """
    try:
        headers = scope.get("headers")
        pairs: list[tuple[str, bytes]] = []
        if isinstance(headers, (list, tuple)):
            for item in headers:
                try:
                    name, value = item
                except (TypeError, ValueError):
                    continue
                if not isinstance(name, (bytes, bytearray)) or not isinstance(
                    value, (bytes, bytearray)
                ):
                    continue
                try:
                    name_text = bytes(name).decode("latin-1")
                except UnicodeDecodeError:
                    continue
                pairs.append((name_text, bytes(value)))
        query = scope.get("query_string")
        if not isinstance(query, (bytes, bytearray)):
            query = b""
        secrets, _notes, _hint = collect_incoming_secrets(
            query=bytes(query),
            headers=pairs,
            body=b"",
            accepted_prefixes=tuple(accepted_prefixes),
        )
        if len(secrets) > _MAX_CREDENTIAL_VALUES:
            return None, False  # discovery incomplete: fail closed
        chosen: list[tuple[bytes, bytes]] = []
        for secret, _hint in secrets:
            if not 0 < len(secret) <= _MAX_CREDENTIAL_BYTES:
                return None, False  # unmaskable value: fail closed
            chosen.append((bytes(secret), _CLIENT_ID_MASK_REPLACEMENT))
        if not chosen:
            return None, True
        return build_capture_masker(chosen), True
    except (CaptureRedactionError, ValueError):
        return None, False  # unsafe construction: fail closed
    except Exception:  # noqa: BLE001 - alias detection must never affect the request
        return None, False  # any discovery fault: fail closed


def _classify_client_id(
    value: str | None,
    *,
    accepted_prefixes: tuple[str, ...],
    client_id_masker: Callable[[bytes], bytes] | None,
    client_id_mask_complete: bool = True,
) -> tuple[str | None, str | None]:
    """Project a client-facing request ID to a safe stored value.

    Returns ``(safe_id, reason)``.  A complete incoming authentication
    secret can arrive as an ID or embedded inside one, so known aliases
    (custom gateway prefixes, known credential shapes detected anywhere in
    the value via the existing ``redact_text`` helpers, and any incoming
    bearer/cookie/session/proxy/query credential via the pure masker) are
    omitted with the fixed reason ``secret_alias``.  When credential
    discovery is incomplete the ID is omitted (``secret_alias``) fail
    closed; anything outside the safe ID charset is ``unsafe``; absence is
    ``absent``.
    """
    if value is None or not isinstance(value, str):
        return None, "absent"
    if not value or not _SAFE_ID_RE.fullmatch(value):
        return None, "unsafe"
    if not client_id_mask_complete:
        # Discovery was incomplete: the value cannot be proven non-secret.
        return None, "secret_alias"
    for prefix in accepted_prefixes:
        if prefix and value.startswith(prefix):
            return None, "secret_alias"
    try:
        if redact_text(value, accepted_prefixes) != value:
            return None, "secret_alias"
    except Exception:  # noqa: BLE001 - fail closed on a redaction fault
        return None, "secret_alias"
    if client_id_masker is not None:
        try:
            raw = value.encode("utf-8")
            if client_id_masker(raw) != raw:
                return None, "secret_alias"
        except Exception:  # noqa: BLE001 - fail closed on a masker fault
            return None, "secret_alias"
    return value, None


def safe_route_pattern(value: object) -> str | None:
    """Return the value when it is a safe static route pattern, else ``None``.

    Used by the narrow observation hooks so an unusual configured pattern
    never drops the whole diagnostic record; the pattern is the actual
    configured route identity, not a raw client model value.
    """
    if isinstance(value, str) and _SAFE_PATTERN_RE.fullmatch(value):
        return value[:128]
    return None


def is_safe_diagnostic_id(value: object) -> bool:
    """True only when ``value`` matches the safe diagnostic ID grammar.

    Pure syntax check (211-a GUI redisplay decisions).  A value that
    matches the grammar can STILL be a known incoming authentication
    alias (e.g. an opaque session cookie); HTTP boundaries must also
    apply :func:`is_known_incoming_secret_alias`.
    """
    return isinstance(value, str) and bool(_SAFE_ID_RE.fullmatch(value))


def is_known_incoming_secret_alias(
    value: object,
    *,
    scope: dict[str, Any],
    accepted_prefixes: Sequence[str],
) -> bool:
    """Pure, fail-closed known-secret alias check for GUI lookup/search.

    Reuses the exact pure discovery/masker helpers the diagnostic writer
    uses: accepted gateway-key prefixes, the credential-shaped
    ``redact_text`` discovery, and the bounded single-pass masker built
    from incoming Authorization/proxy-authorization/cookie/X-API-Key
    values and known credential query parameters.  Returns True when the
    value IS or EMBEDS such an alias.  When discovery is incomplete the
    value cannot be proven non-secret, so it is reported as an alias
    (fail closed).  No capture is enabled, no I/O is performed, and no
    authentication authority is involved.
    """
    text = value if isinstance(value, str) else None
    if text is None or not text:
        return False
    prefixes = tuple(accepted_prefixes)
    masker, complete = build_client_id_masker(scope, accepted_prefixes=prefixes)
    if not complete:
        return True  # discovery incomplete: cannot prove non-secret
    for prefix in prefixes:
        if prefix and text.startswith(prefix):
            return True
    try:
        if redact_text(text, prefixes) != text:
            return True
    except Exception:  # noqa: BLE001 - fail closed on a redaction fault
        return True
    if masker is not None:
        try:
            raw = text.encode("utf-8")
            if masker(raw) != raw:
                return True
        except Exception:  # noqa: BLE001 - fail closed on a masker fault
            return True
    return False


def _deployment_revision(settings: Settings) -> str | None:
    revision = getattr(settings, "REQUEST_CAPTURE_DEPLOYED_REVISION", "")
    if isinstance(revision, str) and revision and _SAFE_REVISION_RE.fullmatch(revision):
        return revision
    return None


def safe_deployment_revision(value: object) -> str | None:
    """Public safe projection of one operator-declared revision value.

    The operator-declared deployment revision and its provenance label
    are display values only: the GUI shows them when they match the
    exact safe charset the write path records, and otherwise reports
    them as unavailable. This never arms or configures capture.
    """
    if isinstance(value, str) and value and _SAFE_REVISION_RE.fullmatch(value):
        return value[:128]
    return None


def build_diagnostic_record(
    facts: Mapping[str, Any],
    *,
    settings: Settings,
    client_id_masker: Callable[[bytes], bytes] | None = None,
    client_id_mask_complete: bool = True,
) -> RequestDiagnosticRecord:
    """Strictly project known safe facts to one typed record.

    Raises :class:`DiagnosticsProjectionError` with a fixed reason on any
    unknown field, unsafe required value, missing required identity, or an
    over-cap serialized payload (the whole record, not just the facts
    columns).
    """
    unknown = set(facts) - _KNOWN_FACT_FIELDS
    if unknown:
        raise DiagnosticsProjectionError("unknown_field")

    def get(field: str) -> Any:
        return facts.get(field)

    gateway_request_id = get("gateway_request_id")
    if not isinstance(gateway_request_id, str) or not _SAFE_ID_RE.fullmatch(gateway_request_id):
        raise DiagnosticsProjectionError("missing_gateway_request_id")

    method = get("method")
    if not isinstance(method, str) or not _SAFE_METHOD_RE.fullmatch(method):
        raise DiagnosticsProjectionError("unsafe_method")

    stream_outcome = get("stream_outcome")
    if stream_outcome not in DIAGNOSTIC_STREAM_OUTCOMES:
        raise DiagnosticsProjectionError("unsafe_stream_outcome")

    occurred_at = get("occurred_at")
    if not isinstance(occurred_at, datetime):
        raise DiagnosticsProjectionError("unsafe_occurred_at")
    recorded_at = get("recorded_at")
    if not isinstance(recorded_at, datetime):
        recorded_at = utcnow()

    http_status = _safe_int(get("http_status"), minimum=100, maximum=599)

    endpoint_template = get("endpoint_template")
    if endpoint_template is not None:
        if not isinstance(endpoint_template, str) or not _SAFE_PATTERN_RE.fullmatch(endpoint_template):
            raise DiagnosticsProjectionError("unsafe_endpoint_template")
        endpoint_template = endpoint_template[:256]

    route_pattern = get("route_pattern")
    if route_pattern is not None:
        if not isinstance(route_pattern, str) or not _SAFE_PATTERN_RE.fullmatch(route_pattern):
            raise DiagnosticsProjectionError("unsafe_route_pattern")
        route_pattern = route_pattern[:128]

    try:
        accepted_prefixes = settings.get_gateway_key_accepted_prefixes()
    except Exception:  # noqa: BLE001 - fall back to the single default prefix
        accepted_prefixes = (settings.GATEWAY_KEY_PREFIX,)
    client_request_id, client_reason = _classify_client_id(
        get("client_request_id"),
        accepted_prefixes=accepted_prefixes,
        client_id_masker=client_id_masker,
        client_id_mask_complete=client_id_mask_complete,
    )

    deployment_revision = get("deployment_revision") or _deployment_revision(settings)
    if not (
        isinstance(deployment_revision, str)
        and _SAFE_REVISION_RE.fullmatch(deployment_revision)
    ):
        # An unsafe optional revision becomes explicitly unavailable; it
        # never drops the whole record.
        deployment_revision = None

    candidate = RequestDiagnosticRecord(
        id=uuid.uuid4(),
        gateway_request_id=gateway_request_id,
        client_request_id=client_request_id,
        client_id_unavailable_reason=client_reason,
        method=method,
        endpoint_template=endpoint_template,
        occurred_at=occurred_at,
        http_status=http_status,
        stream_outcome=stream_outcome,
        source=_safe_code(get("source")),
        reason_code=_safe_reason_code(get("reason_code")),
        error_code=_safe_error_code(get("error_code")),
        error_param=_safe_error_param(get("error_param")),
        positions=_safe_positions(get("positions")),
        counts=_safe_fact_map(get("counts")),
        limits=_safe_fact_map(get("limits")),
        gateway_key_id=_safe_uuid(get("gateway_key_id")),
        route_id=_safe_uuid(get("route_id")),
        route_pattern=route_pattern,
        deployment_revision=deployment_revision,
        estimated_input_tokens=_safe_int(
            get("estimated_input_tokens"), minimum=0, maximum=_MAX_FACT_MAP_VALUE
        ),
        output_allowance_tokens=_safe_int(
            get("output_allowance_tokens"), minimum=0, maximum=_MAX_FACT_MAP_VALUE
        ),
        context_window_tokens=_safe_int(
            get("context_window_tokens"), minimum=0, maximum=_MAX_FACT_MAP_VALUE
        ),
        replay_error_code=_safe_replay_error_code(get("replay_error_code")),
        recorded_at=recorded_at,
    )
    payload = _serialize_record(candidate)
    if len(payload) > DIAGNOSTIC_MAX_RECORD_BYTES:
        raise DiagnosticsProjectionError("record_over_byte_cap")
    return candidate


# Exact unique constraint for the stable server diagnostic ID (see the
# model/migration).  Only THIS constraint qualifies a conflict as a repeat.
_GATEWAY_ID_UNIQUE_CONSTRAINT = "uq_request_diagnostics_gateway_request_id"


def _is_gateway_id_repeat(exc: IntegrityError) -> bool:
    """True only for a unique violation on the gateway diagnostic ID."""
    orig = exc.orig
    if getattr(orig, "sqlstate", None) != "23505":
        return False
    constraint = getattr(orig, "constraint_name", None)
    if isinstance(constraint, str):
        return constraint == _GATEWAY_ID_UNIQUE_CONSTRAINT
    return _GATEWAY_ID_UNIQUE_CONSTRAINT in str(orig)


def _serialize_record(record: RequestDiagnosticRecord) -> bytes:
    """Canonical serialization used for the 8 KiB whole-record cap."""
    return json.dumps(
        {
            "id": str(record.id),
            "gateway_request_id": record.gateway_request_id,
            "client_request_id": record.client_request_id,
            "client_id_unavailable_reason": record.client_id_unavailable_reason,
            "method": record.method,
            "endpoint_template": record.endpoint_template,
            "occurred_at": record.occurred_at.isoformat(),
            "http_status": record.http_status,
            "stream_outcome": record.stream_outcome,
            "source": record.source,
            "reason_code": record.reason_code,
            "error_code": record.error_code,
            "error_param": record.error_param,
            "positions": record.positions,
            "counts": record.counts,
            "limits": record.limits,
            "gateway_key_id": str(record.gateway_key_id) if record.gateway_key_id else None,
            "route_id": str(record.route_id) if record.route_id else None,
            "route_pattern": record.route_pattern,
            "deployment_revision": record.deployment_revision,
            "estimated_input_tokens": record.estimated_input_tokens,
            "output_allowance_tokens": record.output_allowance_tokens,
            "context_window_tokens": record.context_window_tokens,
            "replay_error_code": record.replay_error_code,
            "recorded_at": record.recorded_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


# -- service ------------------------------------------------------------------


class RequestDiagnosticsService:
    """Bounded, best-effort diagnostics writes and typed read-only lookups."""

    _LOCK_ATTEMPTS = 3
    _LOCK_RETRY_SECONDS = 0.01

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    @property
    def recording_enabled(self) -> bool:
        return bool(self._settings.REQUEST_DIAGNOSTICS_ENABLED)

    async def record_failure(
        self,
        facts: Mapping[str, Any],
        *,
        client_id_masker: Callable[[bytes], bytes] | None = None,
        client_id_mask_complete: bool = True,
    ) -> DiagnosticsWriteOutcome:
        """Best-effort record one failure.

        Ordinary internal diagnostics failures (projection errors, write
        timeouts, store failures) become typed drop outcomes and are never
        raised to the caller.  An EXTERNALLY propagated
        ``asyncio.CancelledError`` is NOT swallowed by design: it is a
        ``BaseException`` the ``except Exception`` boundaries do not
        catch, so the surrounding task's cancellation propagates (there is
        no catch-BaseException anywhere in the write path).
        """
        if not self.recording_enabled:
            return DiagnosticsWriteOutcome.DROPPED_DISABLED
        try:
            record = build_diagnostic_record(
                facts,
                settings=self._settings,
                client_id_masker=client_id_masker,
                client_id_mask_complete=client_id_mask_complete,
            )
        except DiagnosticsProjectionError:
            return DiagnosticsWriteOutcome.DROPPED_INVALID
        except Exception:  # noqa: BLE001 - observability must never affect the request
            return DiagnosticsWriteOutcome.DROPPED_UNAVAILABLE
        timeout_seconds = max(0.01, self._settings.REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS / 1000.0)
        try:
            return await asyncio.wait_for(self._record(record), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return DiagnosticsWriteOutcome.DROPPED_TIMEOUT
        except Exception:  # noqa: BLE001 - a diagnostics failure never affects the request
            return DiagnosticsWriteOutcome.DROPPED_UNAVAILABLE

    async def _record(self, record: RequestDiagnosticRecord) -> DiagnosticsWriteOutcome:
        """One bounded capacity-enforced write (true cap under concurrency).

        Under the nonblocking transactional capacity lock (at most three
        bounded nonblocking acquisition attempts with 10 ms retry intervals,
        all inside the single configured awaited-write budget): prune a
        bounded batch of expired rows (its own phase bound), then, only if
        at or above the configured maximum, evict ``count - cap + 1`` oldest
        rows (capped by the separate per-write eviction phase bound) and
        RECOUNT.  The record is inserted only when room exists; a writer
        that still cannot make room drops its own record
        (``DROPPED_CAPACITY``) so the configured maximum is never exceeded
        by an insert, and that capacity drop COMMITS the bounded prune
        already performed without inserting.  Pre-existing excess (for
        example after an operator lowers
        ``REQUEST_DIAGNOSTICS_MAX_RECORDS`` beyond what one write's bounded
        phases clear) therefore drains across subsequent non-repeat writes,
        never by an unbounded sweep.
        Before any prune/eviction, a bounded point lookup on the unique
        stable gateway diagnostic ID converts a repeat of a retained row
        into a true idempotent no-op (``STORED``, original row unchanged),
        so a repeat at full capacity can never evict and replace the very
        row it duplicates; the unique constraint remains the race fallback
        for concurrent writers.
        """
        # Repeat-safety at capacity: a retained row for this exact stable
        # gateway diagnostic ID makes the write a true idempotent no-op.
        # The check runs under the same capacity lock, BEFORE expiry
        # pruning/oldest eviction, so a repeat can never evict (and replace)
        # the original row it is duplicating.  The DB unique constraint
        # remains the race fallback for concurrent writers.
        not_before = utcnow() - timedelta(seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS)
        async with self._session_factory() as session:
            try:
                repository = RequestDiagnosticsRepository(session)
                locked = False
                for _ in range(self._LOCK_ATTEMPTS):
                    locked = await repository.try_acquire_capacity_lock()
                    if locked:
                        break
                    await asyncio.sleep(self._LOCK_RETRY_SECONDS)
                if not locked:
                    await session.rollback()
                    return DiagnosticsWriteOutcome.DROPPED_UNAVAILABLE
                if await repository.gateway_id_exists(gateway_request_id=record.gateway_request_id):
                    return DiagnosticsWriteOutcome.STORED
                evicted = (await repository.delete_expired(not_before=not_before)) > 0
                max_records = self._settings.REQUEST_DIAGNOSTICS_MAX_RECORDS
                count = await repository.count_rows()
                if count >= max_records:
                    overflow = count - max_records + 1
                    if await repository.evict_oldest(count=overflow) > 0:
                        evicted = True
                    if await repository.count_rows() >= max_records:
                        # This is an independent, this-table-only
                        # transaction: persist the bounded prune (so the
                        # documented gradual draining actually occurs) and
                        # drop the new record instead of exceeding the cap.
                        await session.commit()
                        return DiagnosticsWriteOutcome.DROPPED_CAPACITY
                await repository.insert_row(record)
                await session.commit()
            except IntegrityError as exc:
                # The failed statement aborts this PostgreSQL transaction,
                # so roll back.  Only a unique violation on the EXACT
                # stable gateway diagnostic ID constraint is a genuine
                # idempotent repeat; a primary-key collision, any other
                # unique failure, or any CHECK failure is a bounded, safe
                # drop, never labelled as stored.
                await session.rollback()
                if _is_gateway_id_repeat(exc):
                    return DiagnosticsWriteOutcome.STORED
                return DiagnosticsWriteOutcome.DROPPED_UNAVAILABLE
            return DiagnosticsWriteOutcome.STORED_AFTER_EVICTION if evicted else DiagnosticsWriteOutcome.STORED

    async def resolve(
        self,
        lookup_id: str,
        *,
        namespace: DiagnosticsNamespace = DiagnosticsNamespace.ANY,
    ) -> DiagnosticLookupResult:
        """Resolve one lookup ID in the requested namespace (typed outcome).

        The retained row fetch is bounded (one row past the 100-candidate
        bound) and the reported match count is an exact ``COUNT`` in the same
        transaction, so ambiguity/overflow is reported honestly without
        loading an unbounded result set.
        """
        if not isinstance(lookup_id, str) or not _SAFE_ID_RE.fullmatch(lookup_id):
            # Unsafe IDs can never match a stored safe value.
            return DiagnosticLookupResult(
                outcome=DiagnosticLookupOutcome.NOT_FOUND, namespace=namespace
            )
        not_before = utcnow() - timedelta(seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS)
        try:
            async with self._session_factory() as session:
                repository = RequestDiagnosticsRepository(session)
                rows, total = await repository.lookup_retained(
                    lookup_id=lookup_id,
                    namespace=namespace,
                    not_before=not_before,
                    limit=DIAGNOSTIC_LOOKUP_BOUND + 1,
                )
        except Exception:  # noqa: BLE001 - an unavailable store is a typed outcome
            return DiagnosticLookupResult(
                outcome=DiagnosticLookupOutcome.UNAVAILABLE,
                namespace=namespace,
                reason="store_unavailable",
            )
        if not rows:
            return DiagnosticLookupResult(
                outcome=DiagnosticLookupOutcome.NOT_FOUND, namespace=namespace
            )
        if len(rows) == 1:
            return DiagnosticLookupResult(
                outcome=DiagnosticLookupOutcome.FOUND,
                namespace=namespace,
                record=rows[0],
                match_count=total,
            )
        candidates = tuple(
            DiagnosticDisambiguationCandidate(
                gateway_request_id=row.gateway_request_id,
                occurred_at=row.occurred_at,
                matched_namespace="gateway"
                if row.gateway_request_id == lookup_id
                else "client",
            )
            for row in rows[:DIAGNOSTIC_LOOKUP_BOUND]
        )
        return DiagnosticLookupResult(
            outcome=DiagnosticLookupOutcome.AMBIGUOUS,
            namespace=namespace,
            match_count=total,
            candidates=candidates,
            overflow=total > DIAGNOSTIC_LOOKUP_BOUND,
        )

    async def status(self) -> DiagnosticsStatus:
        not_before = utcnow() - timedelta(seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS)
        try:
            async with self._session_factory() as session:
                repository = RequestDiagnosticsRepository(session)
                count, oldest, newest = await repository.retained_summary(not_before=not_before)
        except Exception:  # noqa: BLE001 - an unavailable store is a typed outcome
            return DiagnosticsStatus(
                recording_enabled=self.recording_enabled,
                retention_seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS,
                max_records=self._settings.REQUEST_DIAGNOSTICS_MAX_RECORDS,
                write_timeout_ms=self._settings.REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS,
                store_available=False,
            )
        return DiagnosticsStatus(
            recording_enabled=self.recording_enabled,
            retention_seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS,
            max_records=self._settings.REQUEST_DIAGNOSTICS_MAX_RECORDS,
            write_timeout_ms=self._settings.REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS,
            store_available=True,
            retained_records=count,
            oldest_occurred_at=oldest,
            newest_occurred_at=newest,
        )

    async def cleanup(self) -> DiagnosticsCleanupResult:
        """One bounded physical prune of expired records (this table only).

        Each cleanup operation removes at most one bounded batch; repeated
        operations (or the bounded prune on writes) drain the rest.  There is
        no background expiry daemon: idle storage needs explicit cleanup.
        """
        not_before = utcnow() - timedelta(seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS)
        try:
            async with self._session_factory() as session:
                repository = RequestDiagnosticsRepository(session)
                deleted = await repository.delete_expired(not_before=not_before)
                await session.commit()
        except Exception:  # noqa: BLE001 - a cleanup failure is a typed outcome
            return DiagnosticsCleanupResult(
                deleted_count=0, store_available=False, reason="store_unavailable"
            )
        return DiagnosticsCleanupResult(deleted_count=deleted, store_available=True)

    async def cleanup_audited(
        self,
        *,
        actor_admin_user_id: uuid.UUID | None,
        reason: str,
    ) -> DiagnosticsCleanupResult:
        """One bounded physical prune PLUS its one audit, in ONE transaction.

        211-a audited operator cleanup: the delete and its single
        actor/reason/count/cutoff audit commit together or roll back
        together, so a late audit/commit failure can never leave a
        committed delete without its audit (and vice versa).  The CLI
        ``cleanup()`` above keeps its exact un-audited signature, typed
        output, and recording behavior.  A successful zero-delete action
        is audited once with the actual count 0.
        """
        not_before = utcnow() - timedelta(seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repository = RequestDiagnosticsRepository(session)
                    deleted = await repository.delete_expired(not_before=not_before)
                    await AuditRepository(session).add_audit_log(
                        action="diagnostics_expired_cleanup",
                        entity_type="request_diagnostics",
                        admin_user_id=actor_admin_user_id,
                        new_values={
                            "deleted_count": int(deleted),
                            "retention_cutoff": not_before.isoformat(),
                        },
                        note=reason,
                    )
        except Exception:  # noqa: BLE001 - a cleanup failure is a typed outcome
            return DiagnosticsCleanupResult(
                deleted_count=0, store_available=False, reason="store_unavailable"
            )
        return DiagnosticsCleanupResult(deleted_count=deleted, store_available=True)

    async def lookup_choices(
        self,
        *,
        namespace: DiagnosticsNamespace,
        query: str | None = None,
        selected: Sequence[str] = (),
    ) -> DiagnosticIdChoiceResult:
        """Bounded retained ID choices for the diagnostics picker (211-a).

        The newest retained IDs (at most :data:`DIAGNOSTIC_LOOKUP_BOUND`)
        for the requested namespace, optionally filtered by a bounded
        substring query, plus direct hydration of submitted safe selected
        IDs (older than the batch) under the SAME retention/namespace law.
        Selected IDs RESERVE their slots before the recent batch fills
        the remainder, so an explicitly selected older ID is never
        dropped by a full recent batch; the merged set is de-duplicated
        by submitted value before the final 100 cap.  Excess selected
        inputs (more than the bound after cleaning) are refused
        explicitly with a fixed reason.  Values are identifiers, not
        authority: the resolve() law still decides.  A store failure is
        a distinct safe unavailable outcome, never an empty match set.
        """
        not_before = utcnow() - timedelta(seconds=self._settings.REQUEST_DIAGNOSTICS_RETENTION_SECONDS)
        clean_query = query.strip() if isinstance(query, str) else ""
        if len(clean_query) > DIAGNOSTIC_CHOICE_QUERY_MAX_LENGTH:
            raise ValueError("choice_query_over_bound")
        stems: list[str] = []
        seen_stems: set[str] = set()
        for raw in selected:
            stem = str(raw).strip()
            if not stem or stem in seen_stems or not _SAFE_ID_RE.fullmatch(stem):
                continue
            seen_stems.add(stem)
            stems.append(stem)
        if len(stems) > DIAGNOSTIC_CHOICE_SELECTED_MAX:
            raise ValueError("choice_selected_over_bound")
        try:
            async with self._session_factory() as session:
                repository = RequestDiagnosticsRepository(session)
                # Selected (older) IDs reserve their slots first; a
                # vanished row is simply omitted (never re-timestamped).
                choices: list[DiagnosticIdChoice] = []
                seen: set[str] = set()
                for stem in stems:
                    hit = await repository.retained_choice_for(
                        lookup_id=stem,
                        namespace=namespace,
                        not_before=not_before,
                    )
                    if hit is None:
                        continue
                    tag, when = hit
                    seen.add(stem)
                    choices.append(
                        DiagnosticIdChoice(id=stem, namespace=tag, recorded_at=when)
                    )
                remaining = DIAGNOSTIC_LOOKUP_BOUND - len(choices)
                if remaining > 0:
                    recent = await repository.recent_retained_ids(
                        namespace=namespace,
                        not_before=not_before,
                        query=clean_query or None,
                        limit=remaining,
                    )
                    for value, tag, when in recent:
                        if value in seen:
                            continue
                        seen.add(value)
                        choices.append(
                            DiagnosticIdChoice(id=value, namespace=tag, recorded_at=when)
                        )
        except Exception:  # noqa: BLE001 - an unavailable store is a typed outcome
            return DiagnosticIdChoiceResult(
                choices=(), cutoff=not_before, store_available=False
            )
        choices.sort(key=lambda choice: choice.recorded_at, reverse=True)
        return DiagnosticIdChoiceResult(
            choices=tuple(choices[:DIAGNOSTIC_LOOKUP_BOUND]),
            cutoff=not_before,
            store_available=True,
        )
