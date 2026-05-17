from pathlib import Path


MIGRATION_PATH = Path("migrations/versions/0007_usage_profiles.py")


def test_usage_profiles_migration_file_exists_and_targets_safe_table() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    assert "op.create_table(" in content
    assert '"usage_profiles"' in content
    assert "usage_ledger_id" in content
    assert "gateway_key_id" in content
    assert "tool_call_counts" in content
    assert "function_tool_names" in content
    assert "profile_metadata" in content

    for forbidden_name in (
        "prompt_content",
        "completion_content",
        "messages",
        "request_body",
        "response_body",
        "raw_request",
        "raw_response",
        "token_hash",
        "encrypted_payload",
        "nonce",
    ):
        assert forbidden_name not in content


def test_usage_profiles_migration_down_revision_points_to_previous_head() -> None:
    content = MIGRATION_PATH.read_text()

    assert 'down_revision = "0006_email_delivery_attempt_state"' in content
