"""Repository for OIDC identity records."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import OidcIdentity


class OidcIdentitiesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_issuer_subject(self, issuer_url: str, subject: str) -> OidcIdentity | None:
        stmt = select(OidcIdentity).where(
            OidcIdentity.issuer_url == issuer_url,
            OidcIdentity.subject == subject,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> list[OidcIdentity]:
        stmt = select(OidcIdentity).where(OidcIdentity.email == email)
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        issuer_url: str,
        subject: str,
        email: str,
    ) -> OidcIdentity:
        identity = OidcIdentity(
            owner_id=owner_id,
            issuer_url=issuer_url,
            subject=subject,
            email=email,
        )
        self._session.add(identity)
        await self._session.flush()
        return identity
