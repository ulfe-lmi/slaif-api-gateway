from __future__ import annotations

from scripts import verify_qwen38_text_codex as verifier
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_TEXT_CODEX_CANDIDATE,
    QWEN38_TEXT_PROFILE_ID,
    get_codex_profile,
)


def test_candidate_is_exact_and_unregistered() -> None:
    profile = QWEN38_TEXT_CODEX_CANDIDATE
    assert profile.profile_id == QWEN38_TEXT_PROFILE_ID
    assert profile.cli_version == "0.148.0"
    assert profile.public_model == "qwen3.8-27b-text"
    assert profile.upstream_model == "qwen3.8-27b"
    assert profile.context_window_tokens == 150_000
    assert profile.default_max_output_tokens == 32_768
    assert profile.max_output_tokens == 128_000
    assert profile.auto_compaction_token_threshold == 125_000
    assert profile.input_modalities == ("text",)
    assert profile.catalog_source == "replacement"
    assert not profile.mocked_qualification
    assert not profile.live_qualification
    assert get_codex_profile(profile.profile_id) is None


def test_absent_target_is_safe_and_non_live() -> None:
    assert verifier.validate_environment({}) == "live_target_absent"


def test_target_url_boundary_does_not_accept_public_or_query_targets() -> None:
    for value in (
        "https://8.8.8.8/v1",
        "http://127.0.0.1/v1?x=1",
        "http://user:secret@127.0.0.1/v1",
    ):
        try:
            verifier.validate_target_url(value)
        except verifier.VerificationError:
            pass
        else:
            raise AssertionError("unsafe target accepted")
