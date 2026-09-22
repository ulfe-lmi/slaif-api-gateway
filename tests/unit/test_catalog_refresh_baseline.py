"""180-e E1/E2: baseline projections, monetary validation, and FX classification.

Pure unit tests (no database): the runtime capabilities projection keeps
nested structure for the recognized contract and flags — instead of silently
dropping — anything unrepresentable; pricing metadata is projected to the
typed monetary allowlist; FX sources become sanitized URLs or safe labels;
and the baseline document's monetary fields are bounded (no decimal
overflow, no hostile spellings).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from slaif_gateway.schemas.catalog_refresh import (
    BaselineCounts,
    BaselineDocument,
    BaselineFxRow,
    BaselinePricingRow,
    BaselineProviderRow,
    BaselineRouteRow,
    BaselineTarget,
    parse_decimal_text,
)
from slaif_gateway.services.catalog_refresh.baseline import (
    _classify_fx_source_export,
    canonical_baseline_content,
    capabilities_fingerprint,
    classify_fx_source,
    load_baseline,
    project_pricing_metadata,
    project_route_capabilities,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.chat_completion_route_capabilities import (
    ensure_default_chat_completion_capabilities,
)


# --- E1: route capability projection ----------------------------------------

def test_full_runtime_chat_capabilities_project_verbatim() -> None:
    raw = ensure_default_chat_completion_capabilities({}, supports_streaming=True)
    canonical, unrepresented = project_route_capabilities(raw)
    assert unrepresented is False
    assert canonical == raw
    block = canonical["chat_completions"]
    assert block["chat_text"] is True
    assert block["chat_streaming"] is True
    # keys are sorted and values are plain bools (JSON-stable)
    assert list(block) == sorted(block)
    assert all(type(value) is bool for value in block.values())


def test_partial_known_bool_block_projects() -> None:
    raw = {"chat_completions": {"chat_text": True, "chat_streaming": True}}
    canonical, unrepresented = project_route_capabilities(raw)
    assert unrepresented is False
    assert canonical == {"chat_completions": {"chat_streaming": True, "chat_text": True}}


def test_unknown_top_level_key_flags_unrepresented_and_is_dropped() -> None:
    raw = {"chat_completions": {"chat_text": True}, "mystery_block": {"x": True}}
    canonical, unrepresented = project_route_capabilities(raw)
    assert unrepresented is True
    assert "mystery_block" not in canonical
    # the recognized sibling block still projects (no wholesale loss)
    assert canonical == {"chat_completions": {"chat_text": True}}


def test_violating_bool_block_is_dropped_whole() -> None:
    # an inner key outside the known contract drops the entire block:
    # partial data is never published as canonical
    raw = {"chat_completions": {"chat_text": True, "bogus_key": False}}
    canonical, unrepresented = project_route_capabilities(raw)
    assert unrepresented is True
    assert canonical == {}


def test_non_bool_value_flags_unrepresented() -> None:
    raw = {"chat_completions": {"chat_text": "yes"}}
    canonical, unrepresented = project_route_capabilities(raw)
    assert unrepresented is True
    assert canonical == {}
    raw = {"chat_completions": {"chat_text": 1}}
    canonical, unrepresented = project_route_capabilities(raw)
    assert unrepresented is True


def test_non_mapping_capabilities_flag_unrepresented() -> None:
    canonical, unrepresented = project_route_capabilities(["chat_text"])
    assert unrepresented is True
    assert canonical == {}


def test_codex_limits_contract_projects_and_rejects() -> None:
    ok = {
        "codex_limits": {
            "context_window_tokens": 1050000,
            "default_max_output_tokens": 32768,
            "max_output_tokens": 128000,
        }
    }
    canonical, unrepresented = project_route_capabilities(ok)
    assert unrepresented is False
    assert canonical["codex_limits"] == ok["codex_limits"]

    # output > max: violates the runtime contract, whole block dropped
    bad = {
        "codex_limits": {
            "context_window_tokens": 10,
            "default_max_output_tokens": 20,
            "max_output_tokens": 5,
        }
    }
    canonical, unrepresented = project_route_capabilities(bad)
    assert unrepresented is True
    assert "codex_limits" not in canonical


def test_external_tools_contract_projects_and_rejects() -> None:
    ok = {
        "version": 1,
        "supported_capabilities": [],
        "approved_destination_ids": [],
        "max_provider_tool_calls_per_request": 0,
        "call_limit_enforced": False,
        "final_usage_required": False,
        "final_cost_required": False,
    }
    canonical, unrepresented = project_route_capabilities({"external_tools": ok})
    assert unrepresented is False
    assert canonical["external_tools"] == ok

    canonical, unrepresented = project_route_capabilities({"external_tools": {"version": 99}})
    assert unrepresented is True
    assert "external_tools" not in canonical


def test_none_and_empty_capabilities_are_represented() -> None:
    canonical, unrepresented = project_route_capabilities(None)
    assert (canonical, unrepresented) == ({}, False)
    canonical, unrepresented = project_route_capabilities({"chat_completions": {}})
    assert unrepresented is False
    assert canonical == {"chat_completions": {}}


def test_fingerprint_is_opaque_deterministic_identity() -> None:
    raw = {"chat_completions": {"chat_text": True}}
    fp_a = capabilities_fingerprint(raw)
    fp_b = capabilities_fingerprint(dict(raw))
    assert fp_a == fp_b
    assert len(fp_a) == 64 and int(fp_a, 16) >= 0
    expected = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert fp_a == expected
    # a different raw map has a different fingerprint
    assert capabilities_fingerprint({"chat_completions": {"chat_text": False}}) != fp_a
    assert capabilities_fingerprint(None) == capabilities_fingerprint({})


# --- E1: FX source classification --------------------------------------------

def test_fx_source_url_is_sanitized() -> None:
    url, label = classify_fx_source("https://user:pw@data.example/eurofx?token=abc#frag")
    assert url == "https://data.example/eurofx"
    assert label is None
    url, _ = classify_fx_source("http://ecb.local:8080/rates")
    assert url == "http://ecb.local:8080/rates"


def test_fx_source_safe_labels_are_normalized() -> None:
    assert classify_fx_source("manual") == (None, "manual")
    assert classify_fx_source("ECB") == (None, "ecb")
    assert classify_fx_source("ecb.reference") == (None, "ecb.reference")


def test_fx_source_secret_and_free_form_are_not_carried() -> None:
    assert classify_fx_source("sk-or-abc123") == (None, None)
    assert classify_fx_source("Bearer abc123") == (None, None)
    assert classify_fx_source("see notes 2026, page 3") == (None, None)
    assert classify_fx_source("ftp://ecb.example/x") == (None, None)
    assert classify_fx_source(None) == (None, None)
    assert classify_fx_source("   ") == (None, None)


def test_fx_export_free_form_source_blocks_naming_row_only() -> None:
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _classify_fx_source_export("free form secret text here", row_id="777")
    assert excinfo.value.code == "baseline_fx_source_unsafe"
    assert "777" in excinfo.value.detail
    assert "free form secret text" not in excinfo.value.detail

    url, label = _classify_fx_source_export("manual", row_id="777")
    assert (url, label) == (None, "manual")
    url, label = _classify_fx_source_export("https://data.example/eurofx", row_id="777")
    assert url == "https://data.example/eurofx" and label is None
    url, label = _classify_fx_source_export(None, row_id="777")
    assert (url, label) == (None, None)


# --- E2: pricing metadata projection -----------------------------------------

def test_metadata_full_allowlist_projects() -> None:
    projected = project_pricing_metadata(
        {
            "audio_output_price_per_1m": "15.00",
            "codex_accounting": {
                "long_context_threshold_tokens": 272000,
                "long_context_input_multiplier": "2.00",
                "long_context_output_multiplier": "3.00",
                "cache_write_input_price_per_1m": "7.50",
            },
            "external_tool_pricing": {
                "openai_web_search_call_price_native": "0.01",
                "source": "openai_published_per_call",
            },
        }
    )
    assert projected["unrepresented"] is False
    assert projected["audio_output_price_per_1m"] == "15.00"
    assert projected["long_context_threshold_tokens"] == 272000
    assert projected["long_context_input_multiplier"] == "2.00"
    assert projected["cache_write_input_price_per_1m"] == "7.50"
    assert projected["external_tool_price_per_call"] == "0.01"
    assert projected["external_tool_source"] == "openai_published_per_call"


def test_metadata_audio_accepts_decimal_text_rejects_float() -> None:
    projected = project_pricing_metadata({"audio_output_price_per_1m": "15"})
    assert projected["unrepresented"] is False
    assert projected["audio_output_price_per_1m"] == "15"
    projected = project_pricing_metadata({"audio_output_price_per_1m": 15})
    assert projected["unrepresented"] is False
    projected = project_pricing_metadata({"audio_output_price_per_1m": 0.5})
    assert projected["unrepresented"] is True
    projected = project_pricing_metadata({"audio_output_price_per_1m": True})
    assert projected["unrepresented"] is True


def test_metadata_codex_requires_full_set_and_exactly_one_cache_field() -> None:
    """The runtime _codex_accounting_metadata contract: the full
    long-context set plus EXACTLY ONE cache-write field, nothing else."""
    full = {
        "long_context_threshold_tokens": 272000,
        "long_context_input_multiplier": "2.00",
        "long_context_output_multiplier": "3.00",
    }
    # long-context only, no cache-write field: NOT a valid runtime row
    assert project_pricing_metadata({"codex_accounting": full})["unrepresented"] is True
    # exactly one cache-write field: the price variant
    price = dict(full, cache_write_input_price_per_1m="7.50")
    projected = project_pricing_metadata({"codex_accounting": price})
    assert projected["unrepresented"] is False
    assert projected["cache_write_input_price_per_1m"] == "7.50"
    # exactly one cache-write field: the multiplier variant
    multiplier = dict(full, cache_write_input_multiplier="1.5")
    projected = project_pricing_metadata({"codex_accounting": multiplier})
    assert projected["unrepresented"] is False
    assert projected["cache_write_input_multiplier"] == "1.5"
    # both cache-write fields at once: invalid
    both = dict(full, cache_write_input_price_per_1m="7.50", cache_write_input_multiplier="1.5")
    assert project_pricing_metadata({"codex_accounting": both})["unrepresented"] is True
    # partial long-context set
    assert (
        project_pricing_metadata(
            {"codex_accounting": {"long_context_threshold_tokens": 272000}}
        )["unrepresented"]
        is True
    )
    # unknown key inside codex_accounting
    assert (
        project_pricing_metadata({"codex_accounting": {**full, "mystery": "1"}})[
            "unrepresented"
        ]
        is True
    )
    # threshold must be a positive int (bool is not an int here)
    bad = dict(full, long_context_threshold_tokens=True)
    assert project_pricing_metadata({"codex_accounting": bad})["unrepresented"] is True
    bad = dict(full, long_context_input_multiplier=2.0)
    assert project_pricing_metadata({"codex_accounting": bad})["unrepresented"] is True


def test_metadata_external_tool_requires_exact_pair() -> None:
    ok = {
        "openai_web_search_call_price_native": "0.01",
        "source": "openai_published_per_call",
    }
    assert project_pricing_metadata({"external_tool_pricing": ok})["unrepresented"] is False
    # wrong source literal
    bad = dict(ok, source="somewhere_else")
    assert project_pricing_metadata({"external_tool_pricing": bad})["unrepresented"] is True
    # price without source
    assert (
        project_pricing_metadata(
            {"external_tool_pricing": {"openai_web_search_call_price_native": "0.01"}}
        )["unrepresented"]
        is True
    )


def test_metadata_unknown_key_and_none() -> None:
    assert project_pricing_metadata({"some_free_form": "x"})["unrepresented"] is True
    assert project_pricing_metadata(None)["unrepresented"] is False
    assert project_pricing_metadata({})["unrepresented"] is False


# --- E2: parse_decimal_text bounds (no overflow, exact rejection) -------------

def test_parse_decimal_text_bounds() -> None:
    assert parse_decimal_text("123456789.123456789", field="p") == "123456789.123456789"
    assert parse_decimal_text("-0.000001", field="p") == "-0.000001"
    # trailing-zero spellings are preserved (no re-normalization)
    assert parse_decimal_text("0.250000000", field="p") == "0.250000000"
    assert parse_decimal_text("1E+2", field="p") == "1E+2"
    # numerically equivalent trailing-zero spellings are judged by VALUE:
    # accepted when the value fits the bound, preserved verbatim
    assert parse_decimal_text("1.0000000000", field="p") == "1.0000000000"
    assert parse_decimal_text("0.0000000010", field="p") == "0.0000000010"
    assert parse_decimal_text("0.0000000000", field="p") == "0.0000000000"
    # but the VALUE still must fit: 10 integer digits stays out of range
    with pytest.raises(ValueError):
        parse_decimal_text("1234567890.000000000", field="p")
    with pytest.raises(ValueError):
        parse_decimal_text("12345678901", field="p")  # 11 integer digits
    with pytest.raises(ValueError):
        parse_decimal_text("0.12345678901", field="p")  # 11 fraction digits
    with pytest.raises(ValueError):
        parse_decimal_text("-1", field="p", non_negative=True)


def test_parse_decimal_text_extreme_exponent_is_bounded_not_overflowing() -> None:
    # 1E+1000000: the OLD code overflowed Decimal in abs(); the bound is
    # applied to the exponent BEFORE any arithmetic.
    with pytest.raises(ValueError):
        parse_decimal_text("1E+1000000", field="p")
    with pytest.raises(ValueError):
        parse_decimal_text("1E-1000000", field="p")


def test_parse_decimal_text_rejects_non_text() -> None:
    for bad in (1.5, 1, True, None, "NaN", "Infinity", "1.5.2", "", "  "):
        with pytest.raises(ValueError):
            parse_decimal_text(bad, field="p")


# --- baseline document monetary validation ------------------------------------

def _pricing_row(**overrides) -> BaselinePricingRow:
    base = dict(
        id="33333333-0000-4000-8000-000000000001",
        provider="openrouter",
        upstream_model="synthetic/stable-v1",
        endpoint="/v1/chat/completions",
        currency="EUR",
        input_price_per_1m="0.5",
        cached_input_price_per_1m=None,
        output_price_per_1m="2",
        reasoning_price_per_1m=None,
        request_price=None,
        valid_from=datetime(2026, 9, 1, tzinfo=UTC),
        valid_until=None,
        enabled=True,
        source_url="https://openrouter.ai/models",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return BaselinePricingRow(**base)


def test_pricing_row_hostile_monetary_values_rejected() -> None:
    for field in ("input_price_per_1m", "output_price_per_1m", "request_price"):
        for bad in ("1E+1000000", "not-a-number", "12345678901", "NaN", "1.5.2"):
            with pytest.raises(ValidationError):
                _pricing_row(**{field: bad})
    # negative prices are not monetary values in this contract
    with pytest.raises(ValidationError):
        _pricing_row(input_price_per_1m="-1")


def test_pricing_row_metadata_fields_are_validated() -> None:
    row = _pricing_row(
        audio_output_price_per_1m="15",
        long_context_threshold_tokens=272000,
        long_context_input_multiplier="2.00",
        long_context_output_multiplier="3.00",
        cache_write_input_price_per_1m="7.50",
        external_tool_price_per_call="0.01",
        external_tool_source="openai_published_per_call",
    )
    assert row.audio_output_price_per_1m == "15"
    with pytest.raises(ValidationError):
        _pricing_row(audio_output_price_per_1m="1E+1000000")
    with pytest.raises(ValidationError):
        _pricing_row(long_context_input_multiplier="0")
    with pytest.raises(ValidationError):
        _pricing_row(external_tool_source="somewhere_else")
    # codex long-context fields are all-or-none
    with pytest.raises(ValidationError):
        _pricing_row(long_context_threshold_tokens=272000)
    full = dict(
        long_context_threshold_tokens=272000,
        long_context_input_multiplier="2.00",
        long_context_output_multiplier="3.00",
    )
    # long-context set without a cache-write field is not a valid runtime row
    with pytest.raises(ValidationError):
        _pricing_row(**full)
    with pytest.raises(ValidationError):
        _pricing_row(**full, cache_write_input_price_per_1m="7.50",
                     cache_write_input_multiplier="1.5")
    # a cache-write field without the long-context set is not a valid row
    with pytest.raises(ValidationError):
        _pricing_row(cache_write_input_price_per_1m="7.50")
    # exactly one cache-write field plus the full set: the runtime row
    _pricing_row(**full, cache_write_input_price_per_1m="7.50")  # ok
    _pricing_row(**full, cache_write_input_multiplier="1.5")  # ok


def test_pricing_row_flat_price_fields_are_validated() -> None:
    with pytest.raises(ValidationError):
        _pricing_row(input_price_per_1m="1E+2000000")
    with pytest.raises(ValidationError):
        _pricing_row(cached_input_price_per_1m="nope")


def test_fx_row_hostile_rate_rejected() -> None:
    base = dict(
        id="44444444-0000-4000-8000-000000000001",
        base_currency="EUR",
        quote_currency="USD",
        valid_from=datetime(2026, 9, 21, tzinfo=UTC),
        valid_until=None,
        created_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    with pytest.raises(ValidationError):
        BaselineFxRow(rate="1.08E+999999", **base)
    with pytest.raises(ValidationError):
        BaselineFxRow(rate="-1", **base)
    row = BaselineFxRow(rate="1.08", source_label="manual", **base)
    assert row.source_label == "manual"
    with pytest.raises(ValidationError):
        BaselineFxRow(rate="1.08", source="https://ecb.example/x",
                      source_label="manual", **base)


def test_route_row_requires_valid_nested_capabilities_and_fingerprint() -> None:
    base = dict(
        id="22222222-0000-4000-8000-000000000001",
        requested_model="synthetic/stable-v1",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider="openrouter",
        upstream_model="synthetic/stable-v1",
        priority=100,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    # flat legacy shape is no longer a representable baseline shape
    with pytest.raises(ValidationError):
        BaselineRouteRow(
            capabilities={"text": True},
            capabilities_unrepresented=False,
            capabilities_fingerprint="0" * 64,
            **base,
        )
    nested = {"chat_completions": {"chat_text": True, "chat_streaming": True}}
    row = BaselineRouteRow(
        capabilities=nested,
        capabilities_unrepresented=False,
        capabilities_fingerprint=capabilities_fingerprint(nested),
        **base,
    )
    assert row.capabilities == nested
    with pytest.raises(ValidationError):
        BaselineRouteRow(
            capabilities=nested,
            capabilities_unrepresented=False,
            capabilities_fingerprint="0" * 63 + "z",
            **base,
        )


def _document(routes, pricing, fx) -> BaselineDocument:
    doc = BaselineDocument(
        schema_version="1",
        exported_at=datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC),
        target=BaselineTarget(
            server_host="127.0.0.1",
            server_port=5433,
            database="slaif-unit-baseline",
            postgres_version="16.4",
        ),
        sql_checked=True,
        counts=BaselineCounts(
            providers=1,
            routes=len(routes),
            pricing_rules=len(pricing),
            fx_rates=len(fx),
        ),
        content_sha256="0" * 64,
        providers=(
            BaselineProviderRow(
                id="11111111-0000-4000-8000-000000000001",
                provider="openrouter",
                display_name="OpenRouter (unit)",
                kind="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                api_key_env_var="OPENROUTER_API_KEY",
                enabled=True,
                timeout_seconds=300,
                max_retries=2,
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
                updated_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        ),
        routes=routes,
        pricing=pricing,
        fx=fx,
    )
    digest = hashlib.sha256(
        canonical_baseline_content(doc.model_copy(update={"content_sha256": "0" * 64}))
    ).hexdigest()
    return doc.model_copy(update={"content_sha256": digest})


def test_document_round_trip_preserves_projection_and_flags() -> None:
    nested = {"chat_completions": {"chat_text": True, "chat_streaming": True}}
    routes = (
        BaselineRouteRow(
            id="22222222-0000-4000-8000-000000000001",
            requested_model="synthetic/stable-v1",
            match_type="exact",
            endpoint="/v1/chat/completions",
            provider="openrouter",
            upstream_model="synthetic/stable-v1",
            priority=100,
            enabled=True,
            visible_in_models=True,
            supports_streaming=True,
            capabilities=nested,
            capabilities_unrepresented=False,
            capabilities_fingerprint=capabilities_fingerprint(nested),
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
            updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        ),
    )
    pricing = (_pricing_row(),)
    fx = (
        BaselineFxRow(
            id="44444444-0000-4000-8000-000000000001",
            base_currency="EUR",
            quote_currency="USD",
            rate="1.08",
            valid_from=datetime(2026, 9, 21, tzinfo=UTC),
            valid_until=None,
            source_label="manual",
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        ),
    )
    doc = _document(routes, pricing, fx)
    loaded = load_baseline(json.dumps(doc.model_dump(mode="json"), sort_keys=True).encode("utf-8"))
    assert loaded.content_sha256 == doc.content_sha256
    assert loaded.routes[0].capabilities == nested
    assert loaded.routes[0].capabilities_unrepresented is False
    assert loaded.routes[0].capabilities_fingerprint == capabilities_fingerprint(nested)
    assert loaded.fx[0].source_label == "manual"
    # metadata fields survive the round trip
    doc2 = _document(
        routes,
        (_pricing_row(audio_output_price_per_1m="15",
                      long_context_threshold_tokens=272000,
                      long_context_input_multiplier="2.00",
                      long_context_output_multiplier="3.00",
                      cache_write_input_price_per_1m="7.50"),),
        fx,
    )
    loaded2 = load_baseline(
        json.dumps(doc2.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    )
    assert loaded2.pricing[0].audio_output_price_per_1m == "15"
    # a metadata-only difference changes the content digest
    assert doc2.content_sha256 != doc.content_sha256
