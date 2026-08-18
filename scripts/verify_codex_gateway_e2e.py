#!/usr/bin/env python3
"""Run the pinned Codex CLI through a real local SLAIF gateway.

This is an opt-in manual verifier. It requires an explicitly disposable
``TEST_DATABASE_URL`` and never contacts a non-loopback endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import uvicorn
from sqlalchemy import String, Text, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.base import Base
from slaif_gateway.db.models import (
    CodexReplayReference,
    GatewayKey,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, CreatedGatewayKey
from slaif_gateway.services.codex_qualification import (
    CODEX_CLI_VERSION,
    CODEX_COMPACT_ENDPOINT,
    CODEX_FIXTURE_SHA256,
    CODEX_MODEL,
    CODEX_QUALIFICATION_METADATA,
    CODEX_RESPONSES_ENDPOINT,
    CODEX_RESPONSES_POLICY,
    render_codex_profile,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
)

try:
    import capture_codex_protocol as capture
    import verify_codex_context_compaction as context_fixture
except ModuleNotFoundError:  # Imported as a namespace package by unit tests.
    from scripts import capture_codex_protocol as capture
    from scripts import verify_codex_context_compaction as context_fixture


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_BINARY = Path("/usr/bin/codex")
PROFILE_NAME = "slaif"
UPSTREAM_KEY_ENV = "SLAIF_OAP011_UPSTREAM_KEY"
DUMMY_UPSTREAM_KEY = "oap011-fixed-loopback-provider-key"
MAX_CAPTURE_BYTES = 1_000_000
MAX_CODEX_OUTPUT_BYTES = 1_000_000
SERVER_TIMEOUT_SECONDS = 30.0
SAFE_DATABASE_ERROR = "unsafe_test_database_url"
SAFE_ARGUMENT_ERROR = "invalid_arguments"
SAFE_STAGE_ERROR = "verification_failed"
SAFE_ERROR_CODES = frozenset(
    {
        SAFE_ARGUMENT_ERROR,
        SAFE_DATABASE_ERROR,
        SAFE_STAGE_ERROR,
        "cli_preflight_failed",
        "migration_failed",
        "redis_start_failed",
        "seed_failed",
        "gateway_start_failed",
        "tool_scenario_failed",
        "context_scenario_failed",
        "quota_scenario_failed",
        "interruption_scenario_failed",
        "provider_error_scenario_failed",
        "accounting_proof_failed",
        "privacy_proof_failed",
        "final_reduction_failed",
        "tool_fact_failed",
        "context_fact_failed",
        "quota_fact_failed",
        "failure_fact_failed",
        "accounting_fact_failed",
        "isolation_fact_failed",
    }
)

OUTPUT_KEYS = (
    "RESULT",
    "CLI_VERSION_MATCHED",
    "FIXTURE_DIGEST_MATCHED",
    "SCENARIO_COUNT",
    "TEXT_COMPLETION_SEEN",
    "LOCAL_EXEC_SEEN",
    "LOCAL_EDIT_SEEN",
    "WORKSPACE_MARKER_MATCHED",
    "MULTI_ROUND_REPLAY_SEEN",
    "ENCRYPTED_REASONING_REPLAY_SEEN",
    "CACHE_READ_USAGE_SEEN",
    "CACHE_WRITE_USAGE_SEEN",
    "LONG_CONTEXT_TIERS_SEEN",
    "V1_COMPACT_SEEN",
    "POST_COMPACT_CONTINUATION_SEEN",
    "QUOTA_REJECTION_SEEN",
    "QUOTA_REJECTED_BEFORE_UPSTREAM",
    "STREAM_INTERRUPTION_SEEN",
    "PROVIDER_ERROR_SEEN",
    "ACCOUNTING_MATCHED",
    "OUTSTANDING_RESERVATIONS",
    "PROVIDER_AUTH_REPLACED",
    "OUTBOUND_HEADERS_SANITIZED",
    "LOOPBACK_ONLY",
    "RAW_PAYLOADS_PERSISTED",
    "REDIS_PRIVATE_EPHEMERAL",
    "WORKSPACES_REMOVED",
    "REAL_PROVIDER_CALLED",
)


class VerificationError(RuntimeError):
    """A fixed safe failure; messages must never contain captured values."""

    def __init__(self, code: str = SAFE_STAGE_ERROR) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SafeDatabaseTarget:
    """Validated disposable PostgreSQL target without a printable representation."""

    url: str = field(repr=False)
    database_name: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MockAction:
    path: str
    kind: Literal["sse", "json", "interrupted", "error"]
    payload: object = field(repr=False)
    status_code: int = 200


@dataclass(frozen=True, slots=True)
class UpstreamRequestFacts:
    path: str
    authorization_replaced: bool
    headers_sanitized: bool
    content_encoding_absent: bool
    model_matched: bool
    input_items: tuple[dict[str, object], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class KeyAccountingFacts:
    requests_used: int
    tokens_used: int
    requests_reserved: int
    tokens_reserved: int
    pending_reservations: int
    reservation_statuses: tuple[str, ...]
    ledger_statuses: tuple[str, ...]
    ledger_successes: tuple[bool | None, ...]
    ledger_error_types: tuple[str | None, ...]
    usage: tuple[tuple[int, int, int, int, int], ...]
    component_metadata: tuple[dict[str, object], ...] = field(repr=False)


@dataclass(slots=True)
class VerificationFacts:
    cli_version_matched: bool = False
    fixture_digest_matched: bool = False
    scenario_count: int = 0
    text_completion_seen: bool = False
    local_exec_seen: bool = False
    local_edit_seen: bool = False
    workspace_marker_matched: bool = False
    multi_round_replay_seen: bool = False
    encrypted_reasoning_replay_seen: bool = False
    cache_read_usage_seen: bool = False
    cache_write_usage_seen: bool = False
    long_context_tiers_seen: bool = False
    v1_compact_seen: bool = False
    post_compact_continuation_seen: bool = False
    quota_rejection_seen: bool = False
    quota_rejected_before_upstream: bool = False
    stream_interruption_seen: bool = False
    provider_error_seen: bool = False
    accounting_matched: bool = False
    outstanding_reservations: int = -1
    provider_auth_replaced: bool = False
    outbound_headers_sanitized: bool = False
    loopback_only: bool = False
    raw_payloads_persisted: bool = True
    redis_private_ephemeral: bool = False
    workspaces_removed: bool = False
    real_provider_called: bool = False


@dataclass(slots=True)
class GatewayPeerFacts:
    """Thread-safe low-cardinality record of every request peer."""

    peers: list[str] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, host: str) -> None:
        with self._lock:
            self.peers.append(host)

    @property
    def loopback_only(self) -> bool:
        with self._lock:
            return bool(self.peers) and all(host == "127.0.0.1" for host in self.peers)


def parse_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    """Parse the intentionally argument-free manual interface."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--help", action="store_true")
    namespace, extras = parser.parse_known_args(arguments)
    if namespace.help or extras:
        raise VerificationError(SAFE_ARGUMENT_ERROR)
    return namespace


def validate_test_database_url(value: str | None) -> SafeDatabaseTarget:
    """Require a numeric-loopback disposable PostgreSQL database URL."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise VerificationError(SAFE_DATABASE_ERROR)
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql", "postgres"}:
        raise VerificationError(SAFE_DATABASE_ERROR)
    if parsed.hostname != "127.0.0.1":
        raise VerificationError(SAFE_DATABASE_ERROR)
    database_name = parsed.path.removeprefix("/")
    lowered = database_name.lower()
    if (
        not database_name
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in database_name
        )
        or not any(marker in lowered for marker in ("test", "dev", "local"))
    ):
        raise VerificationError(SAFE_DATABASE_ERROR)
    query = parsed.query.lower()
    if "sslmode=require" in query or parsed.fragment:
        raise VerificationError(SAFE_DATABASE_ERROR)
    return SafeDatabaseTarget(url=value, database_name=database_name)


def fixed_error_output(code: str) -> str:
    """Return a bounded failure without reflecting operator or captured data."""

    safe_code = code if code in SAFE_ERROR_CODES else SAFE_STAGE_ERROR
    return f"RESULT=FAIL\nERROR_CODE={safe_code}\nREAL_PROVIDER_CALLED=false\n"


@contextmanager
def safe_stage(code: str) -> Iterator[None]:
    """Reduce any failure to one reviewed low-cardinality stage code."""

    if code not in SAFE_ERROR_CODES:
        raise VerificationError(SAFE_STAGE_ERROR)
    try:
        yield
    except VerificationError as exc:
        if exc.code != SAFE_STAGE_ERROR:
            raise
        raise VerificationError(code) from exc
    except Exception as exc:
        raise VerificationError(code) from exc


def fixed_success_output(facts: VerificationFacts) -> str:
    """Render only the fixed low-cardinality success contract."""

    values: dict[str, object] = {
        "RESULT": "OK",
        "CLI_VERSION_MATCHED": facts.cli_version_matched,
        "FIXTURE_DIGEST_MATCHED": facts.fixture_digest_matched,
        "SCENARIO_COUNT": facts.scenario_count,
        "TEXT_COMPLETION_SEEN": facts.text_completion_seen,
        "LOCAL_EXEC_SEEN": facts.local_exec_seen,
        "LOCAL_EDIT_SEEN": facts.local_edit_seen,
        "WORKSPACE_MARKER_MATCHED": facts.workspace_marker_matched,
        "MULTI_ROUND_REPLAY_SEEN": facts.multi_round_replay_seen,
        "ENCRYPTED_REASONING_REPLAY_SEEN": facts.encrypted_reasoning_replay_seen,
        "CACHE_READ_USAGE_SEEN": facts.cache_read_usage_seen,
        "CACHE_WRITE_USAGE_SEEN": facts.cache_write_usage_seen,
        "LONG_CONTEXT_TIERS_SEEN": facts.long_context_tiers_seen,
        "V1_COMPACT_SEEN": facts.v1_compact_seen,
        "POST_COMPACT_CONTINUATION_SEEN": facts.post_compact_continuation_seen,
        "QUOTA_REJECTION_SEEN": facts.quota_rejection_seen,
        "QUOTA_REJECTED_BEFORE_UPSTREAM": facts.quota_rejected_before_upstream,
        "STREAM_INTERRUPTION_SEEN": facts.stream_interruption_seen,
        "PROVIDER_ERROR_SEEN": facts.provider_error_seen,
        "ACCOUNTING_MATCHED": facts.accounting_matched,
        "OUTSTANDING_RESERVATIONS": facts.outstanding_reservations,
        "PROVIDER_AUTH_REPLACED": facts.provider_auth_replaced,
        "OUTBOUND_HEADERS_SANITIZED": facts.outbound_headers_sanitized,
        "LOOPBACK_ONLY": facts.loopback_only,
        "RAW_PAYLOADS_PERSISTED": facts.raw_payloads_persisted,
        "REDIS_PRIVATE_EPHEMERAL": facts.redis_private_ephemeral,
        "WORKSPACES_REMOVED": facts.workspaces_removed,
        "REAL_PROVIDER_CALLED": facts.real_provider_called,
    }
    if tuple(values) != OUTPUT_KEYS:
        raise VerificationError(SAFE_STAGE_ERROR)
    return "".join(f"{key}={_output_value(value)}\n" for key, value in values.items())


def _output_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if value == "OK":
        return "OK"
    raise VerificationError(SAFE_STAGE_ERROR)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _sse(events: Sequence[Mapping[str, object]]) -> bytes:
    body = "".join(
        f"event: {event['type']}\ndata: "
        f"{json.dumps(event, sort_keys=True, separators=(',', ':'))}\n\n"
        for event in events
    ).encode("utf-8")
    if len(body) > MAX_CAPTURE_BYTES:
        raise VerificationError(SAFE_STAGE_ERROR)
    return body


def _deep_replace(value: object, replacements: Mapping[str, str]) -> object:
    if isinstance(value, str):
        result = value
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
    if isinstance(value, list):
        return [_deep_replace(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(_deep_replace(item, replacements) for item in value)
    if isinstance(value, dict):
        return {key: _deep_replace(item, replacements) for key, item in value.items()}
    return value


def _usage(
    input_tokens: int,
    *,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 1,
    reasoning_tokens: int = 0,
) -> dict[str, object]:
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
        "total_tokens": input_tokens + output_tokens,
    }


def _tool_events(
    *, item_id: str, call_id: str, source: str, output_index: int = 0
) -> tuple[dict[str, object], ...]:
    return (
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {
                "type": "custom_tool_call",
                "id": item_id,
                "status": "in_progress",
                "namespace": "functions",
                "name": "exec",
                "call_id": call_id,
                "input": "",
            },
        },
        {
            "type": "response.custom_tool_call_input.delta",
            "output_index": output_index,
            "item_id": item_id,
            "call_id": call_id,
            "delta": source,
        },
        {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": {
                "type": "custom_tool_call",
                "id": item_id,
                "status": "completed",
                "namespace": "functions",
                "name": "exec",
                "call_id": call_id,
                "input": source,
            },
        },
    )


def _completed_events(
    response_id: str, message_id: str, final_text: str
) -> tuple[dict[str, object], ...]:
    return (
        {"type": "response.created", "response": {"id": response_id}},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "message",
                "id": message_id,
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        },
        {
            "type": "response.output_text.delta",
            "item_id": message_id,
            "output_index": 0,
            "content_index": 0,
            "delta": final_text,
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "message",
                "id": message_id,
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": final_text}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "status": "completed",
                "usage": _usage(1),
            },
        },
    )


def build_tool_scenario_actions(
    *, workspace: Path, marker_content: str, encrypted_content: str, final_text: str
) -> tuple[MockAction, ...]:
    """Build one shell call, one patch call, encrypted replay, and final text."""

    marker_name = "oap011-marker.txt"
    exec_source = (
        'const r = await tools.exec_command({cmd:"pwd",workdir:'
        + json.dumps(str(workspace))
        + '}); text("EXEC_OK");'
    )
    patch_text = (
        "*** Begin Patch\n*** Add File: " + marker_name + "\n+" + marker_content + "\n*** End Patch"
    )
    edit_source = (
        "const r = await tools.apply_patch(" + json.dumps(patch_text) + '); text("EDIT_OK");'
    )
    first_id = "resp_oap011_tool_1"
    second_id = "resp_oap011_tool_2"
    reasoning_id = "rs_oap011_tool_replay"
    first = (
        {"type": "response.created", "response": {"id": first_id}},
        *_tool_events(
            item_id="ctc_oap011_exec",
            call_id="call_oap011_exec",
            source=exec_source,
        ),
        {
            "type": "response.completed",
            "response": {"id": first_id, "status": "completed", "usage": _usage(1)},
        },
    )
    reasoning_item = {
        "type": "reasoning",
        "id": reasoning_id,
        "summary": [],
        "encrypted_content": encrypted_content,
    }
    second = (
        {"type": "response.created", "response": {"id": second_id}},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "reasoning", "id": reasoning_id, "summary": []},
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": reasoning_item,
        },
        *_tool_events(
            item_id="ctc_oap011_edit",
            call_id="call_oap011_edit",
            source=edit_source,
            output_index=1,
        ),
        {
            "type": "response.completed",
            "response": {"id": second_id, "status": "completed", "usage": _usage(1)},
        },
    )
    third = _completed_events("resp_oap011_tool_3", "msg_oap011_tool_final", final_text)
    return tuple(MockAction("/v1/responses", "sse", events) for events in (first, second, third))


def build_context_scenario_actions(
    *, marker: str, encrypted_content: str
) -> tuple[MockAction, ...]:
    """Carry the objective-009 three-tier V1-compaction fixture through SLAIF."""

    replacements = {
        context_fixture.COMPACTION_VALUE: encrypted_content,
        "SLAIF_CODEX_CONTEXT_COMPACTION_OK": marker,
        "SAFE_CONTEXT_COMPACTION": marker,
    }
    first = _deep_replace(copy.deepcopy(context_fixture.FIRST_EVENTS), replacements)
    compact = json.loads(context_fixture.COMPACT_BODY)
    compact = _deep_replace(compact, replacements)
    final = _deep_replace(copy.deepcopy(context_fixture.FINAL_EVENTS), replacements)
    assert isinstance(first, tuple) and isinstance(compact, dict) and isinstance(final, tuple)
    return (
        MockAction("/v1/responses", "sse", first),
        MockAction("/v1/responses/compact", "json", compact),
        MockAction("/v1/responses", "sse", final),
    )


class ScriptedOpenAIMock:
    """Bounded numeric-loopback HTTP server with an explicit response queue."""

    def __init__(self) -> None:
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._actions: list[MockAction] = []
        self._facts: list[UpstreamRequestFacts] = []
        self.error: VerificationError | None = None
        self.port: int | None = None
        self.loopback_only = True

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        listener.settimeout(0.1)
        host, port = listener.getsockname()
        if host != "127.0.0.1":
            listener.close()
            raise VerificationError(SAFE_STAGE_ERROR)
        self._listener = listener
        self.port = int(port)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def queue(self, actions: Sequence[MockAction]) -> int:
        with self._lock:
            if self._actions:
                raise VerificationError(SAFE_STAGE_ERROR)
            start = len(self._facts)
            self._actions.extend(actions)
            return start

    def facts_since(self, start: int, expected: int) -> tuple[UpstreamRequestFacts, ...]:
        deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.error is not None:
                raise self.error
            with self._lock:
                facts = tuple(self._facts[start:])
                pending = len(self._actions)
            if len(facts) == expected and pending == 0:
                return facts
            time.sleep(0.02)
        raise VerificationError(SAFE_STAGE_ERROR)

    @property
    def request_count(self) -> int:
        with self._lock:
            return len(self._facts)

    def _serve(self) -> None:
        assert self._listener is not None
        while not self._stop.is_set():
            try:
                connection, peer = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                if peer[0] != "127.0.0.1":
                    self.loopback_only = False
                    self.error = VerificationError(SAFE_STAGE_ERROR)
                    return
                try:
                    raw = capture._read_bounded_request(connection)
                    if len(raw) > MAX_CAPTURE_BYTES:
                        raise VerificationError(SAFE_STAGE_ERROR)
                    request = capture._parse_http_request(raw)
                    with self._lock:
                        if not self._actions:
                            raise VerificationError(SAFE_STAGE_ERROR)
                        action = self._actions.pop(0)
                    facts = self._reduce_request(request, expected_path=action.path)
                    with self._lock:
                        self._facts.append(facts)
                    self._respond(connection, action)
                    del raw, request
                except Exception:
                    self.error = VerificationError(SAFE_STAGE_ERROR)
                    return

    def _reduce_request(
        self, request: capture.ParsedHttpRequest, *, expected_path: str
    ) -> UpstreamRequestFacts:
        if request.method != "POST" or request.target != expected_path:
            raise VerificationError(SAFE_STAGE_ERROR)
        headers = {name.lower(): value for name, value in request.headers}
        authorization = headers.get("authorization")
        forbidden_headers = {
            "cookie",
            "set-cookie",
            "x-admin-token",
            "x-internal-auth",
            "x-forwarded-authorization",
        }
        headers_sanitized = not forbidden_headers.intersection(headers)
        if authorization != f"Bearer {DUMMY_UPSTREAM_KEY}" or not headers_sanitized:
            raise VerificationError(SAFE_STAGE_ERROR)
        try:
            body = json.loads(request.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError(SAFE_STAGE_ERROR) from exc
        if not isinstance(body, dict) or body.get("model") != CODEX_MODEL:
            raise VerificationError(SAFE_STAGE_ERROR)
        input_value = body.get("input")
        input_items = (
            tuple(item for item in input_value if isinstance(item, dict))
            if isinstance(input_value, list)
            else ()
        )
        del body
        return UpstreamRequestFacts(
            path=request.target,
            authorization_replaced=True,
            headers_sanitized=headers_sanitized,
            content_encoding_absent="content-encoding" not in headers,
            model_matched=True,
            input_items=input_items,
        )

    @staticmethod
    def _respond(connection: socket.socket, action: MockAction) -> None:
        if action.kind == "sse":
            if not isinstance(action.payload, (tuple, list)):
                raise VerificationError(SAFE_STAGE_ERROR)
            body = _sse(action.payload)
            content_type = b"text/event-stream"
        elif action.kind == "json":
            body = json.dumps(action.payload, sort_keys=True, separators=(",", ":")).encode()
            content_type = b"application/json"
        elif action.kind == "error":
            body = json.dumps(action.payload, sort_keys=True, separators=(",", ":")).encode()
            content_type = b"application/json"
        elif action.kind == "interrupted":
            body = _sse(action.payload if isinstance(action.payload, (tuple, list)) else ())
            header = b"\r\n".join(
                (
                    b"HTTP/1.1 200 OK",
                    b"Content-Type: text/event-stream",
                    b"Transfer-Encoding: chunked",
                    b"Connection: close",
                    b"",
                    f"{len(body):x}\r\n".encode() + body + b"\r\n",
                )
            )
            connection.sendall(header)
            return
        else:
            raise VerificationError(SAFE_STAGE_ERROR)
        reason = b"OK" if action.status_code < 400 else b"Too Many Requests"
        response = b"\r\n".join(
            (
                f"HTTP/1.1 {action.status_code} ".encode() + reason,
                b"Content-Type: " + content_type,
                b"X-Request-ID: oap011-loopback",
                f"Content-Length: {len(body)}".encode(),
                b"Connection: close",
                b"",
                body,
            )
        )
        connection.sendall(response)

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2)


@contextmanager
def private_redis() -> Iterator[tuple[str, subprocess.Popen[bytes]]]:
    """Start a no-persistence Redis child bound only to numeric loopback."""

    port = _free_loopback_port()
    with tempfile.TemporaryDirectory(prefix="slaif-oap011-redis-") as directory:
        command = [
            "redis-server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--dir",
            directory,
            "--save",
            "",
            "--appendonly",
            "no",
            "--protected-mode",
            "yes",
            "--daemonize",
            "no",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise VerificationError(SAFE_STAGE_ERROR) from exc
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = subprocess.run(
                    ["redis-cli", "-h", "127.0.0.1", "-p", str(port), "ping"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
                if result.stdout.strip() == b"PONG":
                    break
                if process.poll() is not None:
                    raise VerificationError(SAFE_STAGE_ERROR)
                time.sleep(0.05)
            else:
                raise VerificationError(SAFE_STAGE_ERROR)
            yield f"redis://127.0.0.1:{port}/0", process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@contextmanager
def gateway_server(settings: Settings) -> Iterator[tuple[int, GatewayPeerFacts]]:
    """Serve the real app on one ephemeral numeric-loopback port."""

    from slaif_gateway.main import create_app

    app = create_app(settings)
    peer_facts = GatewayPeerFacts()

    @app.middleware("http")
    async def record_verifier_peer(request, call_next):
        client = request.client
        peer_facts.record(client.host if client is not None else "")
        return await call_next(request)

    port = _free_loopback_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
            lifespan="on",
            timeout_keep_alive=1,
        )
    )
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise VerificationError(SAFE_STAGE_ERROR)
            time.sleep(0.05)
        yield port, peer_facts
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        if thread.is_alive():
            raise VerificationError(SAFE_STAGE_ERROR)


def _gateway_settings(database_url: str, redis_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        REDIS_URL=redis_url,
        ENABLE_REDIS_RATE_LIMITS=True,
        RATE_LIMIT_FAIL_CLOSED=True,
        GATEWAY_KEY_PREFIX="sk-slaif-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="oap011-fixed-hmac-secret-with-safe-length",
        ADMIN_SESSION_SECRET="oap011-fixed-admin-secret-with-safe-length",
        ONE_TIME_SECRET_ENCRYPTION_KEY=("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"),
        ENABLE_EMAIL_DELIVERY=False,
        ENABLE_SCHEDULED_RECONCILIATION=False,
        ENABLE_METRICS=False,
        STRUCTURED_LOGS=False,
    )


def migrate_database(target: SafeDatabaseTarget) -> None:
    """Apply migrations only after the target passes the strict disposable check."""

    from alembic import command
    from alembic.config import Config

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", target.url)
    try:
        command.upgrade(config, "head")
    except Exception as exc:
        raise VerificationError(SAFE_STAGE_ERROR) from exc


def _route_capabilities(companion_id: uuid.UUID) -> dict[str, object]:
    responses = default_responses_capabilities()
    responses.update(
        {
            "text": True,
            "stateless": True,
            "streaming": True,
            "compact": True,
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": True,
            "codex_compaction": True,
        }
    )
    return {
        "responses": responses,
        "codex_limits": {
            "context_window_tokens": 1_050_000,
            "default_max_output_tokens": 32_768,
            "max_output_tokens": 128_000,
        },
        "codex_compaction_compatible_route_ids": [str(companion_id)],
        "codex_qualification": copy.deepcopy(CODEX_QUALIFICATION_METADATA),
    }


async def seed_gateway(
    *, database_url: str, mock_port: int, settings: Settings
) -> dict[str, CreatedGatewayKey]:
    """Seed only verifier-owned rows using current repositories and KeyService."""

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = secrets.token_hex(8)
    try:
        async with session_factory() as session:
            institution = await InstitutionsRepository(session).create_institution(
                name=f"Reserved OAP011 verifier {suffix}",
                country="SI",
                notes="Disposable local verifier identity",
            )
            owner = await OwnersRepository(session).create_owner(
                name="Reserved",
                surname="Verifier",
                email=f"oap011-{suffix}@example.invalid",
                institution_id=institution.id,
                notes="Disposable local verifier owner",
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"oap011-{suffix}",
                description="Disposable local verifier cohort",
                starts_at=now - timedelta(minutes=5),
                ends_at=now + timedelta(hours=2),
            )
            await ProviderConfigsRepository(session).create_provider_config(
                provider="openai",
                display_name="OpenAI loopback verifier",
                base_url=f"http://127.0.0.1:{mock_port}/v1",
                api_key_env_var=UPSTREAM_KEY_ENV,
                enabled=True,
                timeout_seconds=10,
                max_retries=0,
                notes="Numeric-loopback scripted verifier only",
            )
            routes = ModelRoutesRepository(session)
            responses_route = await routes.create_model_route(
                requested_model=CODEX_MODEL,
                provider="openai",
                upstream_model=CODEX_MODEL,
                match_type="exact",
                endpoint=CODEX_RESPONSES_ENDPOINT,
                priority=1,
                enabled=True,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={},
                notes="OAP011 disposable Responses route",
            )
            compact_route = await routes.create_model_route(
                requested_model=CODEX_MODEL,
                provider="openai",
                upstream_model=CODEX_MODEL,
                match_type="exact",
                endpoint=CODEX_COMPACT_ENDPOINT,
                priority=1,
                enabled=True,
                visible_in_models=False,
                supports_streaming=False,
                capabilities={},
                notes="OAP011 disposable compact route",
            )
            await routes.update_model_route_metadata(
                responses_route.id,
                capabilities=_route_capabilities(compact_route.id),
            )
            await routes.update_model_route_metadata(
                compact_route.id,
                capabilities=_route_capabilities(responses_route.id),
            )
            pricing = PricingRulesRepository(session)
            pricing_metadata = {
                "codex_accounting": {
                    "long_context_threshold_tokens": 272_000,
                    "long_context_input_multiplier": "2",
                    "long_context_output_multiplier": "1.5",
                    "cache_write_input_multiplier": "1.25",
                }
            }
            for endpoint in (CODEX_RESPONSES_ENDPOINT, CODEX_COMPACT_ENDPOINT):
                await pricing.create_pricing_rule(
                    provider="openai",
                    upstream_model=CODEX_MODEL,
                    endpoint=endpoint,
                    valid_from=now - timedelta(minutes=5),
                    currency="EUR",
                    input_price_per_1m=Decimal("1"),
                    cached_input_price_per_1m=Decimal("0.5"),
                    output_price_per_1m=Decimal("2"),
                    reasoning_price_per_1m=Decimal("2"),
                    request_price=Decimal("0"),
                    pricing_metadata=pricing_metadata,
                    notes="OAP011 deterministic local pricing",
                )
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
                model_routes_repository=routes,
            )
            keys: dict[str, CreatedGatewayKey] = {}
            for name, request_limit, token_limit in (
                ("tool", 10, 2_000_000),
                ("context", 10, 2_000_000),
                ("quota", 1, 2_000_000),
                ("interruption", 2, 2_000_000),
                ("provider_error", 2, 2_000_000),
            ):
                keys[name] = await key_service.create_gateway_key(
                    CreateGatewayKeyInput(
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        valid_from=now - timedelta(minutes=1),
                        valid_until=now + timedelta(hours=1),
                        cost_limit_eur=Decimal("20"),
                        token_limit_total=token_limit,
                        request_limit_total=request_limit,
                        allowed_models=[CODEX_MODEL],
                        allowed_endpoints=[
                            "/v1/models",
                            CODEX_RESPONSES_ENDPOINT,
                            CODEX_COMPACT_ENDPOINT,
                        ],
                        allowed_providers=["openai"],
                        responses_policy=copy.deepcopy(CODEX_RESPONSES_POLICY),
                        rate_limit_policy={
                            "requests_per_minute": 100,
                            "tokens_per_minute": 5_000_000,
                            "max_concurrent_requests": 1,
                            "window_seconds": 60,
                        },
                        note=f"OAP011 disposable {name} verifier key",
                    )
                )
            await session.commit()
            return keys
    except Exception as exc:
        raise VerificationError(SAFE_STAGE_ERROR) from exc
    finally:
        await engine.dispose()


def _profile_environment(codex_home: Path, gateway_key: str) -> dict[str, str]:
    dead_proxy = "http://127.0.0.1:9"
    return {
        "ALL_PROXY": dead_proxy,
        "CODEX_HOME": str(codex_home),
        "HOME": str(codex_home),
        "HTTPS_PROXY": dead_proxy,
        "HTTP_PROXY": dead_proxy,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "127.0.0.1",
        "OPENAI_API_KEY": gateway_key,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "RUST_BACKTRACE": "0",
        "XDG_CACHE_HOME": str(codex_home / "cache"),
        "XDG_CONFIG_HOME": str(codex_home / "config"),
        "XDG_DATA_HOME": str(codex_home / "data"),
        "all_proxy": dead_proxy,
        "http_proxy": dead_proxy,
        "https_proxy": dead_proxy,
        "no_proxy": "127.0.0.1",
    }


def build_codex_command(*, workdir: Path, prompt: str, sandbox: str) -> list[str]:
    """Select only the generated named profile; never override model/provider."""

    return [
        str(CODEX_BINARY),
        "--ask-for-approval",
        "never",
        "--profile",
        PROFILE_NAME,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        sandbox,
        "--cd",
        str(workdir),
        "-c",
        "check_for_update_on_startup=false",
        "-c",
        'model_reasoning_effort="low"',
        "-c",
        'model_verbosity="low"',
        "-c",
        "model_providers.slaif.request_max_retries=0",
        "-c",
        "model_providers.slaif.stream_max_retries=0",
        "-c",
        "model_providers.slaif.stream_idle_timeout_ms=5000",
        prompt,
    ]


def run_codex(
    *, gateway_port: int, gateway_key: str, prompt: str, sandbox: str
) -> tuple[subprocess.CompletedProcess[bytes], Path, Path]:
    """Run one actual pinned Codex child in private profile/workspace roots."""

    root = Path(tempfile.mkdtemp(prefix="slaif-oap011-codex-"))
    codex_home = root / "codex-home"
    workspace = root / "workspace"
    codex_home.mkdir(mode=0o700)
    workspace.mkdir(mode=0o700)
    artifacts = render_codex_profile(f"http://127.0.0.1:{gateway_port}/v1")
    (codex_home / "config.toml").write_text(artifacts.base_config_toml, encoding="utf-8")
    (codex_home / "slaif.config.toml").write_text(artifacts.profile_config_toml, encoding="utf-8")
    (codex_home / "config.toml").chmod(0o600)
    (codex_home / "slaif.config.toml").chmod(0o600)
    (codex_home / "config.toml").chmod(0o600)
    (codex_home / "slaif.config.toml").chmod(0o600)
    try:
        result = subprocess.run(
            build_codex_command(workdir=workspace, prompt=prompt, sandbox=sandbox),
            check=False,
            capture_output=True,
            env=_profile_environment(codex_home, gateway_key),
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _remove_private_root(root)
        raise VerificationError(SAFE_STAGE_ERROR) from exc
    if len(result.stdout) > MAX_CODEX_OUTPUT_BYTES or len(result.stderr) > MAX_CODEX_OUTPUT_BYTES:
        _remove_private_root(root)
        raise VerificationError(SAFE_STAGE_ERROR)
    return result, workspace, root


def _remove_private_root(root: Path) -> None:
    """Remove only an explicitly generated verifier root."""

    import shutil

    if not root.name.startswith("slaif-oap011-codex-") or root.parent != Path("/tmp"):
        raise VerificationError(SAFE_STAGE_ERROR)
    shutil.rmtree(root)


def _codex_completed(result: subprocess.CompletedProcess[bytes]) -> bool:
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed":
            return True
    return False


def _contains_replay_item(
    facts: UpstreamRequestFacts, *, kind: str, item_id: str | None = None
) -> bool:
    return any(
        item.get("type") == kind and (item_id is None or item.get("id") == item_id)
        for item in facts.input_items
    )


async def load_accounting(database_url: str, gateway_key_id: uuid.UUID) -> KeyAccountingFacts:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            key = await session.get(GatewayKey, gateway_key_id)
            if key is None:
                raise VerificationError(SAFE_STAGE_ERROR)
            reservations = list(
                (
                    await session.execute(
                        select(QuotaReservation)
                        .where(QuotaReservation.gateway_key_id == gateway_key_id)
                        .order_by(QuotaReservation.created_at)
                    )
                ).scalars()
            )
            ledgers = list(
                (
                    await session.execute(
                        select(UsageLedger)
                        .where(UsageLedger.gateway_key_id == gateway_key_id)
                        .order_by(UsageLedger.created_at)
                    )
                ).scalars()
            )
            return KeyAccountingFacts(
                requests_used=int(key.requests_used_total),
                tokens_used=int(key.tokens_used_total),
                requests_reserved=int(key.requests_reserved_total),
                tokens_reserved=int(key.tokens_reserved_total),
                pending_reservations=sum(row.status == "pending" for row in reservations),
                reservation_statuses=tuple(row.status for row in reservations),
                ledger_statuses=tuple(row.accounting_status for row in ledgers),
                ledger_successes=tuple(row.success for row in ledgers),
                ledger_error_types=tuple(row.error_type for row in ledgers),
                usage=tuple(
                    (
                        int(row.input_tokens),
                        int(row.cached_tokens),
                        int(row.output_tokens),
                        int(row.reasoning_tokens),
                        int(row.total_tokens),
                    )
                    for row in ledgers
                ),
                component_metadata=tuple(dict(row.response_metadata or {}) for row in ledgers),
            )
    finally:
        await engine.dispose()


async def outstanding_reservations(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(QuotaReservation)
                        .where(QuotaReservation.status == "pending")
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


async def sentinels_persisted(database_url: str, sentinels: Sequence[str]) -> bool:
    """Search every known text/JSON column without returning stored values."""

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            for table in Base.metadata.sorted_tables:
                columns = [
                    column
                    for column in table.columns
                    if isinstance(column.type, (String, Text, JSON, JSONB))
                ]
                if not columns:
                    continue
                for sentinel in sentinels:
                    predicates = [cast(column, Text).contains(sentinel) for column in columns]
                    count = (
                        await session.execute(
                            select(func.count()).select_from(table).where(or_(*predicates))
                        )
                    ).scalar_one()
                    if count:
                        return True
            return False
    finally:
        await engine.dispose()


async def replay_rows_are_hmac_only(database_url: str) -> bool:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = list((await session.execute(select(CodexReplayReference))).scalars())
            return bool(rows) and all(
                len(row.item_id_hmac) == 64
                and all(character in "0123456789abcdef" for character in row.item_id_hmac)
                and (
                    row.call_id_hmac is None
                    or (
                        len(row.call_id_hmac) == 64
                        and all(character in "0123456789abcdef" for character in row.call_id_hmac)
                    )
                )
                for row in rows
            )
    finally:
        await engine.dispose()


def _verify_fixture_digest() -> bool:
    fixture = REPO_ROOT / capture.FIXTURE_RELATIVE_PATH
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    return digest == CODEX_FIXTURE_SHA256


def _common_request_facts(facts: Sequence[UpstreamRequestFacts]) -> bool:
    return bool(facts) and all(
        fact.authorization_replaced
        and fact.headers_sanitized
        and fact.content_encoding_absent
        and fact.model_matched
        for fact in facts
    )


def _run_tool_scenario(
    mock: ScriptedOpenAIMock,
    *,
    gateway_port: int,
    key: CreatedGatewayKey,
    sentinels: list[str],
) -> tuple[bool, bool, bool, bool, bool, tuple[UpstreamRequestFacts, ...]]:
    marker_content = "marker-" + secrets.token_hex(24)
    final_text = "final-" + secrets.token_hex(24)
    ciphertext_source = "reasoning-" + secrets.token_hex(24)
    encrypted = base64.b64encode(ciphertext_source.encode()).decode()
    prompt = "bounded-tool-scenario-" + secrets.token_hex(24)
    root = Path(tempfile.mkdtemp(prefix="slaif-oap011-codex-"))
    codex_home = root / "codex-home"
    workspace = root / "workspace"
    codex_home.mkdir(mode=0o700)
    workspace.mkdir(mode=0o700)
    artifacts = render_codex_profile(f"http://127.0.0.1:{gateway_port}/v1")
    (codex_home / "config.toml").write_text(artifacts.base_config_toml, encoding="utf-8")
    (codex_home / "slaif.config.toml").write_text(artifacts.profile_config_toml, encoding="utf-8")
    start = mock.queue(
        build_tool_scenario_actions(
            workspace=workspace,
            marker_content=marker_content,
            encrypted_content=encrypted,
            final_text=final_text,
        )
    )
    try:
        result = subprocess.run(
            build_codex_command(workdir=workspace, prompt=prompt, sandbox="workspace-write"),
            check=False,
            capture_output=True,
            env=_profile_environment(codex_home, key.plaintext_key),
            timeout=120,
        )
        if (
            len(result.stdout) > MAX_CODEX_OUTPUT_BYTES
            or len(result.stderr) > MAX_CODEX_OUTPUT_BYTES
        ):
            raise VerificationError(SAFE_STAGE_ERROR)
        facts = mock.facts_since(start, 3)
        marker_matched = (workspace / "oap011-marker.txt").read_text(encoding="utf-8") == (
            marker_content + "\n"
        )
        replay_seen = any(
            _contains_replay_item(fact, kind="custom_tool_call_output") for fact in facts[1:]
        )
        reasoning_seen = _contains_replay_item(
            facts[2], kind="reasoning", item_id="rs_oap011_tool_replay"
        )
        sentinels.extend(
            [prompt, marker_content, final_text, ciphertext_source, encrypted, key.plaintext_key]
        )
        return (
            _codex_completed(result),
            marker_matched,
            replay_seen,
            reasoning_seen,
            _common_request_facts(facts),
            facts,
        )
    finally:
        _remove_private_root(root)


def _run_context_scenario(
    mock: ScriptedOpenAIMock,
    *,
    gateway_port: int,
    key: CreatedGatewayKey,
    sentinels: list[str],
) -> tuple[bool, bool, bool, tuple[UpstreamRequestFacts, ...]]:
    marker = "context-final-" + secrets.token_hex(24)
    ciphertext_source = "compaction-" + secrets.token_hex(24)
    encrypted = base64.b64encode(ciphertext_source.encode()).decode()
    prompt = "bounded-context-scenario-" + secrets.token_hex(24)
    start = mock.queue(build_context_scenario_actions(marker=marker, encrypted_content=encrypted))
    result, _workspace, root = run_codex(
        gateway_port=gateway_port,
        gateway_key=key.plaintext_key,
        prompt=prompt,
        sandbox="read-only",
    )
    try:
        facts = mock.facts_since(start, 3)
        compact_seen = [fact.path for fact in facts] == [
            "/v1/responses",
            "/v1/responses/compact",
            "/v1/responses",
        ]
        continuation = _contains_replay_item(facts[2], kind="compaction")
        sentinels.extend([prompt, marker, ciphertext_source, encrypted, key.plaintext_key])
        return _codex_completed(result), compact_seen, continuation, facts
    finally:
        _remove_private_root(root)


def _run_quota_scenario(
    mock: ScriptedOpenAIMock,
    *,
    gateway_port: int,
    key: CreatedGatewayKey,
    sentinels: list[str],
) -> tuple[bool, bool, tuple[UpstreamRequestFacts, ...]]:
    prompt = "bounded-quota-scenario-" + secrets.token_hex(24)
    source = 'text("QUOTA_FIRST_ROUND")'
    events = (
        {"type": "response.created", "response": {"id": "resp_oap011_quota"}},
        *_tool_events(item_id="ctc_oap011_quota", call_id="call_oap011_quota", source=source),
        {
            "type": "response.completed",
            "response": {
                "id": "resp_oap011_quota",
                "status": "completed",
                "usage": _usage(1),
            },
        },
    )
    start = mock.queue((MockAction("/v1/responses", "sse", events),))
    before = mock.request_count
    result, _workspace, root = run_codex(
        gateway_port=gateway_port,
        gateway_key=key.plaintext_key,
        prompt=prompt,
        sandbox="read-only",
    )
    try:
        facts = mock.facts_since(start, 1)
        after_codex = mock.request_count
        with httpx.Client(timeout=10, trust_env=False) as client:
            response = client.post(
                f"http://127.0.0.1:{gateway_port}/v1/responses",
                headers={"Authorization": f"Bearer {key.plaintext_key}"},
                json={"model": CODEX_MODEL, "input": prompt, "stream": False},
            )
        following_blocked = response.status_code == 429 and mock.request_count == after_codex
        sentinels.extend([prompt, key.plaintext_key])
        return (
            result.returncode != 0 and after_codex == before + 1,
            following_blocked,
            facts,
        )
    finally:
        _remove_private_root(root)


def _run_failure_scenario(
    mock: ScriptedOpenAIMock,
    *,
    gateway_port: int,
    key: CreatedGatewayKey,
    interrupted: bool,
    sentinels: list[str],
) -> tuple[bool, tuple[UpstreamRequestFacts, ...]]:
    prompt = (
        "bounded-interruption-" if interrupted else "bounded-provider-error-"
    ) + secrets.token_hex(24)
    if interrupted:
        action = MockAction(
            "/v1/responses",
            "interrupted",
            ({"type": "response.created", "response": {"id": "resp_oap011_interrupted"}},),
        )
    else:
        action = MockAction(
            "/v1/responses",
            "error",
            {
                "error": {
                    "message": "bounded loopback provider error",
                    "type": "rate_limit_error",
                    "code": "rate_limit_exceeded",
                }
            },
            status_code=429,
        )
    start = mock.queue((action,))
    result, _workspace, root = run_codex(
        gateway_port=gateway_port,
        gateway_key=key.plaintext_key,
        prompt=prompt,
        sandbox="read-only",
    )
    try:
        facts = mock.facts_since(start, 1)
        sentinels.extend([prompt, key.plaintext_key])
        return result.returncode != 0, facts
    finally:
        _remove_private_root(root)


def _validate_accounting(
    *,
    tool: KeyAccountingFacts,
    context: KeyAccountingFacts,
    quota: KeyAccountingFacts,
    interruption: KeyAccountingFacts,
    provider_error: KeyAccountingFacts,
) -> tuple[bool, bool, bool, bool]:
    tool_ok = (
        tool.requests_used == 3
        and tool.tokens_used == 6
        and tool.reservation_statuses == ("finalized", "finalized", "finalized")
        and tool.ledger_statuses == ("finalized", "finalized", "finalized")
    )
    context_expected = (
        (600_000, 200_000, 10, 4, 600_010),
        (272_000, 100_000, 2, 1, 272_002),
        (10, 5, 2, 1, 12),
    )
    context_ok = (
        context.requests_used == 3
        and context.tokens_used == 872_024
        and context.usage == context_expected
        and context.reservation_statuses == ("finalized", "finalized", "finalized")
        and context.ledger_statuses == ("finalized", "finalized", "finalized")
    )
    component_counts = [
        metadata.get("component_token_counts") for metadata in context.component_metadata
    ]
    component_costs = [
        metadata.get("component_costs_native") for metadata in context.component_metadata
    ]
    tiers = [
        component.get("long_context_tier_applied") if isinstance(component, Mapping) else None
        for component in component_counts
    ]
    tier_ok = tiers == [1, 0, 0]
    derived_cache_write = [
        expected_input
        - int(metadata.get("actual_cached_tokens", -1))
        - int(component.get("input_uncached_tokens", -1))
        if isinstance(component, Mapping)
        else -1
        for expected_input, metadata, component in zip(
            (600_000, 272_000, 10),
            context.component_metadata,
            component_counts,
            strict=True,
        )
    ]
    cache_ok = derived_cache_write == [100_000, 50_000, 1] and all(
        isinstance(component, Mapping)
        and Decimal(str(component.get("input_cache_write", "-1"))) > 0
        for component in component_costs
    )
    quota_ok = (
        quota.requests_used == 1
        and quota.tokens_used == 2
        and quota.pending_reservations == 0
        and quota.reservation_statuses == ("finalized",)
        and quota.ledger_statuses == ("finalized",)
    )
    failure_ok = all(
        facts.requests_used == 0
        and facts.tokens_used == 0
        and facts.pending_reservations == 0
        and facts.reservation_statuses == ("released",)
        and facts.ledger_statuses == ("failed",)
        and facts.ledger_successes == (False,)
        for facts in (interruption, provider_error)
    )
    overall = (
        all(
            facts.requests_reserved == 0 and facts.tokens_reserved == 0
            for facts in (tool, context, quota, interruption, provider_error)
        )
        and tool_ok
        and context_ok
        and quota_ok
        and failure_ok
    )
    return overall, cache_ok, tier_ok, failure_ok


def verify(target: SafeDatabaseTarget) -> VerificationFacts:
    """Execute the complete local-only five-scenario phase gate."""

    with safe_stage("cli_preflight_failed"):
        version = capture.verify_codex_version(CODEX_BINARY, CODEX_CLI_VERSION)
        facts = VerificationFacts(
            cli_version_matched=version == CODEX_CLI_VERSION,
            fixture_digest_matched=_verify_fixture_digest(),
        )
        if not facts.cli_version_matched or not facts.fixture_digest_matched:
            raise VerificationError(SAFE_STAGE_ERROR)
    with safe_stage("migration_failed"):
        migrate_database(target)
    mock = ScriptedOpenAIMock()
    with safe_stage("gateway_start_failed"):
        mock.start()
    sentinels: list[str] = [DUMMY_UPSTREAM_KEY]
    private_roots_before = set(Path("/tmp").glob("slaif-oap011-codex-*"))
    prior_upstream = os.environ.get(UPSTREAM_KEY_ENV)
    os.environ[UPSTREAM_KEY_ENV] = DUMMY_UPSTREAM_KEY
    try:
        assert mock.port is not None
        with safe_stage("redis_start_failed"):
            with private_redis() as (redis_url, redis_process):
                settings = _gateway_settings(target.url, redis_url)
                with safe_stage("seed_failed"):
                    keys = asyncio.run(
                        seed_gateway(
                            database_url=target.url,
                            mock_port=mock.port,
                            settings=settings,
                        )
                    )
                with safe_stage("gateway_start_failed"):
                    gateway_context = gateway_server(settings)
                    gateway_port, gateway_peer_facts = gateway_context.__enter__()
                try:
                    with safe_stage("tool_scenario_failed"):
                        (
                            tool_completed,
                            marker_matched,
                            replay_seen,
                            reasoning_seen,
                            tool_transport_ok,
                            tool_requests,
                        ) = _run_tool_scenario(
                            mock,
                            gateway_port=gateway_port,
                            key=keys["tool"],
                            sentinels=sentinels,
                        )
                    with safe_stage("context_scenario_failed"):
                        (
                            context_completed,
                            compact_seen,
                            continuation_seen,
                            context_requests,
                        ) = _run_context_scenario(
                            mock,
                            gateway_port=gateway_port,
                            key=keys["context"],
                            sentinels=sentinels,
                        )
                    with safe_stage("quota_scenario_failed"):
                        quota_seen, quota_sticky, quota_requests = _run_quota_scenario(
                            mock,
                            gateway_port=gateway_port,
                            key=keys["quota"],
                            sentinels=sentinels,
                        )
                    with safe_stage("interruption_scenario_failed"):
                        interruption_seen, interruption_requests = _run_failure_scenario(
                            mock,
                            gateway_port=gateway_port,
                            key=keys["interruption"],
                            interrupted=True,
                            sentinels=sentinels,
                        )
                    with safe_stage("provider_error_scenario_failed"):
                        provider_error_seen, error_requests = _run_failure_scenario(
                            mock,
                            gateway_port=gateway_port,
                            key=keys["provider_error"],
                            interrupted=False,
                            sentinels=sentinels,
                        )
                finally:
                    with safe_stage("gateway_start_failed"):
                        gateway_context.__exit__(None, None, None)
                if redis_process.poll() is not None:
                    raise VerificationError(SAFE_STAGE_ERROR)
                facts.redis_private_ephemeral = True
        with safe_stage("accounting_proof_failed"):
            accounting = {
                name: asyncio.run(load_accounting(target.url, key.gateway_key_id))
                for name, key in keys.items()
            }
            accounting_ok, cache_ok, tiers_ok, failure_accounting_ok = _validate_accounting(
                tool=accounting["tool"],
                context=accounting["context"],
                quota=accounting["quota"],
                interruption=accounting["interruption"],
                provider_error=accounting["provider_error"],
            )
            pending = asyncio.run(outstanding_reservations(target.url))
        with safe_stage("privacy_proof_failed"):
            persisted = asyncio.run(sentinels_persisted(target.url, sentinels))
            hmac_only = asyncio.run(replay_rows_are_hmac_only(target.url))
        all_requests = (
            *tool_requests,
            *context_requests,
            *quota_requests,
            *interruption_requests,
            *error_requests,
        )
        private_roots_after = set(Path("/tmp").glob("slaif-oap011-codex-*"))
        facts.scenario_count = 5
        facts.text_completion_seen = tool_completed
        facts.local_exec_seen = tool_completed and len(tool_requests) == 3
        facts.local_edit_seen = marker_matched
        facts.workspace_marker_matched = marker_matched
        facts.multi_round_replay_seen = replay_seen
        facts.encrypted_reasoning_replay_seen = reasoning_seen
        facts.cache_read_usage_seen = cache_ok
        facts.cache_write_usage_seen = cache_ok
        facts.long_context_tiers_seen = tiers_ok
        facts.v1_compact_seen = compact_seen
        facts.post_compact_continuation_seen = context_completed and continuation_seen
        facts.quota_rejection_seen = quota_seen
        facts.quota_rejected_before_upstream = quota_seen and quota_sticky
        facts.stream_interruption_seen = interruption_seen and failure_accounting_ok
        facts.provider_error_seen = provider_error_seen and failure_accounting_ok
        facts.accounting_matched = accounting_ok
        facts.outstanding_reservations = pending
        facts.provider_auth_replaced = tool_transport_ok and all(
            request.authorization_replaced for request in all_requests
        )
        facts.outbound_headers_sanitized = all(
            request.headers_sanitized for request in all_requests
        )
        facts.loopback_only = (
            mock.loopback_only
            and gateway_peer_facts.loopback_only
            and _common_request_facts(all_requests)
        )
        facts.raw_payloads_persisted = persisted or not hmac_only
        facts.workspaces_removed = private_roots_after == private_roots_before
        facts.real_provider_called = False
        fact_groups = (
            (
                "final_reduction_failed",
                facts.cli_version_matched
                and facts.fixture_digest_matched
                and facts.scenario_count == 5,
            ),
            (
                "tool_fact_failed",
                facts.text_completion_seen
                and facts.local_exec_seen
                and facts.local_edit_seen
                and facts.workspace_marker_matched
                and facts.multi_round_replay_seen
                and facts.encrypted_reasoning_replay_seen,
            ),
            (
                "context_fact_failed",
                facts.cache_read_usage_seen
                and facts.cache_write_usage_seen
                and facts.long_context_tiers_seen
                and facts.v1_compact_seen
                and facts.post_compact_continuation_seen,
            ),
            (
                "quota_fact_failed",
                facts.quota_rejection_seen and facts.quota_rejected_before_upstream,
            ),
            (
                "failure_fact_failed",
                facts.stream_interruption_seen and facts.provider_error_seen,
            ),
            (
                "accounting_fact_failed",
                facts.accounting_matched and facts.outstanding_reservations == 0,
            ),
            (
                "isolation_fact_failed",
                facts.provider_auth_replaced
                and facts.outbound_headers_sanitized
                and facts.loopback_only
                and not facts.raw_payloads_persisted
                and facts.redis_private_ephemeral
                and facts.workspaces_removed
                and not facts.real_provider_called,
            ),
        )
        for error_code, passed in fact_groups:
            if not passed:
                raise VerificationError(error_code)
        return facts
    finally:
        mock.stop()
        if prior_upstream is None:
            os.environ.pop(UPSTREAM_KEY_ENV, None)
        else:
            os.environ[UPSTREAM_KEY_ENV] = prior_upstream
        for name in (
            "OPENAI_API_KEY",
            "OPENAI_UPSTREAM_API_KEY",
            "OPENROUTER_API_KEY",
        ):
            if os.environ.get(name):
                raise VerificationError(SAFE_STAGE_ERROR)


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        parse_arguments(sys.argv[1:] if arguments is None else arguments)
        target = validate_test_database_url(os.environ.get("TEST_DATABASE_URL"))
        if os.environ.get("DATABASE_URL"):
            raise VerificationError(SAFE_DATABASE_ERROR)
        if any(
            os.environ.get(name)
            for name in (
                "OPENAI_API_KEY",
                "OPENAI_UPSTREAM_API_KEY",
                "OPENROUTER_API_KEY",
                "RUN_UPSTREAM_TESTS",
            )
        ):
            raise VerificationError(SAFE_STAGE_ERROR)
        internal_output = io.StringIO()
        with redirect_stdout(internal_output), redirect_stderr(internal_output):
            summary = verify(target)
        if len(internal_output.getvalue().encode("utf-8")) > MAX_CAPTURE_BYTES:
            raise VerificationError(SAFE_STAGE_ERROR)
        internal_output.close()
    except VerificationError as exc:
        sys.stdout.write(fixed_error_output(exc.code))
        return 1
    except capture.CaptureError:
        sys.stdout.write(fixed_error_output(SAFE_STAGE_ERROR))
        return 1
    except Exception:
        sys.stdout.write(fixed_error_output(SAFE_STAGE_ERROR))
        return 1
    sys.stdout.write(fixed_success_output(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
