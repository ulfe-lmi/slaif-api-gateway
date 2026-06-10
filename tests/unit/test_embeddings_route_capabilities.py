from __future__ import annotations

import pytest

from slaif_gateway.services.embeddings_route_capabilities import (
    EMBEDDINGS_CAPABILITIES_KEY,
    ensure_default_embeddings_capabilities,
    enforce_embeddings_route_capabilities,
)


def test_embeddings_route_defaults_enable_endpoint_and_disable_dimensions() -> None:
    capabilities = ensure_default_embeddings_capabilities({}, endpoint="/v1/embeddings")

    assert capabilities[EMBEDDINGS_CAPABILITIES_KEY]["embeddings"] is True
    assert capabilities[EMBEDDINGS_CAPABILITIES_KEY]["embeddings_dimensions"] is False


def test_embeddings_route_capability_absent_or_false_fails_closed() -> None:
    with pytest.raises(Exception) as absent_exc:
        enforce_embeddings_route_capabilities(route_capabilities={}, dimensions_requested=False)
    assert getattr(absent_exc.value, "error_code", None) == "embeddings_capability_not_supported"

    with pytest.raises(Exception) as dimensions_exc:
        enforce_embeddings_route_capabilities(
            route_capabilities={EMBEDDINGS_CAPABILITIES_KEY: {"embeddings": True}},
            dimensions_requested=True,
        )
    assert getattr(dimensions_exc.value, "error_code", None) == "embeddings_dimensions_not_supported"

    with pytest.raises(Exception) as invalid_shape_exc:
        enforce_embeddings_route_capabilities(
            route_capabilities={EMBEDDINGS_CAPABILITIES_KEY: "yes"},
            dimensions_requested=False,
        )
    assert getattr(invalid_shape_exc.value, "error_code", None) == "embeddings_capability_not_supported"


def test_embeddings_route_capability_true_allows_endpoint() -> None:
    enforce_embeddings_route_capabilities(
        route_capabilities={
            EMBEDDINGS_CAPABILITIES_KEY: {
                "embeddings": True,
                "embeddings_dimensions": True,
            }
        },
        dimensions_requested=True,
    )
