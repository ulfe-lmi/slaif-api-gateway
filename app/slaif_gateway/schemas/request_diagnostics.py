"""Safe typed schemas for the content-free request-failure diagnostics facility.

These schemas carry bounded FAILURE metadata only.  They never carry request
or response bodies, prompts, tool arguments/results, media URLs, reasoning,
replay/provider item/call IDs, HMACs, credentials, headers, queries, or raw
path variables.  Unsafe or unknown free-form values are omitted (``None``)
rather than stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

DIAGNOSTIC_STREAM_OUTCOMES = ("http_rejection", "stream_failure", "cancelled")
CLIENT_ID_UNAVAILABLE_REASONS = ("absent", "unsafe", "secret_alias")
DIAGNOSTIC_LOOKUP_BOUND = 100
DIAGNOSTIC_MAX_RECORD_BYTES = 8 * 1024


class DiagnosticsNamespace(StrEnum):
    """Which recorded ID namespace a lookup ID is resolved against."""

    ANY = "any"
    GATEWAY = "gateway"
    CLIENT = "client"


class DiagnosticLookupOutcome(StrEnum):
    """Stable typed outcomes for a diagnostics lookup."""

    FOUND = "found"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"


class DiagnosticsWriteOutcome(StrEnum):
    """Best-effort outcomes for a diagnostics write (never raised).

    ``DROPPED_CAPACITY`` is the documented drop policy: under concurrent
    writers the record is inserted only when bounded eviction (plus the
    bounded expiry prune) leaves room under the configured maximum; a writer
    that cannot make room drops its own record instead of exceeding the cap.
    """

    STORED = "stored"
    STORED_AFTER_EVICTION = "stored_after_eviction"
    DROPPED_DISABLED = "dropped_disabled"
    DROPPED_TIMEOUT = "dropped_timeout"
    DROPPED_UNAVAILABLE = "dropped_unavailable"
    DROPPED_INVALID = "dropped_invalid"
    DROPPED_CAPACITY = "dropped_capacity"


@dataclass(frozen=True, slots=True)
class RequestDiagnosticRecord:
    """One bounded, content-free recorded request failure diagnostic."""

    id: uuid.UUID
    gateway_request_id: str
    client_request_id: str | None
    client_id_unavailable_reason: str | None
    method: str
    endpoint_template: str | None
    occurred_at: datetime
    http_status: int | None
    stream_outcome: str
    source: str | None
    reason_code: str | None
    error_code: str | None
    error_param: str | None
    # Known classifier index names only (namespace_index / tool_index /
    # line / column / pos) with bounded integer values.
    positions: dict[str, int] | None
    # Closed numeric key vocabulary (count / limit / max_output_tokens /
    # max_input_tokens / context_window_tokens) with bounded integers.
    counts: dict[str, int] | None
    limits: dict[str, int] | None
    gateway_key_id: uuid.UUID | None
    route_id: uuid.UUID | None
    route_pattern: str | None
    deployment_revision: str | None
    estimated_input_tokens: int | None
    output_allowance_tokens: int | None
    context_window_tokens: int | None
    replay_error_code: str | None
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class DiagnosticDisambiguationCandidate:
    """One safe disambiguation hint inside an ambiguous lookup result."""

    gateway_request_id: str
    occurred_at: datetime
    matched_namespace: str  # "gateway" | "client"


@dataclass(frozen=True, slots=True)
class DiagnosticIdChoice:
    """One minimal safe ID choice for the diagnostics picker (211-a).

    Carries the submitted lookup value, the namespace it was observed
    in, and the time the record was written - never free-form content.
    The value is an identifier, not authority or a guaranteed match.
    """

    id: str
    namespace: str  # "gateway" | "client"
    # When the record was WRITTEN (recency for the picker ordering and
    # label); the diagnostic's occurred_at stays on the record itself.
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class DiagnosticIdChoiceResult:
    """Typed outcome of the bounded diagnostics ID-choice read (211-a).

    ``store_available=False`` is a distinct safe unavailable outcome
    (empty choices, no details) - it is not conflated with a valid
    empty match set.
    """

    choices: tuple[DiagnosticIdChoice, ...]
    cutoff: datetime
    store_available: bool = True


@dataclass(frozen=True, slots=True)
class DiagnosticLookupResult:
    """Typed lookup outcome for ``diagnostics request show``."""

    outcome: DiagnosticLookupOutcome
    namespace: DiagnosticsNamespace
    record: RequestDiagnosticRecord | None = None
    match_count: int = 0
    candidates: tuple[DiagnosticDisambiguationCandidate, ...] = ()
    overflow: bool = False
    # Fixed safe reason for ``unavailable`` (store/database), never content.
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsStatus:
    """Metadata-only status; distinguishes disabled recording, an
    unavailable store, and an empty retained dataset."""

    recording_enabled: bool
    retention_seconds: int
    max_records: int
    write_timeout_ms: int
    store_available: bool
    retained_records: int | None = None
    oldest_occurred_at: datetime | None = None
    newest_occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsCleanupResult:
    """Outcome of one bounded expired-record cleanup operation."""

    deleted_count: int
    store_available: bool
    reason: str | None = None
