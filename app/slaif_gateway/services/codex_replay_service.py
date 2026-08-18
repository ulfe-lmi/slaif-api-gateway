"""HMAC-only ownership and persistence for Codex client-managed replay."""

from __future__ import annotations

import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, Sequence

from slaif_gateway.config import Settings
from slaif_gateway.db.models import CodexReplayReference
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferenceInsert,
    CodexReplayReferencesRepository,
)
from slaif_gateway.utils.crypto import hmac_sha256_token


CODEX_REPLAY_REFERENCE_TTL = timedelta(hours=24)
CODEX_REPLAY_ITEM_KINDS = frozenset(
    {"reasoning", "function_call", "custom_tool_call", "compaction"}
)
_MAX_ACTIVE_HMAC_VERSIONS = 8
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


class CodexReplayCandidate(Protocol):
    """Transient validated ID fields accepted by the immediate HMAC step."""

    item_kind: str
    item_id: str
    call_id: str | None
    tool_namespace: str | None
    tool_name: str | None


class _CodexReplayRepository(Protocol):
    async def usage_ledger_is_finalized_for_key(
        self,
        *,
        usage_ledger_id: uuid.UUID,
        gateway_key_id: uuid.UUID,
        source_request_id: str,
    ) -> bool: ...

    async def list_active_hmac_versions_for_key(
        self,
        *,
        gateway_key_id: uuid.UUID,
        item_kinds: frozenset[str],
        now: datetime,
    ) -> list[int]: ...

    async def list_active_by_item_digests(
        self,
        *,
        gateway_key_id: uuid.UUID,
        item_digests: Sequence[tuple[str, str]],
        now: datetime,
    ) -> list[CodexReplayReference]: ...

    async def upsert_many(self, records: Sequence[CodexReplayReferenceInsert]) -> None: ...


class CodexReplayReferenceError(ValueError):
    """Safe fail-closed replay error without IDs or digest values."""

    def __init__(self, safe_message: str, *, error_code: str) -> None:
        self.safe_message = safe_message
        self.error_code = error_code
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedCodexReplayReference:
    """Content-free authorization result used for the later route check."""

    item_kind: str
    provider: str
    route_id: uuid.UUID
    upstream_model: str
    tool_namespace: str | None
    tool_name: str | None
    expires_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class CodexReplayAuthorization:
    """Opaque same-key authorization result; it contains no raw IDs or digests."""

    references: tuple[AuthorizedCodexReplayReference, ...]


class CodexReplayService:
    """Bind replayable provider IDs to one key and one compatible route."""

    def __init__(
        self,
        *,
        repository: _CodexReplayRepository | CodexReplayReferencesRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    async def verify_owned_replay(
        self,
        *,
        candidates: Sequence[CodexReplayCandidate],
        gateway_key_id: uuid.UUID,
        now: datetime | None = None,
    ) -> CodexReplayAuthorization:
        """Prove same-key active ownership before route or quota side effects."""

        checked = _validated_candidates(candidates)
        if not checked:
            return CodexReplayAuthorization(references=())
        checked_now = now or datetime.now(UTC)
        try:
            versions = await self._repository.list_active_hmac_versions_for_key(
                gateway_key_id=gateway_key_id,
                item_kinds=frozenset(candidate.item_kind for candidate in checked),
                now=checked_now,
            )
        except Exception:
            raise _ownership_error() from None
        if not versions or len(versions) > _MAX_ACTIVE_HMAC_VERSIONS:
            raise _ownership_error()

        secrets: dict[int, str] = {}
        for version in versions:
            secret = self._settings.get_hmac_secret(str(version))
            if not secret:
                raise CodexReplayReferenceError(
                    "Codex replay reference key material is unavailable.",
                    error_code="responses_codex_replay_hmac_unavailable",
                )
            secrets[version] = secret

        digest_candidates: list[tuple[str, str]] = []
        for candidate in checked:
            for secret in secrets.values():
                digest_candidates.append(
                    (candidate.item_kind, _item_digest(candidate, secret=secret))
                )
        try:
            rows = await self._repository.list_active_by_item_digests(
                gateway_key_id=gateway_key_id,
                item_digests=digest_candidates,
                now=checked_now,
            )
        except Exception:
            raise _ownership_error() from None
        rows_by_digest = {(row.item_kind, row.item_id_hmac): row for row in rows}

        authorized: list[AuthorizedCodexReplayReference] = []
        for candidate in checked:
            matches = []
            for version, secret in secrets.items():
                row = rows_by_digest.get(
                    (candidate.item_kind, _item_digest(candidate, secret=secret))
                )
                if row is not None and row.hmac_key_version == version:
                    matches.append((row, secret))
            if len(matches) != 1:
                raise _ownership_error()
            row, secret = matches[0]
            _validate_row_matches_candidate(row, candidate, secret=secret)
            authorized.append(
                AuthorizedCodexReplayReference(
                    item_kind=row.item_kind,
                    provider=row.provider,
                    route_id=row.route_id,
                    upstream_model=row.upstream_model,
                    tool_namespace=row.tool_namespace,
                    tool_name=row.tool_name,
                    expires_at=row.expires_at,
                )
            )
        return CodexReplayAuthorization(references=tuple(authorized))

    @staticmethod
    def verify_route_compatibility(
        authorization: CodexReplayAuthorization,
        *,
        provider: str,
        route_id: uuid.UUID,
        upstream_model: str,
        compatible_route_ids: frozenset[uuid.UUID] = frozenset(),
        allow_compact_endpoint_route_compatibility: bool = False,
    ) -> None:
        """Fail closed unless every owned reference matches the selected route."""

        if any(
            reference.provider != provider
            or (
                reference.route_id != route_id
                and not (
                    (
                        reference.item_kind == "compaction"
                        or allow_compact_endpoint_route_compatibility
                    )
                    and reference.route_id in compatible_route_ids
                )
            )
            or reference.upstream_model != upstream_model
            for reference in authorization.references
        ):
            raise CodexReplayReferenceError(
                "Codex replay references are not valid for this model route.",
                error_code="responses_codex_replay_route_mismatch",
            )

    async def persist_validated_references(
        self,
        *,
        candidates: Sequence[CodexReplayCandidate],
        gateway_key_id: uuid.UUID,
        usage_ledger_id: uuid.UUID,
        source_request_id: str,
        provider: str,
        route_id: uuid.UUID,
        upstream_model: str,
        now: datetime | None = None,
    ) -> int:
        """HMAC and upsert validated completion candidates after accounting."""

        checked = _validated_candidates(candidates)
        if not checked:
            return 0
        if not source_request_id.strip() or not provider.strip() or not upstream_model.strip():
            raise _persistence_error()
        try:
            ledger_is_finalized = await self._repository.usage_ledger_is_finalized_for_key(
                usage_ledger_id=usage_ledger_id,
                gateway_key_id=gateway_key_id,
                source_request_id=source_request_id,
            )
        except Exception:
            raise _persistence_error() from None
        if not ledger_is_finalized:
            raise _persistence_error()
        try:
            version_text, secret = self._settings.get_active_hmac_secret()
            version = int(version_text)
        except (TypeError, ValueError):
            raise CodexReplayReferenceError(
                "Codex replay reference key material is unavailable.",
                error_code="responses_codex_replay_hmac_unavailable",
            ) from None
        if version <= 0:
            raise CodexReplayReferenceError(
                "Codex replay reference key material is unavailable.",
                error_code="responses_codex_replay_hmac_unavailable",
            )

        created_at = now or datetime.now(UTC)
        expires_at = created_at + CODEX_REPLAY_REFERENCE_TTL
        records = [
            CodexReplayReferenceInsert(
                id=uuid.uuid4(),
                gateway_key_id=gateway_key_id,
                usage_ledger_id=usage_ledger_id,
                source_request_id=source_request_id,
                provider=provider,
                route_id=route_id,
                upstream_model=upstream_model,
                item_kind=candidate.item_kind,
                item_id_hmac=_item_digest(candidate, secret=secret),
                call_id_hmac=_call_digest(candidate, secret=secret),
                hmac_key_version=version,
                tool_namespace=candidate.tool_namespace,
                tool_name=candidate.tool_name,
                created_at=created_at,
                expires_at=expires_at,
            )
            for candidate in checked
        ]
        try:
            await self._repository.upsert_many(records)
            rows = await self._repository.list_active_by_item_digests(
                gateway_key_id=gateway_key_id,
                item_digests=[(record.item_kind, record.item_id_hmac) for record in records],
                now=created_at,
            )
        except Exception:
            raise _persistence_error() from None
        rows_by_digest = {(row.item_kind, row.item_id_hmac): row for row in rows}
        for candidate, record in zip(checked, records, strict=True):
            row = rows_by_digest.get((record.item_kind, record.item_id_hmac))
            if row is None or row.hmac_key_version != version:
                raise _persistence_error()
            _validate_persisted_row(
                row,
                candidate,
                record=record,
                secret=secret,
            )
        return len(records)


def _validated_candidates(
    candidates: Sequence[CodexReplayCandidate],
) -> tuple[CodexReplayCandidate, ...]:
    checked = tuple(candidates)
    seen_items: set[tuple[str, str]] = set()
    seen_calls: set[tuple[str, str]] = set()
    for candidate in checked:
        if candidate.item_kind not in CODEX_REPLAY_ITEM_KINDS:
            raise _ownership_error()
        if _IDENTIFIER_RE.fullmatch(candidate.item_id) is None:
            raise _ownership_error()
        item_key = (candidate.item_kind, candidate.item_id)
        if item_key in seen_items:
            raise _ownership_error()
        seen_items.add(item_key)
        if candidate.item_kind in {"reasoning", "compaction"}:
            if any(
                value is not None
                for value in (candidate.call_id, candidate.tool_namespace, candidate.tool_name)
            ):
                raise _ownership_error()
            encrypted_content = getattr(candidate, "encrypted_content", None)
            if candidate.item_kind == "compaction":
                if (
                    not isinstance(encrypted_content, str)
                    or not encrypted_content
                    or len(encrypted_content.encode("utf-8")) > 1_048_576
                ):
                    raise _ownership_error()
            elif encrypted_content is not None:
                raise _ownership_error()
            continue
        if getattr(candidate, "encrypted_content", None) is not None:
            raise _ownership_error()
        if candidate.call_id is None or _IDENTIFIER_RE.fullmatch(candidate.call_id) is None:
            raise _ownership_error()
        if candidate.tool_namespace is None or candidate.tool_name is None:
            raise _ownership_error()
        if not _bounded_safe_tool_name(candidate.tool_namespace) or not _bounded_safe_tool_name(
            candidate.tool_name
        ):
            raise _ownership_error()
        call_key = (candidate.item_kind, candidate.call_id)
        if call_key in seen_calls:
            raise _ownership_error()
        seen_calls.add(call_key)
    return checked


def _bounded_safe_tool_name(value: str) -> bool:
    return bool(value.strip()) and len(value) <= 256


def _item_digest(candidate: CodexReplayCandidate, *, secret: str) -> str:
    if candidate.item_kind == "compaction":
        encrypted_content = getattr(candidate, "encrypted_content", None)
        assert encrypted_content is not None
        token = (
            "slaif-codex-replay:v2:compaction:"
            f"{len(candidate.item_id.encode('utf-8'))}:{candidate.item_id}:"
            f"{len(encrypted_content.encode('utf-8'))}:{encrypted_content}"
        )
        return hmac_sha256_token(token=token, secret=secret)
    return hmac_sha256_token(
        token=f"slaif-codex-replay:v1:item:{candidate.item_kind}:{candidate.item_id}",
        secret=secret,
    )


def _call_digest(candidate: CodexReplayCandidate, *, secret: str) -> str | None:
    if candidate.call_id is None:
        return None
    return hmac_sha256_token(
        token=f"slaif-codex-replay:v1:call:{candidate.item_kind}:{candidate.call_id}",
        secret=secret,
    )


def _validate_row_matches_candidate(
    row: CodexReplayReference,
    candidate: CodexReplayCandidate,
    *,
    secret: str,
) -> None:
    expected_call_digest = _call_digest(candidate, secret=secret)
    call_matches = (
        row.call_id_hmac is None
        if expected_call_digest is None
        else row.call_id_hmac is not None
        and hmac.compare_digest(row.call_id_hmac, expected_call_digest)
    )
    if (
        not call_matches
        or row.tool_namespace != candidate.tool_namespace
        or row.tool_name != candidate.tool_name
    ):
        raise _ownership_error()


def _validate_persisted_row(
    row: CodexReplayReference,
    candidate: CodexReplayCandidate,
    *,
    record: CodexReplayReferenceInsert,
    secret: str,
) -> None:
    _validate_row_matches_candidate(row, candidate, secret=secret)
    if (
        row.gateway_key_id != record.gateway_key_id
        or row.usage_ledger_id != record.usage_ledger_id
        or row.source_request_id != record.source_request_id
        or row.provider != record.provider
        or row.route_id != record.route_id
        or row.upstream_model != record.upstream_model
        or row.created_at != record.created_at
        or row.expires_at != record.expires_at
    ):
        raise _persistence_error()


def _ownership_error() -> CodexReplayReferenceError:
    return CodexReplayReferenceError(
        "One or more Codex replay references are unavailable.",
        error_code="responses_codex_replay_reference_not_found",
    )


def _persistence_error() -> CodexReplayReferenceError:
    return CodexReplayReferenceError(
        "Codex replay references could not be persisted safely.",
        error_code="responses_codex_replay_persistence_failed",
    )
