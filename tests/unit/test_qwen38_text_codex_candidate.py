from __future__ import annotations

import hashlib
import json

from scripts import verify_qwen38_text_codex as verifier
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_TEXT_CODEX_CANDIDATE,
    QWEN38_TEXT_PROFILE_FIXTURE_SHA256,
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
    assert profile.default_max_output_tokens == 8_192
    assert profile.max_output_tokens == 24_576
    assert profile.auto_compaction_token_threshold == 125_000
    assert profile.input_modalities == ("text",)
    assert profile.catalog_source == "replacement"
    assert not profile.mocked_qualification
    assert not profile.live_qualification
    assert get_codex_profile(profile.profile_id) is None


def test_captured_fixture_is_structural_deterministic_and_canary_free() -> None:
    fixture = json.loads(verifier.FIXTURE_PATH.read_text(encoding="utf-8"))
    projection = dict(fixture)
    projection.pop("digest")
    assert verifier.sanitize_captured_fixture(projection) == fixture
    assert fixture["event_sequence"]
    assert fixture["request_facts"]["count"] == 2
    assert fixture["catalog_facts"]["field_type"] == "replacement"
    assert hashlib.sha256(verifier.FIXTURE_PATH.read_bytes()).hexdigest() == QWEN38_TEXT_PROFILE_FIXTURE_SHA256
    forbidden = ("prompt", "response body", "authorization", "https://", "workspace", "QWEN38_TOOL_OK")
    assert not any(marker in verifier.FIXTURE_PATH.read_text(encoding="utf-8") for marker in forbidden)


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


def test_present_target_enters_bounded_orchestration_seam() -> None:
    called = False

    def runner() -> dict[str, object]:
        nonlocal called
        called = True
        return {
            "codex_version": "0.148.0",
            "request_count": 2,
            "event_count": 10,
            "accounting_proved": True,
            "privacy_proved": True,
        }

    assert verifier.validate_environment(
        {
            verifier.BASE_URL_ENV: "http://127.0.0.1:8080/v1",
            verifier.API_KEY_ENV: "private-test-key",
        }
    ) == "live_target_present"
    result = verifier.run_hermetic_phase(runner=runner)
    assert called
    assert result["accounting_proved"] is True


def test_present_target_runs_hermetic_then_distinct_live_runner() -> None:
    calls: list[str] = []

    def hermetic() -> dict[str, object]:
        calls.append("hermetic")
        return {
            "codex_version": "0.148.0", "request_count": 2, "event_count": 10,
            "accounting_proved": True, "privacy_proved": True,
        }

    def live(base_url: str, api_key: str) -> dict[str, object]:
        calls.extend((base_url, api_key, "live"))
        return {"real_provider_called": True}

    phase = verifier.run_hermetic_phase(runner=hermetic)
    result = verifier.run_live_phase(
        base_url="http://127.0.0.1:8080/v1", api_key="private-test-key", runner=live
    )
    assert phase["request_count"] == 2
    assert result["real_provider_called"] is True
    assert calls == ["hermetic", "http://127.0.0.1:8080/v1", "private-test-key", "live"]


def test_target_url_rejects_percent_backslash_and_bad_port() -> None:
    for value in (
        "http://127.0.0.1:0/v1",
        "http://127.0.0.1:65536/v1",
        "http://127.0.0.1%2fv1/v1",
        "http://127.0.0.1\\v1",
    ):
        try:
            verifier.validate_target_url(value)
        except verifier.VerificationError:
            pass
        else:
            raise AssertionError("unsafe target accepted")
