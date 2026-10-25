"""195-a focused unit coverage: bounded multi-value admin list filters.

Layers:

- the pure normalizer (``slaif_gateway.utils.admin_list_filters``):
  UUID canonical dedupe, per-field 20-unique / 100-submitted / 1024-char
  bounds (incremental, allocation-bounded), newline fallback, stable
  order, fixed-message errors that never echo values;
- the scalar compatibility contract: scalar-in -> cleaned scalar-out
  (``clean_text_filter``), raw-preserving ``as_value_tuple`` /
  ``as_uuid_tuple``, and ``collapse_singleton`` so a one-value HTTP
  request keeps the exact legacy scalar service call;
- the HTTP list-filter boundary (TestClient, services monkeypatched):
  multi UUID/text pass-through as tuples, legacy one-value links as
  scalars, 400 safe pages for invalid member / over-unique /
  over-submitted / over-length, and a >200-character text selection
  round-trip;
- the record-choices lookup bounds: explicit 100-value / 1024-char
  selected and target_type limits (no silent 8-value truncation), the
  no-selected empty-sequence boundary, and full (untruncated)
  parent-value preservation;
- JSON-safe export filter metadata (UUID/datetime tuples -> lists).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from slaif_gateway.db.models import Cohort
from slaif_gateway.services.admin_export_service import _safe_filter_metadata
from slaif_gateway.services.admin_record_choices import _target_type_values
from slaif_gateway.utils.admin_list_filters import (
    MAX_LIST_FILTER_VALUE_LENGTH,
    MAX_LIST_FILTER_VALUES,
    MAX_SUBMITTED_FILTER_VALUES,
    AdminListFilterError,
    as_uuid_tuple,
    as_value_tuple,
    clean_text_filter,
    collapse_singleton,
    normalize_filter_values,
    or_equals,
    parse_uuid_filter_values,
)
from tests.unit.test_admin_keys_routes import _app, _login, _row

FIELD = "cohort_id"


# ---------------------------------------------------------------------------
# Pure normalizer
# ---------------------------------------------------------------------------


def test_uuid_filter_canonical_spelling_dedupe_is_one() -> None:
    base = uuid.uuid4()
    variants = [
        str(base),
        str(base).upper(),
        str(base).replace("-", ""),
        str(base).replace("-", "").upper(),
        f"{base.int:032x}",
    ]
    # 21 spelling variants of ONE id collapse to a single accepted value.
    raw = [variants[i % len(variants)] for i in range(21)]
    result = parse_uuid_filter_values(raw, field_name=FIELD)
    assert result is not None
    assert len(result) == 1
    assert result[0] == base


def test_uuid_filter_invalid_member_rejects_whole_field() -> None:
    good = [str(uuid.uuid4()) for _ in range(3)]
    for index in range(len(good) + 1):
        raw = good[:index] + ["definitely-not-a-uuid"] + good[index:]
        try:
            parse_uuid_filter_values(raw, field_name=FIELD)
        except AdminListFilterError as exc:
            assert FIELD in str(exc)
            # Fixed message: the raw (potentially sensitive) value is
            # never echoed.
            assert "definitely-not-a-uuid" not in str(exc)
        else:
            raise AssertionError(f"invalid member at {index} was accepted")


def test_text_dedup_stable_first_seen_order() -> None:
    # First-seen order after strip: "b" (from " b ") precedes "a".
    result = normalize_filter_values([" b ", "a", "b", "B", " a "], field_name="f")
    assert result == ("b", "a", "B")


def test_newline_fallback_serialization() -> None:
    result = normalize_filter_values(["alpha\nbeta\ngamma", ""], field_name="f")
    assert result == ("alpha", "beta", "gamma")


def test_blank_members_clear_to_none() -> None:
    assert normalize_filter_values([], field_name="f") is None
    assert normalize_filter_values(None, field_name="f") is None
    assert normalize_filter_values(["", "   ", None], field_name="f") is None
    assert parse_uuid_filter_values(["", "  "], field_name=FIELD) is None


def test_unique_bound_exact_and_over() -> None:
    ids = [str(uuid.uuid4()) for _ in range(MAX_LIST_FILTER_VALUES)]
    assert len(parse_uuid_filter_values(ids, field_name=FIELD)) == (
        MAX_LIST_FILTER_VALUES
    )
    ids.append(str(uuid.uuid4()))
    try:
        parse_uuid_filter_values(ids, field_name=FIELD)
    except AdminListFilterError as exc:
        assert str(exc) == f"{FIELD}: at most {MAX_LIST_FILTER_VALUES} values are accepted."
        assert ids[-1] not in str(exc)
    else:
        raise AssertionError("21 unique values were accepted")


def test_submitted_count_bound_includes_blanks_and_newline_fallback() -> None:
    # Exactly the bound: accepted.
    assert len(normalize_filter_values(["v"] * MAX_SUBMITTED_FILTER_VALUES, field_name="f")) == 1
    # One over via repeats:
    try:
        normalize_filter_values(["v"] * (MAX_SUBMITTED_FILTER_VALUES + 1), field_name="f")
    except AdminListFilterError as exc:
        assert str(exc) == (
            f"f: at most {MAX_SUBMITTED_FILTER_VALUES} submitted values are accepted."
        )
    else:
        raise AssertionError("101 submitted repeats were accepted")
    # One over via BLANKS (blanks count against the raw bound):
    try:
        normalize_filter_values([""] * (MAX_SUBMITTED_FILTER_VALUES + 1), field_name="f")
    except AdminListFilterError:
        pass
    else:
        raise AssertionError("101 blank members were accepted")
    # One over via a single element's NEWLINE fallback members:
    try:
        normalize_filter_values(["\n".join(["v"] * (MAX_SUBMITTED_FILTER_VALUES + 1))], field_name="f")
    except AdminListFilterError:
        pass
    else:
        raise AssertionError("101 newline-fallback members were accepted")
    # The flood never materializes the whole string: a multi-MB newline
    # element is rejected at the bound (allocation stays bounded).
    try:
        normalize_filter_values(["\n" * (2 * 1024 * 1024)], field_name="f")
    except AdminListFilterError:
        pass
    else:
        raise AssertionError("a 2MiB newline flood was accepted")


def test_per_value_length_bound_exact_and_over() -> None:
    ok = "x" * MAX_LIST_FILTER_VALUE_LENGTH
    assert normalize_filter_values([ok], field_name="f") == (ok,)
    try:
        normalize_filter_values(["x" * (MAX_LIST_FILTER_VALUE_LENGTH + 1)], field_name="f")
    except AdminListFilterError as exc:
        assert str(exc) == (
            f"f: values are limited to {MAX_LIST_FILTER_VALUE_LENGTH} characters."
        )
    else:
        raise AssertionError("a 1025-character value was accepted")


def test_clean_text_filter_scalar_shape_is_legacy() -> None:
    # Scalar in -> cleaned scalar out (blank -> None), exactly like the
    # pre-195 _clean_filter service contract.
    assert clean_text_filter("  value  ") == "value"
    assert clean_text_filter("   ") is None
    assert clean_text_filter(None) is None
    assert clean_text_filter("value") == "value"
    # Sequence in -> tuple out (additive 195 behavior).
    assert clean_text_filter((" a ", "b", "", None)) == ("a", "b")
    assert clean_text_filter([]) is None
    assert clean_text_filter(()) is None
    try:
        clean_text_filter(42)
    except TypeError:
        pass
    else:
        raise AssertionError("non-text filter value was accepted")


def test_collapse_singleton_keeps_legacy_scalar_contract() -> None:
    single_uuid = uuid.uuid4()
    assert collapse_singleton(None) is None
    assert collapse_singleton(()) is None
    assert collapse_singleton("") is None
    assert collapse_singleton("scalar") == "scalar"
    assert collapse_singleton(("scalar",)) == "scalar"
    assert collapse_singleton((single_uuid,)) is single_uuid
    pair = ("a", "b")
    assert collapse_singleton(pair) == pair
    assert collapse_singleton(list(pair)) == pair


def test_as_value_tuple_preserves_raw_and_never_erases() -> None:
    assert as_value_tuple(None) is None
    assert as_value_tuple("   ") is None
    # Raw-preserving: no strip here (per-family normalization lives in
    # the repository predicate, exactly as before 195).
    assert as_value_tuple("  v  ") == ("  v  ",)
    assert as_value_tuple(["  ", "a", None, "b"]) == ("a", "b")
    assert as_value_tuple(()) is None
    try:
        as_value_tuple(7)
    except TypeError:
        pass
    else:
        raise AssertionError("non-text value accepted")


def test_as_uuid_tuple_is_strict() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert as_uuid_tuple(None) is None
    assert as_uuid_tuple(a) == (a,)
    assert as_uuid_tuple([a, b]) == (a, b)
    assert as_uuid_tuple((a,)) == (a,)
    for bad in ("x", 5, [a, "x"], ["x"]):
        try:
            as_uuid_tuple(bad)
        except TypeError:
            pass
        else:
            raise AssertionError(f"wrong-type UUID filter accepted: {bad!r}")


def test_or_equals_single_eq_multi_in() -> None:
    # Single value keeps the exact legacy ``column == value`` SQL shape;
    # multiple values are a bounded IN.
    single = str(or_equals(Cohort.name, ("v",)))
    assert " = " in single and " IN " not in single.upper()
    multi = str(or_equals(Cohort.name, ("a", "b")))
    assert " IN " in multi.upper()


def test_target_type_values_preserve_full_accepted_values() -> None:
    # 195-a lookup review regression: an API-accepted parent value
    # (>200 chars, within the 1024 bound) must reach the scope UNCHANGED.
    parent = "gateway_key_" + "p" * 240
    assert _target_type_values((parent,))[0] == parent
    multi = _target_type_values(("a" * 300, "b" * 300))
    assert multi == ("a" * 300, "b" * 300)
    scalar = _target_type_values("  " + "c" * 250 + "  ")
    assert scalar == ("c" * 250,)
    assert _target_type_values(None) is None
    assert _target_type_values("   ") is None
    assert _target_type_values(()) is None
    assert _target_type_values((" x ", "", "y")) == ("x", "y")


# ---------------------------------------------------------------------------
# HTTP list-filter boundary (TestClient, services monkeypatched)
# ---------------------------------------------------------------------------


def _keys_client(monkeypatch, client: TestClient, seen: dict[str, object]) -> None:
    async def list_keys(self, **kwargs):
        seen.update(kwargs)
        return [_row()]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    _login(monkeypatch, client)


def test_keys_multi_cohorts_pass_through_tuple_and_render_chips(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)
    cohort_a, cohort_b = uuid.uuid4(), uuid.uuid4()

    response = client.get(
        "/admin/keys", params={"cohort_id": [str(cohort_a), str(cohort_b)]}
    )

    assert response.status_code == 200
    assert seen["cohort_id"] == (cohort_a, cohort_b)
    # Both accepted values survive SSR into the multi control's textarea
    # (newline-serialized chip source).
    assert str(cohort_a) in response.text
    assert str(cohort_b) in response.text
    assert 'data-input-name="cohort_id"' in response.text


def test_keys_legacy_single_value_link_keeps_scalar_contract(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)
    cohort_a = uuid.uuid4()

    response = client.get("/admin/keys", params={"cohort_id": str(cohort_a)})

    assert response.status_code == 200
    # One-value request: EXACT legacy scalar service call (collapsed at
    # the HTTP boundary) — a uuid.UUID scalar, never a 1-tuple.
    assert type(seen["cohort_id"]) is uuid.UUID
    assert seen["cohort_id"] == cohort_a
    assert str(cohort_a) in response.text


def test_keys_no_filter_param_means_unfiltered(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)

    response = client.get("/admin/keys")

    assert response.status_code == 200
    assert seen["cohort_id"] is None
    assert seen["owner_email"] is None


def test_keys_invalid_uuid_member_is_400_without_echo(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)

    response = client.get(
        "/admin/keys", params={"cohort_id": ["not-a-uuid-secret"]}
    )

    assert response.status_code == 400
    assert "cohort_id" in response.text
    assert "valid UUID" in response.text
    # The error page never echoes the submitted (potentially sensitive)
    # value.
    assert "not-a-uuid-secret" not in response.text
    assert not seen, "the service must not run for a rejected field"


def test_keys_over_unique_uuids_is_400(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)

    response = client.get(
        "/admin/keys", params={"cohort_id": [str(uuid.uuid4()) for _ in range(21)]}
    )

    assert response.status_code == 400
    assert f"at most {MAX_LIST_FILTER_VALUES} values" in response.text
    assert not seen


def test_keys_over_submitted_values_is_400(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)

    response = client.get(
        "/admin/keys", params={"cohort_id": ["same"] * (MAX_SUBMITTED_FILTER_VALUES + 1)}
    )

    assert response.status_code == 400
    assert f"at most {MAX_SUBMITTED_FILTER_VALUES} submitted" in response.text
    assert not seen


def test_keys_over_length_value_is_400(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)

    response = client.get(
        "/admin/keys", params={"owner_email": "e" * (MAX_LIST_FILTER_VALUE_LENGTH + 1)}
    )

    assert response.status_code == 400
    assert f"limited to {MAX_LIST_FILTER_VALUE_LENGTH} characters" in response.text
    assert "e" * 100 not in response.text
    assert not seen


def test_keys_long_text_selection_over_200_chars_roundtrips(monkeypatch) -> None:
    seen: dict[str, object] = {}
    client = TestClient(_app())
    _keys_client(monkeypatch, client, seen)
    long_email = "long-enough-owner" + "n" * 240 + "@example.org"  # 255 chars

    response = client.get("/admin/keys", params={"owner_email": long_email})

    assert response.status_code == 200
    # The 200-char SEARCH limit (q) must not truncate a stored/selected
    # identifier: the full value passes to the service and renders.
    assert seen["owner_email"] == long_email.strip()
    assert long_email in response.text


# ---------------------------------------------------------------------------
# Record-choices lookup bounds (authenticated, fake DB session)
# ---------------------------------------------------------------------------


def test_lookup_no_selected_boundary_is_empty_sequence(monkeypatch) -> None:
    """The no-selection lookup must hit the real producer/consumer
    boundary (empty sequence, never None) for every kind."""
    client = TestClient(_app())
    _login(monkeypatch, client)

    for kind in ("owner", "cohort", "key", "audit_target", "request_id"):
        response = client.get("/admin/record-choices", params={"kind": kind})
        assert response.status_code == 200, kind
        payload = response.json()
        assert payload["choices"] == []
        assert response.headers.get("cache-control") == "no-store"


def test_lookup_selected_over_100_is_400_fixed_message(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    values = [f"v-{i}" for i in range(101)]
    response = client.get(
        "/admin/record-choices", params={"kind": "owner", "selected": values}
    )

    assert response.status_code == 400
    body = response.json()
    assert (
        body["error"]["message"]
        == f"At most 100 values of at most {MAX_LIST_FILTER_VALUE_LENGTH} "
        "characters are accepted per selected list."
    )
    assert "v-100" not in response.text, "raw values must never be echoed"


def test_lookup_selected_exact_100_is_accepted(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    values = [f"v-{i}" for i in range(100)]
    response = client.get(
        "/admin/record-choices", params={"kind": "owner", "selected": values}
    )
    assert response.status_code == 200


def test_lookup_selected_value_over_1024_is_400(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(
        "/admin/record-choices",
        params={"kind": "owner", "selected": ["s" * (MAX_LIST_FILTER_VALUE_LENGTH + 1)]},
    )
    assert response.status_code == 400
    assert "s" * 100 not in response.text


def test_lookup_target_type_multi_and_full_value(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    # A >200-character parent is WITHIN the explicit 1024 bound: it must
    # be accepted (and preserved in full by the service, covered by the
    # _target_type_values unit test above).
    parent = "gateway_key_" + "p" * 240
    response = client.get(
        "/admin/record-choices",
        params={"kind": "audit_target", "target_type": [parent, "owner"]},
    )
    assert response.status_code == 200
    response = client.get(
        "/admin/record-choices",
        params={"kind": "audit_target", "target_type": ["t" * (MAX_LIST_FILTER_VALUE_LENGTH + 1)]},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Export filter metadata
# ---------------------------------------------------------------------------


def test_safe_filter_metadata_is_json_safe_for_multi_filters() -> None:
    now = datetime.now(UTC)
    key_a, key_b = uuid.uuid4(), uuid.uuid4()
    metadata = _safe_filter_metadata(
        {
            "provider": ("openai", "openrouter"),
            "gateway_key_id": (key_a, key_b),
            "start_at": now,
            "status": "active",
            "empty_tuple": (),
            "blank": "",
            "none_value": None,
        }
    )
    serialized = json.dumps(metadata)  # must not raise
    parsed = json.loads(serialized)
    assert parsed["provider"] == ["openai", "openrouter"]
    assert parsed["gateway_key_id"] == [str(key_a), str(key_b)]
    assert parsed["start_at"] == str(now)
    assert parsed["status"] == "active"
    assert "empty_tuple" not in parsed
    assert "blank" not in parsed
    assert "none_value" not in parsed
