"""Unit tests for the demo-admin CLI and fake-admin account service boundary.

Objective 220 foundation. No database is touched: the CLI layer is tested
against a stubbed session/service pair, and the service layer against a
stubbed repository. Credential canaries prove that no plaintext password,
salted hash, DB URL, or user-supplied value can reach CLI output.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError
from typer.testing import CliRunner

from slaif_gateway.cli.demo_admin import app as demo_admin_app
from slaif_gateway.cli.main import app as root_app
from slaif_gateway.services.fake_admin_accounts import (
    PASSWORD_MAX_LENGTH,
    FakeAdminAccountEnabledResult,
    FakeAdminAccountError,
    FakeAdminAccountListResult,
    FakeAdminAccountProjection,
    FakeAdminAccountService,
    validate_demo_admin_password,
    validate_demo_admin_password_matches_username,
    validate_demo_admin_reason,
    validate_demo_admin_username,
)

RUNNER = CliRunner()

CANARY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdWNhbmFyeQ$canary-hash-never-leak"
CANARY_PASSWORD = "canary-demo-password-220a-0123456789"
CANARY_DSN = "postgresql+asyncpg://test-secret:test-secret@127.0.0.1:5432/test"

_STDIN_REFUSED = (
    "stdin password must be a single line of at most "
    f"{PASSWORD_MAX_LENGTH} characters with no extra data."
)


# --- stubs -----------------------------------------------------------------


def _projection(
    username: str = "demoalice", *, enabled: bool = True, generation: int = 0
) -> FakeAdminAccountProjection:
    now = datetime.now(UTC)
    return FakeAdminAccountProjection(
        id=uuid.uuid4(),
        username=username,
        is_enabled=enabled,
        credential_generation=generation,
        created_at=now,
        updated_at=now,
    )


class _StubService:
    """Records calls; never touches a database."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def create_account(self, *, username: str, password: str, reason: str):
        self.calls.append(("create", username, password, reason))
        return _projection(username)

    async def list_accounts(self, *, limit: int, offset: int):
        self.calls.append(("list", limit, offset))
        return FakeAdminAccountListResult(
            items=(_projection(), _projection("bob-demo-2", enabled=False, generation=3)),
            limit=limit,
            offset=offset,
            active_account_count=1,
        )

    async def set_enabled(self, *, username: str, enabled: bool, reason: str):
        self.calls.append(("set_enabled", username, enabled, reason))
        return FakeAdminAccountEnabledResult(projection=_projection(username), state_changed=enabled)

    async def reset_password(self, *, username: str, password: str, reason: str):
        self.calls.append(("reset_password", username, password, reason))
        return _projection(username)


@asynccontextmanager
async def _stub_db_session():
    yield (None, None)


def _patch_cli(monkeypatch, stub: _StubService) -> None:
    monkeypatch.setattr("slaif_gateway.cli.demo_admin.cli_db_session", _stub_db_session)
    monkeypatch.setattr("slaif_gateway.cli.demo_admin._service", lambda session: stub)


def _safe_fields(payload: dict) -> set[str]:
    allowed = {
        "id",
        "username",
        "is_enabled",
        "credential_generation",
        "created_at",
        "updated_at",
        "created",
        "reset",
        "state_changed",
        "items",
        "limit",
        "offset",
        "active_account_count",
    }
    assert set(payload) <= allowed, f"unsafe fields in payload: {sorted(set(payload) - allowed)}"


def _json_output(output: str) -> dict:
    """Parse the JSON payload; hidden prompts label lines BEFORE the JSON."""
    for line in reversed([ln for ln in output.splitlines() if ln.strip()]):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise AssertionError(f"no JSON payload in output: {output!r}")


# --- CLI registration -------------------------------------------------------


def test_root_cli_registers_demo_admin_group() -> None:
    result = RUNNER.invoke(root_app, ["demo-admin", "--help"])
    assert result.exit_code == 0
    for command in ("create", "list", "enable", "disable", "reset-password"):
        assert command in result.output


def test_no_literal_password_argv_option_anywhere() -> None:
    for args in (["create", "--help"], ["reset-password", "--help"]):
        result = RUNNER.invoke(demo_admin_app, args)
        assert result.exit_code == 0
        assert "--password-stdin" in result.output
        # No literal `--password` argv option (only `--password-stdin`).
        for line in result.output.splitlines():
            stripped = line.strip()
            assert not stripped.startswith("--password "), stripped


# --- validator law ----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["ab", "a" * 65, "1abc", "a b", "ab.c", "ab c", "üser"],
)
def test_username_invalid_shapes_are_fixed_and_unechoed(value: str) -> None:
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_username(value)
    assert excinfo.value.code == "demo_admin_username_invalid"
    assert value not in excinfo.value.safe_message


def test_username_normalization_and_valid_shapes() -> None:
    assert validate_demo_admin_username("  abc  ") == "abc"
    assert validate_demo_admin_username("Demo-User_9") == "Demo-User_9"
    assert validate_demo_admin_username("a" * 64) == "a" * 64


def test_credential_shaped_username_is_withheld_without_echo() -> None:
    value = "Bearer abcdef1234567890"
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_username(value)
    assert excinfo.value.code == "demo_admin_username_withheld"
    assert value not in excinfo.value.safe_message


@pytest.mark.parametrize("value", ["a" * 15, "a" * 129])
def test_password_length_bounds(value: str) -> None:
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_password(value)
    assert excinfo.value.code == "demo_admin_password_invalid"
    assert value not in excinfo.value.safe_message


def test_password_accepts_documented_minimum_and_maximum() -> None:
    validate_demo_admin_password("a" * PASSWORD_MAX_LENGTH)
    validate_demo_admin_password("password12345678")


def test_credential_shaped_password_is_withheld_without_echo() -> None:
    value = "sk-proj-ABCDEFGHIJKLMNOP123456789"
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_password(value)
    assert excinfo.value.code == "demo_admin_password_withheld"
    assert value not in excinfo.value.safe_message


def test_password_equal_to_username_is_refused() -> None:
    username = "abcdefghijklmnop"
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_password_matches_username(username, username)
    assert excinfo.value.code == "demo_admin_password_invalid"


@pytest.mark.parametrize("value", ["", "a" * 513])
def test_reason_bounds(value: str) -> None:
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_reason(value)
    assert excinfo.value.code == "demo_admin_reason_invalid"


def test_credential_shaped_reason_is_withheld_without_echo() -> None:
    value = "rotate, Authorization: Bearer secrettoken123456"
    with pytest.raises(FakeAdminAccountError) as excinfo:
        validate_demo_admin_reason(value)
    assert excinfo.value.code == "demo_admin_reason_withheld"
    assert value not in excinfo.value.safe_message


# --- CLI create: prompt + stdin channels ------------------------------------


def test_create_hidden_prompt_success_and_safe_output(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["create", "demoalice", "--reason", "initial setup", "--json"],
        input=f"{CANARY_PASSWORD}\n{CANARY_PASSWORD}\n",
    )
    assert result.exit_code == 0
    payload = _json_output(result.output)
    _safe_fields(payload)
    assert payload["username"] == "demoalice"
    assert payload["created"] is True
    assert payload["credential_generation"] == 0
    assert payload["is_enabled"] is True
    assert CANARY_PASSWORD not in result.output
    assert CANARY_HASH not in result.output
    assert "password" not in {key.lower() for key in payload}
    (kind, username, password, reason) = stub.calls[0]
    assert (kind, username, password, reason) == (
        "create",
        "demoalice",
        CANARY_PASSWORD,
        "initial setup",
    )


def test_create_prompt_mismatch_is_fixed_and_writes_nothing(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["create", "demoalice", "--reason", "x", "--json"],
        input="abcdefghijklmnop0123\nabcdefghijklmnop9999\n",
    )
    assert result.exit_code == 1
    payload = _json_output(result.output)
    assert payload == {
        "error": {"code": "invalid_parameter", "message": "Password confirmation mismatch."}
    }
    assert "abcdefghijklmnop0123" not in result.output
    assert stub.calls == []


def test_create_password_stdin_single_line_accepted(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["create", "demoalice", "--reason", "x", "--password-stdin", "--json"],
        input=f"{CANARY_PASSWORD}\n",
    )
    assert result.exit_code == 0
    (kind, username, password, reason) = stub.calls[0]
    assert password == CANARY_PASSWORD  # no trailing newline
    assert CANARY_PASSWORD not in result.output


# SECOND_LINE_SENTINEL / TRAILING_SENTINEL are unique so the no-echo
# assertion cannot collide with the fixed safe message wording.
SECOND_LINE_SENTINEL = "zzsecondline220a-sentinel-9f3c"
TRAILING_SENTINEL = "zztrailing220a-sentinel-71b4"


@pytest.mark.parametrize(
    "stdin_payload,forbidden_sentinel",
    [
        ("a" * (PASSWORD_MAX_LENGTH + 1) + "\n", None),  # oversized first line
        ("a" * (PASSWORD_MAX_LENGTH + 1), None),  # oversized, no trailing newline
        (f"abcdefghijklmnop0123\n{SECOND_LINE_SENTINEL}\n", SECOND_LINE_SENTINEL),
        (f"abcdefghijklmnop0123\n{TRAILING_SENTINEL}", TRAILING_SENTINEL),
    ],
)
def test_create_password_stdin_rejects_oversized_and_extra_data(
    monkeypatch, stdin_payload: str, forbidden_sentinel: str | None
) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["create", "demoalice", "--reason", "x", "--password-stdin", "--json"],
        input=stdin_payload,
    )
    assert result.exit_code == 1
    payload = _json_output(result.output)
    assert payload == {
        "error": {"code": "invalid_parameter", "message": _STDIN_REFUSED}
    }
    # No user value echoed, and zero writes: the service was never reached.
    if forbidden_sentinel is not None:
        assert forbidden_sentinel not in result.output
    assert stub.calls == []


def test_create_password_stdin_crlf_single_line_accepted_via_text_transport(
    monkeypatch,
) -> None:
    """Ordinary text-mode stdin normalizes a single CRLF line to one LF.

    CliRunner (like ordinary Python text stdin) applies universal-newline
    translation, so ``"pw\r\n"`` arrives as the accepted single line
    ``"pw\n"`` — tested honestly as acceptance, not rejection.
    """
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["create", "demoalice", "--reason", "x", "--password-stdin", "--json"],
        input=f"{CANARY_PASSWORD}\r\n",
    )
    assert result.exit_code == 0
    (kind, username, password, reason) = stub.calls[0]
    assert password == CANARY_PASSWORD  # \r normalized away by the transport
    assert CANARY_PASSWORD not in result.output


def test_stdin_reader_rejects_untranslated_carriage_return(monkeypatch) -> None:
    """A \\r that SURVIVES the transport (no universal-newline translation)
    is malformed input and refused by the bounded reader itself."""
    import io

    from typer import BadParameter

    from slaif_gateway.cli.demo_admin import _read_password_from_stdin

    monkeypatch.setattr("sys.stdin", io.StringIO(f"{CANARY_PASSWORD}\r\n"))
    with pytest.raises(BadParameter) as excinfo:
        _read_password_from_stdin()
    assert excinfo.value.message == _STDIN_REFUSED


def test_stdin_reader_accepts_bounded_single_line(monkeypatch) -> None:
    import io

    from slaif_gateway.cli.demo_admin import _read_password_from_stdin

    monkeypatch.setattr("sys.stdin", io.StringIO(f"{CANARY_PASSWORD}\n"))
    assert _read_password_from_stdin() == CANARY_PASSWORD
    monkeypatch.setattr("sys.stdin", io.StringIO(CANARY_PASSWORD))  # no newline
    assert _read_password_from_stdin() == CANARY_PASSWORD


def test_create_password_stdin_empty_refused(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["create", "demoalice", "--reason", "x", "--password-stdin", "--json"],
        input="",
    )
    assert result.exit_code == 1
    payload = _json_output(result.output)
    assert payload["error"]["message"] == "No password found on stdin."
    assert stub.calls == []


# --- CLI list/enable/disable/reset: safe output -----------------------------


def test_list_json_reveals_only_safe_fields(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(demo_admin_app, ["list", "--json"])
    assert result.exit_code == 0
    payload = _json_output(result.output)
    assert set(payload) == {"items", "limit", "offset", "active_account_count"}
    for item in payload["items"]:
        _safe_fields(item)
    assert payload["active_account_count"] == 1
    assert payload["limit"] == 50
    assert CANARY_HASH not in result.output


def test_list_rejects_unbounded_numeric_parsing(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    for args in (
        ["list", "--limit", "0"],
        ["list", "--limit", "101"],
        ["list", "--limit", "1e50"],
        ["list", "--limit", "12345"],
        ["list", "--offset", "-1"],
        ["list", "--offset", "1000001"],
        ["list", "--offset", "0x10"],
    ):
        result = RUNNER.invoke(demo_admin_app, args)
        assert result.exit_code != 0, args
    assert stub.calls == []


def test_enable_reports_idempotent_noop_honestly(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app, ["enable", "demoalice", "--reason", "reopen", "--json"]
    )
    assert result.exit_code == 0
    payload = _json_output(result.output)
    _safe_fields(payload)
    # The payload mirrors the repository's changed flag; the idempotent
    # no-op case (state_changed False) is covered below.
    assert payload["state_changed"] is True


def test_disable_idempotent_noop_payload(monkeypatch) -> None:
    class _NoopService(_StubService):
        async def set_enabled(self, *, username: str, enabled: bool, reason: str):
            return FakeAdminAccountEnabledResult(
                projection=_projection(username, enabled=False), state_changed=False
            )

    _patch_cli(monkeypatch, _NoopService())
    result = RUNNER.invoke(
        demo_admin_app, ["disable", "demoalice", "--reason", "already off", "--json"]
    )
    assert result.exit_code == 0
    payload = _json_output(result.output)
    assert payload["state_changed"] is False
    assert payload["is_enabled"] is False


def test_reset_password_stdin_safe_output(monkeypatch) -> None:
    stub = _StubService()
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["reset-password", "demoalice", "--reason", "rotation", "--password-stdin", "--json"],
        input=f"{CANARY_PASSWORD}\n",
    )
    assert result.exit_code == 0
    payload = _json_output(result.output)
    _safe_fields(payload)
    assert payload["reset"] is True
    assert CANARY_PASSWORD not in result.output
    assert CANARY_HASH not in result.output


# --- fixed safe errors: DB / duplicate / not found --------------------------


def test_database_not_configured_is_fixed_and_unechoed(monkeypatch) -> None:
    # No session stub: cli_db_session must raise the fixed config error
    # BEFORE any database contact, and never print a DSN.
    from slaif_gateway.config import get_settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        result = RUNNER.invoke(
            demo_admin_app,
            ["create", "demoalice", "--reason", "x", "--password-stdin", "--json"],
            input=f"{CANARY_PASSWORD}\n",
        )
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 1
    payload = _json_output(result.output)
    assert payload["error"]["code"] == "database_not_configured"
    assert CANARY_DSN not in result.output
    assert CANARY_PASSWORD not in result.output


class _ErrorService(_StubService):
    def __init__(self, exc: FakeAdminAccountError) -> None:
        super().__init__()
        self.exc = exc

    async def create_account(self, **kw):
        raise self.exc

    async def set_enabled(self, **kw):
        raise self.exc

    async def reset_password(self, **kw):
        raise self.exc


@pytest.mark.parametrize(
    "code,message",
    [
        ("demo_admin_account_exists", "A demo-admin account with this username already exists."),
        (
            "demo_admin_account_create_unconfirmed",
            "Account creation outcome could not be confirmed; the transaction "
            "was rolled back and no account state was committed.",
        ),
        ("demo_admin_account_not_found", "No demo-admin account exists for the supplied username."),
    ],
)
def test_fixed_safe_errors_never_echo_internals(monkeypatch, code: str, message: str) -> None:
    stub = _ErrorService(FakeAdminAccountError(code, message))
    _patch_cli(monkeypatch, stub)
    result = RUNNER.invoke(
        demo_admin_app,
        ["enable", "demoalice", "--reason", "x", "--json"],
    )
    assert result.exit_code == 1
    payload = _json_output(result.output)
    assert payload["error"] == {"code": code, "message": message}


# --- service-level transaction oracles (stubbed repository) ------------------


class _FakeOrig:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _StubRepository:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.create_error: IntegrityError | None = None
        self.existing: object | None = None

    async def get_account_by_username(self, username: str, *, for_update: bool = False):
        return self.existing

    async def create_account(self, *, username: str, password_hash: str, reason: str | None):
        if self.create_error is not None:
            raise self.create_error
        return SimpleNamespace(
            id=uuid.uuid4(),
            username=username,
            password_hash=password_hash,
            is_enabled=True,
            credential_generation=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def set_enabled(self, account, *, enabled: bool, reason: str | None) -> bool:
        if account.is_enabled == enabled:
            return False
        account.is_enabled = enabled
        account.credential_generation += 1
        self.events.append(("enable" if enabled else "disable", account.credential_generation))
        return True

    async def reset_password(self, account, *, password_hash: str, reason: str | None) -> None:
        account.password_hash = password_hash
        account.credential_generation += 1
        self.events.append(("password_reset", account.credential_generation))


def _service_with_stub_repo() -> tuple[FakeAdminAccountService, _StubRepository]:
    repo = _StubRepository()
    service = FakeAdminAccountService(session=None)  # type: ignore[arg-type]
    service._repository = repo  # unit oracle: no session needed
    return service, repo


@pytest.mark.asyncio
async def test_create_duplicate_is_only_exact_username_constraint() -> None:
    service, repo = _service_with_stub_repo()
    repo.create_error = IntegrityError(
        "stmt", {}, _FakeOrig("uq_demo_fake_admin_accounts_username")
    )
    with pytest.raises(FakeAdminAccountError) as excinfo:
        await service.create_account(
            username="demoalice", password="password12345678", reason="x"
        )
    assert excinfo.value.code == "demo_admin_account_exists"


@pytest.mark.asyncio
async def test_create_late_write_fault_is_unconfirmed_not_duplicate() -> None:
    service, repo = _service_with_stub_repo()
    # Simulated late persistence fault (e.g. the event INSERT violating a
    # constraint AFTER the account row was flushed): the exact duplicate
    # constraint name is NOT present, so the outcome must be unconfirmed.
    repo.create_error = IntegrityError(
        "stmt", {}, _FakeOrig("demo_fake_admin_account_events_action_allowed")
    )
    with pytest.raises(FakeAdminAccountError) as excinfo:
        await service.create_account(
            username="demoalice", password="password12345678", reason="x"
        )
    assert excinfo.value.code == "demo_admin_account_create_unconfirmed"


@pytest.mark.asyncio
async def test_reset_never_reenables_and_bumps_generation() -> None:
    service, repo = _service_with_stub_repo()
    account = SimpleNamespace(
        id=uuid.uuid4(),
        username="demoalice",
        password_hash="old-hash",
        is_enabled=False,
        credential_generation=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.existing = account
    projection = await service.reset_password(
        username="demoalice", password="password12345678", reason="rotation"
    )
    assert account.is_enabled is False  # reset never re-enables
    assert account.credential_generation == 3
    assert projection.is_enabled is False
    assert repo.events == [("password_reset", 3)]


@pytest.mark.asyncio
async def test_repeat_disable_is_idempotent_noop_without_event() -> None:
    service, repo = _service_with_stub_repo()
    account = SimpleNamespace(
        id=uuid.uuid4(),
        username="demoalice",
        password_hash="old-hash",
        is_enabled=False,
        credential_generation=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.existing = account
    result = await service.set_enabled(
        username="demoalice", enabled=False, reason="already off"
    )
    assert result.state_changed is False
    assert account.credential_generation == 1
    assert repo.events == []  # no fake success audit
