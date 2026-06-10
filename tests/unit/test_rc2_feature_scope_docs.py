from pathlib import Path


def test_rc2_feature_scope_doc_exists_with_required_labels_and_rows() -> None:
    content = Path("docs/rc2-feature-scope.md").read_text(encoding="utf-8")

    for label in (
        "RC2_REQUIRED_IMPLEMENTED",
        "RC2_REQUIRED_MISSING",
        "RC2_EXPLICITLY_DEFERRED",
        "RC2_UNSUPPORTED_BY_POLICY",
        "NEEDS_MAINTAINER_DECISION",
    ):
        assert label in content

    for row in (
        "GET /v1/models",
        "POST /v1/chat/completions",
        "Chat text streaming",
        "Chat streaming live-burn",
        "Chat image input",
        "Chat file input",
        "Chat audio input",
        "Chat non-streaming audio output",
        "Chat streaming audio output",
        "Chat local function tools",
        "Chat local custom tools",
        "POST /v1/responses",
        "Responses typed text streaming",
        "Responses streaming live-burn",
        "Responses stored response lifecycle",
        "GET /v1/responses/{response_id}",
        "DELETE /v1/responses/{response_id}",
        "GET /v1/responses/{response_id}/input_items",
        "POST /v1/responses/input_tokens",
        "POST /v1/responses/compact",
        "Responses previous_response_id",
        "Conversations create/retrieve/update/delete",
        "Conversation items create/list/retrieve/delete",
        "POST /v1/audio/speech",
        "POST /v1/audio/transcriptions",
        "POST /v1/audio/translations",
        "Realtime audio",
        "POST /v1/embeddings",
        "Hosted/provider-side tools",
        "MCP/connectors",
        "File search",
        "Web search",
        "Code interpreter",
        "Image generation",
        "Video",
        "Moderations",
        "Batch",
        "Vector stores",
        "Responses `background=true`",
        "POST /v1/responses/{response_id}/cancel",
        "/v1/files",
        "/v1/uploads",
        "Legacy `POST /v1/completions`",
        "Responses audio",
        "Responses multimodal output",
    ):
        assert row in content


def test_rc2_scope_doc_marks_green_harness_as_implemented_scope_only() -> None:
    content = Path("docs/rc2-feature-scope.md").read_text(encoding="utf-8")

    assert "verification-clean for implemented scope" in content
    assert "feature-full RC2" in content


def test_rc2_scope_doc_moves_standalone_audio_to_implemented_and_keeps_remaining_missing() -> None:
    content = Path("docs/rc2-feature-scope.md").read_text(encoding="utf-8")

    assert (
        "| `POST /v1/audio/speech` | Implemented for bounded standalone speech subset |" in content
    )
    assert (
        "| `POST /v1/audio/transcriptions` | Implemented for bounded multipart transcription subset |"
        in content
    )
    assert (
        "| `POST /v1/audio/translations` | Implemented for bounded multipart translation subset |"
        in content
    )
    assert (
        "| Realtime audio | Implemented for bounded WebRTC client-secret admission foundation "
        "with explicit direct-provider-exposure gating for quota-limited keys |"
    ) in content
    assert "| `POST /v1/embeddings` | Implemented for bounded standalone embeddings subset |" in content
    assert "| `RC2_REQUIRED_MISSING` | 0 |" in content
    assert "| `POST /v1/realtime/calls` | Not implemented |" in content
    assert "`feature/realtime-audio-foundation` — completed for the bounded first slice" in content
    assert "client_secret_direct_provider_exposure_accepted=true" in content


def test_rc_beta_docs_no_longer_read_as_feature_full_rc2() -> None:
    for path in (
        Path("README.md"),
        Path("docs/openai-compatibility.md"),
        Path("docs/compatibility-matrix.md"),
        Path("docs/beta-readiness.md"),
        Path("docs/rc-beta.md"),
    ):
        content = path.read_text(encoding="utf-8")
        assert "rc2-feature-scope.md" in content

    beta_readiness = Path("docs/beta-readiness.md").read_text(encoding="utf-8")
    assert "Feature-full RC2: no" in beta_readiness
