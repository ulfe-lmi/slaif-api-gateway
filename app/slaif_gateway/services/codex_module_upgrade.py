"""Audited, exact-tuple upgrade and rollback of pinned Codex client modules.

This service mutates only the ``responses_policy.client_module``
compatibility metadata of one explicitly selected gateway key.  Every other
key, policy, quota, usage, secret, and metadata field is preserved.  The
source identity must match an exact (id, version, fixture_sha256) tuple;
malformed, drifted, or unexpected identities fail closed.  The row is
locked for the mutation, and the audit record and the update commit or
roll back atomically in the caller's transaction.  Dry runs perform no
write and no audit record.
"""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE_ID
from slaif_gateway.modules.clients.registry import get_client_module
from slaif_gateway.services.record_errors import RecordServiceError

_UPGRADE_SOURCE_TARGET = "0149-v4"
_UPGRADE_TARGET_0149_V5 = "0149-v5"
_UPGRADE_TARGET_0162_V1 = "0162-v1"
_UPGRADE_TARGET_0162_V2 = "0162-v2"
_UPGRADE_TARGETS = frozenset(
    {_UPGRADE_TARGET_0149_V5, _UPGRADE_TARGET_0162_V1, _UPGRADE_TARGET_0162_V2}
)

# The exact legacy tuple of the pinned 0.149 deployment.  Its fixture digest
# is frozen as a literal historical value (not imported from the current
# module) so future registry changes cannot silently retarget the historical
# selector.  It is the only legacy upgrade source and the rollback target of
# the original four 0.149-v4 edges.
CODEX_0149_V4_CLIENT_MODULE = MappingProxyType(
    {
        "id": "codex-0.149-responses-v1",
        "version": "4",
        "fixture_sha256": "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec",
    }
)
# The exact historical 0.162-v1 tuple, frozen as literal values: it is the
# only source for the 0162-v2 hop and the rollback target back to v1.
CODEX_0162_V1_CLIENT_MODULE = MappingProxyType(
    {
        "id": "codex-0.162-responses-v1",
        "version": "1",
        "fixture_sha256": "724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e",
    }
)
UPGRADE_TARGET_CLIENT_MODULES = MappingProxyType(
    {
        _UPGRADE_TARGET_0149_V5: MappingProxyType(
            {
                "id": "codex-0.149-responses-v1",
                "version": "5",
                "fixture_sha256": "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec",
            }
        ),
        _UPGRADE_TARGET_0162_V1: CODEX_0162_V1_CLIENT_MODULE,
        _UPGRADE_TARGET_0162_V2: MappingProxyType(
            {
                "id": "codex-0.162-responses-v1",
                "version": "2",
                "fixture_sha256": "b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85",
            }
        ),
    }
)

# The complete set of legal transitions.  The original four 0.149-v4 edges
# are unchanged; the 0162-v1 -> 0162-v2 hop and its reverse are the only new
# edges.  No cross-target move (for example 0149-v4 -> 0162-v2 or
# 0162-v2 -> 0149-v4) is legal: 0.149-v4 keys reach 0162-v2 only through an
# explicit documented two-hop sequence while quiesced.
_LEGAL_TRANSITIONS = frozenset(
    {
        (_UPGRADE_SOURCE_TARGET, _UPGRADE_TARGET_0149_V5),
        (_UPGRADE_SOURCE_TARGET, _UPGRADE_TARGET_0162_V1),
        (_UPGRADE_TARGET_0149_V5, _UPGRADE_SOURCE_TARGET),
        (_UPGRADE_TARGET_0162_V1, _UPGRADE_SOURCE_TARGET),
        (_UPGRADE_TARGET_0162_V1, _UPGRADE_TARGET_0162_V2),
        (_UPGRADE_TARGET_0162_V2, _UPGRADE_TARGET_0162_V1),
    }
)

_CLIENT_MODULE_FIELDS = frozenset({"id", "version", "fixture_sha256"})
_REASON_PATTERN = re.compile(r"^[\x20-\x7E]{8,200}$")


class CodexModuleUpgradeError(RecordServiceError):
    """Safe operator-facing error for the bounded client-module mutation.

    Carries the RecordServiceError convention so the CLI renderer preserves
    the specific upgrade error code without echoing caller details.
    """

    def __init__(self, message: str, *, code: str) -> None:
        self.error_code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CodexModuleUpgradeResult:
    """Safe outcome facts; only key UUID, exact tuples, and action counts."""

    gateway_key_id: uuid.UUID
    status: str
    action: str
    source_module: Mapping[str, str]
    target_module: Mapping[str, str]
    changed: bool


def _module_facts(value: Mapping[str, str]) -> dict[str, str]:
    return {key: str(value[key]) for key in ("id", "version", "fixture_sha256")}


def _validate_reason(reason: object) -> str:
    if not isinstance(reason, str) or not reason.strip() or not _REASON_PATTERN.fullmatch(reason):
        raise CodexModuleUpgradeError(
            "The upgrade reason must be 8-200 printable ASCII characters "
            "with non-whitespace content.",
            code="codex_module_upgrade_reason_invalid",
        )
    return reason


def _current_client_module(key: GatewayKey) -> Mapping[str, str]:
    metadata = key.metadata_json
    if not isinstance(metadata, dict):
        raise CodexModuleUpgradeError(
            "The gateway key has no readable compatibility metadata.",
            code="codex_module_upgrade_metadata_invalid",
        )
    policy = metadata.get("responses_policy")
    if not isinstance(policy, dict):
        raise CodexModuleUpgradeError(
            "The gateway key has no Responses policy to upgrade.",
            code="codex_module_upgrade_identity_missing",
        )
    raw_module = policy.get("client_module")
    if (
        not isinstance(raw_module, Mapping)
        or set(raw_module) != _CLIENT_MODULE_FIELDS
        or not all(
            isinstance(raw_module.get(key), str) and raw_module.get(key)
            for key in _CLIENT_MODULE_FIELDS
        )
    ):
        raise CodexModuleUpgradeError(
            "The gateway key client-module identity is malformed or drifted.",
            code="codex_module_upgrade_identity_invalid",
        )
    return MappingProxyType(_module_facts(raw_module))


async def mutate_codex_client_module(
    *,
    session: AsyncSession,
    keys_repository: GatewayKeysRepository,
    audit_repository: AuditRepository,
    gateway_key_id: uuid.UUID,
    expected_source: str,
    target: str,
    action: str,
    actor_admin_id: uuid.UUID | None,
    reason: str,
    apply: bool,
) -> CodexModuleUpgradeResult:
    """Apply or dry-run one exact-tuple client-module transition.

    ``expected_source`` and ``target`` are the literal target selectors from
    ``UPGRADE_TARGET_CLIENT_MODULES`` plus ``0149-v4``.  Only the original
    0149-v4 -> (0149-v5 | 0162-v1) upgrade and reverse rollbacks, plus the
    0162-v1 -> 0162-v2 hop and its reverse, are legal; any other pairing
    raises before the row is read.
    """
    _validate_reason(reason)
    source_module = (
        CODEX_0149_V4_CLIENT_MODULE
        if expected_source == _UPGRADE_SOURCE_TARGET
        else UPGRADE_TARGET_CLIENT_MODULES.get(expected_source)
    )
    target_module = (
        CODEX_0149_V4_CLIENT_MODULE
        if target == _UPGRADE_SOURCE_TARGET
        else UPGRADE_TARGET_CLIENT_MODULES.get(target)
    )
    if (expected_source, target) not in _LEGAL_TRANSITIONS:
        raise CodexModuleUpgradeError(
            "The requested client-module transition is not an approved pairing.",
            code="codex_module_upgrade_transition_invalid",
        )

    key = await keys_repository.get_gateway_key_for_update(gateway_key_id)
    if key is None:
        raise CodexModuleUpgradeError(
            "The gateway key was not found.",
            code="codex_module_upgrade_key_not_found",
        )
    current = _current_client_module(key)
    if _module_facts(current) == _module_facts(target_module):
        # Idempotent repeat: the key already carries the target identity, so
        # the transition is a safe no-op regardless of how it got there.
        return CodexModuleUpgradeResult(
            gateway_key_id=gateway_key_id,
            status="already_at_target",
            action=action,
            source_module=_module_facts(source_module),
            target_module=_module_facts(target_module),
            changed=False,
        )
    if _module_facts(current) != _module_facts(source_module):
        raise CodexModuleUpgradeError(
            "The gateway key client-module identity does not match the expected source tuple.",
            code="codex_module_upgrade_identity_mismatch",
        )

    status = "applied" if apply else "dry_run"
    if apply:
        metadata = copy.deepcopy(key.metadata_json)
        policy = dict(metadata["responses_policy"])
        policy["client_module"] = _module_facts(target_module)
        metadata["responses_policy"] = policy
        key.metadata_json = metadata
        await audit_repository.add_audit_log(
            action=action,
            entity_type="gateway_key",
            entity_id=key.id,
            admin_user_id=actor_admin_id,
            old_values={"client_module": _module_facts(source_module)},
            new_values={"client_module": _module_facts(target_module)},
            note=reason,
        )
    return CodexModuleUpgradeResult(
        gateway_key_id=gateway_key_id,
        status=status,
        action=action,
        source_module=_module_facts(source_module),
        target_module=_module_facts(target_module),
        changed=apply,
    )


# --- Neutral 0.162 key-profile migration (190-b) ---
#
# This bounded extension migrates one explicitly selected key's
# ``client_module`` compatibility metadata for the fixed
# ``codex-0.162-responses-v1`` module.  The source is the exact
# (version, digest) tuple supplied by the operator and must match the key's
# current pin; legacy revisions 1/2 additionally require their frozen
# literal fixture digests, while data revisions of 3 or higher are matched
# by their explicit values with no compiled history allowlist.  The target
# is the active validated data profile loaded at bootstrap, or one of the
# two explicit frozen legacy tuples for binary rollback.  The original
# selector/edge upgrade above is unchanged.


_PROFILE_MIGRATION_TARGETS = frozenset({"active", _UPGRADE_TARGET_0162_V1, _UPGRADE_TARGET_0162_V2})
_PROFILE_VERSION_PATTERN = re.compile(r"[1-9][0-9]{0,8}")
_PROFILE_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


def _validate_profile_version(value: object) -> str:
    if not isinstance(value, str) or _PROFILE_VERSION_PATTERN.fullmatch(value) is None:
        raise CodexModuleUpgradeError(
            "The profile revision is invalid.",
            code="codex_profile_migration_version_invalid",
        )
    return value


def _validate_profile_digest(value: object) -> str:
    if not isinstance(value, str) or _PROFILE_DIGEST_PATTERN.fullmatch(value) is None:
        raise CodexModuleUpgradeError(
            "The profile digest is invalid.",
            code="codex_profile_migration_digest_invalid",
        )
    return value


def _resolve_profile_migration_target(target: object) -> Mapping[str, str]:
    if target == "active":
        active = get_client_module(CODEX_0162_CLIENT_MODULE_ID)
        if getattr(active, "module_id", None) != CODEX_0162_CLIENT_MODULE_ID:
            raise CodexModuleUpgradeError(
                "The active Codex profile module is unavailable.",
                code="codex_profile_migration_target_invalid",
            )
        return MappingProxyType(
            {
                "id": CODEX_0162_CLIENT_MODULE_ID,
                "version": active.module_version,
                "fixture_sha256": active.fixture_sha256,
            }
        )
    if target == _UPGRADE_TARGET_0162_V1:
        return MappingProxyType(dict(CODEX_0162_V1_CLIENT_MODULE))
    if target == _UPGRADE_TARGET_0162_V2:
        return MappingProxyType(
            {
                "id": "codex-0.162-responses-v1",
                "version": "2",
                "fixture_sha256": "b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85",
            }
        )
    raise CodexModuleUpgradeError(
        "The profile migration target is not an approved target.",
        code="codex_profile_migration_target_invalid",
    )


async def migrate_codex_0162_key_profile(
    *,
    session: AsyncSession,
    keys_repository: GatewayKeysRepository,
    audit_repository: AuditRepository,
    gateway_key_id: uuid.UUID,
    from_version: str,
    from_digest: str,
    target: str,
    action: str,
    actor_admin_id: uuid.UUID | None,
    reason: str,
    apply: bool,
) -> CodexModuleUpgradeResult:
    """Migrate one key's 0.162 pinned profile tuple, explicitly and audited.

    The source must be the key's exact current (version, digest) pin; legacy
    1/2 sources must carry the frozen literal digest and data sources of
    revision 3 or higher are matched by their explicit values.  The target
    is the active validated data profile (bootstrap snapshot) or one of the
    two frozen legacy tuples.  A same-revision different-digest migration is
    rejected (a profile change requires a revision change).  A repeated
    exact target is a no-op with no audit record; a drifted or malformed
    source fails closed.  Only the ``client_module`` metadata is written,
    in one transaction with the audit record, under the row lock.
    """
    _validate_reason(reason)
    source_version = _validate_profile_version(from_version)
    source_digest = _validate_profile_digest(from_digest)
    if source_version == "1" and (source_digest != CODEX_0162_V1_CLIENT_MODULE["fixture_sha256"]):
        raise CodexModuleUpgradeError(
            "The legacy source profile identity does not match the frozen tuple.",
            code="codex_profile_migration_source_drifted",
        )
    if source_version == "2" and (
        source_digest != UPGRADE_TARGET_CLIENT_MODULES[_UPGRADE_TARGET_0162_V2]["fixture_sha256"]
    ):
        raise CodexModuleUpgradeError(
            "The legacy source profile identity does not match the frozen tuple.",
            code="codex_profile_migration_source_drifted",
        )
    if target not in _PROFILE_MIGRATION_TARGETS:
        raise CodexModuleUpgradeError(
            "The profile migration target is not an approved target.",
            code="codex_profile_migration_target_invalid",
        )
    target_module = _resolve_profile_migration_target(target)
    if target_module["id"] != CODEX_0162_CLIENT_MODULE_ID:
        raise CodexModuleUpgradeError(
            "The profile migration target is not an approved target.",
            code="codex_profile_migration_target_invalid",
        )
    if source_version == target_module["version"] and (
        source_digest != target_module["fixture_sha256"]
    ):
        raise CodexModuleUpgradeError(
            "A profile change requires a profile revision change.",
            code="codex_profile_migration_revision_unchanged",
        )
    source_module = MappingProxyType(
        {
            "id": CODEX_0162_CLIENT_MODULE_ID,
            "version": source_version,
            "fixture_sha256": source_digest,
        }
    )

    key = await keys_repository.get_gateway_key_for_update(gateway_key_id)
    if key is None:
        raise CodexModuleUpgradeError(
            "The gateway key was not found.",
            code="codex_module_upgrade_key_not_found",
        )
    current = _current_client_module(key)
    if _module_facts(current) == _module_facts(target_module):
        return CodexModuleUpgradeResult(
            gateway_key_id=gateway_key_id,
            status="already_at_target",
            action=action,
            source_module=_module_facts(source_module),
            target_module=_module_facts(target_module),
            changed=False,
        )
    if _module_facts(current) != _module_facts(source_module):
        raise CodexModuleUpgradeError(
            "The gateway key client-module identity does not match the expected source tuple.",
            code="codex_module_upgrade_identity_mismatch",
        )

    status = "applied" if apply else "dry_run"
    if apply:
        metadata = copy.deepcopy(key.metadata_json)
        policy = dict(metadata["responses_policy"])
        policy["client_module"] = _module_facts(target_module)
        metadata["responses_policy"] = policy
        key.metadata_json = metadata
        await audit_repository.add_audit_log(
            action=action,
            entity_type="gateway_key",
            entity_id=key.id,
            admin_user_id=actor_admin_id,
            old_values={"client_module": _module_facts(source_module)},
            new_values={"client_module": _module_facts(target_module)},
            note=reason,
        )
    return CodexModuleUpgradeResult(
        gateway_key_id=gateway_key_id,
        status=status,
        action=action,
        source_module=_module_facts(source_module),
        target_module=_module_facts(target_module),
        changed=apply,
    )
