"""Context admission is a strict, portable operator route policy, not a key grant."""

from copy import deepcopy

import pytest

from slaif_gateway.schemas.catalog_refresh import validate_route_capability_projection
from slaif_gateway.schemas.provider_route_configuration import (
    merge_capability_patch,
    parse_capability_patch,
    validate_capabilities_document,
)
from slaif_gateway.services.catalog_refresh.baseline import project_route_capabilities
from slaif_gateway.services.responses_route_capabilities import (
    parse_codex_context_admission,
    ResponsesRouteCapabilityError,
)


@pytest.mark.parametrize("mode", ["gateway_estimate", "upstream"])
def test_context_policy_survives_configuration_patch_and_catalog_roundtrip(mode) -> None:
    original = {
        "codex_limits": {
            "context_window_tokens": 393216,
            "default_max_output_tokens": 64000,
            "max_output_tokens": 128000,
        },
        "responses": {"text": True, "stateless": True},
        "codex_context_admission": "upstream",
    }
    saved = deepcopy(original)
    patch = parse_capability_patch({"codex_context_admission": mode})
    merged = merge_capability_patch(original, patch)
    assert original == saved
    assert merged["codex_limits"] == original["codex_limits"]
    assert parse_codex_context_admission(merged) == mode
    validate_capabilities_document(merged)
    projected, unrepresented = project_route_capabilities(merged)
    assert not unrepresented
    assert projected == merged
    validate_route_capability_projection(projected)
    assert not patch.is_empty()


@pytest.mark.parametrize("bad", [None, True, 0, "auto", "UPSTREAM", {}, []])
def test_invalid_context_policy_cannot_enter_configuration_or_catalog(bad) -> None:
    cap = {"codex_context_admission": bad}
    with pytest.raises(ResponsesRouteCapabilityError):
        parse_codex_context_admission(cap)
    with pytest.raises(Exception):
        validate_capabilities_document(cap)
    with pytest.raises(Exception):
        parse_capability_patch(cap)
    with pytest.raises(ValueError):
        validate_route_capability_projection(cap)
    assert project_route_capabilities(cap) == ({}, True)


def test_omission_keeps_legacy_admission_and_unrelated_patch_preserves_mode() -> None:
    assert parse_codex_context_admission(None) == "gateway_estimate"
    assert parse_codex_context_admission({}) == "gateway_estimate"
    assert (
        merge_capability_patch(
            {"codex_context_admission": "upstream"},
            parse_capability_patch({"responses": {"text": True}}),
        )["codex_context_admission"]
        == "upstream"
    )
