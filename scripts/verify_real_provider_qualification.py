#!/usr/bin/env python3
"""Guarded, operator-authorized real-provider accounting qualification.

This verifier is intentionally fail-closed. It accepts only file-backed
secrets, a disposable loopback PostgreSQL target, an HTTPS gateway URL, and a
bounded authorization document. It never prints secret material, request IDs,
content, raw JSON, or exception text.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import asyncpg
import httpx

MAX_REQUESTS = 8
DEFAULT_MIN_GAP_SECONDS = 15.0
MAX_AUTHORIZED_COST_EUR = Decimal("0.05")
MAX_SAFE_JSON_BYTES = 64 * 1024
POLL_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.25
PROMPT_MARKER = "SLAIF-152A-PROBE"
EXPECTED_RESPONSE_MARKER = "SLAIF-152A-OK"
AUTHORIZATION_FIELDS = frozenset(
    {"candidate_commit", "max_requests", "providers", "max_total_cost_eur", "expires_at"}
)
PROVIDERS = ("openai", "openrouter")
COST_CONFIDENCES = frozenset(
    {
        "slaif_calculated",
        "slaif_calculated_with_fallbacks",
        "slaif_calculated_provider_cost_untrusted",
        "provider_reported_with_slaif_comparison",
    }
)
PROVIDER_DIRECT_HOSTS = frozenset(
    {"api.openai.com", "api.openrouter.ai", "openrouter.ai", "openrouter.ai."}
)
DIAGNOSTIC_ID_RE = re.compile(
    r"^gw-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,255}$")
DATABASE_NAME_RE = re.compile(r"^slaif_real_provider_qualification_[a-z0-9]+$")
DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,9})?$")
SECRET_ARG_RE = re.compile(r"(?:^|[=:])(?:sk-[A-Za-z0-9_-]{8,}|sk-or-[A-Za-z0-9_-]{8,})")
REJECTED_ENVIRONMENT_SECRETS = (
    "OPENAI_API_KEY",
    "OPENAI_UPSTREAM_API_KEY",
    "OPENROUTER_API_KEY",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "RUN_UPSTREAM_TESTS",
)


class VerificationError(Exception):
    """An error whose code is safe to expose to an operator."""

    def __init__(
        self,
        code: str,
        *,
        attempted_requests: int = 0,
        correlated_completed_count: int = 0,
        real_provider_call_proven: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.attempted_requests = attempted_requests
        self.correlated_completed_count = correlated_completed_count
        self.real_provider_call_proven = real_provider_call_proven


def _duplicate_json_key_error(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("json_duplicate_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    del value
    raise VerificationError("json_nonstandard_number")


def _normalize_json_value(value: object) -> object:
    """Return only bounded, ordinary JSON-compatible Python structures."""

    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str):
            try:
                value.encode("utf-8", "strict")
            except UnicodeError:
                raise VerificationError("json_invalid_utf8") from None
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VerificationError("json_nonstandard_number")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise VerificationError("json_object_key_invalid")
            if key in normalized:
                raise VerificationError("json_duplicate_key")
            normalized[key] = _normalize_json_value(nested)
        return normalized
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    raise VerificationError("json_value_type_invalid")


def _bounded_json_text(value: object, *, error_code: str) -> str:
    try:
        normalized = _normalize_json_value(value)
        text = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        size = len(text.encode("utf-8", "strict"))
    except VerificationError:
        raise
    except (TypeError, UnicodeError, ValueError, RecursionError):
        raise VerificationError(error_code) from None
    if size > MAX_SAFE_JSON_BYTES:
        raise VerificationError("json_value_too_large")
    return text


def _decode_json_value(value: object) -> object:
    """Strict asyncpg JSON decoder with a bounded input and ordinary output."""

    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeError:
            raise VerificationError("json_invalid_utf8") from None
    elif isinstance(value, str):
        try:
            raw = value.encode("utf-8", "strict")
        except UnicodeError:
            raise VerificationError("json_invalid_utf8") from None
        text = value
    else:
        raise VerificationError("json_codec_value_invalid")
    if len(raw) > MAX_SAFE_JSON_BYTES:
        raise VerificationError("json_value_too_large")
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_duplicate_json_key_error,
            parse_constant=_reject_json_constant,
        )
    except VerificationError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeError):
        raise VerificationError("json_decode_invalid") from None
    _bounded_json_text(decoded, error_code="json_decode_invalid")
    return decoded


def _encode_json_value(value: object) -> str:
    """Standard JSON text encoder paired with the private asyncpg codecs."""

    return _bounded_json_text(value, error_code="json_encode_invalid")


@dataclass(frozen=True, slots=True)
class Authorization:
    candidate_commit: str
    max_requests: int
    providers: frozenset[str]
    max_total_cost_eur: Decimal
    expires_at: dt.datetime


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    connect_url: str
    database_name: str


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class Flow:
    provider: str
    endpoint: str
    streaming: bool
    model: str


@dataclass(frozen=True, slots=True)
class TerminalEvidence:
    http_status: int
    terminal_shape_valid: bool
    usage: Usage


@dataclass(frozen=True, slots=True)
class CorrelationEvidence:
    gateway_key_id: str
    cost_source: str
    cost_confidence: str
    actual_cost_eur: Decimal
    stored_usage: Usage
    pending_reservations: int
    counters_zero: bool


@dataclass(frozen=True, slots=True)
class LiveConfiguration:
    gateway_base_url: str
    gateway_key: str
    gateway_key_id: str
    database_target: DatabaseTarget
    authorization: Authorization
    ca_file: str | None
    min_gap_seconds: float
    poll_timeout_seconds: float
    poll_interval_seconds: float
    flows: tuple[Flow, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_current_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError("candidate_commit_unavailable") from exc
    commit = result.stdout.strip()
    if not COMMIT_RE.fullmatch(commit):
        raise VerificationError("candidate_commit_invalid")
    return commit


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _protected_file_path(raw_path: str, *, name: str) -> Path:
    if not raw_path or "\x00" in raw_path:
        raise VerificationError(f"{name}_path_invalid")
    path = Path(raw_path)
    if not path.is_absolute():
        raise VerificationError(f"{name}_path_not_absolute")
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError):
        raise VerificationError(f"{name}_file_invalid") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise VerificationError(f"{name}_file_invalid")
    if os.path.normpath(os.path.abspath(raw_path)) != str(resolved):
        raise VerificationError(f"{name}_path_resolved")
    if metadata.st_uid != os.getuid():
        raise VerificationError(f"{name}_file_owner_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise VerificationError(f"{name}_file_permissions_invalid")
    if _is_under(resolved, _repo_root()):
        raise VerificationError(f"{name}_file_in_repository")
    if metadata.st_size > 64 * 1024:
        raise VerificationError(f"{name}_file_too_large")
    return resolved


def _read_protected_text(raw_path: str, *, name: str) -> str:
    path = _protected_file_path(raw_path, name=name)
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise VerificationError(f"{name}_file_unreadable") from None
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise VerificationError(f"{name}_value_invalid")
    return value


def _read_authorization(raw_path: str) -> Authorization:
    path = _protected_file_path(raw_path, name="authorization")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise VerificationError("authorization_malformed") from None
    if not isinstance(document, dict) or set(document) != AUTHORIZATION_FIELDS:
        raise VerificationError("authorization_fields_invalid")

    candidate_commit = document.get("candidate_commit")
    if not isinstance(candidate_commit, str) or not COMMIT_RE.fullmatch(candidate_commit):
        raise VerificationError("authorization_commit_invalid")
    if candidate_commit != _safe_current_commit():
        raise VerificationError("authorization_commit_mismatch")

    max_requests = document.get("max_requests")
    if isinstance(max_requests, bool) or max_requests != MAX_REQUESTS:
        raise VerificationError("authorization_request_bound_invalid")

    providers = document.get("providers")
    if not isinstance(providers, list) or any(
        not isinstance(provider, str) for provider in providers
    ):
        raise VerificationError("authorization_providers_invalid")
    if len(providers) != len(PROVIDERS) or set(providers) != set(PROVIDERS):
        raise VerificationError("authorization_providers_invalid")

    maximum_cost = document.get("max_total_cost_eur")
    if isinstance(maximum_cost, bool) or not isinstance(maximum_cost, (str, int, float)):
        raise VerificationError("authorization_cost_invalid")
    maximum_cost_text = str(maximum_cost)
    if not DECIMAL_RE.fullmatch(maximum_cost_text):
        raise VerificationError("authorization_cost_invalid")
    try:
        maximum_cost_decimal = Decimal(maximum_cost_text)
    except InvalidOperation:
        raise VerificationError("authorization_cost_invalid") from None
    if maximum_cost_decimal <= 0 or maximum_cost_decimal > MAX_AUTHORIZED_COST_EUR:
        raise VerificationError("authorization_cost_bound_invalid")

    expires_at = document.get("expires_at")
    if not isinstance(expires_at, str):
        raise VerificationError("authorization_expiry_invalid")
    try:
        parsed_expiry = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        raise VerificationError("authorization_expiry_invalid") from None
    if parsed_expiry.tzinfo is None:
        raise VerificationError("authorization_expiry_invalid")
    if parsed_expiry <= dt.datetime.now(dt.UTC):
        raise VerificationError("authorization_expired")

    return Authorization(
        candidate_commit=candidate_commit,
        max_requests=max_requests,
        providers=frozenset(providers),
        max_total_cost_eur=maximum_cost_decimal,
        expires_at=parsed_expiry,
    )


def _reject_inherited_secrets() -> None:
    if any(os.environ.get(name) for name in REJECTED_ENVIRONMENT_SECRETS):
        raise VerificationError("inherited_secret_environment_present")


def _reject_secret_argv(argv: Sequence[str]) -> None:
    for argument in argv:
        lowered = argument.lower()
        if "postgresql" in lowered or SECRET_ARG_RE.search(argument):
            raise VerificationError("secret_argument_rejected")
        if any(f"{name}=" in argument for name in REJECTED_ENVIRONMENT_SECRETS):
            raise VerificationError("secret_argument_rejected")


def _validate_model(model: str, *, provider: str) -> str:
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise VerificationError(f"{provider}_model_invalid")
    return model


def validate_gateway_key_id(raw_value: str) -> str:
    if not isinstance(raw_value, str):
        raise VerificationError("gateway_key_id_invalid")
    try:
        parsed = uuid.UUID(raw_value)
    except (ValueError, AttributeError):
        raise VerificationError("gateway_key_id_invalid") from None
    if str(parsed) != raw_value:
        raise VerificationError("gateway_key_id_invalid")
    return raw_value


def validate_gateway_base_url(raw_url: str) -> str:
    if not raw_url:
        raise VerificationError("gateway_base_url_missing")
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname
    except ValueError:
        raise VerificationError("gateway_base_url_invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/v1"
        or not hostname
    ):
        raise VerificationError("gateway_base_url_invalid")
    hostname = hostname.rstrip(".").lower()
    if hostname in PROVIDER_DIRECT_HOSTS or hostname.endswith(".openai.com"):
        raise VerificationError("gateway_provider_direct_url_rejected")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def validate_database_url(raw_url: str) -> DatabaseTarget:
    if not raw_url:
        raise VerificationError("database_url_missing")
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname
    except ValueError:
        raise VerificationError("database_url_invalid") from None
    if (
        parsed.scheme not in {"postgresql", "postgresql+asyncpg"}
        or hostname is None
        or hostname.lower() not in {"localhost", "127.0.0.1", "::1"}
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.count("/") != 1
    ):
        raise VerificationError("database_url_invalid")
    database_name = unquote(parsed.path[1:])
    if not DATABASE_NAME_RE.fullmatch(database_name):
        raise VerificationError("database_name_invalid")
    connect_scheme = "postgresql" if parsed.scheme == "postgresql+asyncpg" else parsed.scheme
    connect_url = urlunsplit((connect_scheme, parsed.netloc, f"/{database_name}", "", ""))
    return DatabaseTarget(connect_url=connect_url, database_name=database_name)


def _validate_ca_file(raw_path: str | None) -> str | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError):
        raise VerificationError("ca_file_invalid") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise VerificationError("ca_file_invalid")
    return str(resolved)


def _build_flows(openai_model: str, openrouter_model: str) -> tuple[Flow, ...]:
    return (
        Flow("openai", "/v1/chat/completions", False, openai_model),
        Flow("openai", "/v1/chat/completions", True, openai_model),
        Flow("openai", "/v1/responses", False, openai_model),
        Flow("openai", "/v1/responses", True, openai_model),
        Flow("openrouter", "/v1/chat/completions", False, openrouter_model),
        Flow("openrouter", "/v1/chat/completions", True, openrouter_model),
        Flow("openrouter", "/v1/responses", False, openrouter_model),
        Flow("openrouter", "/v1/responses", True, openrouter_model),
    )


def _positive_finite_float(raw: str, *, code: str, minimum: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise VerificationError(code) from None
    if not math.isfinite(value) or value < minimum:
        raise VerificationError(code)
    return value


def load_live_configuration(arguments: argparse.Namespace) -> LiveConfiguration:
    _reject_inherited_secrets()
    _reject_secret_argv(sys.argv)
    if not arguments.execute_live:
        raise VerificationError("live_execution_switch_required")
    required = (
        ("gateway_base_url", arguments.gateway_base_url),
        ("gateway_key_file", arguments.gateway_key_file),
        ("gateway_key_id", arguments.gateway_key_id),
        ("database_url_file", arguments.database_url_file),
        ("authorization_file", arguments.authorization_file),
        ("openai_model", arguments.openai_model),
        ("openrouter_model", arguments.openrouter_model),
    )
    if any(not value for _, value in required):
        raise VerificationError("live_argument_missing")

    gateway_base_url = validate_gateway_base_url(arguments.gateway_base_url)
    gateway_key_id = validate_gateway_key_id(arguments.gateway_key_id)
    gateway_key_path = _protected_file_path(arguments.gateway_key_file, name="gateway_key")
    database_path = _protected_file_path(arguments.database_url_file, name="database_url")
    authorization_path = _protected_file_path(
        arguments.authorization_file,
        name="authorization",
    )
    if len({gateway_key_path, database_path, authorization_path}) != 3:
        raise VerificationError("protected_files_must_be_distinct")
    try:
        gateway_key = gateway_key_path.read_text(encoding="utf-8").strip()
        database_url = database_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise VerificationError("protected_file_unreadable") from None
    if (
        not gateway_key
        or not database_url
        or any(character.isspace() for character in gateway_key)
        or any(character.isspace() for character in database_url)
    ):
        raise VerificationError("protected_file_value_invalid")
    database_target = validate_database_url(database_url)
    authorization = _read_authorization(str(authorization_path))
    ca_file = _validate_ca_file(arguments.ca_file)
    min_gap_seconds = _positive_finite_float(
        arguments.min_gap_seconds,
        code="minimum_gap_invalid",
        minimum=DEFAULT_MIN_GAP_SECONDS,
    )
    poll_timeout_seconds = _positive_finite_float(
        arguments.poll_timeout_seconds,
        code="poll_timeout_invalid",
        minimum=0.1,
    )
    poll_interval_seconds = _positive_finite_float(
        arguments.poll_interval_seconds,
        code="poll_interval_invalid",
        minimum=0.01,
    )
    openai_model = _validate_model(arguments.openai_model, provider="openai")
    openrouter_model = _validate_model(arguments.openrouter_model, provider="openrouter")
    return LiveConfiguration(
        gateway_base_url=gateway_base_url,
        gateway_key=gateway_key,
        gateway_key_id=gateway_key_id,
        database_target=database_target,
        authorization=authorization,
        ca_file=ca_file,
        min_gap_seconds=min_gap_seconds,
        poll_timeout_seconds=poll_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        flows=_build_flows(openai_model, openrouter_model),
    )


def _local_alembic_head() -> str:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(_repo_root() / "alembic.ini"))
        config.set_main_option("script_location", str(_repo_root() / "migrations"))
        heads = ScriptDirectory.from_config(config).get_heads()
    except Exception as exc:  # noqa: BLE001
        raise VerificationError("alembic_head_unavailable") from exc
    if len(heads) != 1:
        raise VerificationError("alembic_head_ambiguous")
    return heads[0]


def _row_value(row: Mapping[str, Any], key: str) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError):
        return None


def _normalize_metadata(value: object, *, field: str) -> dict[str, object]:
    """Normalize asyncpg JSONB mappings or bounded JSON text to a mapping."""

    try:
        if isinstance(value, (str, bytes, bytearray)):
            decoded = _decode_json_value(value)
        elif isinstance(value, Mapping):
            decoded = _normalize_json_value(value)
        else:
            raise VerificationError("json_object_invalid")
    except VerificationError as exc:
        raise VerificationError(f"{field}_{exc.code}") from None
    except RecursionError:
        raise VerificationError(f"{field}_json_recursion_limit") from None
    try:
        _bounded_json_text(decoded, error_code=f"{field}_json_normalization_invalid")
    except VerificationError as exc:
        raise VerificationError(f"{field}_{exc.code}") from None
    if not isinstance(decoded, Mapping) or isinstance(decoded, bool):
        raise VerificationError(f"{field}_json_object_invalid")
    return dict(decoded)


def _as_nonnegative_decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise VerificationError(f"correlation_{field}_invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise VerificationError(f"correlation_{field}_invalid") from None
    if parsed < 0:
        raise VerificationError(f"correlation_{field}_negative")
    return parsed


def _as_nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise VerificationError(f"correlation_{field}_invalid")
    return value


def _validate_usage_mapping(payload: object) -> Usage:
    if not isinstance(payload, Mapping):
        raise VerificationError("usage_object_invalid")
    input_value = payload.get("input_tokens", payload.get("prompt_tokens"))
    output_value = payload.get("output_tokens", payload.get("completion_tokens"))
    total_value = payload.get("total_tokens")
    values = (input_value, output_value, total_value)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise VerificationError("usage_fields_invalid")
    if any(value < 0 for value in values):
        raise VerificationError("usage_negative")
    if input_value + output_value != total_value:
        raise VerificationError("usage_total_inconsistent")
    if total_value <= 0:
        raise VerificationError("usage_zero")
    return Usage(input_value, output_value, total_value)


def _usage_from_body(body: object) -> Usage:
    if not isinstance(body, Mapping):
        raise VerificationError("response_body_invalid")
    return _validate_usage_mapping(body.get("usage"))


def _contains_text(value: object, marker: str) -> bool:
    if isinstance(value, str):
        return marker in value
    if isinstance(value, Mapping):
        return any(_contains_text(item, marker) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_text(item, marker) for item in value)
    return False


def validate_chat_body(body: object) -> Usage:
    if not isinstance(body, Mapping):
        raise VerificationError("chat_response_shape_invalid")
    if body.get("object") != "chat.completion":
        raise VerificationError("chat_response_shape_invalid")
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise VerificationError("chat_response_choices_invalid")
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise VerificationError("chat_response_choice_invalid")
    message = choice.get("message")
    if not isinstance(message, Mapping) or message.get("role") != "assistant":
        raise VerificationError("chat_response_message_invalid")
    if not _contains_text(message.get("content"), EXPECTED_RESPONSE_MARKER):
        raise VerificationError("chat_response_marker_missing")
    return _usage_from_body(body)


def validate_responses_body(body: object) -> Usage:
    if not isinstance(body, Mapping):
        raise VerificationError("responses_response_shape_invalid")
    if body.get("object") != "response" or body.get("status") != "completed":
        raise VerificationError("responses_response_shape_invalid")
    if not isinstance(body.get("output"), list) or not body.get("output"):
        raise VerificationError("responses_response_output_invalid")
    if not _contains_text(body.get("output"), EXPECTED_RESPONSE_MARKER):
        raise VerificationError("responses_response_marker_missing")
    return _usage_from_body(body)


async def _iter_sse_events(response: httpx.Response):
    event_name: str | None = None
    data_lines: list[str] = []
    dispatched = False
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                dispatched = True
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            if event_name is not None or data_lines:
                raise VerificationError("sse_event_framing_invalid")
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        else:
            raise VerificationError("sse_event_framing_invalid")
    if data_lines:
        raise VerificationError("sse_terminal_frame_missing")
    if not dispatched:
        raise VerificationError("sse_empty")


def _json_event(raw_data: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        raise VerificationError("sse_json_invalid") from None
    if not isinstance(payload, Mapping):
        raise VerificationError("sse_json_shape_invalid")
    if "error" in payload:
        raise VerificationError("sse_error_event")
    return payload


async def validate_chat_stream(response: httpx.Response) -> TerminalEvidence:
    saw_done = False
    usage: Usage | None = None
    content: list[str] = []
    async for _, raw_data in _iter_sse_events(response):
        if raw_data == "[DONE]":
            if saw_done:
                raise VerificationError("chat_stream_duplicate_done")
            saw_done = True
            continue
        if saw_done:
            raise VerificationError("chat_stream_after_done")
        payload = _json_event(raw_data)
        if "usage" in payload:
            usage = _validate_usage_mapping(payload["usage"])
        choices = payload.get("choices")
        if choices is not None:
            if not isinstance(choices, list):
                raise VerificationError("chat_stream_choices_invalid")
            for choice in choices:
                if not isinstance(choice, Mapping):
                    raise VerificationError("chat_stream_choice_invalid")
                delta = choice.get("delta")
                if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
                    content.append(delta["content"])
    if not saw_done:
        raise VerificationError("chat_stream_done_missing")
    if EXPECTED_RESPONSE_MARKER not in "".join(content):
        raise VerificationError("chat_stream_marker_missing")
    if usage is None:
        raise VerificationError("chat_stream_usage_missing")
    return TerminalEvidence(200, True, usage)


async def validate_responses_stream(response: httpx.Response) -> TerminalEvidence:
    completed_count = 0
    usage: Usage | None = None
    completed_response: Mapping[str, Any] | None = None
    terminal_seen = False
    async for event_name, raw_data in _iter_sse_events(response):
        if raw_data == "[DONE]":
            if not terminal_seen:
                raise VerificationError("responses_stream_terminal_missing")
            continue
        if terminal_seen:
            raise VerificationError("responses_stream_after_terminal")
        payload = _json_event(raw_data)
        event_type = payload.get("type")
        if event_name and event_type != event_name:
            raise VerificationError("responses_stream_event_type_mismatch")
        if event_type in {"response.failed", "response.incomplete", "error"}:
            raise VerificationError("responses_stream_failed_event")
        if event_type == "response.completed":
            completed_count += 1
            if completed_count != 1:
                raise VerificationError("responses_stream_duplicate_completed")
            raw_response = payload.get("response")
            if not isinstance(raw_response, Mapping):
                raise VerificationError("responses_stream_response_invalid")
            completed_response = raw_response
            usage = _validate_usage_mapping(raw_response.get("usage"))
            terminal_seen = True
    if not terminal_seen or completed_count != 1 or completed_response is None:
        raise VerificationError("responses_stream_completed_missing")
    if completed_response.get("object") != "response" or completed_response.get("status") != "completed":
        raise VerificationError("responses_stream_response_invalid")
    if not _contains_text(completed_response.get("output"), EXPECTED_RESPONSE_MARKER):
        raise VerificationError("responses_stream_marker_missing")
    if usage is None:
        raise VerificationError("responses_stream_usage_missing")
    return TerminalEvidence(200, True, usage)


def _diagnostic_id(response: httpx.Response) -> str:
    value = response.headers.get("X-SLAIF-Diagnostic-ID")
    if value is None or DIAGNOSTIC_ID_RE.fullmatch(value) is None:
        raise VerificationError("diagnostic_id_invalid")
    return value


def _request_body(flow: Flow) -> dict[str, object]:
    if flow.endpoint == "/v1/chat/completions":
        return {
            "model": flow.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{PROMPT_MARKER}: reply exactly {EXPECTED_RESPONSE_MARKER}",
                }
            ],
            "max_completion_tokens": 32,
            "stream": flow.streaming,
            **({"stream_options": {"include_usage": True}} if flow.streaming else {}),
        }
    return {
        "model": flow.model,
        "input": f"{PROMPT_MARKER}: reply exactly {EXPECTED_RESPONSE_MARKER}",
        "max_output_tokens": 32,
        "store": False,
        "stream": flow.streaming,
    }


async def execute_flow(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    gateway_key: str,
    flow: Flow,
) -> tuple[str, TerminalEvidence]:
    headers = {"Authorization": f"Bearer {gateway_key}", "Content-Type": "application/json"}
    url = f"{base_url}{flow.endpoint.removeprefix('/v1')}"
    try:
        if not flow.streaming:
            response = await client.post(url, headers=headers, json=_request_body(flow))
            diagnostic_id = _diagnostic_id(response)
            if response.status_code != 200:
                raise VerificationError("gateway_http_status")
            try:
                body = response.json()
            except (ValueError, json.JSONDecodeError):
                raise VerificationError("gateway_json_invalid") from None
            usage = (
                validate_chat_body(body)
                if flow.endpoint == "/v1/chat/completions"
                else validate_responses_body(body)
            )
            return diagnostic_id, TerminalEvidence(200, True, usage)

        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=_request_body(flow),
        ) as response:
            diagnostic_id = _diagnostic_id(response)
            if response.status_code != 200:
                raise VerificationError("gateway_http_status")
            terminal = (
                await validate_chat_stream(response)
                if flow.endpoint == "/v1/chat/completions"
                else await validate_responses_stream(response)
            )
            return diagnostic_id, terminal
    except VerificationError:
        raise
    except (httpx.HTTPError, TimeoutError, OSError):
        raise VerificationError("gateway_transport_failure") from None


def _metadata_cost_labels(metadata: object) -> tuple[str, str]:
    normalized = _normalize_metadata(metadata, field="correlation_metadata")
    source = normalized.get("cost_source")
    confidence = normalized.get("cost_confidence")
    if not isinstance(source, str) or not isinstance(confidence, str):
        raise VerificationError("correlation_cost_metadata_missing")
    if source not in {"slaif_calculated", "provider_reported"}:
        raise VerificationError("correlation_cost_source_invalid")
    if confidence not in COST_CONFIDENCES:
        raise VerificationError("correlation_cost_confidence_invalid")
    if source == "provider_reported" and not (
        "provider_reported_cost_eur" in metadata
        or "provider_reported_cost_native" in metadata
    ):
        raise VerificationError("correlation_provider_cost_unsubstantiated")
    return source, confidence


def _scan_json_value(value: object) -> object:
    """Convert database scalar types without accepting arbitrary objects."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VerificationError("privacy_scan_nonstandard_number")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Mapping):
        scanned: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or key in scanned:
                raise VerificationError("privacy_scan_object_key_invalid")
            scanned[key] = _scan_json_value(nested)
        return scanned
    if isinstance(value, (list, tuple)):
        return [_scan_json_value(item) for item in value]
    raise VerificationError("privacy_scan_value_invalid")


def _serialize_scan_value(value: object, *, error_code: str) -> str:
    try:
        serialized = json.dumps(
            _scan_json_value(value),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except VerificationError:
        raise VerificationError(error_code) from None
    except (TypeError, UnicodeError, ValueError, RecursionError):
        raise VerificationError(error_code) from None
    return serialized


def validate_correlation(
    *,
    reservation_rows: Sequence[Mapping[str, Any]],
    ledger_rows: Sequence[Mapping[str, Any]],
    key_rows: Sequence[Mapping[str, Any]],
    pending_reservations: int,
    expected_key: str,
    expected_gateway_key_id: str,
    flow: Flow,
    expected_usage: Usage,
    prompt_marker: str = PROMPT_MARKER,
    response_marker: str = EXPECTED_RESPONSE_MARKER,
) -> CorrelationEvidence:
    if len(reservation_rows) != 1 or len(ledger_rows) != 1 or len(key_rows) != 1:
        raise VerificationError("correlation_cardinality_invalid")
    reservation = reservation_rows[0]
    ledger = ledger_rows[0]
    key = key_rows[0]
    reservation_id = str(_row_value(reservation, "id") or "")
    ledger_reservation_id = str(_row_value(ledger, "quota_reservation_id") or "")
    gateway_key_id = str(_row_value(reservation, "gateway_key_id") or "")
    if not reservation_id or reservation_id != ledger_reservation_id:
        raise VerificationError("correlation_reservation_relationship_invalid")
    if gateway_key_id != str(_row_value(ledger, "gateway_key_id") or ""):
        raise VerificationError("correlation_key_relationship_invalid")
    if gateway_key_id != expected_gateway_key_id:
        raise VerificationError("correlation_selected_key_mismatch")
    if gateway_key_id != str(_row_value(key, "id") or "") or not gateway_key_id:
        raise VerificationError("correlation_key_missing")
    if _row_value(reservation, "endpoint") != flow.endpoint:
        raise VerificationError("correlation_reservation_endpoint_invalid")
    if _row_value(ledger, "endpoint") != flow.endpoint:
        raise VerificationError("correlation_ledger_endpoint_invalid")
    for row in (reservation, ledger):
        if _row_value(row, "provider") != flow.provider:
            raise VerificationError("correlation_provider_invalid")
    if _row_value(reservation, "requested_model") != flow.model:
        raise VerificationError("correlation_requested_model_invalid")
    if _row_value(ledger, "requested_model") != flow.model:
        raise VerificationError("correlation_ledger_model_invalid")
    resolved_model = _row_value(reservation, "resolved_model")
    if not isinstance(resolved_model, str) or not resolved_model:
        raise VerificationError("correlation_resolved_model_invalid")
    if _row_value(ledger, "resolved_model") != resolved_model:
        raise VerificationError("correlation_resolved_model_mismatch")
    if _row_value(reservation, "streaming") is not flow.streaming:
        raise VerificationError("correlation_reservation_streaming_invalid")
    if _row_value(ledger, "streaming") is not flow.streaming:
        raise VerificationError("correlation_ledger_streaming_invalid")
    if _row_value(reservation, "status") != "finalized":
        raise VerificationError("correlation_reservation_not_finalized")
    if _row_value(ledger, "accounting_status") != "finalized":
        raise VerificationError("correlation_ledger_not_finalized")
    if _row_value(ledger, "success") is not True or _row_value(ledger, "http_status") != 200:
        raise VerificationError("correlation_success_invalid")
    if _row_value(reservation, "finalized_at") is None or _row_value(
        reservation, "released_at"
    ) is not None:
        raise VerificationError("correlation_reservation_terminal_time_invalid")
    if _row_value(ledger, "finished_at") is None:
        raise VerificationError("correlation_ledger_terminal_time_invalid")

    ledger_usage = Usage(
        _as_nonnegative_int(_row_value(ledger, "input_tokens"), field="input_tokens"),
        _as_nonnegative_int(_row_value(ledger, "output_tokens"), field="output_tokens"),
        _as_nonnegative_int(_row_value(ledger, "total_tokens"), field="total_tokens"),
    )
    if ledger_usage.total_tokens <= 0 or (
        ledger_usage.input_tokens + ledger_usage.output_tokens != ledger_usage.total_tokens
    ):
        raise VerificationError("correlation_usage_inconsistent")
    if ledger_usage != expected_usage:
        raise VerificationError("correlation_usage_mismatch")

    for row, fields in (
        (
            reservation,
            ("reserved_cost_eur", "reserved_tokens", "reserved_requests"),
        ),
        (
            ledger,
            (
                "estimated_cost_eur",
                "actual_cost_eur",
                "actual_cost_native",
                "prompt_tokens",
                "completion_tokens",
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "reasoning_tokens",
                "total_tokens",
            ),
        ),
    ):
        for field in fields:
            value = _row_value(row, field)
            if value is not None:
                if "cost" in field:
                    _as_nonnegative_decimal(value, field=field)
                else:
                    _as_nonnegative_int(value, field=field)

    usage_raw = _normalize_metadata(
        _row_value(ledger, "usage_raw"),
        field="correlation_usage_raw",
    )
    response_metadata = _normalize_metadata(
        _row_value(ledger, "response_metadata"),
        field="correlation_metadata",
    )
    source, confidence = _metadata_cost_labels(response_metadata)
    actual_cost_eur = _as_nonnegative_decimal(
        _row_value(ledger, "actual_cost_eur"),
        field="actual_cost_eur",
    )
    raw_metadata = _serialize_scan_value(
        {
            "usage_raw": usage_raw,
            "response_metadata": response_metadata,
            "error_message": _row_value(ledger, "error_message"),
            "key_row": dict(key),
        },
        error_code="correlation_privacy_scan_invalid",
    )
    if prompt_marker in raw_metadata or response_marker in raw_metadata or expected_key in raw_metadata:
        raise VerificationError("correlation_privacy_canary_found")

    counters = (
        _as_nonnegative_decimal(_row_value(key, "cost_reserved_eur"), field="key_cost_reserved"),
        _as_nonnegative_int(_row_value(key, "tokens_reserved_total"), field="key_tokens_reserved"),
        _as_nonnegative_int(_row_value(key, "requests_reserved_total"), field="key_requests_reserved"),
    )
    if _row_value(reservation, "reserved_requests") != 1:
        raise VerificationError("correlation_reserved_request_count_invalid")
    counters_zero = counters == (Decimal("0"), 0, 0)
    if pending_reservations != 0 or not counters_zero:
        raise VerificationError("correlation_pending_or_reserved_state")
    return CorrelationEvidence(
        gateway_key_id=gateway_key_id,
        cost_source=source,
        cost_confidence=confidence,
        actual_cost_eur=actual_cost_eur,
        stored_usage=ledger_usage,
        pending_reservations=pending_reservations,
        counters_zero=counters_zero,
    )


_FRESH_KEY_FIELDS = frozenset(
    {
        "id",
        "public_key_id",
        "key_prefix",
        "key_hint",
        "token_hash",
        "status",
        "valid_from",
        "valid_until",
        "cost_limit_eur",
        "token_limit_total",
        "request_limit_total",
        "cost_used_eur",
        "tokens_used_total",
        "requests_used_total",
        "cost_reserved_eur",
        "tokens_reserved_total",
        "requests_reserved_total",
        "external_tool_fence_state",
        "external_tool_fence_reservation_id",
        "external_tool_fence_request_id",
        "external_tool_fence_acquired_at",
        "external_tool_fence_expires_at",
        "allow_all_models",
        "allowed_models",
        "allow_all_endpoints",
        "allowed_endpoints",
        "key_purpose",
        "capability_policy_mode",
        "calibration_metadata",
        "metadata",
    }
)


def _require_zero_key_counters(key: Mapping[str, Any], *, reserved_only: bool = False) -> None:
    fields = (
        ("cost_reserved_eur", "decimal"),
        ("tokens_reserved_total", "integer"),
        ("requests_reserved_total", "integer"),
    )
    if not reserved_only:
        fields += (
            ("cost_used_eur", "decimal"),
            ("tokens_used_total", "integer"),
            ("requests_used_total", "integer"),
        )
    for field, kind in fields:
        value = _row_value(key, field)
        if kind == "decimal":
            parsed = _as_nonnegative_decimal(value, field=field)
            if parsed != 0:
                raise VerificationError("fresh_key_counters_nonzero")
        else:
            if _as_nonnegative_int(value, field=field) != 0:
                raise VerificationError("fresh_key_counters_nonzero")


def _scan_complete_key_row(key: Mapping[str, Any], gateway_key: str) -> None:
    if not _FRESH_KEY_FIELDS.issubset(key.keys()):
        raise VerificationError("fresh_key_row_incomplete")
    serialized = _serialize_scan_value(dict(key), error_code="fresh_key_row_serialization_invalid")
    if gateway_key in serialized:
        raise VerificationError("fresh_key_plaintext_canary_found")


def validate_fresh_key(
    *,
    key_rows: Sequence[Mapping[str, Any]],
    gateway_key_id: str,
    gateway_key: str,
    reservation_count: int,
    ledger_count: int,
    now: dt.datetime | None = None,
) -> None:
    if len(key_rows) != 1:
        raise VerificationError("fresh_key_cardinality_invalid")
    key = key_rows[0]
    if str(_row_value(key, "id") or "") != gateway_key_id:
        raise VerificationError("fresh_key_id_mismatch")
    if _row_value(key, "status") != "active" or _row_value(key, "revoked_at") is not None:
        raise VerificationError("fresh_key_state_invalid")
    valid_until = _row_value(key, "valid_until")
    current_time = now or dt.datetime.now(dt.UTC)
    if not isinstance(valid_until, dt.datetime) or valid_until <= current_time:
        raise VerificationError("fresh_key_expired")
    _require_zero_key_counters(key)
    if _row_value(key, "external_tool_fence_state") != "none":
        raise VerificationError("fresh_key_fence_state_invalid")
    if any(
        _row_value(key, field) is not None
        for field in (
            "external_tool_fence_reservation_id",
            "external_tool_fence_request_id",
            "external_tool_fence_acquired_at",
            "external_tool_fence_expires_at",
        )
    ):
        raise VerificationError("fresh_key_fence_state_invalid")
    if reservation_count != 0 or ledger_count != 0:
        raise VerificationError("fresh_key_has_history")
    _scan_complete_key_row(key, gateway_key)


def validate_ordinal_run_isolation(
    *,
    reservation_ids: Sequence[str],
    ledger_ids: Sequence[str],
    seen_request_ids: Sequence[str],
    ordinal: int,
) -> None:
    seen = set(seen_request_ids)
    if ordinal != len(seen_request_ids) or len(seen) != ordinal:
        raise VerificationError("run_seen_id_cardinality_invalid")
    if len(reservation_ids) != ordinal or len(ledger_ids) != ordinal:
        raise VerificationError("run_ordinal_cardinality_invalid")
    if set(reservation_ids) != seen or set(ledger_ids) != seen:
        raise VerificationError("run_ordinal_uncorrelated_rows")


def validate_final_key_state(
    *,
    key_rows: Sequence[Mapping[str, Any]],
    gateway_key_id: str,
    pending_reservations: int,
) -> None:
    if len(key_rows) != 1 or str(_row_value(key_rows[0], "id") or "") != gateway_key_id:
        raise VerificationError("final_key_cardinality_invalid")
    if _row_value(key_rows[0], "status") != "active":
        raise VerificationError("final_key_state_invalid")
    _require_zero_key_counters(key_rows[0], reserved_only=True)
    if pending_reservations != 0:
        raise VerificationError("final_key_pending_reservations")


class PostgresProbe:
    """Small read-only PostgreSQL probe used after each gateway terminal."""

    def __init__(self, target: DatabaseTarget, *, timeout_seconds: float) -> None:
        self._target = target
        self._timeout_seconds = timeout_seconds
        self._connection: asyncpg.Connection | None = None

    async def _register_json_codecs(self) -> None:
        connection = self._connection_or_fail()
        try:
            for type_name in ("json", "jsonb"):
                await connection.set_type_codec(
                    type_name,
                    schema="pg_catalog",
                    encoder=_encode_json_value,
                    decoder=_decode_json_value,
                    format="text",
                )
        except VerificationError:
            raise
        except Exception:  # noqa: BLE001
            raise VerificationError("database_json_codec_setup_failure") from None

    async def connect_and_check(self) -> None:
        try:
            self._connection = await asyncpg.connect(
                self._target.connect_url,
                timeout=self._timeout_seconds,
                command_timeout=self._timeout_seconds,
            )
            await self._register_json_codecs()
            database_name = await self._connection.fetchval("SELECT current_database()")
            if database_name != self._target.database_name:
                raise VerificationError("database_name_mismatch")
            rows = await self._connection.fetch("SELECT version_num FROM alembic_version")
            if len(rows) != 1 or rows[0]["version_num"] != _local_alembic_head():
                raise VerificationError("database_schema_not_current")
        except VerificationError:
            await self.close()
            raise
        except (asyncpg.PostgresError, OSError, TimeoutError):
            await self.close()
            raise VerificationError("database_connection_failure") from None

    async def prepare_fresh_key(self, *, gateway_key_id: str, gateway_key: str) -> None:
        connection = self._connection_or_fail()
        try:
            key_rows = await connection.fetch(
                "SELECT * FROM gateway_keys WHERE id = $1::uuid",
                gateway_key_id,
            )
            reservation_count = await connection.fetchval(
                """
                SELECT count(*)::int
                FROM quota_reservations
                WHERE gateway_key_id = $1::uuid
                """,
                gateway_key_id,
            )
            ledger_count = await connection.fetchval(
                """
                SELECT count(*)::int
                FROM usage_ledger
                WHERE gateway_key_id = $1::uuid
                """,
                gateway_key_id,
            )
        except (asyncpg.PostgresError, OSError, TimeoutError):
            raise VerificationError("database_fresh_key_query_failure") from None
        validate_fresh_key(
            key_rows=key_rows,
            gateway_key_id=gateway_key_id,
            gateway_key=gateway_key,
            reservation_count=int(reservation_count or 0),
            ledger_count=int(ledger_count or 0),
        )

    def _connection_or_fail(self) -> asyncpg.Connection:
        if self._connection is None:
            raise VerificationError("database_not_connected")
        return self._connection

    async def correlate(
        self,
        *,
        gateway_request_id: str,
        gateway_key_id: str,
        gateway_key: str,
        flow: Flow,
        expected_usage: Usage,
        timeout_seconds: float,
        interval_seconds: float,
    ) -> CorrelationEvidence:
        connection = self._connection_or_fail()
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                reservation_rows = await connection.fetch(
                    """
                    SELECT id::text, gateway_key_id::text, endpoint, requested_model,
                           provider, resolved_model, streaming, status, reserved_cost_eur,
                           reserved_tokens, reserved_requests, finalized_at, released_at
                    FROM quota_reservations
                    WHERE request_id = $1
                    """,
                    gateway_request_id,
                )
                ledger_rows = await connection.fetch(
                    """
                    SELECT request_id, quota_reservation_id::text, gateway_key_id::text,
                           endpoint, provider, requested_model, resolved_model, streaming,
                           success, accounting_status, http_status, input_tokens,
                           output_tokens, total_tokens, prompt_tokens, completion_tokens,
                           cached_tokens, reasoning_tokens, estimated_cost_eur,
                           actual_cost_eur, actual_cost_native, usage_raw,
                           response_metadata, error_message, finished_at
                    FROM usage_ledger
                    WHERE request_id = $1
                    """,
                    gateway_request_id,
                )
                if len(reservation_rows) == 1:
                    key_rows = await connection.fetch(
                        "SELECT * FROM gateway_keys WHERE id = $1::uuid",
                        gateway_key_id,
                    )
                    pending = await connection.fetchval(
                        """
                        SELECT count(*)::int
                        FROM quota_reservations
                        WHERE gateway_key_id = $1::uuid AND status = 'pending'
                        """,
                        gateway_key_id,
                    )
                    if len(ledger_rows) == 1 and len(key_rows) == 1:
                        return validate_correlation(
                            reservation_rows=reservation_rows,
                            ledger_rows=ledger_rows,
                            key_rows=key_rows,
                            pending_reservations=int(pending or 0),
                            expected_key=gateway_key,
                            expected_gateway_key_id=gateway_key_id,
                            flow=flow,
                            expected_usage=expected_usage,
                        )
            except VerificationError:
                raise
            except (asyncpg.PostgresError, OSError, TimeoutError):
                raise VerificationError("database_query_failure") from None
            if time.monotonic() >= deadline:
                raise VerificationError("accounting_correlation_timeout")
            await asyncio.sleep(interval_seconds)

    async def _all_key_request_ids(self, *, gateway_key_id: str) -> tuple[list[str], list[str]]:
        connection = self._connection_or_fail()
        try:
            reservations = await connection.fetch(
                """
                SELECT request_id
                FROM quota_reservations
                WHERE gateway_key_id = $1::uuid
                """,
                gateway_key_id,
            )
            ledgers = await connection.fetch(
                """
                SELECT request_id
                FROM usage_ledger
                WHERE gateway_key_id = $1::uuid
                """,
                gateway_key_id,
            )
        except (asyncpg.PostgresError, OSError, TimeoutError):
            raise VerificationError("database_run_isolation_query_failure") from None
        return (
            [str(row["request_id"]) for row in reservations],
            [str(row["request_id"]) for row in ledgers],
        )

    async def check_ordinal_isolation(
        self,
        *,
        gateway_key_id: str,
        seen_request_ids: Sequence[str],
        ordinal: int,
    ) -> None:
        reservation_ids, ledger_ids = await self._all_key_request_ids(
            gateway_key_id=gateway_key_id
        )
        validate_ordinal_run_isolation(
            reservation_ids=reservation_ids,
            ledger_ids=ledger_ids,
            seen_request_ids=seen_request_ids,
            ordinal=ordinal,
        )

    async def final_run_check(
        self,
        *,
        gateway_key_id: str,
        request_ids: Sequence[str],
    ) -> None:
        if len(request_ids) != MAX_REQUESTS or len(set(request_ids)) != MAX_REQUESTS:
            raise VerificationError("run_request_cardinality_invalid")
        reservation_ids, ledger_ids = await self._all_key_request_ids(
            gateway_key_id=gateway_key_id
        )
        validate_ordinal_run_isolation(
            reservation_ids=reservation_ids,
            ledger_ids=ledger_ids,
            seen_request_ids=request_ids,
            ordinal=MAX_REQUESTS,
        )
        connection = self._connection_or_fail()
        try:
            key_rows = await connection.fetch(
                "SELECT * FROM gateway_keys WHERE id = $1::uuid",
                gateway_key_id,
            )
            pending = await connection.fetchval(
                """
                SELECT count(*)::int
                FROM quota_reservations
                WHERE gateway_key_id = $1::uuid AND status = 'pending'
                """,
                gateway_key_id,
            )
        except (asyncpg.PostgresError, OSError, TimeoutError):
            raise VerificationError("database_final_query_failure") from None
        validate_final_key_state(
            key_rows=key_rows,
            gateway_key_id=gateway_key_id,
            pending_reservations=int(pending or 0),
        )

    async def close(self) -> None:
        if self._connection is not None:
            try:
                await self._connection.close()
            except (asyncpg.PostgresError, OSError):
                pass
            finally:
                self._connection = None


async def run_live(configuration: LiveConfiguration) -> dict[str, object]:
    database = PostgresProbe(
        configuration.database_target,
        timeout_seconds=configuration.poll_timeout_seconds,
    )
    attempted = 0
    correlated_completed_count = 0
    request_ids: list[str] = []
    seen_diagnostic_ids: set[str] = set()
    correlations: list[dict[str, object]] = []
    total_actual_cost_eur = Decimal("0")
    last_started: float | None = None
    try:
        await database.connect_and_check()
        await database.prepare_fresh_key(
            gateway_key_id=configuration.gateway_key_id,
            gateway_key=configuration.gateway_key,
        )
        timeout = httpx.Timeout(120.0, connect=10.0)
        async with httpx.AsyncClient(
            verify=configuration.ca_file or True,
            follow_redirects=False,
            timeout=timeout,
        ) as client:
            for flow in configuration.flows:
                if last_started is not None:
                    delay = configuration.min_gap_seconds - (time.monotonic() - last_started)
                    if delay > 0:
                        await asyncio.sleep(delay)
                last_started = time.monotonic()
                attempted += 1
                diagnostic_id, terminal = await execute_flow(
                    client,
                    base_url=configuration.gateway_base_url,
                    gateway_key=configuration.gateway_key,
                    flow=flow,
                )
                if diagnostic_id in seen_diagnostic_ids:
                    raise VerificationError("diagnostic_id_duplicate", attempted_requests=attempted)
                seen_diagnostic_ids.add(diagnostic_id)
                correlation = await database.correlate(
                    gateway_request_id=diagnostic_id,
                    gateway_key_id=configuration.gateway_key_id,
                    gateway_key=configuration.gateway_key,
                    flow=flow,
                    expected_usage=terminal.usage,
                    timeout_seconds=configuration.poll_timeout_seconds,
                    interval_seconds=configuration.poll_interval_seconds,
                )
                correlated_completed_count += 1
                request_ids.append(diagnostic_id)
                await database.check_ordinal_isolation(
                    gateway_key_id=configuration.gateway_key_id,
                    seen_request_ids=request_ids,
                    ordinal=correlated_completed_count,
                )
                total_actual_cost_eur += correlation.actual_cost_eur
                if total_actual_cost_eur > configuration.authorization.max_total_cost_eur:
                    raise VerificationError(
                        "authorized_cost_bound_exceeded",
                        attempted_requests=attempted,
                    )
                correlations.append(
                    {
                        "provider": flow.provider,
                        "endpoint": flow.endpoint,
                        "model": flow.model,
                        "streaming": flow.streaming,
                        "http_status": terminal.http_status,
                        "terminal_shape_valid": terminal.terminal_shape_valid,
                        "usage_valid": True,
                        "response_input_tokens": terminal.usage.input_tokens,
                        "response_output_tokens": terminal.usage.output_tokens,
                        "response_total_tokens": terminal.usage.total_tokens,
                        "stored_input_tokens": correlation.stored_usage.input_tokens,
                        "stored_output_tokens": correlation.stored_usage.output_tokens,
                        "stored_total_tokens": correlation.stored_usage.total_tokens,
                        "gateway_request_id_present": True,
                        "reservation_status": "finalized",
                        "accounting_status": "finalized",
                        "cost_source": correlation.cost_source,
                        "cost_confidence": correlation.cost_confidence,
                        "correlated": True,
                    }
                )
        if correlated_completed_count != MAX_REQUESTS:
            raise VerificationError("run_correlated_count_invalid")
        await database.final_run_check(
            request_ids=request_ids,
            gateway_key_id=configuration.gateway_key_id,
        )
        return {
            "result": "ok",
            "real_provider_called": True,
            "real_provider_call_proven": True,
            "attempted_requests": attempted,
            "gateway_requests_attempted": attempted,
            "correlated_completed_count": correlated_completed_count,
            "max_requests": MAX_REQUESTS,
            "providers": list(PROVIDERS),
            "flows": correlations,
            "all_gateway_request_ids_present": True,
            "all_accounting_correlated": True,
            "total_actual_cost_eur_within_authorization": True,
            "live_evidence_scope": "bounded_eight_flow_gateway_and_postgresql_correlation",
        }
    except VerificationError as exc:
        raise VerificationError(
            exc.code,
            attempted_requests=attempted,
            correlated_completed_count=correlated_completed_count,
            real_provider_call_proven=correlated_completed_count > 0,
        ) from None
    finally:
        await database.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gateway-base-url")
    parser.add_argument("--gateway-key-file")
    parser.add_argument("--gateway-key-id")
    parser.add_argument("--database-url-file")
    parser.add_argument("--authorization-file")
    parser.add_argument("--openai-model")
    parser.add_argument("--openrouter-model")
    parser.add_argument("--ca-file")
    parser.add_argument("--min-gap-seconds", default=str(DEFAULT_MIN_GAP_SECONDS))
    parser.add_argument("--poll-timeout-seconds", default=str(POLL_TIMEOUT_SECONDS))
    parser.add_argument("--poll-interval-seconds", default=str(POLL_INTERVAL_SECONDS))
    return parser


def _emit_failure(error: VerificationError) -> int:
    print(
        json.dumps(
            {
                "result": "fail",
                "real_provider_called": error.real_provider_call_proven,
                "real_provider_call_proven": error.real_provider_call_proven,
                "attempted_requests": error.attempted_requests,
                "gateway_requests_attempted": error.attempted_requests,
                "correlated_completed_count": error.correlated_completed_count,
                "max_requests": MAX_REQUESTS,
                "error_code": error.code,
            },
            sort_keys=True,
        )
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        _reject_secret_argv(raw_argv)
    except VerificationError as exc:
        return _emit_failure(exc)
    arguments = _parser().parse_args(argv)
    if arguments.dry_run:
        print(
            json.dumps(
                {
                    "result": "not_run",
                    "real_provider_called": False,
                    "http_requests": 0,
                    "sql_queries": 0,
                    "reason": "guarded_dry_run",
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        configuration = load_live_configuration(arguments)
        result = asyncio.run(run_live(configuration))
    except VerificationError as exc:
        return _emit_failure(exc)
    except Exception:  # noqa: BLE001
        return _emit_failure(VerificationError("internal_failure"))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
