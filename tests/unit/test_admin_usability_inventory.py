"""Static GUI usability coverage inventory (objective 192-a).

Permanent audit that the full admin GUI surface stays covered:

- every admin ``<table>`` carries ``data-sortable`` (no silent
  unsortable list table);
- the independent minimum-96 known-reference / finite-choice field
  inventory (objective 192-a review baseline) is backed, field by field,
  by either the record-choice combobox macro, a native select, the
  dual-list policy selector (with manual-field sync), or a documented
  free-text justification;
- the usage status filter uses the canonical 6-value ledger vocabulary;
- the KEY POLICY endpoint picker carries the EXACT
  ``IMPLEMENTED_CLIENT_ENDPOINTS`` tokens (method prefixes included) and
  never the flattened path vocabulary used by route/pricing/usage path
  fields;
- the catalog proposal ``model-review.md`` artifact remains a non-GUI
  static Markdown export (no script injection surface).

These are source-structure assertions (no DB, no server): they pin the
inventory so a future template edit that drops a picker or a sortable
annotation fails the unit suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from slaif_gateway.api.admin import _build_policy_endpoint_choices
from slaif_gateway.db.models import (
    STATUS_VALUES_EMAIL_DELIVERIES,
    STATUS_VALUES_USAGE_LEDGER_ACCOUNTING,
)
from slaif_gateway.services.admin_record_choices import KNOWN_EMAIL_DELIVERY_STATUSES
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "app" / "slaif_gateway" / "web" / "templates"

# ---------------------------------------------------------------------------
# The independent minimum-96 known-reference / finite-choice field
# inventory (192-a review baseline cd691ab), encoded in-repo with the
# required control class per field:
#   record_choice -> searchable record combobox (latest ~100 + older search)
#   select        -> native select over a canonical/DB vocabulary
#   dual_list     -> dual-list policy selector + synced manual textarea
#   free_text     -> documented free-text justification (none remaining:
#                    institution/cohort name filters are known-option
#                    record choices that submit the NAME, with free typing)
# ---------------------------------------------------------------------------
EXPECTED_FIELDS: dict[str, dict[str, str]] = {
    "audit/list.html": {
        "action": "record_choice",
        "target_type": "record_choice",
        "target_id": "record_choice",
        "request_id": "record_choice",
        "actor_admin_id": "record_choice",
    },
    "cohorts/list.html": {"name": "record_choice", "active": "select"},
    "email_deliveries/list.html": {
        "status": "select",
        "owner_email": "record_choice",
        "gateway_key_id": "record_choice",
        "one_time_secret_id": "record_choice",
    },
    "fx/create.html": {
        "base_currency": "record_choice",
        "quote_currency": "record_choice",
        "source": "record_choice",
    },
    "fx/edit.html": {
        "base_currency": "record_choice",
        "quote_currency": "record_choice",
        "source": "record_choice",
    },
    "fx/import.html": {"import_format": "select"},
    "fx/list.html": {
        "base_currency": "record_choice",
        "quote_currency": "record_choice",
        "source": "record_choice",
        "active": "select",
    },
    # Institution name filter offers known institution names (submitted
    # NAME, latest 100 + older search, free typing retained); the
    # institution RECORD reference (owner's institution) is a separate
    # record_choice on owners/create + owners/edit.
    "institutions/list.html": {"name": "record_choice"},
    "keys/_policy_selector.html": {
        "allowed_providers": "dual_list",
        "allowed_endpoints": "dual_list",
        "allowed_models": "dual_list",
    },
    "keys/bulk_import.html": {"import_format": "select"},
    "keys/bulk_import_preview.html": {"import_format": "select"},
    "keys/calibration_preview.html": {"email_delivery_mode_default": "select"},
    "keys/create.html": {
        "owner_id": "record_choice",
        "cohort_id": "record_choice",
        "policy_source": "select",
        "external_tool_mode": "select",
        "external_tool_destination_ids": "record_choice",
        "email_delivery_mode": "select",
    },
    "keys/detail.html": {
        "rate_action_requests_per_window": "select",
        "rate_action_tokens_per_window": "select",
        "rate_action_concurrency": "select",
        "rate_action_window": "select",
        "endpoint": "select",
        "external_tool_mode": "select",
        "external_tool_destination_ids": "record_choice",
        "email_delivery_mode": "select",
    },
    "keys/list.html": {
        "status": "select",
        "owner_email": "record_choice",
        "public_key_id": "record_choice",
        "cohort_id": "record_choice",
        "expired": "select",
    },
    "openai_assisted/pricing.html": {
        "proposal_model": "record_choice",
        "currency": "record_choice",
        "endpoint_scope": "select",
        "include_models": "record_choice",
        "exclude_models": "record_choice",
    },
    "openai_assisted/routes.html": {
        "proposal_model": "record_choice",
        "endpoint_scope": "select",
        "include_models": "record_choice",
        "exclude_models": "record_choice",
    },
    # 211-a: the diagnostics lookup is ONE integrated record-choice
    # (select a retained ID or type a new one) plus the finite namespace
    # select; the cleanup reason/confirmation are deliberate free text.
    "operations/diagnostics.html": {
        "lookup_id": "record_choice",
        "lookup_namespace": "select",
    },
    "owners/create.html": {"institution_id": "record_choice"},
    "owners/edit.html": {"institution_id": "record_choice"},
    "owners/list.html": {
        # Owner email is a record choice (owner reference); the institution
        # and cohort NAME filters are known-option record choices on their
        # own list pages.
        "email": "record_choice",
        "institution_id": "record_choice",
        "cohort_id": "record_choice",
    },
    "pricing/create.html": {
        "provider": "record_choice",
        "upstream_model": "record_choice",
        "endpoint": "record_choice",
        "currency": "record_choice",
    },
    "pricing/edit.html": {
        "provider": "record_choice",
        "upstream_model": "record_choice",
        "endpoint": "record_choice",
        "currency": "record_choice",
    },
    "pricing/import.html": {"import_format": "select"},
    "pricing/list.html": {
        "provider": "record_choice",
        "model": "record_choice",
        "endpoint": "record_choice",
        "currency": "record_choice",
        "enabled": "select",
        "active": "select",
    },
    "providers/create.html": {"kind": "select"},
    "providers/discover_preview.html": {"preset": "select", "pricing_mode": "select"},
    "providers/edit.html": {"kind": "select"},
    "providers/list.html": {"provider": "record_choice", "enabled": "select"},
    "routes/create.html": {
        "requested_model": "record_choice",
        "match_type": "select",
        "endpoint": "record_choice",
        "provider": "record_choice",
        "upstream_model": "record_choice",
    },
    "routes/edit.html": {
        "requested_model": "record_choice",
        "match_type": "select",
        "endpoint": "record_choice",
        "provider": "record_choice",
        "upstream_model": "record_choice",
    },
    "routes/import.html": {"import_format": "select"},
    "routes/list.html": {
        "provider": "record_choice",
        "requested_model": "record_choice",
        "match_type": "select",
        "enabled": "select",
        "visible": "select",
    },
    "templates/detail.html": {
        "owner_id": "record_choice",
        "cohort_id": "record_choice",
        "email_delivery_mode": "select",
    },
    "usage/list.html": {
        "provider": "record_choice",
        "model": "record_choice",
        "endpoint": "record_choice",
        "request_id": "record_choice",
        "status": "select",
        "streaming": "select",
    },
}


def _template_source(template: str) -> str:
    return (TEMPLATES / template).read_text(encoding="utf-8")


def _field_marker(template: str, field: str, kind: str) -> bool:
    src = _template_source(template)
    if kind == "record_choice":
        # Macro call with the field as its name argument (progressive
        # enhancement combobox; the no-JS plain field is macro-guaranteed).
        return re.search(
            r"record_choice\(\s*[\"']" + re.escape(field) + r"[\"']", src
        ) is not None
    if kind == "select":
        return re.search(
            r"<select\s+name=[\"']" + re.escape(field) + r"[\"']", src
        ) is not None
    if kind == "dual_list":
        # Manual textarea (no-JS) carries the form field name AND the
        # data-policy-manual sync attribute for its dimension.
        return re.search(
            r"<textarea\s+[^>]*name=[\"']" + re.escape(field) + r"[\"'][^>]*data-policy-manual=",
            src,
            flags=re.DOTALL,
        ) is not None
    if kind == "free_text":
        return re.search(
            r"<input\s+[^>]*name=[\"']" + re.escape(field) + r"[\"']", src, flags=re.DOTALL
        ) is not None
    raise ValueError(f"unknown control kind {kind!r}")


def test_expected_field_inventory_is_the_110_field_baseline() -> None:
    total = sum(len(fields) for fields in EXPECTED_FIELDS.values())
    assert total == 110, f"inventory drifted from the 110-field baseline: {total}"
    assert len(EXPECTED_FIELDS) == 35


@pytest.mark.parametrize(
    "template,field",
    sorted(
        (template, field)
        for template, fields in EXPECTED_FIELDS.items()
        for field in fields
    ),
    ids=[f"{t}__{f}" for t, fs in EXPECTED_FIELDS.items() for f in fs],
)
def test_field_has_its_required_control(template: str, field: str) -> None:
    kind = EXPECTED_FIELDS[template][field]
    assert _field_marker(template, field, kind), (
        f"{template} field {field!r} lost its {kind} control"
    )


def test_every_admin_table_is_sortable() -> None:
    unsorted: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        for match in re.finditer(r"<table\b[^>]*>", path.read_text(encoding="utf-8")):
            if "data-sortable" not in match.group(0):
                unsorted.append(f"{path.name}:{match.group(0)[:80]}")
    assert unsorted == [], f"tables lost their sortable annotation: {unsorted}"


def _iter_admin_tables() -> list[tuple[str, str, str]]:
    """(relative_template, table_tag, table_block) for every sortable
    admin table; relative paths keep the list/detail templates distinct
    in failure messages."""
    out: list[tuple[str, str, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        src = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"<table\b[^>]*data-sortable[^>]*>.*?</table>", src, flags=re.DOTALL
        ):
            out.append((str(path.relative_to(TEMPLATES)), match.group(0)[:60], match.group(0)))
    return out


def test_every_admin_table_has_structural_ordinal_column() -> None:
    """194-a R1/R2 source law: EVERY admin table carries the
    first-position structural ordinal column and nothing else changes
    about its rows:

    - the LEAF header row (last thead row; grouped theads keep their
      plain group row above) starts with a plain ``<th data-ordinal>``;
    - each data row starts with ``<td class="row-ordinal">{{ loop.index }}``
      (server-rendered 1..N, renumbered by the fixed sort script);
    - empty-state rows are fixed (``data-no-sort``) and their single
      ``colspan`` equals the leaf column count, so the script can never
      number or corrupt them.
    """
    tables = _iter_admin_tables()
    # Approved first-cell forms: the legacy static table (server renders
    # 1..N, the fixed sorter renumbers from offset 0) and the 214-a
    # paged table (server renders CONTINUED ordinals across pages and
    # hands the accepted server offset to the sorter).
    static_cell = '<td class="row-ordinal">{{ loop.index }}</td>'
    paged_cell = '<td class="row-ordinal">{{ page.first_ordinal + loop.index0 }}</td>'
    # 212-a: +3 for the compatibility pages (index qualification rows,
    # index shipped presets, key migration review tuples).
    # 213-a: +5 for the replay-maintenance pages (index scopes,
    # inspection per-key aggregates, inspection route/model groups,
    # inspection exclusion reasons, review exclusion counts).
    # 214-a: +2 for the report pages (usage-summary group table,
    # reviewed pricing-disable row table).
    assert len(tables) == 40, f"expected 40 sortable admin tables, got {len(tables)}"
    problems: list[str] = []
    for name, tag, block in tables:
        thead = re.search(r"<thead>.*?</thead>", block, flags=re.DOTALL)
        if thead is None:
            problems.append(f"{name}: missing <thead> in {tag}")
            continue
        leaf_rows = re.findall(r"<tr\b[^>]*>.*?</tr>", thead.group(0), flags=re.DOTALL)
        leaf = leaf_rows[-1]
        header_ths = re.findall(r"<th\b[^>]*>", leaf)
        if "data-ordinal" not in header_ths[0]:
            problems.append(f"{name}: first leaf header is not data-ordinal: {header_ths[0]}")
        if any("data-col" in th for th in header_ths):
            problems.append(f"{name}: explicit data-col mapping reintroduced")
        column_count = len(header_ths)
        tbody = re.search(r"<tbody>.*?</tbody>", block, flags=re.DOTALL)
        if tbody is None:
            problems.append(f"{name}: missing <tbody>")
            continue
        data_rows = 0
        empty_rows = 0
        # Inspect EVERY authored tbody row (not just rows that already
        # carry the fixed marker): a data row must START with the SSR
        # ordinal cell, and an empty-state row must be a fixed
        # single-span row whose colspan equals the leaf column count.
        for row in re.findall(r"<tr\b[^>]*>.*?</tr>", tbody.group(0), flags=re.DOTALL):
            open_tag = row[: row.index(">") + 1]
            if "empty-state" in row:
                empty_rows += 1
                if "data-no-sort" not in open_tag:
                    problems.append(
                        f"{name}: empty-state row lost its fixed marker: {open_tag}"
                    )
                if f'colspan="{column_count}"' not in row:
                    problems.append(
                        f"{name}: empty-state colspan != {column_count}: {row[:80]}"
                    )
                if "row-ordinal" in row:
                    problems.append(
                        f"{name}: empty-state row must never be numbered: {row[:80]}"
                    )
                continue
            data_rows += 1
            first_cell = row.split("</td>")[0] + "</td>"
            if static_cell not in first_cell and paged_cell not in first_cell:
                problems.append(
                    f"{name}: data row does not START with the SSR ordinal cell: {first_cell[:100]}"
                )
        # 214-a: a table that renders continued ordinals must also give
        # the fixed sorter the accepted server offset (opt-in attribute;
        # default 0 preserves every static table).
        if paged_cell in block and "data-ordinal-offset" not in tag:
            problems.append(
                f"{name}: continued SSR ordinals without data-ordinal-offset on <table>"
            )
        if data_rows != 1:
            problems.append(f"{name}: expected exactly 1 authored data row, got {data_rows}")
        if empty_rows != 1:
            problems.append(f"{name}: expected exactly 1 empty-state row, got {empty_rows}")
    assert problems == [], problems


def test_import_tables_keep_source_row_provenance_distinct() -> None:
    """194-a R2: import tables label their provenance column "Source row"
    (sortable, the CSV/plan row identity) and no admin template keeps a
    bare "Row" header or collides the provenance with the ordinal column."""
    import_templates = (
        "fx/import_preview.html",
        "fx/import_result.html",
        "pricing/import_preview.html",
        "pricing/import_result.html",
        "routes/import_preview.html",
        "routes/import_result.html",
        "keys/bulk_import_preview.html",
        "keys/bulk_import_result.html",
    )
    problems: list[str] = []
    for template in import_templates:
        src = _template_source(template)
        if '<th data-sort-type="number">Source row</th>' not in src:
            problems.append(f"{template}: missing sortable 'Source row' header")
    for path in sorted(TEMPLATES.rglob("*.html")):
        src = path.read_text(encoding="utf-8")
        for th in re.findall(r"<th\b[^>]*>(.*?)</th>", src, flags=re.DOTALL):
            if th.strip() in ("Row", "Row number"):
                problems.append(f"{path.name}: bare 'Row' header reintroduced: {th!r}")
    assert problems == [], problems


def test_usage_status_select_uses_canonical_ledger_vocabulary() -> None:
    assert len(STATUS_VALUES_USAGE_LEDGER_ACCOUNTING) == 6
    admin_src = (REPO / "app" / "slaif_gateway" / "api" / "admin.py").read_text(
        encoding="utf-8"
    )
    status_options_lines = [
        line for line in admin_src.splitlines() if '"status_options"' in line
    ]
    assert any(
        "list(STATUS_VALUES_USAGE_LEDGER_ACCOUNTING)" in line
        for line in status_options_lines
    ), "usage status filter must be rendered from the canonical vocabulary"
    usage_src = _template_source("usage/list.html")
    assert "{% for status in status_options %}" in usage_src
    # The 6 canonical values, none invented.
    assert set(STATUS_VALUES_USAGE_LEDGER_ACCOUNTING) == {
        "pending",
        "finalized",
        "estimated",
        "failed",
        "interrupted",
        "released",
    }


def test_email_delivery_status_vocabulary_is_the_model_truth() -> None:
    assert KNOWN_EMAIL_DELIVERY_STATUSES == tuple(STATUS_VALUES_EMAIL_DELIVERIES)
    assert "sending" in KNOWN_EMAIL_DELIVERY_STATUSES
    assert "ambiguous" in KNOWN_EMAIL_DELIVERY_STATUSES
    assert "consumed" not in KNOWN_EMAIL_DELIVERY_STATUSES
    assert "expired" not in KNOWN_EMAIL_DELIVERY_STATUSES


def test_key_policy_endpoint_picker_uses_full_canonical_tokens() -> None:
    choices = _build_policy_endpoint_choices()
    values = [choice.value for choice in choices]
    # EXACT canonical vocabulary: method-prefixed tokens are distinct
    # grants and must never be flattened.
    assert set(values) == set(IMPLEMENTED_CLIENT_ENDPOINTS)
    assert values == sorted(values)
    assert any(v.startswith("GET ") for v in values)
    assert any(v.startswith("DELETE ") for v in values)
    assert any(v.startswith("POST ") for v in values)
    # The flattened path vocabulary (kind="endpoint") is for stored path
    # fields only: no key-policy form may use it.
    for template in (
        "keys/create.html",
        "keys/detail.html",
        "keys/_policy_selector.html",
        "templates/detail.html",
    ):
        src = _template_source(template)
        assert re.search(r"record_choice\(\s*[\"']endpoint[\"']", src) is None, (
            f"{template} must not feed the flattened endpoint kind into key policy"
        )


def test_policy_dual_list_and_manual_sync() -> None:
    src = _template_source("keys/_policy_selector.html")
    for dimension in ("providers", "endpoints", "models"):
        assert f'data-policy-available="{dimension}"' in src
        assert f'data-policy-selected="{dimension}"' in src
        assert f'data-policy-add="{dimension}"' in src
        assert f'data-policy-remove="{dimension}"' in src
        assert f'data-policy-toggle="{dimension}"' in src
        assert f'data-policy-manual="{dimension}"' in src
    # Server-side older-value search for the two latest-100 dimensions:
    # the visible page is presentation, not the authority ceiling.
    for dimension in ("provider", "model"):
        assert f'data-policy-{dimension}-search' in src, (
            f"the {dimension} search input was lost"
        )
        assert f'data-policy-{dimension}-search-results' in src, (
            f"the {dimension} search results list was lost"
        )
    js = (
        REPO / "app" / "slaif_gateway" / "web" / "static" / "js" / "policy-selector.js"
    ).read_text(encoding="utf-8")
    assert "data-policy-manual" in js, "manual textareas must stay JS-synchronized"
    assert 'createPolicySearch("providers")' in js, (
        "provider search must be wired to the lookup"
    )
    assert 'createPolicySearch("models")' in js, (
        "model search must be wired to the lookup"
    )


def test_openai_assisted_model_globs_are_multi_record_choices() -> None:
    for template in ("openai_assisted/pricing.html", "openai_assisted/routes.html"):
        src = _template_source(template)
        for field in ("include_models", "exclude_models"):
            block = re.search(
                r"record_choice\(\s*[\"']" + field + r"[\"'].{0,400}",
                src,
                flags=re.DOTALL,
            )
            assert block is not None, f"{template} lost the {field} record choice"
            assert "multi=true" in block.group(0), (
                f"{template} {field} must be a multi-value control"
            )
            assert "serialize=\"newline\"" in block.group(0), (
                f"{template} {field} must keep newline serialization"
            )


def test_model_review_md_stays_a_non_gui_static_export() -> None:
    src = (
        REPO / "app" / "slaif_gateway" / "services" / "provider_catalog_proposal.py"
    ).read_text(encoding="utf-8")
    assert "model-review.md" in src
    # The static Markdown export has no script injection surface.
    assert "<script" not in src.lower()
    # The catalog-refresh REVIEW.html (a GUI surface) gets the ONE fixed
    # bundled sort script; the proposal writer must not embed any script.
    rendering_src = (
        REPO / "app" / "slaif_gateway" / "services" / "catalog_refresh" / "rendering.py"
    ).read_text(encoding="utf-8")
    assert "_fixed_sort_script" in rendering_src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------------------------
# A1 regression: no NEW raw existing-record field may bypass the shared
# pickers. The fixed 110-field baseline pins the known fields; this audit
# additionally catches a newly added visible raw input/textarea whose
# name has existing-record reference semantics (the *_id/*_uuid patterns
# and the known semantic names) unless the field uses a shared
# record-choice picker, a native select, or carries a documented
# exception with a reason. Hidden inputs (CSRF etc.), checkboxes/radios/
# submit/file controls, and genuine free-text/new-record/date/number
# fields are out of scope here (the 110-field baseline classifies finite
# choices; this audit targets reference fields only).
# ---------------------------------------------------------------------------

_RAW_REF_SEMANTICS = frozenset(
    {
        "provider",
        "model",
        "requested_model",
        "upstream_model",
        "proposal_model",
        "include_models",
        "exclude_models",
        "endpoint",
        "request_id",
        "target_id",
        "target_type",
        "actor_admin_id",
        "owner_email",
    }
)

# Raw fields whose names sound like references but are legitimate:
_RAW_FIELD_EXCEPTIONS: dict[str, dict[str, str]] = {
    "owners/create.html": {
        "external_id": (
            "free-form identifier of an EXTERNAL system for the owner being "
            "created; not a reference to an existing SLAIF record"
        ),
    },
    "owners/edit.html": {
        "external_id": (
            "free-form identifier of an EXTERNAL system for the owner being "
            "edited; not a reference to an existing SLAIF record"
        ),
    },
    "providers/create.html": {
        "provider": (
            "the NEW provider's slug is the identity of the record being "
            "created (DB-unique); a picker would require the record to "
            "pre-exist"
        ),
    },
    "providers/edit.html": {
        "provider": (
            "the slug is the identity of the provider record being edited, "
            "not a reference to another record"
        ),
    },
    "keys/detail.html": {
        "model": (
            "explain-route query input: an operator may ask about a model "
            "that is NOT currently routed (to learn why it is blocked), so "
            "a finite picker cannot cover it; suggestions come from a "
            "read-only datalist"
        ),
    },
}


def _raw_field_names(src: str) -> list[str]:
    names: list[str] = []
    for attrs in re.findall(r"<input\b([^>]*)>", src, flags=re.DOTALL) + re.findall(
        r"<textarea\b([^>]*)>", src, flags=re.DOTALL
    ):
        match = re.search(r"""name=["']([a-z0-9_]+)["']""", attrs)
        if not match:
            continue
        kind = re.search(r"""type=["']([a-z]+)["']""", attrs)
        if kind and kind.group(1) in {
            "hidden",
            "checkbox",
            "radio",
            "submit",
            "button",
            "file",
        }:
            continue
        names.append(match.group(1))
    return names


def test_no_unclassified_raw_existing_record_fields() -> None:
    """A newly added raw existing-record field fails this audit: every
    visible raw input/textarea whose name has reference semantics must
    use the shared record-choice picker or a native select, or carry a
    documented exception with a reason. The stale-entry check keeps the
    exception table honest."""
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = str(path.relative_to(TEMPLATES))
        src = path.read_text(encoding="utf-8")
        covered = set(
            re.findall(r"""record_choice\(\s*["']([a-z0-9_]+)["']""", src)
        )
        covered |= set(re.findall(r"""<select\s+name=["']([a-z0-9_]+)["']""", src))
        exceptions = _RAW_FIELD_EXCEPTIONS.get(rel, {})
        for name in _raw_field_names(src):
            reference_like = (
                re.search(r"(_ids?|_uuid)$", name) is not None
                or name in _RAW_REF_SEMANTICS
            )
            if not reference_like or name in covered:
                continue
            assert name in exceptions, (
                f"{rel}: raw field {name!r} has existing-record reference "
                "semantics but no shared record-choice picker, native "
                "select, or documented exception — add the control or a "
                "justified exception"
            )
    for rel, names in _RAW_FIELD_EXCEPTIONS.items():
        raw = set(_raw_field_names((TEMPLATES / rel).read_text(encoding="utf-8")))
        for name in names:
            assert name in raw, f"{rel}: stale exception for {name!r} (no longer raw)"
