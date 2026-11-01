"""Shared filter-preserving Previous/Next navigation for admin lists (214-a).

G13: every actual offset/limit GUI list renders reusable Previous/Next
navigation built from the ALLOWLISTED, ACCEPTED normalized filter pairs
(the same values the handler already validated for the current page),
never a raw copy of the incoming URL or arbitrary unknown query
parameters.

Semantics (honest offset paging):

- ``has_more`` comes from a cap+1 fetch (``row_count > page_size``), so a
  full page alone is NOT ``has_more``;
- the first displayed row ordinal is ``offset + 1`` (continuing across
  pages, never restarting at 1);
- ordinary offset paging can shift under concurrent inserts: pages are a
  view of the current filtered scope at request time, not a frozen
  snapshot, and no cursor/session infrastructure is promised;
- navigation URLs carry the page scope (limit) and the exact accepted
  selected filters, including REPEATED values (OR-within fields);
- no-JS: the navigation is plain anchor links.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

MAX_ADMIN_PAGE_LIMIT = 200


@dataclass(frozen=True, slots=True)
class AdminPage:
    """Accepted paging state for one admin list response."""

    page_size: int
    offset: int
    has_more: bool

    @property
    def first_ordinal(self) -> int:
        return self.offset + 1

    @property
    def can_prev(self) -> bool:
        return self.offset > 0

    @property
    def prev_offset(self) -> int:
        return max(0, self.offset - self.page_size)

    @property
    def next_offset(self) -> int:
        return self.offset + self.page_size


def build_page(*, page_size: int, offset: int, row_count: int) -> AdminPage:
    """Build the page state from a cap+1 fetch.

    ``row_count`` is the number of rows FETCHED for the current page
    (the handler fetches at most ``page_size + 1``).  ``has_more`` is
    true only when the fetch actually overflowed the page, never from a
    full page alone.
    """
    if page_size < 1:
        raise ValueError("page_size must be a positive integer")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    return AdminPage(page_size=page_size, offset=offset, has_more=row_count > page_size)


def build_navigation_url(base_path: str, params: list[tuple[str, str]]) -> str:
    """Build one navigation URL from allowlisted accepted filter pairs.

    ``params`` must contain ONLY the allowlisted, accepted normalized
    pairs for this list (including repeated values for OR-within fields,
    plus ``limit`` and ``offset``).  Values are percent-encoded; the
    order of pairs is preserved so repeated values round-trip exactly.
    """
    encoded = urlencode(params, doseq=False)
    if not encoded:
        return base_path
    return f"{base_path}?{encoded}"


def page_params(
    *,
    limit: int,
    offset: int,
    filters: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Assemble the ordered allowlisted pairs for one page URL.

    ``filters`` is the accepted/normalized list-filter pairs in the
    list's declared field order (repeated values preserved); ``limit``
    and ``offset`` complete the page scope.
    """
    return [
        *filters,
        ("limit", str(limit)),
        ("offset", str(offset)),
    ]
