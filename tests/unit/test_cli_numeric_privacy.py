"""205-b — no-echo numeric input boundaries for the 17 observed CLI positions.

The accepted installed product (source 5e59a02) echoed complete recognized
credential-shaped strings in option-level integer parse errors for the
new/extended numeric options below (root receipts
205-installed-lazy-numeric-canary-probe.json and
205-installed-new-numeric-surface-canary-probe.json; root scope decision
205-numeric-privacy-scope-decision.json). The CLI now converts raw numeric
option strings through the shared no-echo helper
(`slaif_gateway.cli.common.parse_int_option`) BEFORE any database,
provider, queue, or SMTP access.

These are command-boundary unit checks with mocked command captures (no
database/provider/queue/SMTP): invalid input fails with a fixed message
naming only the option — never the value, never a traceback — and valid
input converts to the SAME int payloads as the previous option-level
conversion, including 0, signed values, and omitted/None semantics.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import uuid
from pathlib import Path
from typing import Any, Callable

import pytest
import typer
from typer.testing import CliRunner

from slaif_gateway.cli import codex_replay as codex_replay_cli
from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli import providers as providers_cli
from slaif_gateway.cli import routes as routes_cli
from slaif_gateway.cli.common import parse_int_option
from slaif_gateway.cli.main import app

runner = CliRunner()

# Renderer-stable terminal + ANSI/whitespace-independent assertions
# (established project pattern: tests/unit/test_cli.py,
# tests/unit/test_cli_provider_route_configuration.py). The app renders
# Click usage errors through a rich error panel, whose ANSI styling and
# width-dependent wrapping are terminal properties, not product behavior;
# comparisons below are therefore style-independent.
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TERM_ENV = {"COLUMNS": "220", "NO_COLOR": "1"}


def _plain(text: str) -> str:
    return " ".join(_ANSI_RE.sub("", text).split())


def _invoke(*args: Any, **kwargs: Any) -> Any:
    """Renderer-stable invocation (fixed terminal width, no color)."""
    kwargs.setdefault("env", TERM_ENV)
    return runner.invoke(*args, **kwargs)

KEY_ID = str(uuid.uuid4())
ROUTE_ID = str(uuid.uuid4())
OWNER_ID = str(uuid.uuid4())
SOURCE_ID = str(uuid.uuid4())


class _SentinelReached(Exception):
    """Raised by capture sentinels if the flow reaches the operation layer."""


def _sentinel_async(seen: list[dict[str, Any]]) -> Callable[..., Any]:
    async def _sentinel(*args: Any, **kwargs: Any) -> Any:
        seen.append(dict(kwargs))
        raise _SentinelReached(f"operation layer reached: {sorted(kwargs)}")

    return _sentinel


def _sentinel_factory(seen: list[Any]) -> Callable[[], Any]:
    def _sentinel() -> Any:
        seen.append(object())
        raise _SentinelReached("db session factory reached")

    return _sentinel


class Position:
    """One observed numeric option position and its fixed-refusal oracle."""

    def __init__(
        self,
        name: str,
        argv: Callable[[str, Path], list[str]],
        sentinel: tuple[str, str],
        exit_code: int,
        fixed_substring: str,
        json_error: bool = False,
    ) -> None:
        self.name = name
        self.argv = argv
        self.sentinel = sentinel
        self.exit_code = exit_code
        self.fixed_substring = fixed_substring
        self.json_error = json_error

    def monkeypatch_sentinel(self, monkeypatch, seen: list[Any]) -> None:
        module_name, attr = self.sentinel
        module = {
            "slaif_gateway.cli.keys": keys_cli,
            "slaif_gateway.cli.providers": providers_cli,
            "slaif_gateway.cli.routes": routes_cli,
            "slaif_gateway.cli.codex_replay": codex_replay_cli,
        }[module_name]
        if attr == "cli_db_session":
            monkeypatch.setattr(module, attr, _sentinel_factory(seen))
        else:
            monkeypatch.setattr(module, attr, _sentinel_async(seen))


def _argv_clone(canary: str, tmp: Path) -> list[str]:
    return [
        "keys", "clone",
        "--dry-run", str(tmp / "plan.json"),
        "--source-key-id", SOURCE_ID,
        "--target-owner-id", OWNER_ID,
        "--validity-mode", "duration-from-now",
        "--validity-duration-seconds", canary,
        "--json",
    ]


def _argv_list_limit(canary: str, tmp: Path) -> list[str]:
    return ["keys", "list", "--limit", canary]


def _argv_list_offset(canary: str, tmp: Path) -> list[str]:
    return ["keys", "list", "--offset", canary]


def _argv_lazy_wait(canary: str, tmp: Path) -> list[str]:
    return [
        "keys", "set-lazy-throttling", KEY_ID,
        "--mode", "wait",
        "--max-wait-seconds", canary,
        "--max-waiting-requests", "4",
        "--reason", "205b numeric boundary probe",
    ]


def _argv_lazy_waiting(canary: str, tmp: Path) -> list[str]:
    return [
        "keys", "set-lazy-throttling", KEY_ID,
        "--mode", "wait",
        "--max-wait-seconds", "30",
        "--max-waiting-requests", canary,
        "--reason", "205b numeric boundary probe",
    ]


def _argv_provider_add_timeout(canary: str, tmp: Path) -> list[str]:
    return [
        "providers", "add", "--provider", "probe-provider",
        "--api-key-env-var", "PROBE_UPSTREAM_KEY",
        "--timeout-seconds", canary,
    ]


def _argv_provider_add_retries(canary: str, tmp: Path) -> list[str]:
    return [
        "providers", "add", "--provider", "probe-provider",
        "--api-key-env-var", "PROBE_UPSTREAM_KEY",
        "--max-retries", canary,
    ]


def _argv_provider_update_timeout(canary: str, tmp: Path) -> list[str]:
    return [
        "providers", "update", "probe-provider",
        "--reason", "205b numeric boundary probe",
        "--timeout-seconds", canary,
    ]


def _argv_provider_update_retries(canary: str, tmp: Path) -> list[str]:
    return [
        "providers", "update", "probe-provider",
        "--reason", "205b numeric boundary probe",
        "--max-retries", canary,
    ]


def _argv_route_update(flag: str):
    def _argv(canary: str, tmp: Path) -> list[str]:
        return [
            "routes", "update", ROUTE_ID,
            "--dry-run", str(tmp / "route-plan.json"),
            flag, canary,
        ]

    return _argv


POSITIONS = [
    Position("clone.validity_duration_seconds", _argv_clone,
             ("slaif_gateway.cli.keys", "_build_clone_plan_document"), 1,
             "--validity-duration-seconds must be a whole number", json_error=True),
    Position("keys_list.limit", _argv_list_limit,
             ("slaif_gateway.cli.keys", "_list_gateway_keys"), 2,
             "--limit must be a whole number"),
    Position("keys_list.offset", _argv_list_offset,
             ("slaif_gateway.cli.keys", "_list_gateway_keys"), 2,
             "--offset must be a whole number"),
    Position("set_lazy.max_wait_seconds", _argv_lazy_wait,
             ("slaif_gateway.cli.keys", "_update_lazy_throttling"), 2,
             "--max-wait-seconds must be a whole number"),
    Position("set_lazy.max_waiting_requests", _argv_lazy_waiting,
             ("slaif_gateway.cli.keys", "_update_lazy_throttling"), 2,
             "--max-waiting-requests must be a whole number"),
    Position("providers_add.timeout_seconds", _argv_provider_add_timeout,
             ("slaif_gateway.cli.providers", "_add_provider"), 2,
             "--timeout-seconds must be a whole number"),
    Position("providers_add.max_retries", _argv_provider_add_retries,
             ("slaif_gateway.cli.providers", "_add_provider"), 2,
             "--max-retries must be a whole number"),
    Position("providers_update.timeout_seconds", _argv_provider_update_timeout,
             ("slaif_gateway.cli.providers", "_update_provider"), 2,
             "--timeout-seconds must be a whole number"),
    Position("providers_update.max_retries", _argv_provider_update_retries,
             ("slaif_gateway.cli.providers", "_update_provider"), 2,
             "--max-retries must be a whole number"),
    Position("routes_update.codex_context_window_tokens",
             _argv_route_update("--codex-context-window-tokens"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--codex-context-window-tokens must be a whole number"),
    Position("routes_update.codex_default_max_output_tokens",
             _argv_route_update("--codex-default-max-output-tokens"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--codex-default-max-output-tokens must be a whole number"),
    Position("routes_update.codex_max_output_tokens",
             _argv_route_update("--codex-max-output-tokens"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--codex-max-output-tokens must be a whole number"),
    Position("routes_update.media_image_tokens",
             _argv_route_update("--media-image-tokens"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--media-image-tokens must be a whole number"),
    Position("routes_update.media_video_tokens",
             _argv_route_update("--media-video-tokens"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--media-video-tokens must be a whole number"),
    Position("routes_update.media_video_frames",
             _argv_route_update("--media-video-frames"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--media-video-frames must be a whole number"),
    Position("routes_update.priority",
             _argv_route_update("--priority"),
             ("slaif_gateway.cli.routes", "_preview_route_update_plan"), 2,
             "--priority must be a whole number"),
    Position("replay_extend.ttl_seconds",
             lambda canary, tmp: [
                 "codex", "replay", "extend",
                 "--key-id", KEY_ID,
                 "--output", str(tmp / "replay-plan.json"),
                 "--ttl-seconds", canary,
             ],
             ("slaif_gateway.cli.codex_replay", "cli_db_session"), 2,
             "--ttl-seconds must be a whole number"),
]

# Invalid VALUE SHAPES (in addition to the credential-shaped canary, which
# gets its own full-absence assertions): float, bool-like, blank, and a
# digit string beyond Python's integer-string conversion limit.
INVALID_SHAPES = [
    pytest.param("1.5", id="float"),
    pytest.param("true", id="bool-like"),
    pytest.param(" ", id="blank"),
    pytest.param("9" * 5000, id="huge-digits"),
]


def _fixed_output(result, position: Position) -> str:
    if position.json_error:
        # JSON error payloads are plain stdout (no terminal rendering).
        return result.stdout
    # Terminal-rendered usage errors: compare style-independently.
    return _plain(result.stderr)


@pytest.mark.parametrize("position", POSITIONS, ids=[p.name for p in POSITIONS])
def test_position_rejects_credential_shaped_canary_without_echo(
    position: Position, monkeypatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """The observed defect: a recognized credential-shaped value must fail
    with the fixed option message and never be echoed in full.

    All failure representations are booleans or fixed labels: a regression
    must not make pytest's assertion rewrite print the canary or the raw
    output.
    """
    canary = "sk-proj-205b-" + secrets.token_hex(12)
    seen: list[Any] = []
    position.monkeypatch_sentinel(monkeypatch, seen)
    with caplog.at_level(logging.DEBUG):
        result = _invoke(app, position.argv(canary, tmp_path))

    operation_reached = len(seen) > 0
    exit_matches = result.exit_code == position.exit_code
    fixed_message_present = position.fixed_substring in _fixed_output(result, position)
    canary_in_stdout = canary in result.stdout
    canary_in_stderr = canary in result.stderr
    canary_in_logs = canary in caplog.text
    caplog.clear()  # never let a raw Captured log section appear on failure
    traceback_present = "Traceback" in (result.stdout + result.stderr)
    json_error_ok = True
    if position.json_error:
        try:
            payload = json.loads(result.stdout)
            error = payload.get("error", {})
            json_error_ok = (
                error.get("code") == "invalid_parameter"
                and error.get("message")
                == "--validity-duration-seconds must be a whole number"
            )
        except (AttributeError, json.JSONDecodeError):
            json_error_ok = False

    assert not operation_reached, "invalid numeric input reached the operation layer"
    assert exit_matches, "fixed refusal exit code changed"
    assert fixed_message_present, "fixed option-level refusal message missing"
    assert not (canary_in_stdout or canary_in_stderr or canary_in_logs), (
        "credential-shaped canary leaked into output or logs"
    )
    assert not traceback_present, "traceback leaked into CLI output"
    if position.json_error:
        assert json_error_ok, "--json error mapping is not the fixed invalid_parameter shape"


@pytest.mark.parametrize("position", POSITIONS, ids=[p.name for p in POSITIONS])
@pytest.mark.parametrize("shape", INVALID_SHAPES)
def test_position_rejects_invalid_shapes_with_fixed_message(
    position: Position, shape: str, monkeypatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    seen: list[Any] = []
    position.monkeypatch_sentinel(monkeypatch, seen)
    with caplog.at_level(logging.DEBUG):
        result = _invoke(app, position.argv(shape, tmp_path))

    value = shape.strip()
    operation_reached = len(seen) > 0
    exit_matches = result.exit_code == position.exit_code
    fixed_message_present = position.fixed_substring in _fixed_output(result, position)
    value_echoed = len(value) >= 3 and value in _fixed_output(result, position)
    value_in_logs = len(value) >= 3 and value in caplog.text
    caplog.clear()  # never let a raw Captured log section appear on failure
    traceback_present = "Traceback" in (result.stdout + result.stderr)

    assert not operation_reached, "invalid numeric input reached the operation layer"
    assert exit_matches, "fixed refusal exit code changed"
    assert fixed_message_present, "fixed option-level refusal message missing"
    assert not value_echoed, "supplied value quoted back in the fixed error"
    assert not value_in_logs, "supplied value leaked into logs"
    assert not traceback_present, "traceback leaked into CLI output"


# ---------------------------------------------------------------------------
# Valid-value payload controls (mocked command captures): the conversion
# preserves the SAME int payloads, 0, signed values, and omitted/None.
# ---------------------------------------------------------------------------


def test_keys_list_valid_int_payloads_and_explicit_zero(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []

    async def fake_list(**kwargs: Any) -> list[Any]:
        seen.append(dict(kwargs))
        return []

    monkeypatch.setattr(keys_cli, "_list_gateway_keys", fake_list)

    result = _invoke(app, ["keys", "list", "--limit", "1", "--offset", "0", "--json"])
    assert result.exit_code == 0
    assert len(seen) == 1
    # 197-b bounded lookahead: the operation layer receives limit + 1 so the
    # true end of the result set is known; the converted int payload is the
    # operator value plus that documented lookahead, offset unchanged.
    assert seen[0]["limit"] == 2 and type(seen[0]["limit"]) is int
    assert seen[0]["offset"] == 0 and type(seen[0]["offset"]) is int
    paging = json.loads(result.stdout)["paging"]
    assert paging["limit"] == 1 and paging["offset"] == 0

    # Explicit 0 is DISTINCT from omitted: it reaches the existing domain
    # law (positive limit) and is refused, never coerced to the default.
    result_zero = _invoke(app, ["keys", "list", "--limit", "0"])
    assert result_zero.exit_code == 2
    assert "--limit must be positive" in _plain(result_zero.stderr)
    assert len(seen) == 1  # refused before any operation call


def test_keys_list_omitted_uses_documented_defaults(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []

    async def fake_list(**kwargs: Any) -> list[Any]:
        seen.append(dict(kwargs))
        return []

    monkeypatch.setattr(keys_cli, "_list_gateway_keys", fake_list)

    result = _invoke(app, ["keys", "list", "--json"])
    assert result.exit_code == 0
    assert seen[0]["limit"] == 51 and type(seen[0]["limit"]) is int
    assert seen[0]["offset"] == 0 and type(seen[0]["offset"]) is int
    assert json.loads(result.stdout)["paging"]["limit"] == 50


def test_set_lazy_wait_converts_both_bounds_to_int(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(keys_cli, "_update_lazy_throttling", _sentinel_async(seen))

    result = _invoke(
        app,
        [
            "keys", "set-lazy-throttling", KEY_ID,
            "--mode", "wait",
            "--max-wait-seconds", "30",
            "--max-waiting-requests", "4",
            "--reason", "205b valid lazy control",
        ],
    )
    # The sentinel stops the flow after capture; the point is the converted
    # policy payload that the operation layer would have received.
    assert result.exit_code == 1
    assert len(seen) == 1
    policy = seen[0]["policy"]
    assert policy == {
        "mode": "wait",
        "max_wait_seconds": 30,
        "max_waiting_requests": 4,
    }
    assert type(policy["max_wait_seconds"]) is int
    assert type(policy["max_waiting_requests"]) is int


def test_clone_converts_duration_to_int_and_keeps_domain_law(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", _sentinel_async(seen))

    result = _invoke(
        app,
        [
            "keys", "clone",
            "--dry-run", "/tmp/205b-clone-plan.json",
            "--source-key-id", SOURCE_ID,
            "--target-owner-id", OWNER_ID,
            "--validity-mode", "duration-from-now",
            "--validity-duration-seconds", "3600",
            "--json",
        ],
    )
    assert result.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 1
    assert seen[0]["validity_duration_seconds"] == 3600
    assert type(seen[0]["validity_duration_seconds"]) is int

    # Explicit 0 is still refused by the existing positive-duration law.
    result_zero = _invoke(
        app,
        [
            "keys", "clone",
            "--dry-run", "/tmp/205b-clone-plan.json",
            "--source-key-id", SOURCE_ID,
            "--target-owner-id", OWNER_ID,
            "--validity-mode", "duration-from-now",
            "--validity-duration-seconds", "0",
            "--json",
        ],
    )
    assert result_zero.exit_code == 1
    payload = json.loads(result_zero.stdout)
    assert payload["error"]["code"] == "invalid_parameter"
    assert "must be positive" in payload["error"]["message"]
    assert len(seen) == 1  # no extra operation call


def test_providers_add_converts_timeout_and_retry_zero(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(providers_cli, "_add_provider", _sentinel_async(seen))

    result = _invoke(
        app,
        [
            "providers", "add", "--provider", "probe-provider",
            "--api-key-env-var", "PROBE_UPSTREAM_KEY",
            "--timeout-seconds", "45",
            "--max-retries", "0",
        ],
    )
    assert result.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 1
    assert seen[0]["timeout_seconds"] == 45 and type(seen[0]["timeout_seconds"]) is int
    assert seen[0]["max_retries"] == 0 and type(seen[0]["max_retries"]) is int


def test_providers_update_converts_and_keeps_omitted_none(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(providers_cli, "_update_provider", _sentinel_async(seen))

    result = _invoke(
        app,
        [
            "providers", "update", "probe-provider",
            "--reason", "205b valid provider control",
            "--timeout-seconds", "30",
            "--max-retries", "0",
        ],
    )
    assert result.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 1
    assert seen[0]["timeout_seconds"] == 30 and type(seen[0]["timeout_seconds"]) is int
    assert seen[0]["max_retries"] == 0 and type(seen[0]["max_retries"]) is int

    result_omitted = _invoke(
        app,
        [
            "providers", "update", "probe-provider",
            "--reason", "205b omitted numerics control",
            "--notes", "probe notes",
        ],
    )
    assert result_omitted.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 2
    assert seen[1]["timeout_seconds"] is None
    assert seen[1]["max_retries"] is None


def test_routes_update_converts_signed_priority_and_tokens(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(routes_cli, "_preview_route_update_plan", _sentinel_async(seen))

    result = _invoke(
        app,
        [
            "routes", "update", ROUTE_ID,
            "--dry-run", "/tmp/205b-route-plan.json",
            "--priority", "-5",
            "--codex-max-output-tokens", "400000",
        ],
    )
    assert result.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 1
    assert seen[0]["priority"] == -5 and type(seen[0]["priority"]) is int
    patch = seen[0]["capability_patch"]
    assert patch is not None
    assert patch.codex_limits == {"max_output_tokens": 400000}
    assert type(patch.codex_limits["max_output_tokens"]) is int

    # Omitted numerics stay None (no default injected into a partial patch).
    result_omitted = _invoke(
        app,
        [
            "routes", "update", ROUTE_ID,
            "--dry-run", "/tmp/205b-route-plan.json",
            "--notes", "probe notes",
        ],
    )
    assert result_omitted.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 2
    assert seen[1]["priority"] is None
    assert seen[1]["capability_patch"] is None


def test_replay_extend_converts_ttl_and_keeps_omitted_none(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    seen: list[dict[str, Any]] = []

    @asynccontextmanager
    async def fake_db() -> Any:
        yield "token", object()

    class FakeService:
        async def preview_replay_extend(self, **kwargs: Any) -> Any:
            seen.append(dict(kwargs))
            raise _SentinelReached("preview reached after capture")

    monkeypatch.setattr(codex_replay_cli, "cli_db_session", lambda: fake_db())
    monkeypatch.setattr(codex_replay_cli, "_service", lambda session: FakeService())

    result = _invoke(
        app,
        [
            "codex", "replay", "extend",
            "--key-id", KEY_ID,
            "--output", "/tmp/205b-replay-plan.json",
            "--ttl-seconds", "3600",
        ],
    )
    assert result.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 1
    assert seen[0]["ttl_seconds"] == 3600 and type(seen[0]["ttl_seconds"]) is int

    result_omitted = _invoke(
        app,
        [
            "codex", "replay", "extend",
            "--key-id", KEY_ID,
            "--output", "/tmp/205b-replay-plan.json",
        ],
    )
    assert result_omitted.exit_code == 1  # sentinel stop after capture
    assert len(seen) == 2
    assert seen[1]["ttl_seconds"] is None


# ---------------------------------------------------------------------------
# Shared helper: Click-parity conversion and fixed no-echo refusals.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0),
        ("1", 1),
        ("-3", -3),
        ("+7", 7),
        ("007", 7),
        (" 12 ", 12),
        ("1_000", 1000),
    ],
)
def test_parse_int_option_click_parity(raw: str, expected: int) -> None:
    assert parse_int_option(raw, field_name="--probe") == expected


def test_parse_int_option_omitted_returns_default() -> None:
    assert parse_int_option(None, field_name="--probe") is None
    assert parse_int_option(None, field_name="--probe", default=5) == 5


@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "sk-proj-205b-deadbeef",
        "1.5",
        "true",
        "",
        " ",
        "1e3",
        "0x10",
        "9" * 5000,
    ],
)
def test_parse_int_option_invalid_fails_fixed_without_echo(raw: str) -> None:
    with pytest.raises(typer.BadParameter) as excinfo:
        parse_int_option(raw, field_name="--probe")
    message = str(excinfo.value)
    assert message == "--probe must be a whole number"
    if raw.strip():
        assert raw not in message
