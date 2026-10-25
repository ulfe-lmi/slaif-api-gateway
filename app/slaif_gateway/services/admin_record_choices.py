"""Bounded read-only record/option choices for admin GUI controls (192-a).

This service powers the searchable record-choice dropdowns in the operator
console. It is strictly READ-ONLY:

- no DB writes, no audit entries, no quota/reservation/usage changes;
- a fixed allowlist of option kinds (no arbitrary table/column/SQL);
- every query is bounded AT THE DATABASE LEVEL (``LIMIT`` plus
  ``DISTINCT``/``GROUP BY`` in the SQL itself); the Python side only
  merges a small number of bounded per-source result sets;
- search queries are length-bounded and matched with simple ILIKE against
  label components AND the record's own public identifier (UUID / public
  id), so records are findable by id as well as by name;
- selected-id hydration looks up exactly the requested ids (bounded) and
  is merged so that a current selection outside the initial ~100 batch
  keeps its authoritative label within the cap; eviction never removes a
  selected entry, and accepted UUID spellings (case/hyphenation) are
  canonicalized before comparison;
- option values are public identifiers plus safe display metadata only:
  one-time secret VALUES, session tokens, provider credentials/URLs,
  password hashes, encrypted payloads, raw usage data, and full
  audit-log rows are never included in any option (minimal-column
  selects);
- fixed-vocabulary kinds use the codebase's canonical sources of truth
  (the gateway's implemented-endpoint vocabulary shared with the key
  policy selector, and the canonical DB status values), never invented
  enums.

Initial ordering is created_at DESC with a deterministic unique
tie-breaker (id ASC) where the entity has created_at; data-derived
distinct-value kinds order by the latest observed created_at (NULLs last)
with an alphabetical tie-breaker.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import (
    STATUS_VALUES_EMAIL_DELIVERIES,
    AdminUser,
    AuditLog,
    Cohort,
    FxRate,
    GatewayKey,
    Institution,
    ModelRoute,
    OneTimeSecret,
    Owner,
    PricingRule,
    ProviderConfig,
    UsageLedger,
)
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS

CHOICE_LIMIT = 100
QUERY_MAX_LENGTH = 200


def _endpoint_path(value: str) -> str:
    """Reduce a canonical endpoint entry to the plain /v1 path form.

    The canonical vocabulary (``IMPLEMENTED_CLIENT_ENDPOINTS``) mixes
    plain paths with method-prefixed entries (e.g. ``GET /v1/...``);
    route/pricing endpoint fields store plain paths, so method prefixes
    are stripped here. The source stays the single canonical set.
    """
    if " " in value:
        method, path = value.split(" ", 1)
        if method.isalpha() and path.startswith("/v1/"):
            return path
    return value


# The gateway's implemented client endpoint paths, derived from the same
# canonical vocabulary the key policy selector offers (see
# services/key_policy_validation.py). Not an invented enum.
KNOWN_ENDPOINTS: tuple[str, ...] = tuple(
    sorted({_endpoint_path(endpoint) for endpoint in IMPLEMENTED_CLIENT_ENDPOINTS})
)

# Canonical email-delivery status vocabulary (db.models).
KNOWN_EMAIL_DELIVERY_STATUSES: tuple[str, ...] = tuple(STATUS_VALUES_EMAIL_DELIVERIES)

# Kinds whose option id is the submitted value itself (model tokens,
# endpoints, currency codes, sources, audit vocabulary, request ids,
# fixed status words). A current selection outside the initial batch is
# re-hydrated as a plain id==label option so the UI keeps its label.
_PLAIN_VALUE_KINDS: frozenset[str] = frozenset(
    {
        "model",
        "endpoint",
        "currency",
        "fx_source",
        "audit_action",
        "audit_target_type",
        "request_id",
        "email_delivery_status",
        "one_time_secret",
        # Name-based list filters: the submitted filter value is the
        # entity NAME itself (never a UUID), so a selected name outside
        # the initial batch re-hydrates as a plain id==label option and
        # free-typed names (allow_new) are preserved on redisplay.
        "institution_name",
        "cohort_name",
    }
)


class UnknownChoiceKindError(ValueError):
    """Raised for option kinds outside the fixed allowlist."""


@dataclass(frozen=True, slots=True)
class RecordChoice:
    """One option: a public identifier plus safe display metadata."""

    id: str
    label: str
    sub: str = ""


def _ilike(column: Any, pattern: str) -> Any:
    """Bounded ILIKE with escaped user wildcards."""
    escaped = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%")


def _canonical_uuid(raw: str) -> str | None:
    """Canonical (lowercase, hyphenated) UUID spelling, or None.

    Accepted request ids may use uppercase or unhyphenated spellings;
    canonicalizing both sides keeps hydrated labels for equivalent ids.
    """
    try:
        return str(uuid.UUID(str(raw).strip()))
    except ValueError:
        return None


def _uuids(ids: Sequence[str]) -> list[uuid.UUID]:
    """Parse requested ids; silently drop non-UUID values (bounded set)."""
    parsed: list[uuid.UUID] = []
    for raw in ids:
        canonical = _canonical_uuid(str(raw))
        if canonical is not None:
            parsed.append(uuid.UUID(canonical))
    return parsed


def _sub(*parts: str | None) -> str:
    """Join non-empty display parts for the option sub line."""
    return " · ".join(part for part in (str(p) for p in parts) if part)


def _owner_choice(row: Any) -> RecordChoice:
    return RecordChoice(
        id=str(row.id),
        label=f"{row.name or ''} {row.surname or ''}".strip(),
        sub=_sub(row.email, row.id),
    )


def _institution_choice(row: Any) -> RecordChoice:
    return RecordChoice(
        id=str(row.id),
        label=str(row.name or ""),
        sub=_sub(row.country, row.id),
    )


def _cohort_choice(row: Any) -> RecordChoice:
    return RecordChoice(
        id=str(row.id),
        label=str(row.name or ""),
        sub=_sub(_cohort_window(row.starts_at, row.ends_at), row.id),
    )


def _cohort_window(starts_at: Any, ends_at: Any) -> str:
    """Display window for a cohort (ISO start/end, missing parts omitted)."""
    window = []
    if starts_at is not None:
        window.append(starts_at.isoformat())
    if ends_at is not None:
        window.append(ends_at.isoformat())
    return " ".join(window)

def _key_choice(row: Any) -> RecordChoice:
    return RecordChoice(
        id=str(row.id),
        label=f"{row.key_prefix or ''}{row.public_key_id or ''}",
        sub=_sub(row.status, row.id),
    )


def _key_public_choice(row: Any) -> RecordChoice:
    return RecordChoice(
        id=str(row.public_key_id),
        label=f"{row.key_prefix or ''}{row.public_key_id or ''}",
        sub=_sub(row.status),
    )


def _provider_choice(row: Any) -> RecordChoice:
    state = "enabled" if row.enabled else "disabled"
    if row.display_name:
        return RecordChoice(id=str(row.provider), label=str(row.provider), sub=_sub(row.display_name, state))
    return RecordChoice(id=str(row.provider), label=str(row.provider), sub=state)


def _admin_user_choice(row: Any) -> RecordChoice:
    return RecordChoice(
        id=str(row.id),
        label=str(row.display_name or row.email or ""),
        sub=_sub(row.email, row.id),
    )


def _one_time_secret_choice(row: Any) -> RecordChoice:
    # Minimal public lifecycle metadata only: never the secret value,
    # encrypted payload, nonce, or any other secret-bearing column.
    return RecordChoice(
        id=str(row.id),
        label=f"{str(row.id)[:8]}… ({row.status})",
        sub=str(row.purpose or ""),
    )


async def _fetch_selected(
    session: AsyncSession,
    stmt: Any,
    ids: Sequence[str],
    build: Any,
) -> list[RecordChoice]:
    """Hydrate specific selected ids (bounded) with their labels.

    ``stmt`` must already select the minimal columns and filter on
    ``id IN (<parsed ids>)`` plus any eligibility constraints (e.g.
    non-anonymized owners). Requested ids are canonicalized (UUID
    spelling-insensitive) before matching row ids; results preserve the
    requested order.
    """
    parsed_by_raw: dict[str, str] = {}
    parsed: list[uuid.UUID] = []
    for raw in ids:
        canonical = _canonical_uuid(str(raw))
        if canonical is None:
            continue
        if canonical not in parsed_by_raw.values():
            parsed.append(uuid.UUID(canonical))
        parsed_by_raw[str(raw)] = canonical
    if not parsed:
        return []
    rows = (await session.execute(stmt)).all()
    found: dict[str, RecordChoice] = {}
    for row in rows:
        choice = build(row)
        if choice is not None:
            found[str(row.id)] = choice
    # Preserve requested order; drop unknown ids (the UI keeps its own
    # label for those and the server error path is authoritative).
    return [
        found[parsed_by_raw[str(raw)]]
        for raw in ids
        if str(raw) in parsed_by_raw and parsed_by_raw[str(raw)] in found
    ]


def _merge_selected_keep_cap(
    batch: list[RecordChoice], selected: list[RecordChoice]
) -> list[RecordChoice]:
    """Merge hydrated selections without breaching the cap.

    ``batch`` is newest-first; selected options are appended at the end.
    When hydrated selections are not already in the batch, the OLDEST
    non-selected batch entries (walking from the tail) are evicted to
    make room. A selected entry is NEVER evicted, even when it sits at
    the batch tail, so every requested selected id keeps its
    authoritative label. The result is capped at ``CHOICE_LIMIT``
    entries plus any selections that could not fit (the final
    de-duplication keeps the selections, which are last).
    """
    if not selected:
        return list(batch)
    batch_ids = {choice.id for choice in batch}
    selected_ids = {choice.id for choice in selected}
    extra = [choice for choice in selected if choice.id not in batch_ids]
    if not extra:
        return list(batch)
    room = max(0, CHOICE_LIMIT - len(batch))
    to_evict = max(0, len(extra) - room)
    if to_evict:
        kept: list[RecordChoice] = []
        evicted = 0
        for entry in reversed(batch):  # oldest first
            if evicted < to_evict and entry.id not in selected_ids:
                evicted += 1
                continue
            kept.append(entry)
        batch = list(reversed(kept))
    return [*batch, *extra]


def _distinct_latest_stmt(table: Any, column: Any, *, like_query: str | None = None) -> Any:
    """Bounded DISTINCT single-column select ordered by latest seen.

    Groups by the column with ``max(created_at)`` as the recency signal
    (NULLs last, alphabetical tie-breaker) and caps at CHOICE_LIMIT rows
    in SQL.
    """
    stmt = (
        select(column.label("value"), func.max(table.created_at).label("latest"))
        .where(column.is_not(None), column != "")
        .group_by(column)
        .order_by(func.max(table.created_at).desc().nulls_last(), asc(column))
        .limit(CHOICE_LIMIT)
    )
    if like_query:
        stmt = stmt.where(_ilike(column, like_query))
    return stmt


def _scope_values(value: str | Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalize a scope parameter into a bounded tuple or ``None``.

    ``None`` means no scope. A single string is the dependent-picker /
    legacy form (a blank string is legacy "no scope" and becomes
    ``None``). A sequence is an explicit scope: ``()`` means EXPLICITLY
    empty (the caller returns no choices, mirroring the policy selector's
    client-side all/none/one/many filtering), non-empty means a bounded
    ``IN`` scope.
    """
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()[:QUERY_MAX_LENGTH]
        return (trimmed,) if trimmed else None
    cleaned = tuple(str(item).strip()[:QUERY_MAX_LENGTH] for item in value)
    return tuple(item for item in cleaned if item)


def _grouped_model_stmt(
    table: Any,
    column: Any,
    *,
    provider: tuple[str, ...] | None,
    endpoints: tuple[str, ...] | None = None,
    query: str | None,
) -> Any:
    """Bounded per-source distinct-model select.

    ``GROUP BY <model>`` with ``max(created_at)`` as the recency signal,
    ordered newest-first (NULLs last) with an alphabetical tie-breaker
    and capped at CHOICE_LIMIT rows in SQL.

    ``provider`` / ``endpoints`` are normalized scope tuples: ``None`` =
    unscoped; a non-empty tuple = bounded ``IN`` scope; an explicitly
    empty scope never reaches this helper (callers return no choices).
    """
    stmt = (
        select(column.label("model"), func.max(table.created_at).label("latest"))
        .where(column.is_not(None), column != "")
        .group_by(column)
        .order_by(
            func.max(table.created_at).desc().nulls_last(),
            asc(column),
        )
        .limit(CHOICE_LIMIT)
    )
    if provider is not None:
        stmt = stmt.where(table.provider.in_(provider))
    if endpoints is not None:
        stmt = stmt.where(table.endpoint.in_(endpoints))
    if query:
        stmt = stmt.where(_ilike(column, query))
    return stmt


def _target_type_values(
    value: str | Sequence[str] | None,
) -> tuple[str, ...] | None:
    """Normalize the ``audit_target`` entity-type scope (195-a).

    ``None`` = no scope; a single string is the legacy dependent-picker
    form (a blank string is legacy "no scope" and becomes ``None``). A
    sequence is an explicit scope: ``()`` means "no scope" (the audit
    picker has no all/none semantics), a non-empty tuple is a bounded
    ``IN`` scope applied BEFORE the ``LIMIT``.

    Values are preserved in FULL: the API layer enforces the explicit
    bounds (at most 100 values of at most
    ``MAX_LIST_FILTER_VALUE_LENGTH`` characters each, 400 on excess), so
    no downstream slice is applied here — truncating an accepted parent
    value would change its identity and silently rescope the targets
    (the 200-char ``q`` bound is the SEARCH-term limit only).
    """
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        return (trimmed,) if trimmed else None
    cleaned = tuple(str(item).strip() for item in value)
    return tuple(item for item in cleaned if item) or None

async def _distinct_name_choices(
    session: AsyncSession,
    *,
    table: Any,
    name_column: Any,
    meta_columns: Sequence[Any],
    sub_build: Any,
    query: str | None,
) -> list[RecordChoice]:
    """Bounded distinct-NAME choices for name-based list filters.

    The submitted filter value is the entity name itself (never a UUID),
    so option id and label are both the name. Two bounded queries:

    1. ``GROUP BY <name>`` with ``max(created_at)`` as the recency signal
       — the latest 100 distinct names in SQL, optionally ILIKE-searched,
       so a filter for an OLDER name resolves through server search;
    2. exactly the ``(name, latest)`` pairs from query 1, to read the
       newest matching record's display metadata (country / window + id)
       for the option sub line.
    """
    latest = func.max(table.created_at).label("latest")
    stmt = (
        select(name_column.label("name"), latest)
        .where(name_column.is_not(None), name_column != "")
        .group_by(name_column)
        .order_by(latest.desc().nulls_last(), asc(name_column))
        .limit(CHOICE_LIMIT)
    )
    if query:
        stmt = stmt.where(_ilike(name_column, query))
    name_rows = (await session.execute(stmt)).all()
    if not name_rows:
        return []
    meta_rows = (
        await session.execute(
            select(name_column, *meta_columns)
            .where(
                or_(
                    *[
                        and_(name_column == row.name, table.created_at == row.latest)
                        for row in name_rows
                    ]
                )
            )
            .limit(len(name_rows) * 2)
        )
    ).all()
    meta_by_name: dict[str, Any] = {}
    for meta in meta_rows:
        meta_by_name.setdefault(str(meta.name), meta)
    return [
        RecordChoice(
            id=str(row.name),
            label=str(row.name),
            sub=sub_build(meta_by_name.get(str(row.name))),
        )
        for row in name_rows
    ]


async def load_choices(
    session: AsyncSession,
    kind: str,
    *,
    q: str | None = None,
    selected: Sequence[str] = (),
    provider: str | Sequence[str] | None = None,
    endpoints: Sequence[str] | None = None,
    target_type: str | Sequence[str] | None = None,
) -> list[RecordChoice]:
    """Return bounded choices for one allowlisted kind.

    ``target_type`` scopes the ``audit_target`` kind to one or more
    entity types (the dependent picker's parent selection; a multi
    parent selection OR-scopes the targets BEFORE the LIMIT); all other
    kinds ignore it.

    ``provider`` scopes the ``model`` / ``policy_model`` kinds to one or
    more provider slugs and mirrors the policy selector's client-side
    all/none/one/many semantics: ``None`` = no scope, an explicitly empty
    scope returns no choices, a non-empty scope is a bounded ``IN``.
    ``endpoints`` additionally scopes the ``policy_model`` kind the same
    way (the model kind keeps its provider-only contract).
    """
    query = (q or "").strip()[:QUERY_MAX_LENGTH] or None
    provider_values = _scope_values(provider)
    endpoint_values = _scope_values(endpoints)
    target_type_values = _target_type_values(target_type)
    choices: list[RecordChoice] = []

    # Explicitly-empty scope (an all/none control with nothing selected)
    # must yield no choices, matching the filtered available lists.
    if provider_values == () and kind in {"model", "policy_model"}:
        return []
    if endpoint_values == () and kind == "policy_model":
        return []

    if kind == "owner":
        stmt = select(Owner.id, Owner.name, Owner.surname, Owner.email).where(
            Owner.anonymized_at.is_(None)
        )
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(Owner.name, query),
                    _ilike(Owner.surname, query),
                    _ilike(Owner.email, query),
                    _ilike(Owner.id.cast(String), query),
                )
            )
        stmt = stmt.order_by(desc(Owner.created_at), asc(Owner.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        choices = [_owner_choice(row) for row in rows]
        parsed = _uuids(selected)
        if parsed:
            sel_stmt = select(Owner.id, Owner.name, Owner.surname, Owner.email).where(
                Owner.anonymized_at.is_(None), Owner.id.in_(parsed)
            )
            choices = _merge_selected_keep_cap(
                choices, await _fetch_selected(session, sel_stmt, selected, _owner_choice)
            )

    elif kind == "owner_email":
        stmt = select(Owner.id, Owner.name, Owner.surname, Owner.email).where(
            Owner.anonymized_at.is_(None)
        )
        if query:
            stmt = stmt.where(_ilike(Owner.email, query))
        stmt = stmt.order_by(desc(Owner.created_at), asc(Owner.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        for row in rows:
            choices.append(
                RecordChoice(
                    id=row.email,
                    label=row.email,
                    sub=_sub(f"{row.name or ''} {row.surname or ''}".strip()),
                )
            )
        hydrated: list[RecordChoice] = []
        for raw in selected:
            raw_email = str(raw).strip()
            if not raw_email or any(c.id == raw_email for c in hydrated):
                continue
            in_batch = next((c for c in choices if c.id == raw_email), None)
            if in_batch is not None:
                # Already in the batch: hand it to the merge helper so it
                # is protected from eviction when other selections need room.
                hydrated.append(in_batch)
                continue
            hit = (
                await session.execute(
                    select(Owner.id, Owner.name, Owner.surname, Owner.email)
                    .where(Owner.email == raw_email, Owner.anonymized_at.is_(None))
                    .limit(1)
                )
            ).first()
            if hit is not None:
                hydrated.append(
                    RecordChoice(
                        id=hit.email,
                        label=hit.email,
                        sub=_sub(f"{hit.name or ''} {hit.surname or ''}".strip()),
                    )
                )
        choices = _merge_selected_keep_cap(choices, hydrated)

    elif kind == "institution":
        stmt = select(Institution.id, Institution.name, Institution.country)
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(Institution.name, query),
                    _ilike(Institution.id.cast(String), query),
                )
            )
        stmt = stmt.order_by(desc(Institution.created_at), asc(Institution.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        choices = [_institution_choice(row) for row in rows]
        parsed = _uuids(selected)
        if parsed:
            sel_stmt = select(Institution.id, Institution.name, Institution.country).where(
                Institution.id.in_(parsed)
            )
            choices = _merge_selected_keep_cap(
                choices,
                await _fetch_selected(session, sel_stmt, selected, _institution_choice),
            )

    elif kind == "cohort":
        stmt = select(Cohort.id, Cohort.name, Cohort.starts_at, Cohort.ends_at)
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(Cohort.name, query),
                    _ilike(Cohort.id.cast(String), query),
                )
            )
        stmt = stmt.order_by(desc(Cohort.created_at), asc(Cohort.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        choices = [_cohort_choice(row) for row in rows]
        parsed = _uuids(selected)
        if parsed:
            sel_stmt = select(Cohort.id, Cohort.name, Cohort.starts_at, Cohort.ends_at).where(
                Cohort.id.in_(parsed)
            )
            choices = _merge_selected_keep_cap(
                choices, await _fetch_selected(session, sel_stmt, selected, _cohort_choice)
            )

    elif kind == "institution_name":
        # institutions-list NAME filter: submitted value is the name
        # itself; latest 100 distinct names, older names via ILIKE search.
        choices = await _distinct_name_choices(
            session,
            table=Institution,
            name_column=Institution.name,
            meta_columns=(Institution.id, Institution.country),
            sub_build=lambda meta: _sub(meta.country, str(meta.id)) if meta else "",
            query=query,
        )

    elif kind == "cohort_name":
        # cohorts-list NAME filter: same contract as institution_name;
        # sub shows the newest matching cohort's window + id.
        choices = await _distinct_name_choices(
            session,
            table=Cohort,
            name_column=Cohort.name,
            meta_columns=(Cohort.id, Cohort.starts_at, Cohort.ends_at),
            sub_build=(
                lambda meta: _sub(
                    _cohort_window(meta.starts_at, meta.ends_at), str(meta.id)
                )
                if meta
                else ""
            ),
            query=query,
        )

    elif kind == "key":
        stmt = select(
            GatewayKey.id,
            GatewayKey.public_key_id,
            GatewayKey.key_prefix,
            GatewayKey.key_hint,
            GatewayKey.status,
        )
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(GatewayKey.public_key_id, query),
                    _ilike(GatewayKey.key_prefix, query),
                    _ilike(GatewayKey.key_hint, query),
                    _ilike(GatewayKey.id.cast(String), query),
                )
            )
        stmt = stmt.order_by(desc(GatewayKey.created_at), asc(GatewayKey.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        choices = [_key_choice(row) for row in rows]
        parsed = _uuids(selected)
        if parsed:
            sel_stmt = select(
                GatewayKey.id,
                GatewayKey.public_key_id,
                GatewayKey.key_prefix,
                GatewayKey.key_hint,
                GatewayKey.status,
            ).where(GatewayKey.id.in_(parsed))
            choices = _merge_selected_keep_cap(
                choices, await _fetch_selected(session, sel_stmt, selected, _key_choice)
            )

    elif kind == "key_public_id":
        stmt = select(
            GatewayKey.id,
            GatewayKey.public_key_id,
            GatewayKey.key_prefix,
            GatewayKey.key_hint,
            GatewayKey.status,
        )
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(GatewayKey.public_key_id, query),
                    _ilike(GatewayKey.key_prefix, query),
                    _ilike(GatewayKey.id.cast(String), query),
                )
            )
        stmt = stmt.order_by(desc(GatewayKey.created_at), asc(GatewayKey.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        for row in rows:
            choices.append(_key_public_choice(row))
        hydrated = []
        for raw in selected:
            raw_id = str(raw).strip()
            if not raw_id or any(c.id == raw_id for c in hydrated):
                continue
            in_batch = next((c for c in choices if c.id == raw_id), None)
            if in_batch is not None:
                hydrated.append(in_batch)
                continue
            hit = (
                await session.execute(
                    select(
                        GatewayKey.id,
                        GatewayKey.public_key_id,
                        GatewayKey.key_prefix,
                        GatewayKey.key_hint,
                        GatewayKey.status,
                    ).where(GatewayKey.public_key_id == raw_id).limit(1)
                )
            ).first()
            if hit is not None:
                hydrated.append(_key_public_choice(hit))
        choices = _merge_selected_keep_cap(choices, hydrated)

    elif kind == "provider":
        stmt = select(
            ProviderConfig.id,
            ProviderConfig.provider,
            ProviderConfig.display_name,
            ProviderConfig.enabled,
        )
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(ProviderConfig.provider, query),
                    _ilike(ProviderConfig.display_name, query),
                )
            )
        stmt = stmt.order_by(desc(ProviderConfig.created_at), asc(ProviderConfig.id)).limit(
            CHOICE_LIMIT
        )
        rows = (await session.execute(stmt)).all()
        choices = [_provider_choice(row) for row in rows]
        hydrated = []
        for raw in selected:
            raw_id = str(raw).strip()
            if not raw_id or any(c.id == raw_id for c in hydrated):
                continue
            in_batch = next((c for c in choices if c.id == raw_id), None)
            if in_batch is not None:
                # Provider slug already in the batch: protect it from
                # eviction when another selected provider needs room.
                hydrated.append(in_batch)
                continue
            hit = (
                await session.execute(
                    select(
                        ProviderConfig.id,
                        ProviderConfig.provider,
                        ProviderConfig.display_name,
                        ProviderConfig.enabled,
                    ).where(ProviderConfig.provider == raw_id).limit(1)
                )
            ).first()
            if hit is not None:
                hydrated.append(_provider_choice(hit))
        choices = _merge_selected_keep_cap(choices, hydrated)

    elif kind == "model":
        # Known model tokens from the local catalog AND usage history:
        # route requested/upstream models, pricing upstream models, and
        # historically used requested/resolved models. Both requested
        # and upstream tokens are first-class values (no coalescing that
        # would drop one when the other is present).
        sources = (
            (ModelRoute, ModelRoute.requested_model),
            (ModelRoute, ModelRoute.upstream_model),
            (PricingRule, PricingRule.upstream_model),
            (UsageLedger, UsageLedger.requested_model),
            (UsageLedger, UsageLedger.resolved_model),
        )
        by_model: dict[str, Any] = {}
        for table, column in sources:
            rows = (
                await session.execute(
                    _grouped_model_stmt(table, column, provider=provider_values, query=query)
                )
            ).all()
            for model, latest in rows:
                if model is None:
                    continue
                key = str(model)
                previous = by_model.get(key)
                if previous is None or (latest is not None and (previous is None or latest > previous)):
                    by_model[key] = latest
        ordered = sorted(
            by_model.items(),
            key=lambda item: (
                item[1] is None,
                -(item[1].timestamp() if item[1] is not None else 0),
                item[0],
            ),
        )
        for model, _latest in ordered[:CHOICE_LIMIT]:
            choices.append(RecordChoice(id=model, label=model))

    elif kind == "policy_model":
        # Key-policy model allow-list search: only REQUESTED model tokens
        # from ENABLED routes on ENABLED providers over IMPLEMENTED
        # endpoints. That base catalog eligibility is a SQL predicate
        # (subquery against provider_configs — no registry
        # materialization in Python) applied BEFORE the GROUP/LIMIT even
        # when the UI filters are "All" — a disabled provider or an
        # unimplemented endpoint is never a known policy choice, and an
        # out-of-scope client value can never widen the set. The policy
        # selector's provider/endpoint all/none/one/many scopes then
        # narrow further (canonical method-prefixed endpoint tokens are
        # reduced to the plain path form the route column stores; an
        # unimplemented scope value is dropped, and an explicitly empty
        # scope already returned no choices above). ILIKE-searched,
        # latest-first, capped at 100 — the "older models" server search
        # behind the bounded latest-100 policy catalog.
        implemented_paths = set(KNOWN_ENDPOINTS)
        endpoint_scope = (
            None
            if endpoint_values is None
            else tuple(sorted({_endpoint_path(token) for token in endpoint_values} & implemented_paths))
        )
        if endpoint_values is not None and not endpoint_scope:
            return []
        enabled_providers = (
            select(ProviderConfig.provider)
            .where(
                ProviderConfig.enabled.is_(True),
                ProviderConfig.provider.is_not(None),
                ProviderConfig.provider != "",
            )
            .scalar_subquery()
        )
        stmt = _grouped_model_stmt(
            ModelRoute,
            ModelRoute.requested_model,
            provider=provider_values,
            endpoints=endpoint_scope,
            query=query,
        ).where(
            ModelRoute.enabled.is_(True),
            ModelRoute.provider.in_(enabled_providers),
            ModelRoute.endpoint.in_(sorted(implemented_paths)),
        )
        rows = (await session.execute(stmt)).all()
        for model, _latest in rows:
            choices.append(RecordChoice(id=str(model), label=str(model)))

    elif kind == "policy_provider":
        # Key-policy provider allow-list search: provider slugs of ENABLED
        # provider configs (the submitted value), latest-first,
        # ILIKE-searched across slug and display name, capped at 100 — the
        # "older providers" server search behind the bounded latest-100
        # policy catalog.
        latest = func.max(ProviderConfig.created_at).label("latest")
        stmt = (
            select(
                ProviderConfig.provider.label("value"),
                ProviderConfig.display_name.label("display_name"),
                latest,
            )
            .where(
                ProviderConfig.enabled.is_(True),
                ProviderConfig.provider.is_not(None),
                ProviderConfig.provider != "",
            )
            .group_by(ProviderConfig.provider, ProviderConfig.display_name)
            .order_by(latest.desc().nulls_last(), asc(ProviderConfig.provider))
            .limit(CHOICE_LIMIT)
        )
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(ProviderConfig.provider, query),
                    _ilike(ProviderConfig.display_name, query),
                )
            )
        rows = (await session.execute(stmt)).all()
        for row in rows:
            choices.append(
                RecordChoice(
                    id=str(row.value),
                    label=str(row.value),
                    sub=str(row.display_name or ""),
                )
            )

    elif kind == "endpoint":
        for endpoint in KNOWN_ENDPOINTS:
            if query and query.lower() not in endpoint.lower():
                continue
            choices.append(RecordChoice(id=endpoint, label=endpoint))
            if len(choices) >= CHOICE_LIMIT:
                break

    elif kind == "currency":
        # DB-derived: the currency codes actually present in the local
        # fx/pricing tables, each source bounded in SQL and ordered by
        # latest observed created_at. No static invented vocabulary.
        by_code: dict[str, Any] = {}
        for table, column in (
            (FxRate, FxRate.base_currency),
            (FxRate, FxRate.quote_currency),
            (PricingRule, PricingRule.currency),
        ):
            rows = (
                await session.execute(_distinct_latest_stmt(table, column, like_query=query))
            ).all()
            for code, latest in rows:
                if not code:
                    continue
                key = str(code).upper()
                previous = by_code.get(key)
                if previous is None or (latest is not None and (previous is None or latest > previous)):
                    by_code[key] = latest
        for code, latest in sorted(
            by_code.items(),
            key=lambda item: (
                item[1] is None,
                -(item[1].timestamp() if item[1] is not None else 0),
                item[0],
            ),
        )[:CHOICE_LIMIT]:
            choices.append(RecordChoice(id=code, label=code))

    elif kind == "fx_source":
        rows = (
            await session.execute(_distinct_latest_stmt(FxRate, FxRate.source, like_query=query))
        ).all()
        for source, _latest in rows:
            if source:
                choices.append(RecordChoice(id=str(source), label=str(source)))

    elif kind == "audit_action":
        rows = (
            await session.execute(
                _distinct_latest_stmt(AuditLog, AuditLog.action, like_query=query)
            )
        ).all()
        for (action, _latest) in rows:
            if action:
                choices.append(RecordChoice(id=str(action), label=str(action)))

    elif kind == "audit_target_type":
        rows = (
            await session.execute(
                _distinct_latest_stmt(AuditLog, AuditLog.entity_type, like_query=query)
            )
        ).all()
        for (entity_type, _latest) in rows:
            if entity_type:
                choices.append(RecordChoice(id=str(entity_type), label=str(entity_type)))

    elif kind == "audit_target":
        # Distinct entities grouped BEFORE the LIMIT: many recent events
        # for one entity must not crowd all other known targets out of
        # the initial batch. Scoped to the parent picker's entity type
        # when provided.
        stmt = (
            select(
                AuditLog.entity_id.label("entity_id"),
                AuditLog.entity_type.label("entity_type"),
                func.max(AuditLog.created_at).label("latest"),
            )
            .where(AuditLog.entity_id.is_not(None))
            .group_by(AuditLog.entity_id, AuditLog.entity_type)
            .order_by(
                func.max(AuditLog.created_at).desc().nulls_last(),
                asc(AuditLog.entity_id),
            )
            .limit(CHOICE_LIMIT)
        )
        if target_type_values is not None:
            if len(target_type_values) == 1:
                stmt = stmt.where(AuditLog.entity_type == target_type_values[0])
            else:
                # Multi parent selection: OR scope BEFORE the LIMIT.
                stmt = stmt.where(AuditLog.entity_type.in_(target_type_values))
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(AuditLog.entity_id.cast(String), query),
                    _ilike(AuditLog.entity_type, query),
                )
            )
        rows = (await session.execute(stmt)).all()
        for row in rows:
            choices.append(
                RecordChoice(
                    id=str(row.entity_id),
                    label=f"{row.entity_type or 'unknown'}: {row.entity_id}",
                )
            )
        # Selected-id hydration (195-a): a selected target outside the
        # initial batch keeps its authoritative label. The selected
        # fetch applies the SAME parent constraint as the initial query
        # (all selected parent types ORed, unscoped when the parent is
        # absent): a user-supplied selection is a display request, not
        # eligibility or authority, so an out-of-scope id is never
        # turned into an eligible choice (the UI keeps its raw-id
        # fallback chip; the form submission is still validated).
        #
        # One choice per selected id is guaranteed IN SQL before the
        # 100-limit: the (entity_id, entity_type) groups are ranked per
        # id (latest eligible event first, deterministic tie-breaker)
        # and only rank 1 reaches the limit. Deduplicating in Python
        # AFTER ``LIMIT 100`` would let many (id, type) groups of the
        # first ids starve later eligible ids of their label. Requested
        # selection order is preserved in the merge; evictions never
        # touch a selected entry.
        parsed = _uuids(selected)
        if parsed:
            inner = (
                select(
                    AuditLog.entity_id.label("entity_id"),
                    AuditLog.entity_type.label("entity_type"),
                    func.max(AuditLog.created_at).label("latest"),
                    func.row_number()
                    .over(
                        partition_by=AuditLog.entity_id,
                        order_by=[
                            func.max(AuditLog.created_at).desc().nulls_last(),
                            AuditLog.entity_type.asc(),
                        ],
                    )
                    .label("rn"),
                )
                .where(AuditLog.entity_id.is_not(None), AuditLog.entity_id.in_(parsed))
                .group_by(AuditLog.entity_id, AuditLog.entity_type)
            )
            if target_type_values is not None:
                if len(target_type_values) == 1:
                    inner = inner.where(AuditLog.entity_type == target_type_values[0])
                else:
                    inner = inner.where(AuditLog.entity_type.in_(target_type_values))
            ranked = inner.subquery()
            sel_stmt = (
                select(ranked.c.entity_id, ranked.c.entity_type, ranked.c.latest)
                .where(ranked.c.rn == 1)
                .order_by(asc(ranked.c.entity_id))
                .limit(CHOICE_LIMIT)
            )
            sel_rows = (await session.execute(sel_stmt)).all()
            # Exactly one row per eligible id (SQL); map by canonical id
            # and keep the requested selection order.
            latest_by_id: dict[str, RecordChoice] = {}
            for row in sel_rows:
                key = str(row.entity_id)
                if key not in latest_by_id:
                    latest_by_id[key] = RecordChoice(
                        id=key,
                        label=f"{row.entity_type or 'unknown'}: {row.entity_id}",
                    )
            hydrated: list[RecordChoice] = []
            for raw in selected:
                canonical = _canonical_uuid(str(raw))
                if canonical is None:
                    continue
                choice = latest_by_id.get(canonical)
                if choice is not None and all(c.id != choice.id for c in hydrated):
                    hydrated.append(choice)
            choices = _merge_selected_keep_cap(choices, hydrated)

    elif kind == "audit_actor":
        stmt = select(AdminUser.id, AdminUser.display_name, AdminUser.email)
        if query:
            stmt = stmt.where(
                or_(
                    _ilike(AdminUser.display_name, query),
                    _ilike(AdminUser.email, query),
                    _ilike(AdminUser.id.cast(String), query),
                )
            )
        stmt = stmt.order_by(desc(AdminUser.created_at), asc(AdminUser.id)).limit(CHOICE_LIMIT)
        rows = (await session.execute(stmt)).all()
        choices = [_admin_user_choice(row) for row in rows]
        parsed = _uuids(selected)
        if parsed:
            sel_stmt = select(AdminUser.id, AdminUser.display_name, AdminUser.email).where(
                AdminUser.id.in_(parsed)
            )
            choices = _merge_selected_keep_cap(
                choices, await _fetch_selected(session, sel_stmt, selected, _admin_user_choice)
            )

    elif kind == "request_id":
        # Both request-id vocabularies the operator filters by: the usage
        # ledger (AI calls) AND the audit log (admin actions that carry a
        # request id). Each source is bounded in SQL; the small merge is
        # de-duplicated per request id, keeping the most recent context.
        usage_stmt = select(
            UsageLedger.request_id,
            UsageLedger.endpoint,
            UsageLedger.success,
            UsageLedger.http_status,
            UsageLedger.created_at,
        ).where(UsageLedger.request_id.is_not(None))
        if query:
            usage_stmt = usage_stmt.where(_ilike(UsageLedger.request_id, query))
        usage_stmt = usage_stmt.order_by(
            desc(UsageLedger.created_at), asc(UsageLedger.id)
        ).limit(CHOICE_LIMIT)
        audit_stmt = select(
            AuditLog.request_id,
            AuditLog.action,
            AuditLog.created_at,
        ).where(AuditLog.request_id.is_not(None))
        if query:
            audit_stmt = audit_stmt.where(_ilike(AuditLog.request_id, query))
        audit_stmt = audit_stmt.order_by(desc(AuditLog.created_at), asc(AuditLog.id)).limit(
            CHOICE_LIMIT
        )
        usage_rows = (await session.execute(usage_stmt)).all()
        audit_rows = (await session.execute(audit_stmt)).all()
        merged: dict[str, tuple[object, RecordChoice]] = {}
        for row in usage_rows:
            status = "ok" if row.success else f"error ({row.http_status})"
            merged[str(row.request_id)] = (
                row.created_at,
                RecordChoice(id=str(row.request_id), label=str(row.request_id), sub=_sub(row.endpoint, status)),
            )
        for row in audit_rows:
            existing = merged.get(str(row.request_id))
            if existing is not None and existing[0] is not None and row.created_at is not None:
                if existing[0] >= row.created_at:
                    continue
            merged[str(row.request_id)] = (
                row.created_at,
                RecordChoice(id=str(row.request_id), label=str(row.request_id), sub=f"audit: {row.action}"),
            )
        for _ts, choice in sorted(
            merged.values(),
            key=lambda item: (item[0] is None, -(item[0].timestamp() if item[0] is not None else 0)),
        )[:CHOICE_LIMIT]:
            choices.append(choice)

    elif kind == "email_delivery_status":
        for status in KNOWN_EMAIL_DELIVERY_STATUSES:
            if query and query.lower() not in status.lower():
                continue
            choices.append(RecordChoice(id=status, label=status))

    elif kind == "tool_destination":
        # Destination IDs are an operator-defined opaque namespace
        # (connector:*/remote_mcp:*), validated per key against the key's
        # own stored policy. There is no global table, so server search
        # returns no rows; the control's initial options come from the key's
        # current policy (rendered by the page route) and new values are
        # typed directly.
        return []

    elif kind == "one_time_secret":
        # Minimal columns only: public identifier and lifecycle state.
        # Never the secret value or ciphertext.
        stmt = select(OneTimeSecret.id, OneTimeSecret.status, OneTimeSecret.purpose)
        if query:
            stmt = stmt.where(_ilike(OneTimeSecret.id.cast(String), query))
        stmt = stmt.order_by(desc(OneTimeSecret.created_at), asc(OneTimeSecret.id)).limit(
            CHOICE_LIMIT
        )
        rows = (await session.execute(stmt)).all()
        choices = [_one_time_secret_choice(row) for row in rows]
        # Selected-id hydration (195-a): a selected secret outside the
        # initial batch keeps its public lifecycle label (status +
        # purpose) instead of degrading to a plain id==label fallback.
        # Still minimal columns: never the secret value or ciphertext.
        parsed = _uuids(selected)
        if parsed:
            sel_stmt = select(
                OneTimeSecret.id, OneTimeSecret.status, OneTimeSecret.purpose
            ).where(OneTimeSecret.id.in_(parsed))
            choices = _merge_selected_keep_cap(
                choices,
                await _fetch_selected(session, sel_stmt, selected, _one_time_secret_choice),
            )

    else:
        raise UnknownChoiceKindError(kind)

    # Plain-value kinds: keep a selected value that falls outside the
    # initial batch (e.g. a model/currency not in the latest 100 distinct
    # values) visible and selectable instead of silently dropping it.
    if kind in _PLAIN_VALUE_KINDS and selected:
        plain_selected: list[RecordChoice] = []
        for raw in selected:
            value = str(raw).strip()
            if not value or any(c.id == value for c in plain_selected):
                continue
            in_batch = next((c for c in choices if c.id == value), None)
            if in_batch is not None:
                # Already in the batch: protect it from eviction when
                # another selected value needs room (multi-selection).
                plain_selected.append(in_batch)
            else:
                plain_selected.append(RecordChoice(id=value, label=value))
        choices = _merge_selected_keep_cap(choices, plain_selected)

    # De-duplicate by id, preserving order.
    seen_ids: set[str] = set()
    unique: list[RecordChoice] = []
    for choice in choices:
        if choice.id in seen_ids:
            continue
        seen_ids.add(choice.id)
        unique.append(choice)
    return unique[:CHOICE_LIMIT]
