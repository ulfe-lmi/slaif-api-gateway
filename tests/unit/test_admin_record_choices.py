"""Unit regressions for admin record-choice controls (objective 192-a).

Covers the exact failure classes found during review:

- attribute-serialization round-trip of the macro's ``data-initial-options``
  (plain dicts, real RecordChoice DTOs, markup canaries);
- cap-preserving multi-selection merge (a selected entry sitting at the
  batch tail must never be evicted);
- UUID spelling canonicalization for selected-id hydration;
- canonical vocabularies (endpoints / email statuses) instead of invented
  enums;
- the loader call-site spec shape (tuple of 3-tuples) in admin.py;
- the lookup endpoint must not refresh CSRF tokens or touch sessions;
- the offline report's fixed sort script boundary (identical bytes, no
  network/eval primitives).

These are pure unit tests: no database, no HTTP server, no browser.
"""

from __future__ import annotations

import ast
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from slaif_gateway.api import admin
from slaif_gateway.db.models import STATUS_VALUES_EMAIL_DELIVERIES, Owner
from slaif_gateway.services.admin_record_choices import (
    CHOICE_LIMIT,
    KNOWN_EMAIL_DELIVERY_STATUSES,
    KNOWN_ENDPOINTS,
    RecordChoice,
    UnknownChoiceKindError,
    _canonical_uuid,
    _endpoint_path,
    _ilike,
    _merge_selected_keep_cap,
    _uuids,
    load_choices,
)
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "app/slaif_gateway/services/admin_record_choices.py"
API_PATH = REPO_ROOT / "app/slaif_gateway/api/admin_record_choices.py"
ADMIN_PATH = REPO_ROOT / "app/slaif_gateway/api/admin.py"
MACRO_PATH = REPO_ROOT / "app/slaif_gateway/web/templates/_record_choice.html"
TABLE_SORT_PATH = REPO_ROOT / "app/slaif_gateway/web/static/js/table-sort.js"
RECORD_CHOICES_JS_PATH = REPO_ROOT / "app/slaif_gateway/web/static/js/record-choices.js"

CANARY_LABEL = '"><span data-canary-injected="1">marker</span>'


# ---------------------------------------------------------------------------
# data-initial-options attribute serialization (macro + tojson_attr filter)
# ---------------------------------------------------------------------------


class _AttrScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.attrs: dict[str, str] | None = None
        self.canary = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attribute_map = dict(attrs)
        if "data-rc" in attribute_map:
            self.attrs = attribute_map
        if "data-canary-injected" in attribute_map:
            self.canary = True


def _render_macro(options: object) -> str:
    macro = admin.templates.env.get_template("_record_choice.html").module.record_choice
    return str(macro("owner_id", "owner", "Owner", options=options))


def test_macro_options_roundtrip_plain_dict() -> None:
    options = [{"id": "a", "label": "Alpha", "sub": "safe"}]
    scanner = _AttrScan()
    scanner.feed(_render_macro(options))
    assert scanner.attrs is not None
    parsed = json.loads(scanner.attrs["data-initial-options"])
    assert parsed == options
    assert not scanner.canary


def test_macro_options_roundtrip_record_choice_dto() -> None:
    options = [RecordChoice("a", "Alpha", "safe")]
    scanner = _AttrScan()
    scanner.feed(_render_macro(options))
    assert scanner.attrs is not None
    parsed = json.loads(scanner.attrs["data-initial-options"])
    assert parsed == [{"id": "a", "label": "Alpha", "sub": "safe"}]
    assert not scanner.canary


def test_macro_options_markup_canary_stays_inert() -> None:
    options = [{"id": "a", "label": CANARY_LABEL, "sub": "safe"}]
    scanner = _AttrScan()
    scanner.feed(_render_macro(options))
    assert scanner.attrs is not None
    parsed = json.loads(scanner.attrs["data-initial-options"])
    assert parsed[0]["label"] == CANARY_LABEL
    assert not scanner.canary, "option label escaped into a real DOM element"


def test_tojson_attr_output_contains_no_raw_attribute_breakers() -> None:
    value = [
        {
            "id": "a",
            "label": CANARY_LABEL + " & 'quoted' <tags> 50%_x",
            "sub": "naïve • unicode",
        }
    ]
    rendered = admin.templates.env.from_string("{{ value | tojson_attr }}").render(value=value)
    for raw in ("'", "<", ">", "&"):
        assert raw not in rendered, f"raw {raw!r} would break the single-quoted attribute"
    assert json.loads(rendered) == [
        {"id": "a", "label": CANARY_LABEL + " & 'quoted' <tags> 50%_x", "sub": "naïve • unicode"}
    ]


def test_builtin_tojson_filter_preserved() -> None:
    # The built-in text-context tojson (used by routes/detail.html) must not
    # have been replaced by the attribute serializer.
    env = admin.templates.env
    assert env.filters["tojson"] is not env.filters["tojson_attr"]
    text_context = env.from_string("{{ value | tojson }}").render(value={"a": 1})
    assert json.loads(text_context) == {"a": 1}


# ---------------------------------------------------------------------------
# Cap-preserving merge and UUID canonicalization
# ---------------------------------------------------------------------------


def _batch(size: int, prefix: str = "b") -> list[RecordChoice]:
    # newest-first: b{size-1} ... b0
    return [RecordChoice(id=f"{prefix}{i}", label=f"{prefix}{i}") for i in range(size - 1, -1, -1)]


def test_merge_selected_outside_batch_evicts_oldest() -> None:
    batch = _batch(CHOICE_LIMIT)
    out = _merge_selected_keep_cap(
        batch, [RecordChoice(id="X", label="x"), RecordChoice(id="Y", label="y")]
    )
    ids = [c.id for c in out]
    assert len(out) == CHOICE_LIMIT
    assert ids[-2:] == ["X", "Y"]
    assert "b1" not in ids and "b0" not in ids  # oldest non-selected evicted


def test_merge_selected_at_batch_tail_is_protected() -> None:
    batch = _batch(CHOICE_LIMIT)
    tail_selected = batch[-1]
    out = _merge_selected_keep_cap(
        batch, [tail_selected, RecordChoice(id="OUT", label="out")]
    )
    ids = [c.id for c in out]
    assert tail_selected.id in ids, "selected entry at the batch tail was evicted"
    assert "OUT" in ids
    assert len(out) == CHOICE_LIMIT


def test_merge_selected_already_in_batch_is_unchanged() -> None:
    batch = _batch(CHOICE_LIMIT)
    middle = batch[50]
    out = _merge_selected_keep_cap(batch, [middle])
    assert out == batch


def test_merge_small_batch_grows_within_cap() -> None:
    batch = _batch(50)
    out = _merge_selected_keep_cap(batch, [RecordChoice(id="X", label="x")])
    assert len(out) == 51 and out[-1].id == "X"


def test_canonical_uuid_spelling_insensitive() -> None:
    canonical = "00000000-0000-0000-0000-000000000001"
    assert _canonical_uuid(canonical) == canonical
    assert _canonical_uuid("00000000000000000000000000000001") == canonical
    assert _canonical_uuid(canonical.upper()) == canonical
    assert _canonical_uuid(f" {canonical} ") == canonical
    assert _canonical_uuid("not-a-uuid") is None
    assert _canonical_uuid("") is None
    parsed = _uuids([canonical.upper(), "junk", "00000000-0000-0000-0000-000000000002"])
    assert [str(u) for u in parsed] == [canonical, "00000000-0000-0000-0000-000000000002"]


def test_ilike_escapes_user_wildcards() -> None:
    compiled = str(
        _ilike(Owner.email, "a_b%c").compile(compile_kwargs={"literal_binds": True})
    )
    assert "\\_" in compiled and "\\%" in compiled

# ---------------------------------------------------------------------------
# Canonical vocabularies and plain-value kinds (no DB needed)
# ---------------------------------------------------------------------------


def test_known_endpoints_derive_from_canonical_implementation_vocabulary() -> None:
    expected = {_endpoint_path(endpoint) for endpoint in IMPLEMENTED_CLIENT_ENDPOINTS}
    assert set(KNOWN_ENDPOINTS) == expected
    assert KNOWN_ENDPOINTS == tuple(sorted(KNOWN_ENDPOINTS))
    assert "/v1/chat/completions" in KNOWN_ENDPOINTS
    # Method prefixes are stripped for the route/pricing endpoint fields.
    assert not any(" " in endpoint for endpoint in KNOWN_ENDPOINTS)


def test_endpoint_path_reduces_method_prefixed_entries() -> None:
    assert _endpoint_path("GET /v1/responses/{response_id}") == "/v1/responses/{response_id}"
    assert _endpoint_path("/v1/models") == "/v1/models"


def test_known_email_delivery_statuses_are_canonical() -> None:
    assert KNOWN_EMAIL_DELIVERY_STATUSES == tuple(STATUS_VALUES_EMAIL_DELIVERIES)
    # The previously invented vocabulary must be gone.
    assert "consumed" not in KNOWN_EMAIL_DELIVERY_STATUSES
    assert "expired" not in KNOWN_EMAIL_DELIVERY_STATUSES
    assert "sending" in KNOWN_EMAIL_DELIVERY_STATUSES
    assert "ambiguous" in KNOWN_EMAIL_DELIVERY_STATUSES


def test_email_delivery_status_choices_and_query_filter() -> None:
    import asyncio

    async def _run() -> list[RecordChoice]:
        return await load_choices(_FakeSession(), "email_delivery_status", q="sent")

    choices = asyncio.run(_run())
    assert [c.id for c in choices] == ["sent"]
    assert all(c.label == c.id for c in choices)


class _FakeSession:
    """Enough of an AsyncSession for the DB-free vocabulary kinds."""

    async def execute(self, stmt: object) -> object:
        raise AssertionError("vocabulary kinds must not issue DB statements")


def test_unknown_choice_kind_raises() -> None:
    import asyncio

    async def _run() -> None:
        await load_choices(_FakeSession(), "gateway_keys")

    with pytest.raises(UnknownChoiceKindError):
        asyncio.run(_run())


def test_tool_destination_kind_returns_no_rows() -> None:
    import asyncio

    assert asyncio.run(load_choices(_FakeSession(), "tool_destination")) == []


def test_plain_value_selected_outside_batch_is_kept_within_cap() -> None:
    import asyncio

    class _EmptyResult:
        def all(self) -> list[object]:
            return []

    class _ModelSession:
        """Serves the five bounded model sources as empty result sets."""

        async def execute(self, stmt: object) -> object:
            return _EmptyResult()

    async def _run() -> list[RecordChoice]:
        return await load_choices(
            _ModelSession(),
            "model",
            selected=tuple(f"m-{i}" for i in range(9)) + ("ancient-model",),
        )

    choices = asyncio.run(_run())
    ids = [c.id for c in choices]
    # Empty catalog: every selected value hydrates as a plain option, capped.
    assert len(choices) <= CHOICE_LIMIT
    assert "ancient-model" in ids
    assert ids[-1] == "ancient-model"


def test_plain_value_selected_in_batch_protected_from_eviction() -> None:
    # The merge used by the plain-value tail: a selected value sitting at the
    # batch tail must survive when another selected value needs room.
    batch = _batch(CHOICE_LIMIT, prefix="model-")
    tail = batch[-1]
    out = _merge_selected_keep_cap(batch, [tail, RecordChoice(id="new-model", label="new-model")])
    ids = [c.id for c in out]
    assert tail.id in ids and "new-model" in ids and len(out) == CHOICE_LIMIT


# ---------------------------------------------------------------------------
# Loader call-site spec shape (tuple of 3-tuples) in admin.py
# ---------------------------------------------------------------------------


def _loader_call_specs() -> list[tuple[int, ast.expr]]:
    tree = ast.parse(ADMIN_PATH.read_text())
    specs: list[tuple[int, ast.expr]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name not in {"_load_admin_record_choices", "_load_admin_record_choices_safe"}:
            continue
        if len(node.args) < 2:
            continue
        spec = node.args[1]
        if isinstance(spec, ast.Name):
            continue  # forwarding call (e.g. the _safe wrapper)
        specs.append((node.lineno, spec))
    return specs


def test_all_loader_call_sites_pass_tuple_of_field_specs() -> None:
    specs = _loader_call_specs()
    assert specs, "expected _load_admin_record_choices call sites in admin.py"
    problems = []
    for lineno, spec in specs:
        if not isinstance(spec, ast.Tuple):
            problems.append((lineno, "outer spec is not a tuple literal"))
            continue
        for item in spec.elts:
            if not (isinstance(item, ast.Tuple) and len(item.elts) in (3, 4)):
                problems.append((lineno, f"bad entry: {ast.dump(item)[:80]}"))
    assert not problems, f"invalid loader specs: {problems}"


# ---------------------------------------------------------------------------
# Lookup endpoint read-only authentication invariants (source-level)
# ---------------------------------------------------------------------------


def test_lookup_endpoint_does_not_refresh_csrf_or_touch_session() -> None:
    source = API_PATH.read_text()
    assert "refresh_csrf_token" not in source, "lookups must never rotate the CSRF token"
    assert "_admin_page_context" not in source, "lookups must not use the mutating page context"
    assert "touch=False" in source
    assert "validate_admin_session" in source


def test_lookup_module_docstring_makes_no_readonly_transaction_claim() -> None:
    doc = ast.get_docstring(ast.parse(API_PATH.read_text()))
    assert doc is not None
    assert "read-only transaction" not in doc.lower()


# ---------------------------------------------------------------------------
# Offline report fixed sort script boundary
# ---------------------------------------------------------------------------


def _js_source(path: Path) -> str:
    return path.read_text()


def test_table_sort_js_has_no_network_or_dynamic_code_primitives() -> None:
    source = _js_source(TABLE_SORT_PATH)
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "new Function",
        "eval(",
        "</script",
    ):
        assert forbidden not in source, f"table-sort.js contains {forbidden!r}"
    choices_js = _js_source(RECORD_CHOICES_JS_PATH)
    for forbidden in ("new Function", "eval(", "</script"):
        assert forbidden not in choices_js, f"record-choices.js contains {forbidden!r}"
    # record-choices.js is allowed the single documented lookup GET.
    assert choices_js.count("fetch(") >= 1
    assert "/admin/record-choices" in choices_js


def test_report_embeds_identical_fixed_sort_script_bytes() -> None:
    from slaif_gateway.services.catalog_refresh import rendering

    embedded = rendering._fixed_sort_script()
    assert str(embedded).strip() == _js_source(TABLE_SORT_PATH).strip()
