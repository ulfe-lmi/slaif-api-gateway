"""Repository helpers for catalog-refresh application records and apply
transactions.

Apply transaction contract (objective 182, A2/A3):

- ONE transaction performs: bounded waits, table locks in a FIXED order,
  committed-outcome lookup, stale-baseline comparison, all catalog
  mutations, the application record insert, and the audit row.
- Lock mode is SHARE ROW EXCLUSIVE on the four catalog tables: per the
  PostgreSQL 16 lock-compatibility matrix (explicit-locking / transaction
  isolation, Table 13.2) it conflicts with ROW EXCLUSIVE (acquired by every
  ordinary INSERT/UPDATE/DELETE, so ordinary catalog edits serialize
  against apply) and with itself (so other applies serialize too), while
  ACCESS SHARE (plain SELECT) and ROW SHARE (SELECT FOR UPDATE/SHARE)
  readers keep working. It is the minimum lock mode with that property:
  SHARE UPDATE EXCLUSIVE does NOT conflict with ROW EXCLUSIVE and would
  let ordinary writers race the locked comparison; SHARE EXCLUSIVE and
  stronger modes are unnecessary because they additionally block ROW
  SHARE readers. The behavior is proven on a real PostgreSQL 16 instance
  with an ordinary writer while the apply lock is held (not only two
  applies).
- Idempotency: the committed-outcome lookup is by CANONICAL BUNDLE IDENTITY
  FIRST (any plan hash), before the stale-baseline comparison. A retry of the
  same reviewed bundle therefore resolves its prior committed outcome even if
  a later code version or a current-freshness re-evaluation derives a
  different plan hash for the same sealed bytes. The durable uniqueness
  boundary (bundle_sha256, plan_sha256) remains the check-then-insert
  backstop. The committed row is never overwritten on retry.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from slaif_gateway.db.models import CatalogRefreshApplication

# Bounded waits: a lock request that cannot be satisfied within the bound
# fails the apply cleanly (no partial writes) instead of hanging.
LOCK_TIMEOUT_SQL = "SET LOCAL lock_timeout = '10s'"
STATEMENT_TIMEOUT_SQL = "SET LOCAL statement_timeout = '60s'"

# Fixed table lock order. Every apply transaction locks exactly these four
# tables in exactly this order (deterministic; no cross-transaction
# reordering, so applies cannot deadlock each other on catalog locks).
CATALOG_LOCK_ORDER: tuple[str, ...] = (
    "fx_rates",
    "model_routes",
    "pricing_rules",
    "provider_configs",
)

# See module docstring: conflicts with ROW EXCLUSIVE (ordinary catalog
# writers) and with itself (other applies); ACCESS SHARE / ROW SHARE
# readers are not blocked. SHARE UPDATE EXCLUSIVE would be insufficient
# (it does not conflict with ROW EXCLUSIVE).
CATALOG_LOCK_MODE = "SHARE ROW EXCLUSIVE"


async def apply_transaction_prelude(connection: AsyncConnection) -> None:
    """Set bounded lock/statement waits (transaction-local)."""
    await connection.execute(text(LOCK_TIMEOUT_SQL))
    await connection.execute(text(STATEMENT_TIMEOUT_SQL))


async def lock_catalog_tables(connection: AsyncConnection) -> None:
    """Lock the four catalog tables in the fixed order, bounded."""
    for table_name in CATALOG_LOCK_ORDER:
        await connection.execute(
            text(f"LOCK TABLE {table_name} IN {CATALOG_LOCK_MODE} MODE")
        )


async def current_database_actor(connection: AsyncConnection) -> str:
    """The actual PostgreSQL current_user of the applying transaction."""
    return str((await connection.execute(text("SELECT current_user"))).scalar_one())


class CatalogRefreshApplicationsRepository:
    """Access to the durable catalog-refresh application record."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_committed_by_bundle(
        self, *, bundle_sha256: str
    ) -> list[CatalogRefreshApplication]:
        """All committed records for the canonical bundle identity.

        Exactly one is expected in normal operation (the uniqueness boundary
        plus the committed lookup before mutation make duplicates
        unrepresentable); more than one is an operator anomaly the caller
        must refuse as ambiguous, never pick silently.
        """
        result = await self._session.execute(
            select(CatalogRefreshApplication)
            .where(CatalogRefreshApplication.bundle_sha256 == bundle_sha256)
            .order_by(
                CatalogRefreshApplication.effective_at.asc(),
                CatalogRefreshApplication.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def find_by_identity(
        self, *, bundle_sha256: str, plan_sha256: str
    ) -> CatalogRefreshApplication | None:
        result = await self._session.execute(
            select(CatalogRefreshApplication).where(
                CatalogRefreshApplication.bundle_sha256 == bundle_sha256,
                CatalogRefreshApplication.plan_sha256 == plan_sha256,
            )
        )
        return result.scalar_one_or_none()

    async def create_application_record(
        self,
        *,
        run_id: str,
        bundle_sha256: str,
        receipt_hmac_sha256: str,
        plan_sha256: str,
        mode: str,
        operator_actor: str,
        db_actor: str,
        admin_user_id: uuid.UUID | None,
        reason: str,
        effective_at: datetime,
        applied_provider_ids: list[str],
        applied_route_ids: list[str],
        applied_pricing_created_ids: list[str],
        applied_pricing_superseded_old_ids: list[str],
        applied_pricing_superseded_new_ids: list[str],
        applied_fx_created_ids: list[str],
        applied_fx_superseded_old_ids: list[str],
        applied_fx_superseded_new_ids: list[str],
        created_providers: int,
        created_routes: int,
        created_pricing: int,
        created_fx: int,
        superseded_pricing: int,
        superseded_fx: int,
        outcome: str = "committed",
    ) -> CatalogRefreshApplication:
        row = CatalogRefreshApplication(
            run_id=run_id,
            bundle_sha256=bundle_sha256,
            receipt_hmac_sha256=receipt_hmac_sha256,
            plan_sha256=plan_sha256,
            mode=mode,
            operator_actor=operator_actor,
            db_actor=db_actor,
            admin_user_id=admin_user_id,
            reason=reason,
            effective_at=effective_at,
            applied_provider_ids=list(applied_provider_ids),
            applied_route_ids=list(applied_route_ids),
            applied_pricing_created_ids=list(applied_pricing_created_ids),
            applied_pricing_superseded_old_ids=list(applied_pricing_superseded_old_ids),
            applied_pricing_superseded_new_ids=list(applied_pricing_superseded_new_ids),
            applied_fx_created_ids=list(applied_fx_created_ids),
            applied_fx_superseded_old_ids=list(applied_fx_superseded_old_ids),
            applied_fx_superseded_new_ids=list(applied_fx_superseded_new_ids),
            created_providers=created_providers,
            created_routes=created_routes,
            created_pricing=created_pricing,
            created_fx=created_fx,
            superseded_pricing=superseded_pricing,
            superseded_fx=superseded_fx,
            outcome=outcome,
        )
        self._session.add(row)
        await self._session.flush()
        return row
