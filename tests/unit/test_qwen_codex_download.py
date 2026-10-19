from dataclasses import replace
import json
from pathlib import Path
import tomllib

import pytest

from slaif_gateway.services.codex_profile_registry import (
    CODEX_PROFILE_REGISTRY,
    OPENAI_CODEX_PROFILE,
    QWEN38_CODEX_PROFILE,
    QWEN38_240K_CODEX_PROFILE,
    QWEN38_256K_CODEX_PROFILE,
    QWEN38_TEXT_CODEX_CANDIDATE,
    QWEN38_VISION_CODEX_CANDIDATE,
)
from slaif_gateway.services.codex_qualification import render_codex_profile


def test_qwen_registration_and_two_file_example_match_renderer():
    profile = QWEN38_CODEX_PROFILE
    assert set(CODEX_PROFILE_REGISTRY) == {
        OPENAI_CODEX_PROFILE.profile_id,
        profile.profile_id,
        QWEN38_240K_CODEX_PROFILE.profile_id,
        QWEN38_256K_CODEX_PROFILE.profile_id,
    }
    assert QWEN38_TEXT_CODEX_CANDIDATE.profile_id not in CODEX_PROFILE_REGISTRY
    assert QWEN38_VISION_CODEX_CANDIDATE.profile_id not in CODEX_PROFILE_REGISTRY
    assert profile.mocked_qualification and not profile.live_qualification
    assert profile.cli_version == "0.162.1"
    artifacts = render_codex_profile("https://gateway.example.org/v1", profile.profile_id)
    assert artifacts.profile_config_self_contained
    root = Path(__file__).resolve().parents[2] / "examples/codex/qwen38-27b"
    assert (root / "qwen38.config.toml").read_text() == artifacts.profile_config_toml
    assert json.loads((root / "qwen38-models.json").read_text()) == json.loads(
        artifacts.model_catalog_json
    )
    config = tomllib.loads(artifacts.profile_config_toml)
    assert config["model_providers"]["qwen38"]["env_key"] == "OPENAI_API_KEY"
    assert config["model_catalog_json"] == "qwen38-models.json"
    assert config["sandbox_mode"] == "workspace-write"
    assert config["features"]["apps"] is False
    assert config["features"]["plugins"] is False
    assert config["model_context_window"] == profile.context_window_tokens
    assert config["model_auto_compact_token_limit"] == profile.auto_compaction_token_threshold
    assert "experimental_bearer_token" not in artifacts.profile_config_toml
    assert profile.input_modalities == ("text",)


@pytest.mark.parametrize(
    "mutation", ["oversize", "extra_field", "credential", "control", "other_profile"]
)
def test_coding_catalog_exception_remains_bounded_and_profile_specific(mutation):
    profile = QWEN38_CODEX_PROFILE
    catalog = json.loads(profile.model_catalog_artifact)
    message = catalog["models"][0]["model_messages"]
    updates = {}
    if mutation == "oversize":
        message["instructions_template"] = "x" * 1025
    elif mutation == "extra_field":
        message["extra"] = "unexpected"
    elif mutation == "credential":
        message["instructions_template"] = "Authorization: Bearer private"
    elif mutation == "control":
        message["instructions_template"] = "unsafe\x00value"
    else:
        updates["profile_id"] = "unregistered-coding-profile"
    with pytest.raises(ValueError):
        replace(profile, model_catalog_artifact=json.dumps(catalog), **updates)


@pytest.mark.parametrize(
    "profile,context,compact",
    [(QWEN38_240K_CODEX_PROFILE, 245760, 208125), (QWEN38_256K_CODEX_PROFILE, 262144, 221184)],
)
def test_full_context_profiles_keep_client_and_catalog_limits_consistent(profile, context, compact):
    artifacts = render_codex_profile("https://gateway.example.org/v1", profile.profile_id)
    config = tomllib.loads(artifacts.profile_config_toml)
    entry = json.loads(artifacts.model_catalog_json)["models"][0]
    assert artifacts.profile_config_self_contained
    assert (
        config["model_context_window"]
        == entry["context_window"]
        == entry["max_context_window"]
        == context
    )
    assert config["model_auto_compact_token_limit"] == entry["auto_compact_token_limit"] == compact
    assert config["model"] == entry["slug"] == profile.public_model
    assert profile.live_qualification is False
    assert profile.client_module_version == QWEN38_CODEX_PROFILE.client_module_version
    assert QWEN38_CODEX_PROFILE.context_window_tokens == 131072
