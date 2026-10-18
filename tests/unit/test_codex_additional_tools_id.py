"""Bounded optional additional_tools item ID for the pinned 0.149 dialect.

These tests pin the version-5 identity facts and the spec-driven ID gate:
omitted/null/valid IDs pass the ID gate while every existing gate (role,
taxonomy, grants, strict unknown-field rejection in other modules) is
preserved.  A valid ID only reaches canonicalization once the 0.149
namespace taxonomy approves the declaration, which this historical profile
deliberately keeps fail-closed; the end-to-end preservation proof for the
profile whose client emits IDs belongs to the 0.162 module tests.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0147 import CODEX_0147_POLICY_SPEC
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_ADDITIONAL_TOOLS_ID_FIXTURE_RELATIVE_PATH,
    CODEX_0149_ADDITIONAL_TOOLS_ID_FIXTURE_SHA256,
    CODEX_0149_CLIENT_MODULE_ID,
    CODEX_0149_CLIENT_MODULE_VERSION,
    CODEX_0149_FIXTURE_SHA256,
    CODEX_0149_POLICY_SPEC,
)
from slaif_gateway.modules.clients.registry import (
    CODEX_0149_CLIENT_MODULE,
    ModuleSelectionError,
    client_module_metadata,
    resolve_responses_client_module,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy

ID_FIXTURE = Path(CODEX_0149_ADDITIONAL_TOOLS_ID_FIXTURE_RELATIVE_PATH)
AT_UUID = "at_123e4567-e89b-12d3-a456-426614174000"


def _additional_tools_item(id_value: object = ...) -> dict[str, object]:
    item: dict[str, object] = {
        "type": "additional_tools",
        "role": "developer",
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            }
        ],
    }
    if id_value is not ...:
        item["id"] = id_value
    return item


def _body(item: dict[str, object]) -> dict[str, object]:
    return {
        "model": "classroom-codex",
        "input": [
            item,
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        ],
        "store": False,
    }


def _apply_0149(body: dict[str, object]) -> object:
    policy = ResponsesRequestPolicy(Settings(), client_spec=CODEX_0149_POLICY_SPEC)
    return policy.apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
    )


def _apply_0147(body: dict[str, object]) -> object:
    policy = ResponsesRequestPolicy(Settings(), client_spec=CODEX_0147_POLICY_SPEC)
    return policy.apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
    )


def test_module_identity_bumps_version_and_keeps_session_fixture() -> None:
    assert CODEX_0149_CLIENT_MODULE_ID == "codex-0.149-responses-v1"
    assert CODEX_0149_CLIENT_MODULE_VERSION == "5"
    assert CODEX_0149_CLIENT_MODULE.module_version == "5"
    assert CODEX_0149_CLIENT_MODULE.fixture_sha256 == CODEX_0149_FIXTURE_SHA256
    assert (
        CODEX_0149_FIXTURE_SHA256
        == "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec"
    )
    assert "id" in CODEX_0149_POLICY_SPEC.additional_tools_fields
    assert CODEX_0149_POLICY_SPEC.additional_tools_fields == frozenset(
        {"type", "id", "role", "tools"}
    )
    # The 0.147 spec keeps its historical strict vocabulary.
    assert "id" not in CODEX_0147_POLICY_SPEC.additional_tools_fields
    assert client_module_metadata(CODEX_0149_CLIENT_MODULE) == {
        "id": "codex-0.149-responses-v1",
        "version": "5",
        "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
    }


def test_registry_resolves_v5_and_rejects_stale_v4_metadata() -> None:
    metadata = client_module_metadata(CODEX_0149_CLIENT_MODULE)
    assert resolve_responses_client_module({"client_module": dict(metadata)}) is (
        CODEX_0149_CLIENT_MODULE
    )
    stale = dict(metadata, version="4")
    with pytest.raises(ModuleSelectionError) as exc_info:
        resolve_responses_client_module({"client_module": stale})
    assert exc_info.value.error_code == "client_module_fixture_mismatch"
    for broken in (
        dict(metadata, fixture_sha256="0" * 64),
        dict(metadata, extra="1"),
        dict(metadata, version="4", fixture_sha256="0" * 64),
    ):
        with pytest.raises(ModuleSelectionError):
            resolve_responses_client_module({"client_module": broken})


def test_pinned_supplementary_id_fixture_is_exact_and_immutable() -> None:
    assert hashlib.sha256(ID_FIXTURE.read_bytes()).hexdigest() == (
        CODEX_0149_ADDITIONAL_TOOLS_ID_FIXTURE_SHA256
    )
    fixture = json.loads(ID_FIXTURE.read_bytes())
    assert fixture["schema_version"] == "codex_additional_tools_id_v1"
    assert fixture["contract"]["field_states"] == {
        "absent": "accepted_historical_default",
        "null": "accepted_canonicalizes_to_absent",
        "present_valid": "accepted_preserved_in_canonical_item",
        "present_invalid": "rejected_bounded_opaque_identifier_convention",
    }
    assert {vector["id"] for vector in fixture["synthetic_vectors"]} == {
        "absent",
        "null",
        AT_UUID,
        f"{AT_UUID} extra",
    }
    for value in json.dumps(fixture).split('"'):
        assert "sk-slaif-" not in value and "credential" not in value.lower()


@pytest.mark.parametrize(
    "id_value",
    [..., None, AT_UUID, "msg_abc-123.x_y:z"],
    ids=["omitted", "null", "at-uuid", "plain-bounded"],
)
def test_omitted_null_and_valid_ids_pass_the_id_gate(id_value: object) -> None:
    body = _body(_additional_tools_item(id_value))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_0149(body)
    # The 0.149 historical namespace taxonomy remains fail-closed, so the
    # accepted ID advances the request exactly to the next existing gate.
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].tools"


@pytest.mark.parametrize(
    ("id_value", "detail"),
    [
        (True, "bool"),
        (7, "number"),
        ([AT_UUID], "array"),
        ({"id": AT_UUID}, "object"),
        ("", "empty"),
        ("   ", "whitespace"),
        ("a\tb", "control"),
        ("héllo", "unicode"),
        ("x" * 129, "oversized"),
        ("at_https://private.invalid", "url-like"),
        ("sk_live_private", "secret-like-prefix"),
        ("my_token_abc", "secret-like-fragment"),
        ("-leading-hyphen", "leading-punctuation"),
        ("at_123E4567-E89B-42D3-A456-426614174000 ", "trailing-space"),
    ],
)
def test_invalid_ids_are_rejected_at_the_precise_id_param(
    id_value: object, detail: str
) -> None:
    body = _body(_additional_tools_item(id_value))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_0149(body)
    assert exc_info.value.error_code == "responses_codex_envelope_invalid"
    assert exc_info.value.param == "input[0].id"
    if isinstance(id_value, str) and id_value:
        assert id_value not in exc_info.value.safe_message


def test_valid_id_at_the_128_byte_boundary_is_accepted() -> None:
    boundary = "x" * 128
    body = _body(_additional_tools_item(boundary))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_0149(body)
    assert exc_info.value.param == "input[0].tools"


def test_0147_module_still_rejects_a_present_id_strictly() -> None:
    body = _body(_additional_tools_item(AT_UUID))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_0147(body)
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].id"
    assert AT_UUID not in exc_info.value.safe_message


def test_role_and_grant_gates_are_preserved_with_a_valid_id() -> None:
    item = _additional_tools_item(AT_UUID)
    item["role"] = "user"
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_0149(_body(item))
    assert exc_info.value.param == "input[0].role"

    item = copy.deepcopy(_additional_tools_item(AT_UUID))
    policy = ResponsesRequestPolicy(Settings(), client_spec=CODEX_0149_POLICY_SPEC)
    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(_body(item), allow_codex_request_envelope=True)
    assert exc_info.value.error_code == "responses_codex_client_tools_not_allowed"
    assert exc_info.value.param == "input[0].type"


def test_no_duplicate_additional_tools_item_with_id() -> None:
    body = _body(_additional_tools_item(AT_UUID))
    body["input"].insert(1, copy.deepcopy(body["input"][0]))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_0149(body)
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"

def test_0162_v2_upgrade_identity_facts_are_frozen_and_edges_closed() -> None:
    """Service-level identity facts for the v1 -> v2 hop (no DB).

    The historical 0162-v1 selector is a frozen literal (not derived from
    the live registry), so future registry changes cannot silently
    retarget the historical selector; the six legal edges are exactly the
    original four 0.149-v4 edges plus the 0162-v1 <-> 0162-v2 hop.
    """
    from slaif_gateway.services.codex_module_upgrade import (
        CODEX_0149_V4_CLIENT_MODULE,
        CODEX_0162_V1_CLIENT_MODULE,
        UPGRADE_TARGET_CLIENT_MODULES,
        _LEGAL_TRANSITIONS,
    )

    assert dict(CODEX_0149_V4_CLIENT_MODULE) == {
        "id": "codex-0.149-responses-v1",
        "version": "4",
        "fixture_sha256": "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec",
    }
    assert dict(CODEX_0162_V1_CLIENT_MODULE) == {
        "id": "codex-0.162-responses-v1",
        "version": "1",
        "fixture_sha256": "724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e",
    }
    assert dict(UPGRADE_TARGET_CLIENT_MODULES["0162-v2"]) == {
        "id": "codex-0.162-responses-v1",
        "version": "2",
        "fixture_sha256": "b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85",
    }
    # The v1 selector is the same frozen object, not re-derived from v2.
    assert UPGRADE_TARGET_CLIENT_MODULES["0162-v1"] is CODEX_0162_V1_CLIENT_MODULE

    assert set(_LEGAL_TRANSITIONS) == {
        ("0149-v4", "0149-v5"),
        ("0149-v4", "0162-v1"),
        ("0149-v5", "0149-v4"),
        ("0162-v1", "0149-v4"),
        ("0162-v1", "0162-v2"),
        ("0162-v2", "0162-v1"),
    }
    # No cross-target edge and no self-loop is legal.
    for source, target in (
        ("0149-v4", "0162-v2"),
        ("0162-v2", "0149-v4"),
        ("0149-v5", "0162-v1"),
        ("0162-v2", "0149-v5"),
        ("0162-v1", "0149-v5"),
        ("0149-v4", "0149-v4"),
        ("0162-v1", "0162-v1"),
        ("0162-v2", "0162-v2"),
    ):
        assert (source, target) not in _LEGAL_TRANSITIONS
