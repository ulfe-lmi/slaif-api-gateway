from __future__ import annotations

import copy
from dataclasses import replace
from types import MappingProxyType

import pytest

from slaif_gateway.services.codex_profile_registry import (
    OPENAI_CODEX_PROFILE,
    PROFILE_ID,
    PROFILE_METADATA_VERSION,
    get_codex_profile,
    sanitize_codex_fixture,
    validate_codex_profile_declaration,
    validate_codex_profile_registry,
)


def test_builtin_profile_is_immutable_and_server_defined() -> None:
    profile = get_codex_profile(PROFILE_ID)
    assert profile is OPENAI_CODEX_PROFILE
    assert profile is not None
    assert profile.metadata_version == PROFILE_METADATA_VERSION
    assert profile.public_model == "gpt-5.6-sol"
    assert profile.required_endpoints == ("/v1/responses", "/v1/responses/compact")
    assert profile.live_qualification is False
    with pytest.raises(TypeError):
        profile.credential_free_provider_fields["name"] = "unsafe"  # type: ignore[index]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            {
                "version": PROFILE_METADATA_VERSION,
                "profile_id": PROFILE_ID,
                "fixture_sha256": OPENAI_CODEX_PROFILE.fixture_sha256,
            },
            ("ready", None),
        ),
        ({"version": 2, "profile_id": "unknown-profile", "fixture_sha256": "0" * 64}, ("not_ready", "codex_profile_unknown")),
        (
            {
                "version": PROFILE_METADATA_VERSION,
                "profile_id": PROFILE_ID,
                "fixture_sha256": "0" * 64,
            },
            ("invalid", "codex_profile_fixture_mismatch"),
        ),
        (
            {
                "version": PROFILE_METADATA_VERSION,
                "profile_id": PROFILE_ID,
                "fixture_sha256": OPENAI_CODEX_PROFILE.fixture_sha256,
                "extra": False,
            },
            ("invalid", "codex_profile_declaration_invalid"),
        ),
    ],
)
def test_profile_declaration_fails_closed(value: object, expected: tuple[str, str | None]) -> None:
    assert validate_codex_profile_declaration(value) == (expected[0], expected[1])


def test_registry_validation_rejects_duplicate_key() -> None:
    duplicate = MappingProxyType({PROFILE_ID: OPENAI_CODEX_PROFILE, "other": OPENAI_CODEX_PROFILE})
    with pytest.raises(ValueError, match="duplicate"):
        validate_codex_profile_registry(duplicate)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"event_type": "response.output_text", "text": "secret prompt"},
        {"event_type": "tool", "arguments": {"x": "secret"}},
        {"event_type": "request", "url": "https://private.example"},
        {"event_type": "tool", "metadata": {"provider_key": "secret"}},
    ],
)
def test_fixture_sanitizer_rejects_content_and_sensitive_fields(unsafe: object) -> None:
    with pytest.raises(ValueError):
        sanitize_codex_fixture(unsafe)


def test_fixture_sanitizer_keeps_only_structural_fields_and_deterministic_digest() -> None:
    fixture = {
        "event_type": "response.output_item.done",
        "id": "opaque",
        "count": 1,
        "field_type": "linked",
    }
    first = sanitize_codex_fixture(copy.deepcopy(fixture))
    second = sanitize_codex_fixture(copy.deepcopy(fixture))
    assert first == second
    assert first["id"] == "ID_1"
    assert len(str(first["digest"])) == 64
    assert set(first) == {"event_type", "id", "count", "field_type", "digest"}


def test_fixture_sanitizer_preserves_id_relationship_order_without_raw_ids() -> None:
    fixture = {"event_type": "sequence", "field_type": [{"id": "a"}, {"id": "b"}, {"id": "a"}]}
    result = sanitize_codex_fixture(fixture)
    assert result["field_type"] == [{"id": "ID_1"}, {"id": "ID_2"}, {"id": "ID_1"}]
    assert "'id': 'a'" not in str(result) and "'id': 'b'" not in str(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"model_catalog_artifact": '{"models": ["x"]}', "model_catalog_target": "../unsafe.json"},
        {"model_catalog_artifact": '{ "models": [] }', "model_catalog_target": "models.json"},
        {"model_catalog_artifact": '{"models": ["https://upstream.example"]}', "model_catalog_target": "models.json"},
    ],
)
def test_profile_catalog_artifacts_reject_unsafe_or_noncanonical_values(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(OPENAI_CODEX_PROFILE, **changes)


def test_registry_owned_selection_rejects_caller_mutation() -> None:
    mutated = replace(OPENAI_CODEX_PROFILE, profile_name="mutated")
    assert mutated is not OPENAI_CODEX_PROFILE
    with pytest.raises(ValueError, match="registry-owned"):
        from slaif_gateway.services.codex_qualification import render_codex_profile

        render_codex_profile("https://gateway.example.org/v1", mutated)
