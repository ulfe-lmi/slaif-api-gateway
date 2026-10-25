"""Bounded normalization of repeatable admin list-filter values (195-a).

Admin LIST pages accept one or more values per known-record/text filter
field (OR WITHIN a field, AND ACROSS fields). This module is the single
pure helper shared by the admin route handlers (the 11 GET lists and
the two CSV export POSTs) and the record-choice lookup endpoint; the
service/repository layers coerce scalar-or-sequence values through
:func:`as_value_tuple` / :func:`as_uuid_tuple` so legacy scalar
service/CLI callers keep working unchanged.

- a repeatable parameter value list (existing parameter names) is split
  on newlines (the no-JS ``textarea`` fallback serialization), stripped,
  and blank members are dropped for the accepted-value tuple;
- the RAW SUBMITTED count is enforced FIRST, incrementally during the
  split: every submitted element counts, including blanks and the
  newline-fallback members of one element, so blank/repeat floods
  cannot bypass the count or allocate arbitrarily before rejection;
- accepted members are de-duplicated preserving first-seen (stable)
  order;
- UUID fields are strictly parsed per member and canonicalized
  (case/hyphenation spelling-insensitive); ONE invalid member rejects
  the WHOLE field (a 400 at the handler), never silent removal; the
  unique cap for UUID fields follows canonicalization, so 21 case
  spellings of one id are one accepted value;
- bounds are enforced BEFORE any use and excess/oversize is a
  predictable error, never slice/ignore:
  * at most :data:`MAX_LIST_FILTER_VALUES` UNIQUE selected values per
    list field (canonical for UUID fields);
  * at most :data:`MAX_SUBMITTED_FILTER_VALUES` submitted values per
    field before normalization, including repeats and the newline
    fallback;
  * at most :data:`MAX_LIST_FILTER_VALUE_LENGTH` characters per value
    (the same conservative per-value bound the record-choice lookup
    hydration uses, so an otherwise valid >200-character text selection
    round-trips — this is NOT the 200-character search-term ``q``
    limit).

Error messages derive only from the FIXED parameter name and the
constants above; they never echo the submitted values (which may be
long or contain sensitive identifiers).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

# Unique selected values accepted PER LIST FIELD (list filters and the
# list-filter hydration path). The record-choice lookup's own
# ``selected``/scope parameters keep their separate, larger policy
# contract (up to 100 values) so existing policy multi-controls are not
# broken.
MAX_LIST_FILTER_VALUES = 20
# Submitted values accepted BEFORE normalization, counting every
# submitted element (repeats, blanks, newline-fallback members).
MAX_SUBMITTED_FILTER_VALUES = 100
# Conservative per-value character bound, shared with lookup hydration.
MAX_LIST_FILTER_VALUE_LENGTH = 1024


class AdminListFilterError(ValueError):
    """A submitted list-filter field violates a documented bound or format.

    Raised by the pure helpers; the admin handlers answer a 400 page with
    the fixed safe message. The message never contains raw values.
    """


def _split_members(
    raw_values: Sequence[str | None] | None, *, field_name: str
) -> list[str]:
    """Split a repeatable parameter into stripped non-blank members.

    The raw submitted count is enforced INCREMENTALLY while splitting
    (every submitted element counts, blanks included, and each element's
    newline-fallback members count individually), so a flood is rejected
    at the bound: the per-element split is itself bounded
    (``maxsplit=MAX_SUBMITTED_FILTER_VALUES``), so a single oversized
    newline flood never materializes more than the bound + 1 parts —
    the excess remainder stays one part and the count rejects at the
    bound before it is used. The per-value length bound is enforced per
    member as well. Accepted inputs are byte-for-byte equivalent to an
    unbounded split (an element with at most the bound newlines has no
    embedded newline left in its remainder).
    """
    members: list[str] = []
    submitted = 0
    for raw in raw_values or ():
        if raw is None:
            submitted += 1
            if submitted > MAX_SUBMITTED_FILTER_VALUES:
                raise _too_many_submitted(field_name)
            continue
        for part in str(raw).split("\n", MAX_SUBMITTED_FILTER_VALUES):
            submitted += 1
            if submitted > MAX_SUBMITTED_FILTER_VALUES:
                raise _too_many_submitted(field_name)
            member = part.strip()
            if not member:
                continue
            if len(member) > MAX_LIST_FILTER_VALUE_LENGTH:
                raise AdminListFilterError(
                    f"{field_name}: values are limited to "
                    f"{MAX_LIST_FILTER_VALUE_LENGTH} characters."
                )
            members.append(member)
    return members


def _too_many_submitted(field_name: str) -> AdminListFilterError:
    return AdminListFilterError(
        f"{field_name}: at most {MAX_SUBMITTED_FILTER_VALUES} submitted "
        f"values are accepted."
    )


def _too_many_unique(field_name: str) -> AdminListFilterError:
    return AdminListFilterError(
        f"{field_name}: at most {MAX_LIST_FILTER_VALUES} values are "
        f"accepted."
    )


def normalize_filter_values(
    raw_values: Sequence[str | None] | None, *, field_name: str
) -> tuple[str, ...] | None:
    """Normalize one repeatable text/list filter parameter.

    Returns ``None`` (field absent/all-blank = unfiltered) or a
    de-duplicated tuple in first-seen order. Raises
    :class:`AdminListFilterError` for oversize values, too many
    submitted values (raw, before normalization), or too many unique
    accepted values. Messages name only the fixed field and the limits,
    never the values.
    """
    members = _split_members(raw_values, field_name=field_name)
    if not members:
        return None
    deduped = tuple(dict.fromkeys(members))
    if len(deduped) > MAX_LIST_FILTER_VALUES:
        raise _too_many_unique(field_name)
    return deduped


def parse_uuid_filter_values(
    raw_values: Sequence[str | None] | None, *, field_name: str
) -> tuple[uuid.UUID, ...] | None:
    """Normalize a repeatable UUID filter parameter.

    The raw submitted cap and the per-value length/strict-parse checks
    run first (an invalid member rejects the whole field — the handler
    answers 400 — instead of being silently dropped). The unique cap
    follows CANONICALIZATION: equivalent case/hyphen spellings of one
    id de-duplicate to a single accepted value, and only distinct
    canonical ids count against :data:`MAX_LIST_FILTER_VALUES`.
    """
    members = _split_members(raw_values, field_name=field_name)
    if not members:
        return None
    parsed: list[uuid.UUID] = []
    seen: set[str] = set()
    for value in members:
        try:
            parsed_value = uuid.UUID(value)
        except ValueError:
            raise AdminListFilterError(
                f"{field_name}: every value must be a valid UUID."
            ) from None
        canonical = str(parsed_value)
        if canonical in seen:
            continue
        if len(seen) >= MAX_LIST_FILTER_VALUES:
            raise _too_many_unique(field_name)
        seen.add(canonical)
        parsed.append(parsed_value)
    return tuple(parsed)


def clean_text_filter(value: object) -> str | tuple[str, ...] | None:
    """One-or-many text-filter cleaning that preserves the scalar shape.

    The service pass-through generalization of the legacy admin
    ``_clean_filter``: a scalar returns a cleaned SCALAR (strip,
    empty/whitespace-only -> ``None``) exactly like before — existing
    scalar service->repository contracts are unchanged; a sequence
    (already normalized/capped at the API) is additive and returns a
    tuple of cleaned members or ``None``. Never erases a non-empty
    requested restriction.
    """
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (list, tuple, set)):
        items = tuple(
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        )
        return items or None
    raise TypeError("text filter value must be a string or a sequence of strings")


def or_equals(column, values: tuple) -> object:
    """One-or-many equality predicate (195-a): a single value keeps the
    exact legacy ``column == value`` SQL shape; multiple values are a
    bounded ``IN``. Callers pass an already-canonical tuple."""
    if len(values) == 1:
        return column == values[0]
    return column.in_(values)


def as_value_tuple(value: object) -> tuple[str, ...] | None:
    """Coerce a scalar-or-sequence text filter value to ``None`` or a
    tuple of the raw member strings.

    Existing service/CLI callers keep passing one scalar unchanged (it
    is wrapped, never normalized here — the per-family normalization,
    e.g. strip/case/LIKE, is owned by the repository predicate exactly
    as before 195). Empty strings/whitespace-only members mean "no
    filter" (the pre-195 blank-clear semantics); a non-empty requested
    restriction is never silently erased.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        items = tuple(str(item) for item in value if item is not None and str(item).strip())
        return items or None
    if isinstance(value, str):
        return (value,) if value.strip() else None
    raise TypeError("text list-filter value must be a string or a sequence of strings")


def as_uuid_tuple(value: object) -> tuple[uuid.UUID, ...] | None:
    """Coerce a scalar-or-sequence UUID filter value to ``None`` or a
    tuple of ``uuid.UUID``.

    Existing service/CLI callers keep passing one ``uuid.UUID``
    unchanged. STRICT: a wrong-type scalar or a non-UUID sequence member
    raises :class:`TypeError` rather than silently becoming "no filter"
    — a non-empty requested restriction must never be erased.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        items: list[uuid.UUID] = []
        for item in value:
            if not isinstance(item, uuid.UUID):
                raise TypeError("UUID list-filter values must be uuid.UUID instances")
            items.append(item)
        return tuple(items) or None
    raise TypeError("UUID list-filter value must be a uuid.UUID or a sequence of uuid.UUID")


def collapse_singleton(values: object) -> object:
    """Collapse a normalized one-or-many value to the legacy scalar shape.

    HTTP wiring helper (195-a): ``None``/empty stay ``None``; a
    single-member sequence collapses to the scalar member so a
    one-value request keeps the EXACT legacy service call (scalar
    service/CLI contracts and their tests are byte-identical); a real
    multi-selection stays a tuple. The templates/chips keep the
    normalized sequences; only the service-boundary argument collapses.
    Non-sequence scalars pass through unchanged.
    """
    if values is None or values == "":
        return None
    if isinstance(values, (list, tuple, set)):
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        return tuple(values)
    return values
