"""Versioned SME policy-bundle composition and drift detection."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ApprovedCatalogEntry, PolicyBundle, PolicyBundleRevision


class PolicyDriftError(ValueError):
    def __init__(self, missing_models: list[str], missing_tools: list[str]) -> None:
        self.missing_models = missing_models
        self.missing_tools = missing_tools
        super().__init__("Approved policy catalog drifted from requested resources")


class PolicyBundleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_bundle(self, *, organization_id: uuid.UUID, team_id=None, project_id=None, name: str):
        bundle = PolicyBundle(organization_id=organization_id, team_id=team_id, project_id=project_id, name=name)
        self._session.add(bundle)
        await self._session.flush()
        return bundle

    async def add_revision(self, *, bundle_id: uuid.UUID, policy: dict[str, object]):
        latest = await self._latest_revision_number(bundle_id)
        revision = PolicyBundleRevision(bundle_id=bundle_id, revision=latest + 1, policy_json=policy)
        self._session.add(revision)
        await self._session.flush()
        return revision

    async def import_catalog(self, *, revision_id: uuid.UUID, entries: list[dict[str, str]]):
        rows = [
            ApprovedCatalogEntry(
                revision_id=revision_id,
                entry_kind=str(entry["kind"]),
                provider=str(entry["provider"]),
                name=str(entry["name"]),
            )
            for entry in entries
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def preview(self, *, bundle_id: uuid.UUID, revision_id: uuid.UUID | None = None) -> dict[str, object]:
        if revision_id is None:
            revision = (
                await self._session.execute(
                    select(PolicyBundleRevision)
                    .where(PolicyBundleRevision.bundle_id == bundle_id)
                    .order_by(PolicyBundleRevision.revision.desc())
                    .limit(1)
                )
            ).scalar_one()
        else:
            revision = await self._session.get(PolicyBundleRevision, revision_id)

        entries = (
            await self._session.execute(select(ApprovedCatalogEntry).where(ApprovedCatalogEntry.revision_id == revision.id))
        ).scalars().all()

        return {
            "bundle_id": str(bundle_id),
            "revision": revision.revision,
            "revision_id": str(revision.id),
            "policy": dict(revision.policy_json),
            "models": [entry.name for entry in entries if entry.entry_kind == "model"],
            "tools": [f"{entry.provider}:{entry.name}" for entry in entries if entry.entry_kind == "tool"],
        }

    @staticmethod
    def check_drift(*, preview: dict[str, object], requested_models: list[str], requested_tools: list[str]) -> None:
        approved_models = set(preview["models"])
        approved_tools = set(preview["tools"])
        missing_models = sorted(set(requested_models) - approved_models)
        missing_tools = sorted(set(requested_tools) - approved_tools)
        if missing_models or missing_tools:
            raise PolicyDriftError(missing_models, missing_tools)

    async def _latest_revision_number(self, bundle_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(PolicyBundleRevision.revision)
            .where(PolicyBundleRevision.bundle_id == bundle_id)
            .order_by(PolicyBundleRevision.revision.desc())
            .limit(1)
        )
        return result.scalar() or 0
