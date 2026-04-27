from slaif_gateway.utils.sanitization import sanitize_metadata_mapping


def test_sanitize_metadata_redacts_nested_sensitive_key_variants() -> None:
    metadata = {
        "provider": "openai",
        "model": "gpt-test",
        "request_id": "req_123",
        "providerApiKey": "sk-proj-providersecret123456",
        "nested": {
            "api_key": "api-secret",
            "api-key": "api-secret-2",
            "authorizationHeader": "Bearer sk-slaif-public.secretsecret",
            "accessToken": "access-secret",
            "refresh_token": "refresh-secret",
            "tokenHash": "hash-secret",
            "encryptedPayload": "payload-secret",
            "secretValue": "secret-value",
            "csrfToken": "csrf-secret",
            "sessionCookie": "session-secret",
            "openaiKey": "sk-proj-openai-secret",
            "openrouterKey": "sk-or-openrouter-secret",
            "passwordHash": "password-secret",
            "safe": "kept",
        },
        "items": [{"nonce": "nonce-secret"}, "Bearer sk-or-providersecret123"],
    }

    sanitized = sanitize_metadata_mapping(metadata)
    serialized = str(sanitized)

    for forbidden in (
        "providersecret",
        "api-secret",
        "secretsecret",
        "access-secret",
        "refresh-secret",
        "hash-secret",
        "payload-secret",
        "secret-value",
        "csrf-secret",
        "session-secret",
        "openai-secret",
        "openrouter-secret",
        "password-secret",
        "nonce-secret",
    ):
        assert forbidden not in serialized
    assert sanitized["provider"] == "openai"
    assert sanitized["model"] == "gpt-test"
    assert sanitized["request_id"] == "req_123"
    assert sanitized["nested"]["safe"] == "kept"


def test_sanitize_metadata_drops_prompt_completion_and_body_content_when_requested() -> None:
    metadata = {
        "prompt_tokens": 12,
        "completion_tokens": 4,
        "prompt": "prompt secret",
        "completion": "completion secret",
        "messages": [{"content": "user body"}],
        "choices": [{"message": {"content": "assistant body"}}],
        "request_body": {"api_key": "secret"},
        "response-body": {"content": "secret"},
    }

    sanitized = sanitize_metadata_mapping(metadata, drop_content_keys=True)

    assert sanitized == {"prompt_tokens": 12, "completion_tokens": 4}
