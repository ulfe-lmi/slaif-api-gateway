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
        "external_tool_mode": "select",
        "external_tool_destination_ids": "record_choice",
        "email_delivery_mode": "select",
    },
    "keys/detail.html": {
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


def test_expected_field_inventory_is_the_96_field_baseline() -> None:
    total = sum(len(fields) for fields in EXPECTED_FIELDS.values())
    assert total == 96, f"inventory drifted from the 96-field baseline: {total}"
    assert len(EXPECTED_FIELDS) == 33


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
    js = (
        REPO / "app" / "slaif_gateway" / "web" / "static" / "js" / "policy-selector.js"
    ).read_text(encoding="utf-8")
    assert "data-policy-manual" in js, "manual textareas must stay JS-synchronized"


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
