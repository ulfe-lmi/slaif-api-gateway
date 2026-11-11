"""Objective 220 foundation: typed demo fake-admin account service.

Bounded, safe-vocabulary control plane for the ``demo_control``
PostgreSQL schema. This service is the ONLY writable path for fake-admin
accounts (the trusted operator CLI invokes it); no HTTP route, worker,
or normal-admin path touches these tables at this stage.

Law:
- usernames: 3..64 normalized ASCII letters/digits/underscore/hyphen,
  starting with a letter, case-insensitively unique;
- passwords: salted Argon2id hashes via the existing password primitive;
  a documented strong minimum (16..128 chars) appropriate for publicly
  reachable demo accounts; plaintext is never persisted, logged, or
  echoed;
- credential-shaped usernames/reasons/passwords are refused with fixed
  safe messages (the value is never echoed);
- every account change is one owned PostgreSQL transaction: state change
  + one safe append-only event commit or roll back together;
- repeat enable/disable is a defined idempotent no-op (no event, no
  generation bump, no fake success audit);
- password reset never re-enables a disabled account;
- disabling the last active account makes the database-side active
  account count zero in the same committed state.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.fake_admin_accounts import FakeAdminAccountsRepository
from slaif_gateway.services.provider_route_configuration import contains_known_secret_shape
from slaif_gateway.utils.passwords import hash_admin_password

USERNAME_UNIQUE_CONSTRAINT = "uq_demo_fake_admin_accounts_username"

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64
USERNAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,63}")

PASSWORD_MIN_LENGTH = 16
PASSWORD_MAX_LENGTH = 128

REASON_MIN_LENGTH = 1
REASON_MAX_LENGTH = 512


class FakeAdminAccountError(Exception):
    """Safe fixed-vocabulary error for the demo-admin control path.

    ``safe_message`` names only the failing FLAG/FIELD, never the
    supplied value; the CLI renders exactly this text.
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class FakeAdminAccountProjection:
    """The ONLY safe account fields the control path may reveal.

    Never contains password_hash or any credential material.
    """

    id: uuid.UUID
    username: str
    is_enabled: bool
    credential_generation: int
    created_at: object
    updated_at: object

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "username": self.username,
            "is_enabled": self.is_enabled,
            "credential_generation": self.credential_generation,
            "created_at": (
                self.created_at.isoformat()
                if hasattr(self.created_at, "isoformat")
                else self.created_at
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if hasattr(self.updated_at, "isoformat")
                else self.updated_at
            ),
        }


@dataclass(frozen=True, slots=True)
class FakeAdminAccountListResult:
    items: tuple[FakeAdminAccountProjection, ...]
    limit: int
    offset: int
    active_account_count: int


@dataclass(frozen=True, slots=True)
class FakeAdminAccountEnabledResult:
    projection: FakeAdminAccountProjection
    # True only when the enabled state actually changed (event written,
    # generation bumped); a repeated same-state call is the defined
    # idempotent no-op (False) with no event and no generation change.
    state_changed: bool


def validate_demo_admin_username(value: str) -> str:
    """Normalize and validate a demo-admin username; return the normalized form.

    Raises FakeAdminAccountError with a fixed safe message (never
    echoing the value) on any violation, including credential-shaped
    input.
    """
    normalized = value.strip()
    if contains_known_secret_shape(normalized):
        raise FakeAdminAccountError(
            "demo_admin_username_withheld",
            "--username: value must not contain recognized credential patterns.",
        )
    if (
        len(normalized) < USERNAME_MIN_LENGTH
        or len(normalized) > USERNAME_MAX_LENGTH
        or USERNAME_PATTERN.fullmatch(normalized) is None
    ):
        raise FakeAdminAccountError(
            "demo_admin_username_invalid",
            f"--username: must be {USERNAME_MIN_LENGTH}..{USERNAME_MAX_LENGTH} characters of "
            "ASCII letters, digits, underscore, or hyphen, starting with a letter.",
        )
    return normalized


def validate_demo_admin_password(password: str) -> None:
    """Validate a demo-admin password BEFORE any expensive hash work.

    Publicly reachable demo accounts carry a documented strong minimum:
    at least PASSWORD_MIN_LENGTH (16) and at most PASSWORD_MAX_LENGTH
    (128) characters. Credential-shaped input (gateway/provider key
    text, bearer tokens, sensitive assignments) is refused without
    echoing.
    """
    if contains_known_secret_shape(password):
        raise FakeAdminAccountError(
            "demo_admin_password_withheld",
            "The password must not contain recognized credential patterns.",
        )
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise FakeAdminAccountError(
            "demo_admin_password_invalid",
            f"The password must be {PASSWORD_MIN_LENGTH}..{PASSWORD_MAX_LENGTH} characters.",
        )


def validate_demo_admin_password_matches_username(password: str, username: str) -> None:
    """Refuse a password that is merely the username (no echo)."""
    if password == username or password.lower() == username.lower():
        raise FakeAdminAccountError(
            "demo_admin_password_invalid",
            "The password must be different from the username.",
        )


def validate_demo_admin_reason(value: str) -> str:
    """Normalize and validate a bounded audit reason (never echoed on error)."""
    normalized = value.strip()
    if contains_known_secret_shape(normalized):
        raise FakeAdminAccountError(
            "demo_admin_reason_withheld",
            "--reason: value must not contain recognized credential patterns.",
        )
    if len(normalized) < REASON_MIN_LENGTH or len(normalized) > REASON_MAX_LENGTH:
        raise FakeAdminAccountError(
            "demo_admin_reason_invalid",
            f"--reason: must be {REASON_MIN_LENGTH}..{REASON_MAX_LENGTH} characters after "
            "trimming.",
        )
    return normalized


def _project(account: object) -> FakeAdminAccountProjection:
    return FakeAdminAccountProjection(
        id=account.id,  # type: ignore[attr-defined]
        username=account.username,  # type: ignore[attr-defined]
        is_enabled=account.is_enabled,  # type: ignore[attr-defined]
        credential_generation=account.credential_generation,  # type: ignore[attr-defined]
        created_at=account.created_at,  # type: ignore[attr-defined]
        updated_at=account.updated_at,  # type: ignore[attr-defined]
    )


class FakeAdminAccountService:
    """One-transaction demo fake-admin account operations.

    The caller owns the transaction (the CLI wraps each command in one
    session transaction); every method flushes account state and its
    event together, so a failed late write rolls back both.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repository = FakeAdminAccountsRepository(session)

    async def create_account(
        self, *, username: str, password: str, reason: str
    ) -> FakeAdminAccountProjection:
        normalized_username = validate_demo_admin_username(username)
        validate_demo_admin_password(password)
        validate_demo_admin_password_matches_username(password, normalized_username)
        reason_text = validate_demo_admin_reason(reason)

        existing = await self._repository.get_account_by_username(normalized_username)
        if existing is not None:
            raise FakeAdminAccountError(
                "demo_admin_account_exists",
                "A demo-admin account with this username already exists.",
            )
        try:
            account = await self._repository.create_account(
                username=normalized_username,
                password_hash=hash_admin_password(password),
                reason=reason_text,
            )
        except IntegrityError as exc:
            # Duplicate claim is reserved for the EXACT username unique
            # violation. Any other persistence fault (late event insert,
            # other constraint) must NOT be labelled duplicate: the
            # transaction rolls back and the outcome is unconfirmed.
            if getattr(exc.orig, "constraint_name", None) == USERNAME_UNIQUE_CONSTRAINT:
                raise FakeAdminAccountError(
                    "demo_admin_account_exists",
                    "A demo-admin account with this username already exists.",
                ) from exc
            raise FakeAdminAccountError(
                "demo_admin_account_create_unconfirmed",
                "Account creation outcome could not be confirmed; the transaction "
                "was rolled back and no account state was committed.",
            ) from exc
        return _project(account)

    async def list_accounts(self, *, limit: int, offset: int) -> FakeAdminAccountListResult:
        accounts = await self._repository.list_accounts(limit=limit, offset=offset)
        active = await self._repository.count_active_accounts()
        return FakeAdminAccountListResult(
            items=tuple(_project(account) for account in accounts),
            limit=limit,
            offset=offset,
            active_account_count=active,
        )

    async def _load_for_update(self, username: str):
        normalized_username = validate_demo_admin_username(username)
        account = await self._repository.get_account_by_username(
            normalized_username, for_update=True
        )
        if account is None:
            raise FakeAdminAccountError(
                "demo_admin_account_not_found",
                "No demo-admin account exists for the supplied username.",
            )
        return account

    async def set_enabled(
        self, *, username: str, enabled: bool, reason: str
    ) -> FakeAdminAccountEnabledResult:
        reason_text = validate_demo_admin_reason(reason)
        account = await self._load_for_update(username)
        # Defined idempotent no-op when the state already matches: no
        # event, no generation bump, no fake success audit.
        state_changed = await self._repository.set_enabled(
            account, enabled=enabled, reason=reason_text
        )
        return FakeAdminAccountEnabledResult(projection=_project(account), state_changed=state_changed)

    async def reset_password(self, *, username: str, password: str, reason: str) -> FakeAdminAccountProjection:
        validate_demo_admin_password(password)
        reason_text = validate_demo_admin_reason(reason)
        account = await self._load_for_update(username)
        validate_demo_admin_password_matches_username(password, account.username)
        await self._repository.reset_password(
            account,
            password_hash=hash_admin_password(password),
            reason=reason_text,
        )
        return _project(account)
