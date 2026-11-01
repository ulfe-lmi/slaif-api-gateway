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

import asyncio
import ast
import json
import uuid
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from fastapi.testclient import TestClient

from slaif_gateway.api import admin
from slaif_gateway.config import Settings
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
from slaif_gateway.main import create_app
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


# ---------------------------------------------------------------------------
# Admin GET optional bool filters: the "Any" option submits BLANK, which
# must parse as "no filter" (the same semantics as omitting the parameter)
# on the nine optional admin list filters. True/false keep their meaning;
# an invalid NON-blank value must still be rejected. This exercises the
# REAL FastAPI query parsing (a TypeAdapter-only check missed the original
# RHS `Query(None)` metadata loss), with no auth and no database: an
# unauthenticated parse-accepted request gets the 303 login redirect, a
# parse failure gets 422 before anything else.
# ---------------------------------------------------------------------------

_ADMIN_BOOL_FILTERS: tuple[tuple[str, str], ...] = (
    ("/admin/keys", "expired"),
    ("/admin/cohorts", "active"),
    ("/admin/providers", "enabled"),
    ("/admin/routes", "enabled"),
    ("/admin/routes", "visible"),
    ("/admin/pricing", "enabled"),
    ("/admin/pricing", "active"),
    ("/admin/fx", "active"),
    ("/admin/usage", "streaming"),
)


def _bool_filter_client() -> TestClient:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="s" * 40,
    )
    return TestClient(create_app(settings))


@pytest.mark.parametrize("path,param", _ADMIN_BOOL_FILTERS)
@pytest.mark.parametrize(
    ("value", "expected"),
    [("", 303), ("true", 303), ("false", 303), ("not-a-bool", 422)],
)
def test_admin_get_optional_bool_filter_any_blank_true_false_invalid(
    path: str, param: str, value: str, expected: int
) -> None:
    client = _bool_filter_client()
    response = client.get(path, params={param: value}, follow_redirects=False)
    assert response.status_code == expected, (
        f"{path}?{param}={value!r} must be {expected} (blank=Any=no filter)"
    )


# ---------------------------------------------------------------------------
# 195-a: selected-id hydration for kinds whose options carry authoritative
# display metadata (audit_target parent-scoped, one_time_secret lifecycle).
# A selection outside the initial latest-100 batch must keep its
# authoritative label instead of being dropped (audit_target) or degrading
# to a plain id==label fallback (one_time_secret).
# ---------------------------------------------------------------------------

_HYDRATION_TS = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def _uuid_for(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, name)


def _params_contain(params: dict, needle: object) -> bool:
    def _has(value: object) -> bool:
        if isinstance(value, (list, tuple, set)):
            return any(_has(item) for item in value)
        return str(value) == str(needle)

    return any(_has(value) for value in params.values())


def _scope_from_params(params: dict) -> tuple[str, ...] | None:
    """The entity-type scope a compiled audit statement would apply.

    ``None`` = unscoped; otherwise the bound value(s) (``entity_type ==``
    or ``entity_type IN``), simulating PostgreSQL: rows outside the
    scope simply do not exist for the query.
    """
    for key, value in params.items():
        if "entity_type" in key:
            if isinstance(value, (list, tuple, set)):
                return tuple(value)
            return (value,)
    return None


class _FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


def _audit_target_session(
    old_ids: list[uuid.UUID],
    old_types: dict[uuid.UUID, str],
    recent_ids: list[uuid.UUID],
    recent_type: str = "gateway_key",
) -> object:
    """Serves batch and selected statements like PostgreSQL: a parent
    scope present in the statement's bound parameters filters the rows
    (out-of-scope rows are never returned), and a selected fetch is
    recognized by the selected ids in its parameters."""

    class _AuditSession:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def execute(self, stmt: object) -> object:
            self.statements.append(stmt)
            params = stmt.compile(dialect=postgresql.dialect()).params
            scope = _scope_from_params(params)
            selected_fetch = any(_params_contain(params, old) for old in old_ids)
            rows: list[object] = []
            if selected_fetch:
                # SQL now returns at most one row per id (rank 1); the
                # newest eligible type wins and out-of-scope ids are
                # absent.
                for old in old_ids:
                    if (
                        _params_contain(params, old)
                        and (scope is None or old_types[old] in scope)
                    ):
                        rows.append(
                            SimpleNamespace(
                                entity_id=old, entity_type=old_types[old], latest=_HYDRATION_TS
                            )
                        )
            elif scope is None or recent_type in scope:
                rows = [
                    SimpleNamespace(
                        entity_id=recent, entity_type=recent_type, latest=_HYDRATION_TS
                    )
                    for recent in recent_ids
                ]
            return _FakeResult(rows)

    return _AuditSession()


def test_audit_target_selected_outside_batch_hydrates_authoritative_label() -> None:
    old = _uuid_for("slaif195-audit-older-target")
    recent = [_uuid_for(f"slaif195-audit-recent-{i}") for i in range(CHOICE_LIMIT)]
    session = _audit_target_session([old], {old: "owner"}, recent)

    choices = asyncio.run(
        load_choices(session, "audit_target", selected=(str(old),))
    )
    ids = [c.id for c in choices]
    hydrated = next(c for c in choices if c.id == str(old))
    assert hydrated.label == f"owner: {old}"
    # The hydrated selection is appended (requested order) and the OLDEST
    # non-selected batch entry is evicted to make room within the cap.
    assert ids[-1] == str(old)
    assert len(choices) == CHOICE_LIMIT
    assert str(recent[-1]) not in ids


def test_audit_target_selected_hydration_keeps_parent_scope_consistent() -> None:
    # A selected id whose entity type is OUTSIDE the current parent scope
    # must NOT be turned into an eligible choice (a user-supplied
    # selection is a display request, not eligibility); the same id IS
    # hydrated when its type is in scope, and the multi-parent OR scope
    # hydrates both parents' ids.
    old = _uuid_for("slaif195-audit-older-owner")
    recent = [_uuid_for(f"slaif195-audit-usage-{i}") for i in range(CHOICE_LIMIT)]
    session = _audit_target_session(
        [old], {old: "owner"}, recent, recent_type="usage_ledger"
    )

    choices = asyncio.run(
        load_choices(
            session, "audit_target", selected=(str(old),), target_type=("usage_ledger",)
        )
    )
    assert all(c.id != str(old) for c in choices), (
        "out-of-scope selection must not become an eligible choice"
    )

    in_scope = _audit_target_session([old], {old: "owner"}, [], recent_type="usage_ledger")
    choices = asyncio.run(
        load_choices(
            in_scope, "audit_target", selected=(str(old),), target_type=("owner",)
        )
    )
    assert any(c.id == str(old) and c.label == f"owner: {old}" for c in choices)

    first = _uuid_for("slaif195-audit-older-multi-a")
    second = _uuid_for("slaif195-audit-older-multi-b")
    multi = _audit_target_session(
        [first, second],
        {first: "owner", second: "institution"},
        [],
        recent_type="usage_ledger",
    )
    choices = asyncio.run(
        load_choices(
            multi,
            "audit_target",
            selected=(str(first), str(second)),
            target_type=("owner", "institution"),
        )
    )
    ids = {c.id: c.label for c in choices}
    assert ids[str(first)] == f"owner: {first}"
    assert ids[str(second)] == f"institution: {second}"


def test_audit_target_selected_hydration_preserves_requested_order() -> None:
    first = _uuid_for("slaif195-audit-older-first")
    second = _uuid_for("slaif195-audit-older-second")
    recent = [_uuid_for(f"slaif195-audit-recent-{i}") for i in range(CHOICE_LIMIT)]
    # The DB returns the second id first; the RESULT must follow the
    # requested selection order (first, then second) at the tail.
    session = _audit_target_session(
        [second, first], {second: "owner", first: "institution"}, recent
    )

    choices = asyncio.run(
        load_choices(session, "audit_target", selected=(str(first), str(second)))
    )
    ids = [c.id for c in choices]
    assert ids[-2:] == [str(first), str(second)]
    assert next(c for c in choices if c.id == str(first)).label == (
        f"institution: {first}"
    )


def test_audit_target_hydration_keeps_one_choice_per_selected_id() -> None:
    # One entity audited under two types: the LATEST event's type wins and
    # the id appears exactly once in the result.
    old = _uuid_for("slaif195-audit-older-mixed")
    recent = [_uuid_for(f"slaif195-audit-recent-{i}") for i in range(CHOICE_LIMIT)]

    class _MixedSession:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def execute(self, stmt: object) -> object:
            self.statements.append(stmt)
            params = stmt.compile(dialect=postgresql.dialect()).params
            if _params_contain(params, old):
                rows = [
                    SimpleNamespace(entity_id=old, entity_type="owner", latest=_HYDRATION_TS),
                    SimpleNamespace(
                        entity_id=old, entity_type="gateway_key", latest=_HYDRATION_TS
                    ),
                ]
            else:
                rows = [
                    SimpleNamespace(
                        entity_id=recent, entity_type="gateway_key", latest=_HYDRATION_TS
                    )
                    for recent in recent
                ]
            return _FakeResult(rows)

    choices = asyncio.run(
        load_choices(_MixedSession(), "audit_target", selected=(str(old),))
    )
    matches = [c for c in choices if c.id == str(old)]
    assert len(matches) == 1
    assert matches[0].label == f"owner: {old}"


def test_audit_target_hydration_never_selects_secret_bearing_or_full_rows() -> None:
    old = _uuid_for("slaif195-audit-older-minimal")
    recent = [_uuid_for(f"slaif195-audit-recent-{i}") for i in range(CHOICE_LIMIT)]
    session = _audit_target_session([old], {old: "owner"}, recent)

    asyncio.run(load_choices(session, "audit_target", selected=(str(old),)))
    assert session.statements, "expected batch + hydration statements"
    for stmt in session.statements:
        columns = {col.name for col in stmt.selected_columns}
        assert columns <= {"entity_id", "entity_type", "latest"}, columns


def test_one_time_secret_selected_outside_batch_hydrates_lifecycle_label() -> None:
    old = _uuid_for("slaif195-ots-older")
    recent = [_uuid_for(f"slaif195-ots-recent-{i}") for i in range(CHOICE_LIMIT)]

    class _OtsSession:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def execute(self, stmt: object) -> object:
            self.statements.append(stmt)
            params = stmt.compile(dialect=postgresql.dialect()).params
            if _params_contain(params, old):
                rows = [
                    SimpleNamespace(id=old, status="used", purpose="lifecycle review")
                ]
            else:
                rows = [
                    SimpleNamespace(id=recent, status="pending", purpose="bootstrap")
                    for recent in recent
                ]
            return _FakeResult(rows)

    session = _OtsSession()
    choices = asyncio.run(
        load_choices(session, "one_time_secret", selected=(str(old),))
    )
    hydrated = next(c for c in choices if c.id == str(old))
    # Authoritative public lifecycle label (same format as the batch), not
    # a plain id==label fallback; the purpose sub is preserved too.
    assert hydrated.label == f"{str(old)[:8]}… (used)"
    assert hydrated.sub == "lifecycle review"
    assert len(choices) == CHOICE_LIMIT
    # Minimal columns only: no statement may select a secret-bearing
    # column (encrypted payload / nonce) or the full row.
    for stmt in session.statements:
        columns = {col.name for col in stmt.selected_columns}
        assert "encrypted_payload" not in columns and "nonce" not in columns
        assert columns <= {"id", "status", "purpose"}


def test_one_time_secret_unknown_selected_keeps_plain_fallback() -> None:
    # An unknown (unfound) selected id keeps its id==label fallback option
    # instead of silently disappearing.
    unknown = "00000000-0000-0000-0000-00000000d00d"
    recent = [_uuid_for(f"slaif195-ots-recent-{i}") for i in range(CHOICE_LIMIT)]

    class _OtsSession:
        async def execute(self, stmt: object) -> object:
            params = stmt.compile(dialect=postgresql.dialect()).params
            if _params_contain(params, unknown):
                return _FakeResult([])  # the id is unknown to the source
            return _FakeResult(
                [
                    SimpleNamespace(id=recent, status="pending", purpose="bootstrap")
                    for recent in recent
                ]
            )

    choices = asyncio.run(
        load_choices(_OtsSession(), "one_time_secret", selected=(unknown,))
    )
    matches = [c for c in choices if c.id == unknown]
    assert len(matches) == 1 and matches[0].label == unknown


def test_one_time_secret_selected_in_batch_keeps_batch_label() -> None:
    # A selected id already inside the initial batch keeps its batch
    # choice (no duplicate, no eviction churn).
    old = _uuid_for("slaif195-ots-in-batch")
    recent = [_uuid_for(f"slaif195-ots-recent-{i}") for i in range(CHOICE_LIMIT - 1)] + [old]

    class _OtsSession:
        async def execute(self, stmt: object) -> object:
            params = stmt.compile(dialect=postgresql.dialect()).params
            if _params_contain(params, old):
                return _FakeResult(
                    [SimpleNamespace(id=old, status="used", purpose="lifecycle review")]
                )
            return _FakeResult(
                [
                    SimpleNamespace(id=row, status="pending", purpose="bootstrap")
                    for row in recent
                ]
            )

    choices = asyncio.run(
        load_choices(_OtsSession(), "one_time_secret", selected=(str(old),))
    )
    matches = [c for c in choices if c.id == str(old)]
    assert len(matches) == 1
    # The batch row for the selected id carries the pending label; the
    # selection must not duplicate it under the hydrated "used" label.
    assert matches[0].label == f"{str(old)[:8]}… (pending)"


# ---------------------------------------------------------------------------
# completion_profile kind (210-a)
# ---------------------------------------------------------------------------


def _write_profile(directory: Path, name: str, size: int = 8, mode: int = 0o644) -> Path:
    path = directory / name
    path.write_bytes(b"{}" if size <= 2 else b"{" + b" " * (size - 2) + b"}")
    path.chmod(mode)
    return path


def test_completion_profile_kind_lists_eligible_profiles(tmp_path) -> None:
    import asyncio

    root = tmp_path / "profiles"
    root.mkdir()
    _write_profile(root, "alpha-v1.json")
    _write_profile(root, "beta-v2.json")
    _write_profile(root, "bindings.json")
    _write_profile(root, "Bad ID.json")
    (root / "notes.txt").write_text("not a profile")

    choices = asyncio.run(
        load_choices(_FakeSession(), "completion_profile", profile_dir=str(root))
    )
    assert [c.id for c in choices] == ["alpha-v1", "beta-v2"]
    assert all(c.label == c.id for c in choices)


def test_completion_profile_query_filter_and_100_cap(tmp_path) -> None:
    import asyncio

    root = tmp_path / "profiles"
    root.mkdir()
    for index in range(105):
        _write_profile(root, f"p{index:03d}.json")

    all_choices = asyncio.run(
        load_choices(_FakeSession(), "completion_profile", profile_dir=str(root))
    )
    # enumeration stops at the cap (filesystem order) and the bounded
    # result is sorted - exactly 100 of the 105 eligible profiles
    ids = [c.id for c in all_choices]
    assert len(ids) == CHOICE_LIMIT
    assert ids == sorted(ids)
    assert set(ids) <= {f"p{i:03d}" for i in range(105)}

    queried = asyncio.run(
        load_choices(
            _FakeSession(), "completion_profile", profile_dir=str(root), q="p104"
        )
    )
    assert [c.id for c in queried] == ["p104"]


def test_completion_profile_older_selected_hydrates_directly(tmp_path) -> None:
    import asyncio

    root = tmp_path / "profiles"
    root.mkdir()
    for index in range(105):
        _write_profile(root, f"p{index:03d}.json")
    # an ACTUAL bindings file exists in the directory: the exclusion
    # must come from the law, not from a missing file
    _write_profile(root, "bindings.json")

    initial = asyncio.run(
        load_choices(_FakeSession(), "completion_profile", profile_dir=str(root))
    )
    initial_ids = {c.id for c in initial}
    eligible = {f"p{i:03d}" for i in range(105)} - initial_ids
    assert eligible, "the cap must leave at least one eligible id outside"

    # an older selected id (outside the OBSERVED initial batch) keeps its
    # label without re-scanning the tree
    older = sorted(eligible)[0]
    hydrated = asyncio.run(
        load_choices(
            _FakeSession(),
            "completion_profile",
            profile_dir=str(root),
            selected=(older,),
        )
    )
    assert older in {c.id for c in hydrated}

    # bindings is never hydrated as a profile, even though the file exists
    none_hydrated = asyncio.run(
        load_choices(
            _FakeSession(),
            "completion_profile",
            profile_dir=str(root),
            selected=("bindings",),
        )
    )
    assert all(c.id != "bindings" for c in none_hydrated)


def test_completion_profile_invalid_selected_components_refused(tmp_path) -> None:
    import asyncio

    root = tmp_path / "profiles"
    root.mkdir()
    _write_profile(root, "alpha-v1.json")

    # Path-component selected ids are refused by the ID law (before any
    # I/O) and never offered; a valid name in the SAME call hydrates
    # unchanged.
    choices = asyncio.run(
        load_choices(
            _FakeSession(),
            "completion_profile",
            profile_dir=str(root),
            selected=("../evil", "a/b", "alpha-v1"),
        )
    )
    assert [c.id for c in choices] == ["alpha-v1"]


def test_completion_profile_unsafe_custom_modes_refused(tmp_path) -> None:
    import asyncio

    root = tmp_path / "profiles"
    root.mkdir()
    _write_profile(root, "safe-v1.json", mode=0o644)
    _write_profile(root, "group-writable-v1.json", mode=0o664)
    _write_profile(root, "world-writable-v1.json", mode=0o602)
    _write_profile(root, "oversize-v1.json", size=65537)
    target = root / "safe-v1.json"
    (root / "symlink-v1.json").symlink_to(target)

    choices = asyncio.run(
        load_choices(_FakeSession(), "completion_profile", profile_dir=str(root))
    )
    assert [c.id for c in choices] == ["safe-v1"]


def test_completion_profile_relative_and_symlink_roots_refused(tmp_path) -> None:
    import asyncio
    import os as _os

    real = tmp_path / "real-profiles"
    real.mkdir()
    _write_profile(real, "alpha-v1.json")

    # a relative directory path offers no choices (core loader law)
    old_cwd = _os.getcwd()
    try:
        _os.chdir(tmp_path)
        relative_choices = asyncio.run(
            load_choices(
                _FakeSession(),
                "completion_profile",
                profile_dir="real-profiles",
            )
        )
    finally:
        _os.chdir(old_cwd)
    assert relative_choices == []

    # a symlinked root offers no choices either
    link = tmp_path / "linked-profiles"
    link.symlink_to(real)
    symlink_root = asyncio.run(
        load_choices(_FakeSession(), "completion_profile", profile_dir=str(link))
    )
    assert symlink_root == []


def test_completion_profile_bundled_directory_lists_data_profiles() -> None:
    import asyncio

    choices = asyncio.run(
        load_choices(_FakeSession(), "completion_profile", profile_dir="")
    )
    ids = [c.id for c in choices]
    assert "facial-scoring-v1" in ids
    assert "zap-it-v1" in ids
    assert "bindings" not in ids
