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
        notes: str | None = None,
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
            notes=_clean_optional(notes),
        )
        await self._audit.add_audit_log(
            action="owner_created",
            entity_type="owner",
            entity_id=owner.id,
            new_values={
                "name": owner.name,
                "surname": owner.surname,
                "email": owner.email,
                "institution_id": str(owner.institution_id) if owner.institution_id else None,
                "is_active": owner.is_active,
            },
        )
        return owner

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
