"""Typed key-configuration policy-file and explicit-flag helpers for the CLI.

The policy file is the ONLY source of policy configuration when provided:
any explicitly supplied policy flag is a conflict. Identity, validity,
reason, actor, secret-output, and delivery flags may accompany a file.

Flag explicitness is tracked with click parameter-source callbacks
(verified against the pinned Typer/Click versions): an omitted flag reports
DEFAULT and any explicit form - including ``--no-*`` clear flags - reports
COMMANDLINE. The installed Typer vendors its own Click, so source identity
is compared by the public enum member name rather than class identity.
Error messages use fixed vocabulary and never echo file contents or
operator-supplied values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import typer

from slaif_gateway.schemas.key_configuration import (
    MAX_KEY_CONFIGURATION_FILE_BYTES,
    KeyConfiguration,
    KeyConfigurationError,
    parse_key_configuration_file,
)

_POLICY_SOURCE_META_KEY = "slaif_policy_sources"

#: Sentinel for "provider flags were not used at all" (distinct from the
#: explicit unrestricted value ``None``).
PROVIDER_ABSENT = object()

#: Policy flags that conflict with a policy file (fixed vocabulary).
POLICY_FILE_CONFLICT_FLAG_NAMES: frozenset[str] = frozenset(
    {
        "allowed_models",
        "allowed_endpoints",
        "allow_all_models",
        "allow_all_endpoints",
        "allowed_providers",
        "provider_all",
        "provider_none",
        "cost_limit_eur",
        "token_limit_total",
        "request_limit_total",
        "rate_limit_requests_per_minute",
        "rate_limit_tokens_per_minute",
        "rate_limit_concurrent_requests",
        "rate_limit_window_seconds",
        "chat_streaming_live_burn_enabled",
        "chat_streaming_live_burn_cost_margin_eur",
        "chat_streaming_live_burn_token_margin",
        "external_tool_mode",
        "external_tool_capabilities",
        "external_tool_destination_ids",
        "external_tool_max_calls",
        "acknowledge_single_request_overrun",
        "trusted_calibration",
        "confirm_trusted_calibration",
    }
)

#: Operation acknowledgements that may accompany a policy file (explicit
#: confirmation controls, not policy data). The file's own
#: ``confirm_external_tool_fenced`` field wins when it is present; the
#: explicit CLI flag supplies the confirmation when the file omits it.
OPERATION_CONFIRMATION_FLAG_NAMES: frozenset[str] = frozenset({"confirm_external_tool_fenced"})


def policy_source_callback(
    ctx: click.Context, param: click.Parameter, value: Any
) -> Any:
    """Record whether one tracked flag was explicitly supplied."""
    meta = ctx.meta.setdefault(_POLICY_SOURCE_META_KEY, {})
    if param is not None and param.name:
        source = ctx.get_parameter_source(param.name)
        # Compare by the enum member NAME, not class identity: the installed
        # Typer vendors its own Click, so the ParameterSource returned by
        # get_parameter_source() is a different enum class than the external
        # ``click.core.ParameterSource`` imported here.
        meta[param.name] = getattr(source, "name", None) == "COMMANDLINE"
    return value


def policy_sources(ctx: typer.Context | None) -> dict[str, bool]:
    """Explicitness map for the current command invocation."""
    if ctx is None:
        return {}
    sources = ctx.meta.get(_POLICY_SOURCE_META_KEY, {})
    return dict(sources) if isinstance(sources, dict) else {}


def was_explicit(sources: dict[str, bool], name: str) -> bool:
    return bool(sources.get(name, False))


def read_policy_file(path: Path | str) -> KeyConfiguration:
    """Read one bounded policy file and strictly parse it (safe errors).

    At most limit+1 bytes are ever read, so an oversized file is rejected
    without materializing its full content. Messages are fixed vocabulary;
    they never echo file bodies, paths, or operator-supplied values.
    """
    file_path = Path(path)
    try:
        with file_path.open("rb") as handle:
            data = handle.read(MAX_KEY_CONFIGURATION_FILE_BYTES + 1)
    except OSError as exc:
        raise typer.BadParameter("The policy file is not readable.") from exc
    if len(data) > MAX_KEY_CONFIGURATION_FILE_BYTES:
        raise typer.BadParameter("The policy file exceeds the size limit.")
    try:
        return parse_key_configuration_file(data)
    except KeyConfigurationError as exc:
        raise typer.BadParameter(str(exc)) from exc


def validate_policy_file_conflicts(sources: dict[str, bool]) -> None:
    """Reject a policy file combined with any explicit policy flag."""
    if not was_explicit(sources, "policy_file"):
        return
    for name in sorted(POLICY_FILE_CONFLICT_FLAG_NAMES):
        if was_explicit(sources, name):
            raise typer.BadParameter(
                "The policy file is the only source of policy configuration; "
                "remove the explicit policy flags. Identity, validity, reason, "
                "actor, output, and delivery flags may accompany the file."
            )


def provider_flags_value(
    sources: dict[str, bool],
    *,
    allowed_providers: list[str] | None,
    provider_all: bool,
    provider_none: bool,
) -> object:
    """Resolve the mutually exclusive provider flags.

    Returns :data:`PROVIDER_ABSENT` when none was used, ``None`` for the
    explicit unrestricted choice, ``[]`` for the explicit deny-all choice,
    or the explicit allow-list.
    """
    explicit = [
        name
        for name in ("allowed_providers", "provider_all", "provider_none")
        if was_explicit(sources, name)
    ]
    if len(explicit) > 1:
        raise typer.BadParameter(
            "Use exactly one of --allowed-provider, --provider-all, or "
            "--provider-none."
        )
    if not explicit:
        return PROVIDER_ABSENT
    if explicit[0] == "provider_all":
        return None
    if explicit[0] == "provider_none":
        return []
    return list(allowed_providers or [])


def build_configuration_from_explicit_flags(
    sources: dict[str, bool],
    *,
    allowed_models: list[str] | None,
    allowed_endpoints: list[str] | None,
    allow_all_models: bool,
    allow_all_endpoints: bool,
) -> KeyConfiguration:
    """Project explicit request-policy flags into a presence-aware config."""
    config = KeyConfiguration()
    if was_explicit(sources, "allowed_models"):
        config.allowed_models = list(allowed_models or [])
    if was_explicit(sources, "allowed_endpoints"):
        config.allowed_endpoints = list(allowed_endpoints or [])
    if was_explicit(sources, "allow_all_models"):
        config.allow_all_models = allow_all_models
    if was_explicit(sources, "allow_all_endpoints"):
        config.allow_all_endpoints = allow_all_endpoints
    return config
