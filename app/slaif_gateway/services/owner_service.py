"""Service helpers for key owner records."""

from __future__ import annotations

import uuid

from slaif_gateway.db.models import Owner
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.record_errors import DuplicateRecordError, RecordNotFoundError


class OwnerService:
    """Small service layer for owner CLI operations."""

    def __init__(
        self,
        *,
        owners_repository: OwnersRepository,
        institutions_repository: InstitutionsRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._owners = owners_repository
        self._institutions = institutions_repository
        self._audit = audit_repository

    async def create_owner(
        self,
        *,
        name: str,
        surname: str,
        email: str,
        institution_id: uuid.UUID | None = None,
        external_id: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> Owner:
        normalized_email = _normalize_email(email)
        if await self._owners.get_owner_by_email(normalized_email) is not None:
            raise DuplicateRecordError("Owner", "email")
        if institution_id is not None:
            institution = await self._institutions.get_institution_by_id(institution_id)
            if institution is None:
                raise RecordNotFoundError("Institution")

        owner = await self._owners.create_owner(
            name=_require_text(name, "Owner name"),
            surname=_require_text(surname, "Owner surname"),
            email=normalized_email,
            institution_id=institution_id,
            external_id=_clean_optional(external_id),
            notes=_clean_optional(notes),
            is_active=is_active,
        )
        await self._audit.add_audit_log(
            action="owner_created",
            entity_type="owner",
            admin_user_id=actor_admin_id,
            entity_id=owner.id,
            new_values=_safe_audit_values(owner),
            note=_clean_optional(reason),
        )
        return owner

    async def update_owner(
        self,
        owner_id: uuid.UUID | str,
        *,
        name: str,
        surname: str,
        email: str,
        institution_id: uuid.UUID | None = None,
        external_id: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> Owner:
        parsed_id = _parse_owner_id(owner_id)
        existing = await self._owners.get_owner_by_id(parsed_id)
        if existing is None:
            raise RecordNotFoundError("Owner")
        old_values = _safe_audit_values(existing)

        normalized_email = _normalize_email(email)
        duplicate = await self._owners.get_owner_by_email(normalized_email)
        if duplicate is not None and duplicate.id != existing.id:
            raise DuplicateRecordError("Owner", "email")
        if institution_id is not None:
            institution = await self._institutions.get_institution_by_id(institution_id)
            if institution is None:
                raise RecordNotFoundError("Institution")

        updated = await self._owners.update_owner_metadata(
            parsed_id,
            name=_require_text(name, "Owner name"),
            surname=_require_text(surname, "Owner surname"),
            email=normalized_email,
            institution_id=institution_id,
            external_id=_clean_optional(external_id),
            notes=_clean_optional(notes),
            is_active=is_active,
        )
        if updated is None:
            raise RecordNotFoundError("Owner")
        await self._audit.add_audit_log(
            action="owner_updated",
            entity_type="owner",
            admin_user_id=actor_admin_id,
            entity_id=updated.id,
            old_values=old_values,
            new_values=_safe_audit_values(updated),
            note=_clean_optional(reason),
        )
        return updated

    async def list_owners(
        self,
        *,
        institution_id: uuid.UUID | None = None,
        email: str | None = None,
        limit: int,
    ) -> list[Owner]:
        return await self._owners.list_owners(
            institution_id=institution_id,
            email=_normalize_email(email) if email else None,
            limit=limit,
        )

    async def get_owner(self, owner_id_or_email: str) -> Owner:
        value = owner_id_or_email.strip()
        owner: Owner | None
        try:
            owner = await self._owners.get_owner_by_id(uuid.UUID(value))
        except ValueError:
            owner = await self._owners.get_owner_by_email(_normalize_email(value))
        if owner is None:
            raise RecordNotFoundError("Owner")
        return owner


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("Email cannot be empty")
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Email must be valid")
    return normalized


def _require_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} cannot be empty")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_owner_id(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise RecordNotFoundError("Owner") from exc


def _safe_audit_values(owner: Owner) -> dict[str, object]:
    return {
        "name": owner.name,
        "surname": owner.surname,
        "email": owner.email,
        "institution_id": str(owner.institution_id) if owner.institution_id else None,
        "external_id": owner.external_id,
        "notes": owner.notes,
        "is_active": owner.is_active,
    }
