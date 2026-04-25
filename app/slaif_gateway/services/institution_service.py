"""Service helpers for institution records."""

from __future__ import annotations

import uuid

from slaif_gateway.db.models import Institution
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.services.record_errors import DuplicateRecordError, RecordNotFoundError


class InstitutionService:
    """Small service layer for institution CLI operations."""

    def __init__(
        self,
        *,
        institutions_repository: InstitutionsRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._institutions = institutions_repository
        self._audit = audit_repository

    async def create_institution(
        self,
        *,
        name: str,
        country: str | None = None,
        notes: str | None = None,
    ) -> Institution:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Institution name cannot be empty")
        if await self._institutions.get_institution_by_name(normalized_name) is not None:
            raise DuplicateRecordError("Institution", "name")

        institution = await self._institutions.create_institution(
            name=normalized_name,
            country=_clean_optional(country),
            notes=_clean_optional(notes),
        )
        await self._audit.add_audit_log(
            action="institution_created",
            entity_type="institution",
            entity_id=institution.id,
            new_values={
                "name": institution.name,
                "country": institution.country,
                "notes": institution.notes,
            },
        )
        return institution

    async def list_institutions(self, *, limit: int) -> list[Institution]:
        return await self._institutions.list_institutions(limit=limit)

    async def get_institution(self, institution_id_or_name: str) -> Institution:
        value = institution_id_or_name.strip()
        institution: Institution | None
        try:
            institution = await self._institutions.get_institution_by_id(uuid.UUID(value))
        except ValueError:
            institution = await self._institutions.get_institution_by_name(value)
        if institution is None:
            raise RecordNotFoundError("Institution")
        return institution


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
