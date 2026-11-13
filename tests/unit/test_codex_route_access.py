"""GUI access config grants no key, pricing, or qualification authority."""

import copy
from types import SimpleNamespace

import pytest

from slaif_gateway.api.admin import _parse_model_route_form, _route_form_from_detail
from slaif_gateway.modules.servers.registry import ensure_client_server_pair, resolve_server_module
from slaif_gateway.schemas.provider_route_configuration import validate_capabilities_document
from slaif_gateway.services.codex_route_access import (
    CODEX_GATES, codex_access_enabled, configure_codex_access, uses_existing_route_pricing,
)


def configure(caps=None, **changes):
    args = dict(enabled=True, endpoint="/v1/responses", match_type="exact",
                supports_streaming=True, context="131072", default_output="4096",
                max_output="8192", absolute_input=1050000, absolute_output=128000)
    args.update(changes)
    return configure_codex_access(caps or {}, **args)


@pytest.mark.parametrize("original", [{}, {"responses": {}}, {
    "responses": {"text": True, "function_tools": False, "image_input": True},
    "media_input_estimation": {"version": 1},
}])
def test_enable_disable_restores_owned_state_preserving_other_edits(original):
    before = copy.deepcopy(original)
    enabled = configure(original)
    assert codex_access_enabled(enabled)
    assert uses_existing_route_pricing(enabled)
    assert "codex_profile" not in enabled
    assert original == before
    enabled["responses"]["json_mode"] = True
    restored = configure(enabled, enabled=False)
    expected = copy.deepcopy(original)
    expected.setdefault("responses", {})["json_mode"] = True
    assert restored == expected
    assert configure(configure(original), enabled=False) == original


def test_enabling_twice_keeps_original_rollback_and_selects_registered_generic_adapter():
    caps = configure({"responses": {"text": True}})
    assert configure(caps)["codex_access"] == caps["codex_access"]
    validate_capabilities_document(caps)
    for slug in ("openrouter", "private-provider"):
        module = resolve_server_module(slug, "openai_compatible", caps)
        assert module.module_id == "configured-upstream-llm"
        ensure_client_server_pair("codex-0.162-responses-v1", module.module_id)


@pytest.mark.parametrize("changes", [
    {"endpoint": "/v1/chat/completions"}, {"match_type": "glob"},
    {"supports_streaming": False}, {"context": ""}, {"context": "true"},
    {"context": "0"}, {"max_output": "131072"}, {"default_output": "8193"},
    {"max_output": "128001", "context": "262144"}, {"context": "1050001"},
    {"context": "999999999999999999999999999999"},
])
def test_invalid_configuration_is_refused_without_mutating_original(changes):
    original = {"responses": {"text": True}}
    with pytest.raises(ValueError):
        configure(original, **changes)
    assert original == {"responses": {"text": True}}


def test_existing_configured_route_keeps_transport_and_strict_pricing():
    caps = configure()
    caps.pop("codex_access")
    existing = copy.deepcopy(caps)
    assert configure(caps) == existing
    assert not uses_existing_route_pricing(caps)
    disabled = configure(caps, enabled=False)
    assert not codex_access_enabled(disabled)
    assert disabled["upstream_llm"] == caps["upstream_llm"]
    assert all(disabled["responses"][gate] is False for gate in CODEX_GATES)


def test_catalog_notes_prefill_limits_and_existing_values_win():
    route = SimpleNamespace(requested_model="model", match_type="exact", endpoint="/v1/responses",
                            provider="provider", upstream_model="upstream", priority=100,
                            enabled=True, visible_in_models=True, supports_streaming=True,
                            notes="catalog | context=200000 | max_output_tokens=16384", capabilities={})
    form = _route_form_from_detail(route)
    assert form["codex_context"] == "200000"
    assert form["codex_max_output"] == "16384"
    route.capabilities = configure()
    form = _route_form_from_detail(route)
    assert form["codex_context"] == "131072"
    assert form["codex_enabled"] == "true"


def test_old_edit_posts_preserve_advanced_metadata_without_new_checkbox_fields():
    route = SimpleNamespace(requested_model="model", match_type="exact", endpoint="/v1/responses",
                            provider="provider", upstream_model="upstream", priority=100,
                            enabled=True, visible_in_models=True, supports_streaming=True,
                            notes="", capabilities=configure())
    form = _route_form_from_detail(route)
    form.pop("codex_access_present")
    form.pop("codex_enabled")
    form["reason"] = "legacy route edit"
    parsed = _parse_model_route_form(form, provider_exists=True, require_reason=True)
    assert parsed["capabilities"] == route.capabilities


@pytest.mark.parametrize("marker", [True, {}, {"version": True, "pricing": "existing", "previous": {}},
    {"version": 1, "pricing": "free", "previous": {}},
    {"version": 1, "pricing": "existing", "previous": {"responses": {"unknown": True}}}])
def test_malformed_access_contract_never_selects_standard_pricing(marker):
    with pytest.raises(ValueError):
        uses_existing_route_pricing({"codex_access": marker})
