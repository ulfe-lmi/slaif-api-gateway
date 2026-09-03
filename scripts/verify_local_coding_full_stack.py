#!/usr/bin/env python3
"""Bounded 155-aj verifier for hook-free Objective-155 acceptance.

The verifier is deliberately fail-closed and emits only fixed facts.  It is a
task-local evidence tool, not a deployment or production runner.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import base64
from collections.abc import Callable
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
LOCAL_ROOT = Path("/home/ubuntu/codex-work/slaif-local-coding-005m").resolve()
RUNTIME_REFERENCE = Path("/tmp/slaif-155f-runtime.env")
GATEWAY_REPORT_HEAD = "a9625753716325bc0ef6a75689bf42bddbfbd03d"
GATEWAY_IMPLEMENTATION_HEAD = "3cce1a7612fc9919adf26df9952baabaf703c348"
GATEWAY_ACTIVATION_HEAD = "efadf5e1038dc042a596414282c5383deab80c8e"
GATEWAY_REPORT_PATH = "oap/reports/155-ai-signed-identity-grammar-interoperability-and-acceptance.md"
LOCAL_REPORT_HEAD = "4d3ab2fd97d249710f952dd3d2c28936138cc8fa"
LOCAL_REPORT_PARENT = "258ae2ebad39651076937b9f027e60831b8d2786"
LOCAL_SIGNED_CONTRACT_HEAD = "356be8345dd71d6fddf829278651d18e485731d4"
LOCAL_REPORT_PATH = "oap/reports/005-m-gateway-155r-real-codex-matrix-and-cutover-closure.md"
CODEX_VERSION = "0.149.0"
CODEX_PACKAGE_NAME = "@openai/codex"
CODEX_PACKAGE_SPEC = f"{CODEX_PACKAGE_NAME}@{CODEX_VERSION}"
CODEX_MODEL = "qwen3.8-27b"
FAILURE_MODEL = "155f-synthetic-provider-failure"
CODEX_MODULE_ID = "codex-0.149-responses-v1"
CODEX_MODULE_VERSION = "3"
CODEX_FIXTURE_SHA256 = "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec"
SESSION_FIXTURE = REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json"
HISTORICAL_FIXTURE = REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-structural.json"
V2_FIXTURE = REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-structural-v2.json"
HISTORICAL_FIXTURE_SHA256 = "0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d"
V2_FIXTURE_SHA256 = "baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1"
ORDER_PATH = REPO_ROOT / "oap/orders/155-aj-final-hook-free-objective-155-acceptance.md"
TASK_DB = "slaif_gateway_oap_155aj_hook_free_acceptance"
DIRECT_BASELINE_REPORT = REPO_ROOT / "oap/reports/155-l-total-safe-stream-normalization-and-single-diagnostic.md"
SERVICE_TOKEN_ENV = "SLAIF_155F_LOCAL_SERVICE_TOKEN"
SIGNING_SECRET_ENV = "SLAIF_155F_LOCAL_SIGNING_SECRET"
QWEN_TOKEN_ENV = "QWEN3090_API_KEY"
QWEN_RELAY_TOKEN_ENV = "SLAIF_155F_QWEN_RELAY_TOKEN"
MAX_OUTPUT_BYTES = 256 * 1024
LOCAL_METRICS_URL_PATH = "/metrics"
RELAY_BODY_LIMIT = 512 * 1024
QUALIFICATION_HOOK_ENV = "SLAIF_155X_QUALIFICATION"
QUALIFICATION_ARTIFACT_ENV = "SLAIF_155X_REJECTION_ARTIFACT"
QUALIFICATION_ROOT_ENV = "SLAIF_155X_REJECTION_ROOT"
QUALIFICATION_ARTIFACT_NAME = "qualification-rejection.json"
QUALIFICATION_SUMMARY_NAME = "qualification-summary.json"
QUALIFICATION_MAX_BYTES = 64 * 1024
QUALIFICATION_SUMMARY_MAX_BYTES = 16 * 1024
QUALIFICATION_MAX_FIELDS = 32
QUALIFICATION_FIELD_TYPES = frozenset(
    {"null", "boolean", "integer", "number", "string", "object", "array", "other"}
)
QUALIFICATION_DECLARED_TOOL_CLASSES = frozenset({"none", "bounded", "many"})
QUALIFICATION_WEB_SEARCH_CLASSES = frozenset({"none", "bounded", "other"})
QUALIFICATION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
QUALIFICATION_EVENT_RE = re.compile(r"^[a-z][a-z0-9_.]{0,127}$")

LOCAL_MATRIX_INDICES = tuple(range(16)) + (26, 94, 121)
LOCAL_LEGACY_PUNCTUATION_ROWS = {6: "_", 26: "-", 94: "-", 121: "_"}

_155AJ_DISCREPANCY_MANIFEST = {
    "report": "155-aj-final-hook-free-objective-155-acceptance.md",
    "frozen_candidate": "e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4",
    "reasoning_names_missing_from_frozen_verifier": (
        "response.reasoning_part.added",
        "response.reasoning_text.delta",
        "response.reasoning_text.done",
        "response.reasoning_part.done",
    ),
    "frozen_local_matrix_rows": 8,
    "required_local_matrix_rows": 16,
    "claimed_snapshot_outcome_test": "test_boundary_snapshot_classification_has_fixed_downstream_outcomes",
    "claimed_snapshot_outcome_case_count": 2,
    "hmac_rotation_gap": "new_v2_function_and_idless_case_not_created_by_cited_test",
    "baseline_stage": "postgres_start_failed",
    "strategic_stage": "second_mocked_request_timeout",
}

_155AJ_OBLIGATION_TESTS = {
    "reasoning_vocabulary": "test_155aj_reasoning_vocabulary_is_exact_and_closed",
    "snapshot_missing_collection": "test_boundary_snapshot_rejects_raw_or_malformed_nested_facts",
    "snapshot_one_structure": "test_boundary_snapshot_classification_has_fixed_downstream_outcomes",
    "snapshot_excess_structures": "test_boundary_snapshot_rejects_raw_or_malformed_nested_facts",
    "snapshot_absent_ordinal_0": "test_boundary_snapshot_classification_has_fixed_downstream_outcomes",
    "snapshot_absent_ordinal_1": "test_boundary_snapshot_classification_has_fixed_downstream_outcomes",
    "snapshot_invalid_flag": "test_boundary_snapshot_rejects_raw_or_malformed_nested_facts",
    "snapshot_created_missing_duplicate": "test_sse_structure_rejects_order_duplicates_done_and_wrong_status",
    "snapshot_completed_missing_duplicate": "test_sse_structure_rejects_order_duplicates_done_and_wrong_status",
    "snapshot_id_relationship": "test_stream_summary_rejects_response_completed_sequence_mismatch",
    "snapshot_created_status": "test_sse_structure_rejects_order_duplicates_done_and_wrong_status",
    "snapshot_completed_status": "test_sse_structure_rejects_order_duplicates_done_and_wrong_status",
    "snapshot_model": "test_stream_completion_gate_rejects_missing_or_false_safe_facts",
    "snapshot_terminal_output": "test_stream_completion_gate_rejects_missing_terminal_event_and_invalid_bounds",
    "snapshot_usage": "test_stream_completion_gate_rejects_missing_or_false_safe_facts",
    "snapshot_unknown": "test_sse_structure_rejects_unknown_event_type",
    "snapshot_error_event": "test_error_event_projection_keeps_only_finite_safe_facts",
    "snapshot_trace_overflow": "test_trace_overflow_preserves_producer_completion_fact",
    "snapshot_abnormal_close": "test_forwarding_relay_records_upstream_truncation_without_normal_close",
    "snapshot_early_close": "test_forwarding_relay_drains_upstream_after_downstream_reset",
    "snapshot_handler_error": "test_relay_handle_error_is_safe_and_fail_closed",
    "snapshot_truncation": "test_safe_stream_summary_records_handler_and_truncation_without_private_text",
    "snapshot_reasoning_lifecycle": "test_codex_0149_reasoning_lifecycle_rejects_orphans_duplicates_and_reordering",
    "snapshot_function_lifecycle": "test_composed_tool_roundtrip_requires_function_then_message_gateway_lifecycle",
    "snapshot_message_lifecycle": "test_codex_0149_message_lifecycle_rejects_reordering_and_wrong_terminal_shapes",
    "snapshot_schema_privacy": "test_normalized_summary_rebuild_discards_unexpected_extra_keys",
    "snapshot_failure_survival": "test_dedicated_runner_preserves_boundary_snapshot_after_temp_cleanup",
    "snapshot_cli": "test_qualification_cli_direct_stdout_is_one_bounded_line",
    "outcome_local_before_qwen": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "outcome_qwen_failed": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "outcome_local_stream_invalid": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "outcome_gateway_stream_invalid": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "outcome_verifier_expectation": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "outcome_succeeded": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "outcome_other": "test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values",
    "hmac_rotation": "test_hmac_rotation_verifies_old_rows_and_new_rows_by_row_version",
    "hmac_idless": "test_idless_function_call_uses_exact_same_key_call_hmac_row",
    "hmac_new_v2_function_present": "test_hmac_rotation_new_v2_function_present_and_idless",
    "hmac_new_v2_custom_present": "test_hmac_rotation_new_v2_custom_present_and_idless",
    "hmac_ambiguity": "test_idless_call_digest_ambiguity_is_not_collapsed",
    "hmac_unavailable": "test_hmac_rotation_fails_closed_when_old_secret_is_unavailable",
    "hmac_version": "test_unavailable_stored_hmac_version_is_refused",
    "hmac_scope": "test_cross_key_expiry_name_and_route_mismatches_fail_closed",
    "hmac_privacy": "test_digest_lookup_failure_has_no_private_exception_chain",
    "local_matrix": "test_155aj_local_matrix_declares_fixed_legacy_punctuation_rows",
    "local_identity": "test_signed_local_request_projection_verifies_exact_body_and_headers",
    "fake_roundtrip": "test_fake_qwen_tool_roundtrip_mode_is_dedicated_and_allowlisted",
    "fake_provider_failure": "test_fake_provider_failure_mode_is_opt_in_and_counts_inference_only",
    "fake_validator_failure": "test_verifier_owned_qualification_evidence_is_bounded_and_write_once",
    "hook_absent": "test_production_responses_gateway_has_no_155x_qualification_writer",
    "pinned_candidate": "test_candidate_is_exact_and_unregistered",
}

_155AK_SNAPSHOT_CASE_IDS = (
    "missing_collection", "non_list_collection", "one_structure",
    "excess_structures", "absent_ordinal_0", "absent_ordinal_1", "invalid_flag",
    "created_missing", "created_duplicate", "completed_missing", "completed_duplicate",
    "response_id_relationship", "created_status", "completed_status", "model_mismatch",
    "terminal_output_missing", "terminal_output_invalid", "usage_missing", "usage_invalid",
    "unknown_event", "error_event", "trace_overflow", "abnormal_close",
    "downstream_early_close", "handler_error", "upstream_truncated",
    "reasoning_lifecycle", "function_lifecycle", "message_lifecycle",
)
_155AK_OUTCOME_CASE_IDS = (
    "local_turn2_rejected_before_qwen",
    "local_invoked_qwen_turn2_qwen_rejected_or_failed",
    "qwen_turn2_completed_local_stream_invalid",
    "local_qwen_turn2_completed_gateway_stream_invalid",
    "producer_boundaries_valid_verifier_expectation_wrong",
    "full_two_turn_path_succeeded",
    "other",
)
_155AK_REQUIRED_TEST_NODES = tuple(
    [
        f"tests/unit/test_local_coding_full_stack_verifier.py::test_155ak_snapshot_predicate_matrix[{case}]"
        for case in _155AK_SNAPSHOT_CASE_IDS
    ]
    + [
        f"tests/unit/test_local_coding_full_stack_verifier.py::test_155aj_snapshot_outcome_matrix_has_all_seven_closed_values[{case}]"
        for case in _155AK_OUTCOME_CASE_IDS
    ]
    + [
        "tests/unit/test_local_coding_full_stack_verifier.py::test_155aj_reasoning_vocabulary_is_exact_and_closed",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_155ak_reasoning_lifecycle_matches_production_active_profile",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_155ak_snapshot_outcome_case_ids_match_validator_enum_exactly",
        *(
            "tests/unit/test_local_coding_full_stack_verifier.py::test_boundary_snapshot_rejects_raw_or_malformed_nested_facts[<lambda>"
            f"{index}]"
            for index in range(6)
        ),
        *(
            "tests/unit/test_local_coding_full_stack_verifier.py::test_stream_completion_gate_rejects_missing_or_false_safe_facts["
            f"{field}]"
            for field in (
                "response_id_relation", "completed_status_completed", "model_matches",
                "completed_usage_valid", "first_event_before_upstream_completion", "normal_close",
            )
        ),
        "tests/unit/test_local_coding_full_stack_verifier.py::test_forwarding_relay_records_upstream_truncation_without_normal_close",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_forwarding_relay_drains_upstream_after_downstream_reset",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_relay_handle_error_is_safe_and_fail_closed",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_safe_stream_summary_records_handler_and_truncation_without_private_text",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_dedicated_runner_preserves_boundary_snapshot_after_temp_cleanup",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_qualification_cli_direct_stdout_is_one_bounded_line",
        "tests/unit/test_codex_replay_service.py::test_hmac_rotation_verifies_old_rows_and_new_rows_by_row_version",
        "tests/unit/test_codex_replay_service.py::test_idless_function_call_uses_exact_same_key_call_hmac_row",
        "tests/unit/test_codex_replay_service.py::test_idless_call_digest_ambiguity_is_not_collapsed",
        "tests/unit/test_codex_replay_service.py::test_hmac_rotation_new_v2_function_present_and_idless",
        "tests/unit/test_codex_replay_service.py::test_hmac_rotation_new_v2_custom_present_and_idless",
        "tests/unit/test_codex_replay_service.py::test_hmac_rotation_fails_closed_when_old_secret_is_unavailable",
        "tests/unit/test_codex_replay_service.py::test_unavailable_stored_hmac_version_is_refused",
        "tests/unit/test_codex_replay_service.py::test_cross_key_expiry_name_and_route_mismatches_fail_closed",
        "tests/unit/test_codex_replay_service.py::test_digest_lookup_failure_has_no_private_exception_chain",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_155aj_local_matrix_declares_fixed_legacy_punctuation_rows",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_signed_local_request_projection_verifies_exact_body_and_headers",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_fake_qwen_tool_roundtrip_mode_is_dedicated_and_allowlisted",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_fake_provider_failure_mode_is_opt_in_and_counts_inference_only",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_verifier_owned_qualification_evidence_is_bounded_and_write_once",
        "tests/unit/test_local_coding_full_stack_verifier.py::test_production_responses_gateway_has_no_155x_qualification_writer",
        "tests/unit/test_qwen38_text_codex_candidate.py::test_candidate_is_exact_and_unregistered",
    ]
)

# This is a verifier-owned projection of the immutable Local 005-m response
# vocabulary.  The values are safe only because they are closed and source-
# checked below; arbitrary Local error text never crosses this boundary.
_LOCAL_FIXED_ERROR_CODE_TO_STAGE = {
    "invalid_service_authorization": "service_auth",
    "service_authorization_denied": "service_auth",
    "service_auth_unavailable": "service_auth",
    "signed_identity_headers_invalid": "signed_identity",
    "signed_identity_field_invalid": "signed_identity",
    "signed_identity_path_invalid": "signed_identity",
    "signed_identity_method_invalid": "signed_identity",
    "signed_identity_version_invalid": "signed_identity",
    "signed_identity_timestamp_invalid": "signed_identity",
    "signed_identity_nonce_invalid": "signed_identity",
    "signed_identity_signature_invalid": "signed_identity",
    "signed_identity_clock_unavailable": "signed_identity",
    "signed_identity_timestamp_out_of_window": "signed_identity",
    "signed_identity_secret_unavailable": "signed_identity",
    "signed_identity_signature_mismatch": "signed_identity",
    "signed_identity_replayed": "signed_identity",
    "signed_identity_route_mismatch": "signed_identity",
    "metrics_disabled": "json_route_image",
    "unsupported_endpoint": "json_route_image",
    "request_too_large": "json_route_image",
    "json_nesting_too_deep": "json_route_image",
    "invalid_json": "json_route_image",
    "missing_model": "json_route_image",
    "unknown_route": "json_route_image",
    "ambiguous_image_shape": "json_route_image",
    "image_limit_exceeded": "json_route_image",
    "image_policy_failed": "json_route_image",
    "responses_tool_policy_invalid": "tool_policy",
    "responses_disabled_tool_choice": "tool_policy",
    "upstream_unavailable": "upstream",
    "upstream_timeout": "upstream",
    "upstream_error": "upstream",
    "upstream_response_too_large": "upstream",
}
_LOCAL_CONSTITUTION_INJECTION_SUFFIXES = frozenset(
    {"unsupported_shape", "malformed_marker", "conflicting_marker", "duplicate_marker", "bounds_exceeded"}
)
_LOCAL_ERROR_CODE_CLASSES = frozenset(
    {
        "none",
        "other",
        *_LOCAL_FIXED_ERROR_CODE_TO_STAGE,
        *(f"constitution_{suffix}" for suffix in _LOCAL_CONSTITUTION_INJECTION_SUFFIXES),
    }
)
_LOCAL_REJECTION_STAGES = frozenset(
    {"service_auth", "signed_identity", "json_route_image", "tool_policy", "observation_constitution", "upstream", "other"}
)
_LOCAL_BOUNDARY_STATES = frozenset(
    {"not_reached", "entered", "transformed", "rejected", "succeeded", "unknown"}
)
_LOCAL_TOOL_CHOICE_CLASSES = frozenset(
    {"absent", "automatic_none", "required", "explicit_disabled_search", "explicit_retained_local", "malformed_other"}
)
_LOCAL_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_LOCAL_SOURCE_FILES = (
    "src/slaif_local_coding/app.py",
    "src/slaif_local_coding/gateway_identity.py",
    "src/slaif_local_coding/tool_policy.py",
    "src/slaif_local_coding/constitution/injection.py",
)
_LOCAL_SOURCE_CODE_GROUPS = (
    (
        "src/slaif_local_coding/app.py",
        frozenset(_LOCAL_FIXED_ERROR_CODE_TO_STAGE)
        - {
            "signed_identity_headers_invalid",
            "signed_identity_field_invalid",
            "signed_identity_path_invalid",
            "signed_identity_method_invalid",
            "signed_identity_version_invalid",
            "signed_identity_timestamp_invalid",
            "signed_identity_nonce_invalid",
            "signed_identity_signature_invalid",
            "signed_identity_clock_unavailable",
            "signed_identity_timestamp_out_of_window",
            "signed_identity_secret_unavailable",
            "signed_identity_signature_mismatch",
            "signed_identity_replayed",
            "responses_tool_policy_invalid",
            "responses_disabled_tool_choice",
        },
    ),
    (
        "src/slaif_local_coding/gateway_identity.py",
        frozenset(
            {
                "signed_identity_headers_invalid",
                "signed_identity_field_invalid",
                "signed_identity_path_invalid",
                "signed_identity_method_invalid",
                "signed_identity_version_invalid",
                "signed_identity_timestamp_invalid",
                "signed_identity_nonce_invalid",
                "signed_identity_signature_invalid",
                "signed_identity_clock_unavailable",
                "signed_identity_timestamp_out_of_window",
                "signed_identity_secret_unavailable",
                "signed_identity_signature_mismatch",
                "signed_identity_replayed",
            }
        ),
    ),
    (
        "src/slaif_local_coding/tool_policy.py",
        frozenset({"responses_tool_policy_invalid", "responses_disabled_tool_choice"}),
    ),
)
_LOCAL_SIGNED_HEADER_NAMES = (
    "x-slaif-identity-version",
    "x-slaif-principal",
    "x-slaif-session",
    "x-slaif-repository",
    "x-slaif-route",
    "x-slaif-timestamp",
    "x-slaif-nonce",
    "x-slaif-signature",
)
_LOCAL_SIGNED_IDENTITY_FACT_KEYS = frozenset(
    {
        "service_bearer_equal",
        "required_header_cardinality_class",
        "principal_grammar_valid",
        "session_grammar_valid",
        "repository_grammar_valid",
        "route_grammar_valid",
        "canonical_bytes_reconstructed",
        "raw_body_canonical_participates",
        "signature_verifies",
        "route_matches",
        "method_path_query_valid",
        "version_shape_valid",
        "timestamp_shape_valid",
        "nonce_shape_valid",
        "no_extra_internal_headers",
        "signed_identity_class",
    }
)
_LOCAL_SIGNED_HEADER_CARDINALITY_CLASSES = frozenset(
    {"exact", "missing", "duplicate", "extra", "other"}
)
_LOCAL_SIGNED_IDENTITY_CLASSES = frozenset({"verified", "invalid", "other"})
LOCAL_CODING_ROUTE_NAME = "qwen38-vision-codex"


class VerificationError(RuntimeError):
    """A fixed verifier failure that cannot reflect private values."""


def _codex_version_class(raw: bytes) -> str:
    if raw == f"codex-cli {CODEX_VERSION}\n".encode("ascii"):
        return CODEX_VERSION
    if raw == b"codex-cli 0.149.1\n":
        return "0.149.1"
    return "other"


def _verify_codex_task_local_provenance(
    root: Path, binary: Path
) -> dict[str, object]:
    """Verify the exact disposable Codex executable without retaining paths/output."""
    install = (root / "codex-install").resolve()
    expected_binary = install / "node_modules/.bin/codex"
    try:
        if binary.absolute() != expected_binary:
            raise VerificationError("codex_binary_not_task_local")
        if os.path.commonpath((str(install), str(root.resolve()))) != str(root.resolve()):
            raise VerificationError("codex_binary_not_task_local")
        resolved_binary = binary.resolve(strict=True)
        if not resolved_binary.is_file() or os.path.commonpath(
            (str(resolved_binary), str(root.resolve()))
        ) != str(root.resolve()):
            raise VerificationError("codex_binary_not_task_local")
        metadata_path = install / "node_modules/@openai/codex/package.json"
        metadata = json.loads(metadata_path.read_bytes())
    except VerificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise VerificationError("codex_package_metadata_invalid") from exc
    if (
        not isinstance(metadata, dict)
        or metadata.get("name") != CODEX_PACKAGE_NAME
        or metadata.get("version") != CODEX_VERSION
    ):
        raise VerificationError("codex_package_version_mismatch")
    version_result = _run([str(binary), "--version"], timeout=10)
    if version_result.returncode != 0 or _codex_version_class(version_result.stdout) != CODEX_VERSION:
        raise VerificationError("codex_version_mismatch")

    host_default_version_class = "other"
    host_binary = shutil.which("codex")
    if host_binary is not None:
        host_result = _run([host_binary, "--version"], timeout=10)
        if host_result.returncode == 0:
            host_default_version_class = _codex_version_class(host_result.stdout)
    return _safe_codex_provenance(
        {
            "source_class": "task_local_exact_npm",
            "requested_package_class": CODEX_PACKAGE_NAME,
            "requested_version_class": CODEX_VERSION,
            "package_version_class": metadata["version"],
            "raw_version_class": CODEX_VERSION,
            "invoked_version_class": CODEX_VERSION,
            "task_local_under_root": True,
            "verified_binary_is_invoked": True,
            "catalog_and_command_binary_same": True,
            "host_default_version_class": host_default_version_class,
            "host_default_matches_pinned": host_default_version_class == CODEX_VERSION,
        }
    )


def _safe_codex_provenance(value: object) -> dict[str, object]:
    expected_keys = {
        "source_class",
        "requested_package_class",
        "requested_version_class",
        "package_version_class",
        "raw_version_class",
        "invoked_version_class",
        "task_local_under_root",
        "verified_binary_is_invoked",
        "catalog_and_command_binary_same",
        "host_default_version_class",
        "host_default_matches_pinned",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise VerificationError("codex_provenance_invalid")
    if (
        value["source_class"] != "task_local_exact_npm"
        or value["requested_package_class"] != CODEX_PACKAGE_NAME
        or any(
            value[name] != CODEX_VERSION
            for name in (
                "requested_version_class",
                "package_version_class",
                "raw_version_class",
                "invoked_version_class",
            )
        )
        or any(
            type(value[name]) is not bool or value[name] is not True
            for name in (
                "task_local_under_root",
                "verified_binary_is_invoked",
                "catalog_and_command_binary_same",
            )
        )
        or value["host_default_version_class"] not in {"0.149.0", "0.149.1", "other"}
        or type(value["host_default_matches_pinned"]) is not bool
        or value["host_default_matches_pinned"]
        != (value["host_default_version_class"] == CODEX_VERSION)
    ):
        raise VerificationError("codex_provenance_invalid")
    return dict(value)


COMPOSITION_STAGES = (
    "topology", "runtime_reference", "fixtures", "pinned_direct_baseline",
    "local_config",
    "postgres_image", "postgres_start", "migration", "database_seed",
    "relay_start", "failure_provider_start", "qwen_relay_start", "local_start",
    "gateway_start", "qwen_relay_ready", "local_health", "local_readiness",
    "gateway_health", "gateway_models", "ordinary_response", "stream_response",
    "client_stream", "boundary_capture",
    "tool_codex_execution", "tool_roundtrip_failure_localization",
    "tool_roundtrip_codex_failure_projection", "tool_roundtrip_gateway_snapshot",
    "tool_roundtrip_local_snapshot", "tool_roundtrip_qwen_projection",
    "tool_roundtrip_request_projection", "tool_roundtrip_accounting_projection",
    "tool_roundtrip_qualification_artifact", "tool_roundtrip_failure_decision",
    "tool_roundtrip_boundary_capture", "tool_roundtrip_privacy_aliases",
    "tool_roundtrip_signed_identity_headers", "tool_roundtrip_signed_key_forwarding",
    "tool_roundtrip_sse_validation",
    "tool_roundtrip_qwen_boundary",
    "tool_roundtrip_accounting",
    "image_response", "constitution_root_first", "constitution_root_reuse",
    "zero_root_rehydration", "codex_session_a", "codex_session_a_resume",
    "codex_session_b", "replay_and_tamper", "second_gateway_key",
    "preprovider_negatives", "controlled_provider_failure", "accounting",
    "local_metrics", "qwen_wire_evidence", "privacy", "process_cleanup",
    "container_cleanup", "repository_cleanup", "protected_postcheck", "final_evidence",
)
_SAFE_UNEXPECTED_EXCEPTION_CLASSES = frozenset(
    {
        "AttributeError",
        "IndexError",
        "KeyError",
        "OSError",
        "TypeError",
        "ValueError",
    }
)


class StageTracker:
    """Track only a fixed composition stage for safe unexpected-error codes."""

    def __init__(self) -> None:
        self.current: str | None = None

    def set(self, stage: str) -> None:
        if stage not in COMPOSITION_STAGES:
            raise VerificationError("unknown_composition_stage")
        self.current = stage

    def unexpected(self) -> VerificationError:
        if self.current not in COMPOSITION_STAGES:
            return VerificationError("unexpected_unknown_stage")
        return VerificationError(f"unexpected_{self.current}")

    def unexpected_composed(
        self, exception: BaseException | None = None
    ) -> VerificationError:
        if self.current not in COMPOSITION_STAGES:
            return VerificationError("unexpected_composed_unknown_stage")
        if exception is None:
            return VerificationError(f"unexpected_composed_{self.current}")
        exception_class = type(exception).__name__
        if exception_class not in _SAFE_UNEXPECTED_EXCEPTION_CLASSES:
            exception_class = "Other"
        return VerificationError(
            f"unexpected_composed_{self.current}_{exception_class}"
        )


@dataclass(frozen=True, slots=True)
class RuntimeReference:
    endpoint: str
    credential_source: Path

    def __repr__(self) -> str:
        return "RuntimeReference(<redacted>)"

    __str__ = __repr__


def _safe_path_class(path: str) -> str:
    value = urlsplit(path).path
    if value == "/v1/responses":
        return "v1_responses"
    if value == "/v1/chat/completions":
        return "v1_chat_completions"
    if value == "/responses":
        return "bare_responses"
    if value == "/v1/v1/responses":
        return "double_v1_responses"
    return "other"


@dataclass(frozen=True, slots=True)
class SeededKey:
    gateway_key_id: uuid.UUID
    owner_id: uuid.UUID
    plaintext: str


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 120,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        kwargs: dict[str, object] = {
            "cwd": cwd,
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": timeout,
            "check": False,
        }
        if input_bytes is None:
            kwargs["stdin"] = subprocess.DEVNULL
        else:
            kwargs["input"] = input_bytes
        result = subprocess.run(argv, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("command_failed") from exc
    if len(result.stdout) > MAX_OUTPUT_BYTES or len(result.stderr) > MAX_OUTPUT_BYTES:
        raise VerificationError("command_output_exceeded")
    return result


def _safe_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return str(parsed) == value


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = _run(["git", *args], cwd=cwd)
    if result.returncode != 0:
        raise VerificationError("git_check_failed")
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise VerificationError("git_output_invalid") from exc


def _local_source_string_literals(relative_path: str) -> set[str]:
    """Read only source literals needed to pin the Local error vocabulary."""
    path = LOCAL_ROOT / relative_path
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise VerificationError("local_source_contract_invalid") from exc
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _verify_local_error_source_contract() -> None:
    """Prove the closed Local vocabulary still comes from the pinned source."""
    literals: set[str] = set()
    for relative_path in _LOCAL_SOURCE_FILES:
        literals.update(_local_source_string_literals(relative_path))
    for relative_path, expected_codes in _LOCAL_SOURCE_CODE_GROUPS:
        if not expected_codes.issubset(_local_source_string_literals(relative_path)):
            raise VerificationError("local_source_error_vocabulary_drift")
    injection_literals = _local_source_string_literals(
        "src/slaif_local_coding/constitution/injection.py"
    )
    if not _LOCAL_CONSTITUTION_INJECTION_SUFFIXES.issubset(injection_literals):
        raise VerificationError("local_source_constitution_vocabulary_drift")


def _safe_local_error_code_class(value: object) -> str:
    """Return one source-reviewed Local code, never arbitrary provider text."""
    if not isinstance(value, str):
        return "other"
    if value in _LOCAL_FIXED_ERROR_CODE_TO_STAGE:
        return value
    if value.startswith("constitution_"):
        suffix = value.removeprefix("constitution_")
        if suffix in _LOCAL_CONSTITUTION_INJECTION_SUFFIXES:
            return value
    return value if value in {"none", "other"} else "other"


def _safe_local_rejection_stage(value: object) -> str:
    """Map one safe Local code to the immutable Local execution stage."""
    code = _safe_local_error_code_class(value)
    if code.startswith("constitution_"):
        return "observation_constitution"
    return _LOCAL_FIXED_ERROR_CODE_TO_STAGE.get(code, "other")


def _safe_local_error_classes(value: object, response_statuses: object) -> list[str]:
    """Align Local code classes to response ordinals and totalize malformed input."""
    statuses = response_statuses if isinstance(response_statuses, list) else []
    raw = value if isinstance(value, list) else []
    if len(raw) != len(statuses):
        raw = [
            "none" if type(status) is int and status < 400 else "other"
            for status in statuses
        ]
    return [_safe_local_error_code_class(item) for item in raw[:2]]


def _safe_local_stage_classes(value: object, response_statuses: object) -> list[str]:
    statuses = response_statuses if isinstance(response_statuses, list) else []
    raw = value if isinstance(value, list) else []
    if len(raw) != len(statuses):
        raw = [
            "other" if type(status) is int and status < 400 else "other"
            for status in statuses
        ]
    result = []
    for item in raw[:2]:
        stage = item if isinstance(item, str) and item in _LOCAL_REJECTION_STAGES else "other"
        result.append(stage)
    return result


def _safe_local_boundary_states(value: object) -> dict[str, str]:
    """Rebuild only the four fixed Local boundary states."""
    names = ("tool_policy", "observation", "constitution", "upstream")
    if not isinstance(value, dict):
        return {name: "unknown" for name in names}
    return {
        name: value.get(name)
        if isinstance(value.get(name), str) and value.get(name) in _LOCAL_BOUNDARY_STATES
        else "unknown"
        for name in names
    }


def _empty_signed_identity_projection() -> dict[str, object]:
    return {
        "service_bearer_equal": False,
        "required_header_cardinality_class": "other",
        "principal_grammar_valid": False,
        "session_grammar_valid": False,
        "repository_grammar_valid": False,
        "route_grammar_valid": False,
        "canonical_bytes_reconstructed": False,
        "raw_body_canonical_participates": False,
        "signature_verifies": False,
        "route_matches": False,
        "method_path_query_valid": False,
        "version_shape_valid": False,
        "timestamp_shape_valid": False,
        "nonce_shape_valid": False,
        "no_extra_internal_headers": False,
        "signed_identity_class": "other",
    }


def _safe_signed_identity_projections(
    value: object, response_statuses: object
) -> list[dict[str, object]]:
    statuses = response_statuses if isinstance(response_statuses, list) else []
    raw = value if isinstance(value, list) else []
    if len(raw) != len(statuses):
        raw = [_empty_signed_identity_projection() for _ in statuses]
    result: list[dict[str, object]] = []
    for item in raw[:2]:
        safe = _empty_signed_identity_projection()
        if isinstance(item, dict):
            for name in (
                "service_bearer_equal",
                "principal_grammar_valid",
                "session_grammar_valid",
                "repository_grammar_valid",
                "route_grammar_valid",
                "canonical_bytes_reconstructed",
                "raw_body_canonical_participates",
                "signature_verifies",
                "route_matches",
                "method_path_query_valid",
                "version_shape_valid",
                "timestamp_shape_valid",
                "nonce_shape_valid",
                "no_extra_internal_headers",
            ):
                safe[name] = item.get(name) is True
            cardinality = item.get("required_header_cardinality_class")
            safe["required_header_cardinality_class"] = (
                cardinality
                if isinstance(cardinality, str)
                and cardinality in _LOCAL_SIGNED_HEADER_CARDINALITY_CLASSES
                else "other"
            )
            identity_class = item.get("signed_identity_class")
            safe["signed_identity_class"] = (
                identity_class
                if isinstance(identity_class, str)
                and identity_class in _LOCAL_SIGNED_IDENTITY_CLASSES
                else "other"
            )
        result.append(safe)
    return result


def _safe_local_boundary_states_from_codes(
    codes: object,
    response_statuses: object,
    metrics_before: object | None = None,
    metrics_after: object | None = None,
) -> dict[str, str]:
    """Project Local boundary progress from codes and existing metric deltas."""
    states = {
        "tool_policy": "not_reached",
        "observation": "not_reached",
        "constitution": "not_reached",
        "upstream": "not_reached",
    }
    safe_codes = [
        _safe_local_error_code_class(item) for item in codes
    ] if isinstance(codes, list) else []
    failing_code = next((item for item in reversed(safe_codes) if item not in {"none"}), None)
    if failing_code is not None:
        stage = _safe_local_rejection_stage(failing_code)
        if stage == "tool_policy":
            states["tool_policy"] = "rejected"
        elif stage == "observation_constitution":
            states["observation"] = "entered"
            states["constitution"] = "rejected"
        elif stage == "upstream":
            states["upstream"] = "rejected"
        elif stage == "other":
            states = {name: "unknown" for name in states}
        return states

    def delta(name: str) -> int | None:
        before = getattr(metrics_before, name, None)
        after = getattr(metrics_after, name, None)
        if type(before) is int and type(after) is int and after >= before:
            return after - before
        return None

    if (delta("tool_policy_drops") or 0) > 0:
        states["tool_policy"] = "transformed"
    if any((delta(name) or 0) > 0 for name in (
        "compiler_attempts", "cache_hits", "cache_misses", "rehydration_hits",
        "rehydration_injected",
    )):
        states["observation"] = "entered"
    if (delta("compiler_attempts") or 0) > 0:
        states["constitution"] = "entered"
    statuses = response_statuses if isinstance(response_statuses, list) else []
    if statuses and all(type(status) is int and status < 400 for status in statuses):
        states["upstream"] = "succeeded"
        if states["tool_policy"] == "not_reached":
            states["tool_policy"] = "succeeded"
    return states


def _safe_signed_identity_projection(
    request: CapturedRequest,
    *,
    service_token: str,
    signing_secret: str,
    expected_route: str = LOCAL_CODING_ROUTE_NAME,
) -> dict[str, object]:
    """Verify one captured Local request, retaining only fixed safe facts."""
    safe: dict[str, object] = {
        "service_bearer_equal": False,
        "required_header_cardinality_class": "other",
        "principal_grammar_valid": False,
        "session_grammar_valid": False,
        "repository_grammar_valid": False,
        "route_grammar_valid": False,
        "canonical_bytes_reconstructed": False,
        "raw_body_canonical_participates": False,
        "signature_verifies": False,
        "route_matches": False,
        "method_path_query_valid": False,
        "version_shape_valid": False,
        "timestamp_shape_valid": False,
        "nonce_shape_valid": False,
        "no_extra_internal_headers": False,
        "signed_identity_class": "other",
    }
    headers = request.headers if isinstance(request.headers, dict) else {}
    counts: dict[str, int] = {}
    raw_counts = request.header_name_counts
    if isinstance(raw_counts, tuple) and raw_counts:
        for item in raw_counts:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or type(item[1]) is not int
                or item[1] < 1
            ):
                return safe
            name = item[0].lower()
            counts[name] = counts.get(name, 0) + item[1]
    else:
        for name in headers:
            if isinstance(name, str):
                lowered = name.lower()
                counts[lowered] = counts.get(lowered, 0) + 1
            else:
                return safe
    required = set(_LOCAL_SIGNED_HEADER_NAMES)
    missing = any(counts.get(name, 0) == 0 for name in required)
    duplicate = any(counts.get(name, 0) > 1 for name in required)
    extra = any(
        (
            name.startswith("x-slaif-") and name not in required
        )
        or name.startswith("x-internal-")
        for name in counts
    )
    if duplicate:
        cardinality = "duplicate"
    elif missing:
        cardinality = "missing"
    elif extra:
        cardinality = "extra"
    elif all(counts.get(name) == 1 for name in required):
        cardinality = "exact"
    else:
        cardinality = "other"
    safe["required_header_cardinality_class"] = cardinality
    safe["no_extra_internal_headers"] = not extra
    safe["service_bearer_equal"] = (
        counts.get("authorization") == 1
        and headers.get("authorization") == f"Bearer {service_token}"
    )

    try:
        parsed = urlsplit(request.path)
        query = parsed.query.encode("ascii")
        path = parsed.path
        method = request.method
        identity_values = [headers[name] for name in _LOCAL_SIGNED_HEADER_NAMES[:-1]]
        signature = headers[_LOCAL_SIGNED_HEADER_NAMES[-1]]
        if not all(isinstance(value, str) for value in identity_values):
            raise ValueError
        if not isinstance(signature, str) or not isinstance(request.body, bytes):
            raise ValueError
        safe["method_path_query_valid"] = (
            method == "POST"
            and path == "/v1/responses"
            and not parsed.fragment
            and len(query) <= 256
        )
        safe["version_shape_valid"] = identity_values[0] == "v1"
        grammar_valid = [
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", value) is not None
            for value in identity_values[1:5]
        ]
        (
            safe["principal_grammar_valid"],
            safe["session_grammar_valid"],
            safe["repository_grammar_valid"],
            safe["route_grammar_valid"],
        ) = grammar_valid
        safe["timestamp_shape_valid"] = re.fullmatch(
            r"(?:0|[1-9][0-9]{0,19})", identity_values[5]
        ) is not None
        safe["nonce_shape_valid"] = (
            16 <= len(identity_values[6]) <= 128
            and re.fullmatch(r"[A-Za-z0-9_-]+", identity_values[6]) is not None
        )
        safe["route_matches"] = identity_values[4] == expected_route
        canonical = "\n".join(
            (
                "slaif-local-coding-identity-v1",
                method,
                path,
                hashlib.sha256(query).hexdigest(),
                hashlib.sha256(request.body).hexdigest(),
                *identity_values[1:5],
                identity_values[5],
                identity_values[6],
            )
        ).encode("utf-8")
        safe["canonical_bytes_reconstructed"] = True
        expected = "v1=" + hmac.new(
            signing_secret.encode("utf-8"), canonical, hashlib.sha256
        ).hexdigest()
        safe["signature_verifies"] = bool(
            re.fullmatch(r"v1=[0-9a-f]{64}", signature)
            and hmac.compare_digest(signature, expected)
        )
        altered_canonical = "\n".join(
            (
                "slaif-local-coding-identity-v1",
                method,
                path,
                hashlib.sha256(query).hexdigest(),
                hashlib.sha256(request.body + b" ").hexdigest(),
                *identity_values[1:5],
                identity_values[5],
                identity_values[6],
            )
        ).encode("utf-8")
        altered_expected = "v1=" + hmac.new(
            signing_secret.encode("utf-8"), altered_canonical, hashlib.sha256
        ).hexdigest()
        safe["raw_body_canonical_participates"] = (
            safe["signature_verifies"]
            and not hmac.compare_digest(signature, altered_expected)
        )
    except (KeyError, TypeError, UnicodeEncodeError, ValueError):
        pass
    if all(
        safe[name] is True
        for name in (
            "service_bearer_equal",
            "principal_grammar_valid",
            "session_grammar_valid",
            "repository_grammar_valid",
            "route_grammar_valid",
            "canonical_bytes_reconstructed",
            "raw_body_canonical_participates",
            "signature_verifies",
            "route_matches",
            "method_path_query_valid",
            "version_shape_valid",
            "timestamp_shape_valid",
            "nonce_shape_valid",
            "no_extra_internal_headers",
        )
    ) and safe["required_header_cardinality_class"] == "exact":
        safe["signed_identity_class"] = "verified"
    else:
        safe["signed_identity_class"] = "invalid"
    return safe


def _checks_are_green(output: bytes) -> bool:
    try:
        lines = [line for line in output.decode("utf-8").splitlines() if line.strip()]
    except UnicodeDecodeError:
        return False
    statuses = [line.split("\t", 2)[1] for line in lines if len(line.split("\t", 2)) >= 2]
    return len(lines) >= 10 and len(statuses) == len(lines) and all(
        status == "pass" for status in statuses
    )


def _verify_155aj_discrepancy_inventory() -> dict[str, object]:
    """Prove the bounded defects recorded before the 155-aj repair."""
    def read_blob(path: str) -> str:
        try:
            result = subprocess.run(
                [
                    "git",
                    "show",
                    f"{_155AJ_DISCREPANCY_MANIFEST['frozen_candidate']}:{path}",
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VerificationError("discrepancy_inventory_source_unavailable") from exc
        if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
            raise VerificationError("discrepancy_inventory_source_invalid")
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VerificationError("discrepancy_inventory_source_invalid") from exc

    frozen_verifier = read_blob("scripts/verify_local_coding_full_stack.py")
    frozen_tests = read_blob("tests/unit/test_local_coding_full_stack_verifier.py")
    try:
        tree = ast.parse(frozen_verifier)
        safe_types: set[str] = set()
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not any(
                isinstance(target, ast.Name) and target.id == "_SAFE_SSE_EVENT_TYPES"
                for target in node.targets
            ):
                continue
            value = node.value
            if (
                not isinstance(value, ast.Call)
                or not isinstance(value.func, ast.Name)
                or value.func.id != "frozenset"
                or len(value.args) != 1
                or not isinstance(value.args[0], ast.Set)
            ):
                break
            safe_types = {
                item.value
                for item in value.args[0].elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            break
        missing_reasoning = tuple(
            name
            for name in _155AJ_DISCREPANCY_MANIFEST[
                "reasoning_names_missing_from_frozen_verifier"
            ]
            if name not in safe_types
        )
        frozen_matrix_rows = 8 if "for index in range(8):" in frozen_verifier else None
        snapshot_case_count = 0
        for node in ast.parse(frozen_tests).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != _155AJ_DISCREPANCY_MANIFEST["claimed_snapshot_outcome_test"]:
                continue
            for decorator in node.decorator_list:
                if (
                    not isinstance(decorator, ast.Call)
                    or not isinstance(decorator.func, ast.Attribute)
                    or decorator.func.attr != "parametrize"
                    or len(decorator.args) < 2
                ):
                    continue
                values = decorator.args[1]
                if isinstance(values, (ast.List, ast.Tuple)):
                    snapshot_case_count = len(values.elts)
        expected_reasoning = _155AJ_DISCREPANCY_MANIFEST[
            "reasoning_names_missing_from_frozen_verifier"
        ]
        if (
            missing_reasoning != expected_reasoning
            or frozen_matrix_rows != _155AJ_DISCREPANCY_MANIFEST["frozen_local_matrix_rows"]
            or snapshot_case_count != _155AJ_DISCREPANCY_MANIFEST["claimed_snapshot_outcome_case_count"]
        ):
            raise VerificationError("discrepancy_inventory_changed")
    except (SyntaxError, TypeError, ValueError) as exc:
        raise VerificationError("discrepancy_inventory_invalid") from exc
    return {
        "reasoning_names_missing": len(missing_reasoning),
        "frozen_local_matrix_rows": frozen_matrix_rows,
        "claimed_snapshot_outcome_case_count": snapshot_case_count,
        "hmac_rotation_gap": _155AJ_DISCREPANCY_MANIFEST["hmac_rotation_gap"],
        "baseline_stage": _155AJ_DISCREPANCY_MANIFEST["baseline_stage"],
        "strategic_stage": _155AJ_DISCREPANCY_MANIFEST["strategic_stage"],
    }


def _verify_155aj_obligation_manifest() -> dict[str, object]:
    """Require every 155-ak node to be collected and successfully executed."""
    test_paths = tuple(
        sorted(
            {
                node.split("::", 1)[0]
                for node in _155AK_REQUIRED_TEST_NODES
            }
        )
    )
    collection_command = [
        sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", *test_paths
    ]
    execution_command = [
        sys.executable, "-m", "pytest", "-q", "-o", "addopts=", *_155AK_REQUIRED_TEST_NODES
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = f"{REPO_ROOT}:{REPO_ROOT / 'app'}"

    def run_pytest(command: list[str]) -> bytes:
        try:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VerificationError("obligation_manifest_unavailable") from exc
        if len(result.stdout) > 2 * 1024 * 1024:
            raise VerificationError("obligation_manifest_output_exceeded")
        if result.returncode != 0:
            raise VerificationError("obligation_manifest_execution_failed")
        return result.stdout

    try:
        collected_output = run_pytest(collection_command).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerificationError("obligation_manifest_collection_invalid") from exc
    collected = {
        line.strip()
        for line in collected_output.splitlines()
        if "::test_" in line and not line.startswith("<")
    }
    missing = sorted(set(_155AK_REQUIRED_TEST_NODES) - collected)
    if missing:
        raise VerificationError("obligation_manifest_missing")
    run_pytest(execution_command)
    return {
        "missing": [],
        "collected_node_count": len(collected),
        "executed_node_count": len(_155AK_REQUIRED_TEST_NODES),
        "obligations": {
            f"obligation_{index}": node
            for index, node in enumerate(_155AK_REQUIRED_TEST_NODES)
        },
    }


def _verify_commit_topology() -> None:
    current_head = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain", cwd=REPO_ROOT):
        raise VerificationError("gateway_checkout_dirty")
    if _git("rev-parse", f"{GATEWAY_ACTIVATION_HEAD}^1") != GATEWAY_REPORT_HEAD:
        raise VerificationError("gateway_activation_parent_mismatch")
    activation_changed = _git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", GATEWAY_ACTIVATION_HEAD
    )
    if activation_changed.splitlines() != [
        "oap/active",
        "oap/orders/155-aj-final-hook-free-objective-155-acceptance.md",
    ]:
        raise VerificationError("gateway_activation_not_order_only")
    if _run(
        ["git", "merge-base", "--is-ancestor", GATEWAY_ACTIVATION_HEAD, current_head],
        cwd=REPO_ROOT,
    ).returncode != 0:
        raise VerificationError("gateway_activation_ancestry_failed")
    if _git("rev-parse", f"{GATEWAY_REPORT_HEAD}^1") != GATEWAY_IMPLEMENTATION_HEAD:
        raise VerificationError("gateway_report_parent_mismatch")
    changed = _git("diff-tree", "--no-commit-id", "--name-only", "-r", GATEWAY_REPORT_HEAD)
    if changed != GATEWAY_REPORT_PATH:
        raise VerificationError("gateway_report_not_report_only")
    if _run(["git", "merge-base", "--is-ancestor", GATEWAY_REPORT_HEAD, "HEAD"], cwd=REPO_ROOT).returncode != 0:
        raise VerificationError("gateway_report_ancestry_failed")
    if _git("rev-parse", "HEAD", cwd=LOCAL_ROOT) != LOCAL_REPORT_HEAD:
        raise VerificationError("local_report_head_mismatch")
    if _git("status", "--porcelain", cwd=LOCAL_ROOT):
        raise VerificationError("local_dependency_not_clean")
    if _git("rev-parse", f"{LOCAL_REPORT_HEAD}^1", cwd=LOCAL_ROOT) != LOCAL_REPORT_PARENT:
        raise VerificationError("local_report_parent_mismatch")
    local_report_changed = _git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", LOCAL_REPORT_HEAD,
        cwd=LOCAL_ROOT,
    )
    if local_report_changed != LOCAL_REPORT_PATH:
        raise VerificationError("local_report_not_report_only")
    if _run(["git", "merge-base", "--is-ancestor", LOCAL_SIGNED_CONTRACT_HEAD, LOCAL_REPORT_HEAD], cwd=LOCAL_ROOT).returncode != 0:
        raise VerificationError("local_signed_contract_ancestry_failed")
    _verify_local_error_source_contract()
    for pr, expected in (("291", current_head), ("7", LOCAL_REPORT_HEAD)):
        result = _run(["gh", "pr", "view", pr, "--repo", "ulfe-lmi/slaif-api-gateway" if pr == "291" else "ulfe-lmi/slaif-local-coding", "--json", "state,isDraft,headRefOid,mergeStateStatus,autoMergeRequest"])
        if result.returncode != 0:
            raise VerificationError("github_pr_state_unavailable")
        try:
            state = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError("github_pr_state_invalid") from exc
        if state.get("state") != "OPEN" or state.get("isDraft") is not False or state.get("headRefOid") != expected or state.get("mergeStateStatus") not in {"CLEAN", "MERGEABLE"} or state.get("autoMergeRequest") is not None:
            raise VerificationError("github_pr_state_mismatch")
    checks = _run(["gh", "pr", "checks", "291", "--repo", "ulfe-lmi/slaif-api-gateway"])
    if checks.returncode != 0:
        raise VerificationError("github_checks_unavailable")
    if not _checks_are_green(checks.stdout):
        raise VerificationError("github_checks_not_green")
    report_diff = _run(
        ["git", "diff", f"{GATEWAY_REPORT_HEAD}^1", GATEWAY_REPORT_HEAD, "--", "oap/reports"],
        cwd=REPO_ROOT,
    )
    if report_diff.returncode != 0:
        raise VerificationError("gateway_report_diff_failed")
    strategic_order = Path(
        "/home/ubuntu/codex-work/slaif-api-gateway/oap/orders/155-aj-final-hook-free-objective-155-acceptance.md"
    )
    if ORDER_PATH.read_bytes() != strategic_order.read_bytes():
        raise VerificationError("order_bytes_mismatch")
    if (REPO_ROOT / "oap/active").read_text(encoding="utf-8") != "155-aj\n":
        raise VerificationError("active_selector_mismatch")


def _read_runtime_reference() -> RuntimeReference:
    try:
        mode = stat.S_IMODE(RUNTIME_REFERENCE.stat().st_mode)
    except OSError as exc:
        raise VerificationError("runtime_reference_unavailable") from exc
    if mode != 0o600 or RUNTIME_REFERENCE.stat().st_uid != os.getuid():
        raise VerificationError("runtime_reference_permissions")
    entries: dict[str, str] = {}
    try:
        for line in RUNTIME_REFERENCE.read_text(encoding="utf-8").splitlines():
            if not line or "=" not in line:
                raise VerificationError("runtime_reference_format")
            key, value = line.split("=", 1)
            entries[key] = value
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError("runtime_reference_unreadable") from exc
    if set(entries) != {"SLAIF_155F_QWEN_BASE_URL", "SLAIF_155F_QWEN_CREDENTIAL_SOURCE"}:
        raise VerificationError("runtime_reference_keys")
    endpoint = entries["SLAIF_155F_QWEN_BASE_URL"]
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.path or parsed.query or parsed.fragment:
        raise VerificationError("runtime_endpoint_shape")
    source = Path(entries["SLAIF_155F_QWEN_CREDENTIAL_SOURCE"])
    try:
        source_stat = source.stat()
    except OSError as exc:
        raise VerificationError("credential_source_unavailable") from exc
    if not stat.S_ISREG(source_stat.st_mode) or source.is_symlink() or source_stat.st_uid != os.getuid() or not os.access(source, os.R_OK):
        raise VerificationError("credential_source_shape")
    return RuntimeReference(endpoint=endpoint, credential_source=source)


def _source_qwen_credential_only_for_local(runtime: RuntimeReference) -> None:
    """Source the credential once and pass only the selected variable onward."""
    script = (
        "set +x; . \"$SLAIF_155F_CREDENTIAL_SOURCE\" >/dev/null 2>&1; "
        "test -n \"${QWEN3090_API_KEY:-}\"; "
        "exec /usr/bin/env -i PATH=\"${PATH:-/usr/bin:/bin}\" "
        "QWEN3090_API_KEY=\"${QWEN3090_API_KEY}\" "
        "python3 -c 'import os; raise SystemExit(0 if os.environ.get(\"QWEN3090_API_KEY\") else 1)'"
    )
    result = _run(
        ["bash", "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "SLAIF_155F_CREDENTIAL_SOURCE": str(runtime.credential_source),
        },
        timeout=10,
    )
    if result.returncode != 0:
        raise VerificationError("protected_qwen_credential_unavailable")


def _verify_local_signed_identity_matrix() -> None:
    """Exercise the actual pinned Local verifier with bounded synthetic rows."""
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    local_source = str(LOCAL_ROOT / "src")
    inserted = local_source not in sys.path
    if inserted:
        sys.path.insert(0, local_source)
    try:
        from fastapi import Request
        from slaif_local_coding.config import GatewayIngressConfig
        from slaif_local_coding.gateway_identity import (
            ReplayProtector,
            SignedIdentityError,
            verify_signed_identity,
        )
    except (ImportError, OSError) as exc:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        raise VerificationError("local_signed_identity_matrix_unavailable") from exc
    finally:
        if inserted:
            sys.path.remove(local_source)

    from slaif_gateway.modules.servers.local_coding.contract import (
        LocalCodingRouteContract,
    )
    from slaif_gateway.modules.servers.local_coding.identity import (
        derive_request_identity,
        sign_identity,
    )

    service_token = "155-aj-synthetic-service-token"
    signing_secret = "155-aj-synthetic-signing-secret-0123456789"
    route = LocalCodingRouteContract(
        contract_version="local-coding-v1",
        route_name=LOCAL_CODING_ROUTE_NAME,
        tool_policy_version="responses-tool-policy-v1",
        identity_mode="signed_identity_v1",
        replay_mode="process_local_ttl_lru",
        deployment_mode="single_worker",
    )
    config = GatewayIngressConfig(
        mode="service_bearer_signed_identity_v1",
        service_token_env="SLAIF_155AJ_MATRIX_SERVICE",
        signing_secret_env="SLAIF_155AJ_MATRIX_SIGNING",
    )
    previous = {
        name: os.environ.get(name)
        for name in ("SLAIF_155AJ_MATRIX_SERVICE", "SLAIF_155AJ_MATRIX_SIGNING")
    }
    os.environ["SLAIF_155AJ_MATRIX_SERVICE"] = service_token
    os.environ["SLAIF_155AJ_MATRIX_SIGNING"] = signing_secret

    def request_for(headers: dict[str, str]) -> Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/responses",
            "raw_path": b"/v1/responses",
            "query_string": b"",
            "headers": [
                (name.lower().encode("ascii"), value.encode("ascii"))
                for name, value in {
                    "authorization": f"Bearer {service_token}",
                    **headers,
                }.items()
            ],
        }
        return Request(scope)

    try:
        for index in LOCAL_MATRIX_INDICES:
            owner_id = uuid.UUID(f"00000000-0000-4000-8000-{index:012d}")
            gateway_key_id = uuid.UUID(f"10000000-0000-4000-8000-{index:012d}")
            session = f"20000000-0000-4000-8000-{index:012d}"
            identity = derive_request_identity(
                owner_id=owner_id,
                gateway_key_id=gateway_key_id,
                identity_hints={"session_id": session},
                repository_scope=f"repo-{index}",
                route=route,
                derivation_secret=signing_secret.encode("ascii"),
            )
            if identity is None:
                raise VerificationError("local_signed_identity_matrix_derivation")
            if index in LOCAL_LEGACY_PUNCTUATION_ROWS:
                legacy_owner = str(owner_id)
                legacy_principal = base64.urlsafe_b64encode(
                    hmac.new(
                        signing_secret.encode("ascii"),
                        f"slaif-local-coding:principal:v1\n{legacy_owner}".encode("ascii"),
                        hashlib.sha256,
                    ).digest()
                ).decode("ascii").rstrip("=")
                legacy_session = base64.urlsafe_b64encode(
                    hmac.new(
                        signing_secret.encode("ascii"),
                        (
                            "slaif-local-coding:session:v2\n"
                            f"{legacy_principal}\n{gateway_key_id}\n{session}"
                        ).encode("ascii"),
                        hashlib.sha256,
                    ).digest()
                ).decode("ascii").rstrip("=")
                legacy_value = (
                    legacy_principal
                    if index in {6, 26}
                    else legacy_session
                )
                if not legacy_value.startswith(LOCAL_LEGACY_PUNCTUATION_ROWS[index]):
                    raise VerificationError("local_signed_identity_matrix_legacy_vector")
            body = json.dumps(
                {"model": CODEX_MODEL, "input": [{"type": "message"}]},
                separators=(",", ":"),
            ).encode("ascii")
            headers = sign_identity(
                signing_secret=signing_secret.encode("ascii"),
                identity=identity,
                body=body,
                route=route,
                timestamp="1700000000",
                nonce=f"nonce-{index:08d}-abcdef",
            )
            replay = ReplayProtector(ttl_seconds=120, max_entries=32)
            returned = verify_signed_identity(
                request_for(headers), body, config, replay, now=1700000000
            )
            if (
                returned.principal != identity.principal
                or returned.session != identity.session
                or returned.repository != identity.repository
                or returned.route != identity.route
            ):
                raise VerificationError("local_signed_identity_matrix_relation")
            tampered_body = body + b" "
            try:
                verify_signed_identity(
                    request_for(headers), tampered_body, config,
                    ReplayProtector(ttl_seconds=120, max_entries=32), now=1700000000,
                )
            except SignedIdentityError as exc:
                if exc.code != "signed_identity_signature_mismatch":
                    raise VerificationError("local_signed_identity_matrix_body_tamper") from None
            else:
                raise VerificationError("local_signed_identity_matrix_body_tamper")
            altered_headers = dict(headers)
            signature = altered_headers["X-SLAIF-Signature"]
            altered_headers["X-SLAIF-Signature"] = signature[:-1] + (
                "0" if signature[-1] != "0" else "1"
            )
            try:
                verify_signed_identity(
                    request_for(altered_headers), body, config,
                    ReplayProtector(ttl_seconds=120, max_entries=32), now=1700000000,
                )
            except SignedIdentityError as exc:
                if exc.code != "signed_identity_signature_mismatch":
                    raise VerificationError("local_signed_identity_matrix_signature_tamper") from None
            else:
                raise VerificationError("local_signed_identity_matrix_signature_tamper")
            try:
                verify_signed_identity(
                    request_for(headers), body, config, replay, now=1700000000
                )
            except SignedIdentityError as exc:
                if exc.code != "signed_identity_replayed":
                    raise VerificationError("local_signed_identity_matrix_replay") from None
            else:
                raise VerificationError("local_signed_identity_matrix_replay")
    except VerificationError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise VerificationError("local_signed_identity_matrix_failed") from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _verify_fixtures() -> None:
    import scripts.capture_codex_protocol as capture

    if hashlib.sha256(HISTORICAL_FIXTURE.read_bytes()).hexdigest() != HISTORICAL_FIXTURE_SHA256:
        raise VerificationError("historical_fixture_changed")
    if hashlib.sha256(V2_FIXTURE.read_bytes()).hexdigest() != V2_FIXTURE_SHA256:
        raise VerificationError("structural_fixture_changed")
    fixture = json.loads(SESSION_FIXTURE.read_bytes())
    capture.validate_0149_session_fixture(fixture)
    if hashlib.sha256(capture.canonical_json_bytes(fixture)).hexdigest() != CODEX_FIXTURE_SHA256:
        raise VerificationError("session_fixture_digest_mismatch")
    if fixture["relationships"]["selected_source"]["canonical_key"] != "session_id":
        raise VerificationError("session_source_mismatch")
    if fixture["relationships"]["same_session_stability"] is not True or fixture["relationships"]["cross_session_isolation"] is not True:
        raise VerificationError("session_relationship_missing")


def _read_pinned_direct_baseline() -> dict[str, object]:
    try:
        lines = DIRECT_BASELINE_REPORT.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError("pinned_direct_baseline_unavailable") from exc
    boundary_lines = [line for line in lines if line.startswith("STREAM_BOUNDARY ")]
    direct_lines = [line for line in boundary_lines if '"boundary":"direct_qwen"' in line]
    if len(boundary_lines) != 3 or len(direct_lines) != 1:
        raise VerificationError("pinned_direct_baseline_shape")
    try:
        baseline = json.loads(direct_lines[0][len("STREAM_BOUNDARY ") :])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("pinned_direct_baseline_invalid") from exc
    expected = {
        "boundary": "direct_qwen",
        "completed_output_empty": False,
        "completed_status_completed": True,
        "completed_usage_valid": True,
        "content_type_class": "sse",
        "created_status_in_progress": True,
        "decision": "ambiguous_stream_evidence",
        "done_sentinel": False,
        "downstream_closed_early": False,
        "duplicates": False,
        "event_counts": {
            "other": 1259,
            "response.completed": 1,
            "response.created": 1,
            "response.in_progress": 1,
            "response.output_text.delta": 386,
        },
        "event_trace": [
            {"count": 1, "event": "response.created"},
            {"count": 1, "event": "response.in_progress"},
            {"count": 1256, "event": "other"},
            {"count": 386, "event": "response.output_text.delta"},
            {"count": 3, "event": "other"},
            {"count": 1, "event": "response.completed"},
        ],
        "event_trace_overflow": False,
        "failure_code": "none",
        "first_event_before_upstream_completion": True,
        "handler_error": False,
        "http_status_class": "2xx",
        "invalid": False,
        "model_matches": True,
        "normal_close": True,
        "normalization_reason": "none",
        "normalization_status": "complete",
        "official_client_completion": True,
        "ran": True,
        "response_completed": True,
        "response_id_relation": True,
        "terminal_output_shape": "nonempty_array",
        "unknown_events": True,
        "upstream_truncated": False,
        "valid_completion": False,
    }
    if baseline != expected:
        raise VerificationError("pinned_direct_baseline_mismatch")
    normalized = dict(baseline)
    normalized.update(
        {
            "error_event": False,
            "error_field_names": [],
            "error_code_class": "unknown",
            "error_type_class": "unknown",
            "event_vocabulary_reviewed": False,
            "terminal_completion_valid": True,
            "evidence_source": "pinned_155l",
            "ran_current_invocation": False,
        }
    )
    if not _terminal_completion_valid(normalized):
        raise VerificationError("pinned_direct_terminal_invalid")
    if normalized["event_vocabulary_reviewed"] is not False:
        raise VerificationError("pinned_direct_vocabulary_invalid")
    return normalized


def _verify_protected_model_health(runtime: RuntimeReference) -> None:
    probe = (
        "import json, os, urllib.request; "
        "url=os.environ['SLAIF_155F_QWEN_BASE_URL'].rstrip('/')+'/models'; "
        "request=urllib.request.Request(url, headers={'Authorization': 'Bearer '+os.environ['QWEN3090_API_KEY']}); "
        "response=urllib.request.urlopen(request, timeout=20); "
        "payload=json.load(response); "
        "data=payload.get('data') if isinstance(payload, dict) else None; "
        f"raise SystemExit(0 if response.status == 200 and isinstance(data, list) and any(isinstance(item, dict) and item.get('id') == {CODEX_MODEL!r} for item in data) else 1)"
    )
    script = (
        "set +x; . \"$SLAIF_155F_CREDENTIAL_SOURCE\" >/dev/null 2>&1; "
        "test -n \"${QWEN3090_API_KEY:-}\"; "
        "exec /usr/bin/env -i PATH=\"${PATH:-/usr/bin:/bin}\" "
        "SLAIF_155F_QWEN_BASE_URL=\"${SLAIF_155F_QWEN_BASE_URL}\" "
        "QWEN3090_API_KEY=\"${QWEN3090_API_KEY}\" "
        "python3 -c \"$SLAIF_155F_PROBE\""
    )
    result = _run(
        ["bash", "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "SLAIF_155F_CREDENTIAL_SOURCE": str(runtime.credential_source),
            "SLAIF_155F_QWEN_BASE_URL": runtime.endpoint,
            "SLAIF_155F_PROBE": probe,
        },
        timeout=30,
    )
    if result.returncode != 0:
        raise VerificationError("protected_model_mismatch")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _install_codex(root: Path) -> Path:
    install = root / "codex-install"
    install.mkdir(mode=0o700)
    result = _run(["npm", "init", "-y"], cwd=install, timeout=30)
    if result.returncode != 0:
        raise VerificationError("codex_install_failed")
    result = _run(
        ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", CODEX_PACKAGE_SPEC],
        cwd=install,
        timeout=180,
    )
    if result.returncode != 0:
        raise VerificationError("codex_install_failed")
    binary = install / "node_modules/.bin/codex"
    result = _run([str(binary), "--version"], timeout=10)
    if result.returncode != 0 or result.stdout != f"codex-cli {CODEX_VERSION}\n".encode("ascii"):
        raise VerificationError("codex_version_mismatch")
    return binary


def _docker_prefix() -> tuple[str, ...]:
    direct = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    if direct.returncode == 0:
        return ("docker",)
    sudoed = _run(
        ["sudo", "-n", "docker", "info", "--format", "{{.ServerVersion}}"], timeout=15
    )
    if sudoed.returncode == 0:
        return ("sudo", "-n", "docker")
    raise VerificationError("docker_boundary_unavailable")


def _docker(*args: str, timeout: float = 180) -> subprocess.CompletedProcess[bytes]:
    return _run([*_docker_prefix(), *args], timeout=timeout)


def _start_postgres(
    root: Path, *, tracker: StageTracker | None = None
) -> tuple[str, str, bool]:
    if tracker is not None:
        tracker.set("postgres_image")
    image = "postgres:16"
    image_before = _docker("image", "inspect", image).returncode == 0
    if not image_before and _docker("pull", image).returncode != 0:
        raise VerificationError("postgres_image_unavailable")
    name = f"slaif-155aj-postgres-{os.getpid()}"
    _docker("rm", "-f", name, timeout=30)
    started = False
    try:
        if tracker is not None:
            tracker.set("postgres_start")
        result = _docker(
            "run",
            "-d",
            "--name",
            name,
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            "POSTGRES_PASSWORD=slaif-155f-db",
            "-e",
            f"POSTGRES_DB={TASK_DB}",
            "-p",
            "127.0.0.1::5432",
            image,
            timeout=60,
        )
        if result.returncode != 0:
            raise VerificationError("postgres_start_failed")
        started = True
        port_result = _docker("port", name, "5432/tcp", timeout=30)
        if port_result.returncode != 0:
            raise VerificationError("postgres_port_failed")
        try:
            port_text = port_result.stdout.decode("ascii")
            port = int(port_text.rsplit(":", 1)[1].strip())
        except (UnicodeDecodeError, ValueError, IndexError) as exc:
            raise VerificationError("postgres_port_failed") from exc
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = _docker(
                "exec", name, "pg_isready", "-U", "postgres", "-d", TASK_DB, timeout=10
            )
            if ready.returncode == 0:
                database = _docker(
                    "exec",
                    name,
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    TASK_DB,
                    "-Atqc",
                    "select current_database()",
                    timeout=10,
                )
                if database.returncode != 0 or database.stdout.strip() != TASK_DB.encode("ascii"):
                    raise VerificationError("postgres_named_database_missing")
                return (
                    f"postgresql+asyncpg://postgres:slaif-155f-db@127.0.0.1:{port}/{TASK_DB}",
                    name,
                    not image_before,
                )
            time.sleep(1)
        raise VerificationError("postgres_ready_timeout")
    except Exception:
        if started:
            _docker("rm", "-f", name, timeout=30)
        raise


async def _seed_database(
    database_url: str,
    *,
    relay_port: int,
    failure_port: int,
    differential: bool = False,
    tool_roundtrip_only: bool = False,
) -> tuple[SeededKey, ...]:
    sys.path.insert(0, str(REPO_ROOT / "app"))
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.config import Settings
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService
    from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        async with sessions() as session:
            suffix = secrets.token_hex(8)
            institution = await InstitutionsRepository(session).create_institution(name=f"155f-{suffix}", country="SI")
            owner = await OwnersRepository(session).create_owner(name="Verifier", surname="155f", email=f"155f-{suffix}@example.invalid", institution_id=institution.id)
            cohort = await CohortsRepository(session).create_cohort(name=f"155f-{suffix}", description="disposable", starts_at=now - timedelta(minutes=1), ends_at=now + timedelta(hours=1))
            provider_configs = ProviderConfigsRepository(session)
            await provider_configs.create_provider_config(
                provider="local-coding",
                display_name="155f local",
                base_url=f"http://127.0.0.1:{relay_port}/v1",
                api_key_env_var=SERVICE_TOKEN_ENV,
                enabled=True,
                timeout_seconds=300,
                max_retries=0,
            )
            if not tool_roundtrip_only:
                await provider_configs.create_provider_config(
                    provider="synthetic-failure",
                    display_name="155f failure",
                    base_url=f"http://127.0.0.1:{failure_port}/v1",
                    api_key_env_var="SLAIF_155F_FAILURE_KEY",
                    enabled=True,
                    timeout_seconds=10,
                    max_retries=0,
                )
            capabilities = default_responses_capabilities()
            capabilities.update(
                {
                    "streaming": True,
                    "tools": True,
                    "function_tools": True,
                    "custom_tools": True,
                    "image_input": True,
                    "codex_request_envelope": True,
                    "codex_client_tools": True,
                    "codex_streaming_tool_events": True,
                }
            )
            await ModelRoutesRepository(session).create_model_route(
                requested_model=CODEX_MODEL,
                provider="local-coding",
                upstream_model=CODEX_MODEL,
                match_type="exact",
                endpoint="/v1/responses",
                priority=1,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={
                    "responses": capabilities,
                    "local_coding": {
                        "contract_version": "local-coding-v1",
                        "route_name": "qwen38-vision-codex",
                        "tool_policy_version": "responses-tool-policy-v1",
                        "identity_mode": "signed_identity_v1",
                        "replay_mode": "process_local_ttl_lru",
                        "deployment_mode": "single_worker",
                    },
                },
            )
            if not tool_roundtrip_only:
                failure_capabilities = default_responses_capabilities()
                await ModelRoutesRepository(session).create_model_route(
                    requested_model=FAILURE_MODEL,
                    provider="synthetic-failure",
                    upstream_model=FAILURE_MODEL,
                    match_type="exact",
                    endpoint="/v1/responses",
                    priority=1,
                    visible_in_models=False,
                    supports_streaming=False,
                    capabilities={"responses": failure_capabilities},
                )
            pricing = PricingRulesRepository(session)
            pricing_rows = [("local-coding", CODEX_MODEL)]
            if not tool_roundtrip_only:
                pricing_rows.append(("synthetic-failure", FAILURE_MODEL))
            for provider, model in pricing_rows:
                await pricing.create_pricing_rule(
                    provider=provider,
                    upstream_model=model,
                    endpoint="/v1/responses",
                    valid_from=now - timedelta(minutes=1),
                    currency="EUR",
                    input_price_per_1m=Decimal("1"),
                    output_price_per_1m=Decimal("1"),
                    request_price=Decimal("0"),
                )
            service = KeyService(settings=Settings(), gateway_keys_repository=GatewayKeysRepository(session), one_time_secrets_repository=OneTimeSecretsRepository(session), audit_repository=AuditRepository(session), model_routes_repository=ModelRoutesRepository(session))
            policy = {"version": 1, "local_coding_repository_scope": "155f-repository", "allowed_capabilities": ["codex_request_envelope", "codex_client_tools", "codex_streaming_tool_events"], "client_module": {"id": CODEX_MODULE_ID, "version": CODEX_MODULE_VERSION, "fixture_sha256": CODEX_FIXTURE_SHA256}}
            key_input = dict(owner_id=owner.id, cohort_id=cohort.id, valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1), cost_limit_eur=Decimal("20"), token_limit_total=2_000_000, request_limit_total=50, allowed_models=[CODEX_MODEL] if tool_roundtrip_only else [CODEX_MODEL, FAILURE_MODEL], allowed_endpoints=["/v1/models", "/v1/responses"], responses_policy=policy)
            created = await service.create_gateway_key(CreateGatewayKeyInput(**key_input, note="155f disposable key"))
            if differential:
                await session.commit()
                return (SeededKey(created.gateway_key_id, created.owner_id, created.plaintext_key),)
            second_input = dict(key_input)
            second_input["request_limit_total"] = 1
            second = await service.create_gateway_key(CreateGatewayKeyInput(**second_input, note="155f disposable second key"))
            failure_key_input = dict(
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(minutes=1),
                valid_until=now + timedelta(hours=1),
                cost_limit_eur=Decimal("20"),
                token_limit_total=2_000_000,
                request_limit_total=5,
                allowed_models=[FAILURE_MODEL],
                allowed_endpoints=["/v1/responses"],
            )
            failure_key = await service.create_gateway_key(
                CreateGatewayKeyInput(**failure_key_input, note="155f disposable failure key")
            )
            await session.commit()
            return (
                SeededKey(created.gateway_key_id, created.owner_id, created.plaintext_key),
                SeededKey(second.gateway_key_id, second.owner_id, second.plaintext_key),
                SeededKey(
                    failure_key.gateway_key_id,
                    failure_key.owner_id,
                    failure_key.plaintext_key,
                ),
            )
    except Exception as exc:
        raise VerificationError("database_seed_failed") from exc
    finally:
        await engine.dispose()


def _gateway_environment(
    database_url: str,
    *,
    gateway_port: int,
    service_token: str,
    signing_secret: str,
    derivation_secret: str,
    encryption_key: str,
) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(REPO_ROOT / "app"), "PYTHONDONTWRITEBYTECODE": "1", "APP_ENV": "test", "DATABASE_URL": database_url, "GATEWAY_KEY_PREFIX": "sk-slaif-", "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-", "ACTIVE_HMAC_KEY_VERSION": "1", "TOKEN_HMAC_SECRET_V1": "155f-gateway-hmac-secret-012345678901", "ADMIN_SESSION_SECRET": "155f-admin-secret-012345678901", "ONE_TIME_SECRET_ENCRYPTION_KEY": encryption_key, "ENABLE_REDIS_RATE_LIMITS": "false", "ENABLE_ADMIN_DASHBOARD": "false", "ENABLE_EMAIL_DELIVERY": "false", "ENABLE_METRICS": "true", "LOG_LEVEL": "WARNING", "STRUCTURED_LOGS": "true", "SLAIF_155F_LOCAL_SERVICE_TOKEN": service_token, "LOCAL_CODING_SERVICE_TOKEN": service_token, "LOCAL_CODING_SIGNING_SECRET_V1": signing_secret, "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1": derivation_secret, "SLAIF_155F_FAILURE_KEY": "synthetic-failure-key", "UVICORN_ACCESS_LOG": "false", "APP_BASE_URL": f"http://127.0.0.1:{gateway_port}"}
    return env


def _local_config(
    root: Path, *, local_port: int, qwen_relay_port: int, qwen_relay_token: str
) -> Path:
    config = root / "local-coding.toml"
    body = f'''[server]\nlisten_host = "127.0.0.1"\nlisten_port = {local_port}\n\n[gateway_ingress]\nmode = "service_bearer_signed_identity_v1"\nservice_token_env = "{SERVICE_TOKEN_ENV}"\nsigning_secret_env = "{SIGNING_SECRET_ENV}"\n\n[upstream]\nbase_url = "__SLAIF_155F_QWEN_ENDPOINT__"\napi_key_env = "{QWEN_TOKEN_ENV}"\nmodel = "{CODEX_MODEL}"\nconnect_timeout_seconds = 10\nrequest_timeout_seconds = 300\nwrite_timeout_seconds = 30\npool_timeout_seconds = 10\n\n[compiler]\nenabled = true\napi_key_env = "{QWEN_TOKEN_ENV}"\n\n[cache]\nbackend = "filesystem"\nroot = "{(root / "cache").as_posix()}"\nfallback_root = "{(root / "cache-fallback").as_posix()}"\n\n[constitution]\nenabled = true\nidentity_source = "signed_request"\n\n[observation]\n\n[[routes]]\nname = "qwen38-vision-codex"\nmodel = "{CODEX_MODEL}"\nmax_images_per_request = 1\nimage_overflow_policy = "retain_newest"\nresponses_tool_policy = "drop_disabled_codex_search"\nobservation_enabled = true\nconstitution_enabled = true\n'''
    body = body.replace(
        "__SLAIF_155F_QWEN_ENDPOINT__", f"http://127.0.0.1:{qwen_relay_port}/v1"
    ).replace(QWEN_TOKEN_ENV, QWEN_RELAY_TOKEN_ENV)
    result = _run(
        ["/usr/bin/tee", str(config)],
        env={"PATH": "/usr/bin:/bin"},
        input_bytes=body.encode("utf-8"),
        timeout=10,
    )
    if result.returncode != 0:
        raise VerificationError("local_config_write_failed")
    config.chmod(0o600)
    if not qwen_relay_token:
        raise VerificationError("qwen_relay_token_missing")
    return config


def _validate_local_config(root: Path, runtime: RuntimeReference | None) -> Path:
    del runtime
    config = _local_config(
        root,
        local_port=18031,
        qwen_relay_port=39149,
        qwen_relay_token="synthetic-qwen-relay-token",
    )
    sys.path.insert(0, str(LOCAL_ROOT / "src"))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        from slaif_local_coding.config import load_settings

        settings = load_settings(config)
    except Exception as exc:
        raise VerificationError("local_config_invalid") from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    if (
        settings.server.listen_host != "127.0.0.1"
        or settings.server.listen_port != 18031
        or settings.upstream.model != CODEX_MODEL
        or settings.upstream.api_key_env != QWEN_RELAY_TOKEN_ENV
        or settings.compiler.api_key_env != QWEN_RELAY_TOKEN_ENV
        or settings.upstream.base_url.startswith("http://127.0.0.1:") is False
        or settings.gateway_ingress.mode != "service_bearer_signed_identity_v1"
        or settings.routes[0].responses_tool_policy != "drop_disabled_codex_search"
    ):
        raise VerificationError("local_config_policy_mismatch")
    return config


def _qualification_name(value: object, *, event: bool = False) -> str:
    if value == "other":
        return "other"
    if not isinstance(value, str):
        raise VerificationError("qualification_artifact_invalid")
    pattern = QUALIFICATION_EVENT_RE if event else QUALIFICATION_NAME_RE
    if pattern.fullmatch(value) is None:
        raise VerificationError("qualification_artifact_invalid")
    return value


def _sanitize_qualification_fields(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > QUALIFICATION_MAX_FIELDS:
        raise VerificationError("qualification_artifact_invalid")
    fields: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "type"}:
            raise VerificationError("qualification_artifact_invalid")
        name = _qualification_name(item["name"])
        field_type = item["type"]
        if not isinstance(field_type, str) or field_type not in QUALIFICATION_FIELD_TYPES:
            raise VerificationError("qualification_artifact_invalid")
        fields.append({"name": name, "type": field_type})
    if fields != sorted(fields, key=lambda item: item["name"]):
        raise VerificationError("qualification_artifact_invalid")
    if len({item["name"] for item in fields}) != len(fields):
        raise VerificationError("qualification_artifact_invalid")
    return fields


def _sanitize_qualification_rejection(value: object) -> dict[str, object]:
    required = {
        "schema", "event_type", "top_level_fields", "nested_object_fields",
        "validator_profile", "rejection",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise VerificationError("qualification_artifact_invalid")
    if value["schema"] != "responses_stream_rejection_v1":
        raise VerificationError("qualification_artifact_invalid")
    nested_value = value["nested_object_fields"]
    if not isinstance(nested_value, list) or len(nested_value) > QUALIFICATION_MAX_FIELDS:
        raise VerificationError("qualification_artifact_invalid")
    nested: list[dict[str, object]] = []
    for item in nested_value:
        if not isinstance(item, dict) or set(item) != {"name", "fields"}:
            raise VerificationError("qualification_artifact_invalid")
        nested.append(
            {
                "name": _qualification_name(item["name"]),
                "fields": _sanitize_qualification_fields(item["fields"]),
            }
        )
    if nested != sorted(nested, key=lambda item: item["name"]):
        raise VerificationError("qualification_artifact_invalid")
    if len({item["name"] for item in nested}) != len(nested):
        raise VerificationError("qualification_artifact_invalid")
    profile = value["validator_profile"]
    profile_keys = {
        "codex_reasoning_events", "codex_0149_function_tool_events",
        "codex_streaming_tool_events", "codex_encrypted_reasoning_replay", "web_search",
        "declared_client_tools_class", "web_search_max_tool_calls_class",
    }
    if not isinstance(profile, dict) or set(profile) != profile_keys:
        raise VerificationError("qualification_artifact_invalid")
    if any(
        type(profile[name]) is not bool
        for name in (
            "codex_reasoning_events",
            "codex_0149_function_tool_events",
            "codex_streaming_tool_events",
            "codex_encrypted_reasoning_replay",
            "web_search",
        )
    ):
        raise VerificationError("qualification_artifact_invalid")
    if profile["declared_client_tools_class"] not in QUALIFICATION_DECLARED_TOOL_CLASSES:
        raise VerificationError("qualification_artifact_invalid")
    if profile["web_search_max_tool_calls_class"] not in QUALIFICATION_WEB_SEARCH_CLASSES:
        raise VerificationError("qualification_artifact_invalid")
    rejection = value["rejection"]
    if not isinstance(rejection, dict) or set(rejection) != {"outcome", "code"}:
        raise VerificationError("qualification_artifact_invalid")
    if rejection["outcome"] != "validator_rejected" or rejection["code"] not in {
        "responses_stream_event_not_supported",
        "responses_stream_provider_failure",
        "other",
    }:
        raise VerificationError("qualification_artifact_invalid")
    return {
        "schema": "responses_stream_rejection_v1",
        "event_type": _qualification_name(value["event_type"], event=True),
        "top_level_fields": _sanitize_qualification_fields(value["top_level_fields"]),
        "nested_object_fields": nested,
        "validator_profile": {
            name: profile[name]
            for name in (
                "codex_reasoning_events",
                "codex_0149_function_tool_events",
                "codex_streaming_tool_events",
                "codex_encrypted_reasoning_replay",
                "web_search",
                "declared_client_tools_class",
                "web_search_max_tool_calls_class",
            )
        },
        "rejection": {"outcome": "validator_rejected", "code": rejection["code"]},
    }


def _read_qualification_rejection(root: Path) -> dict[str, object] | None:
    artifact = root / QUALIFICATION_ARTIFACT_NAME
    try:
        artifact_stat = artifact.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise VerificationError("qualification_artifact_invalid") from exc
    if (
        not stat.S_ISREG(artifact_stat.st_mode)
        or stat.S_IMODE(artifact_stat.st_mode) != 0o600
        or artifact_stat.st_uid != os.getuid()
    ):
        raise VerificationError("qualification_artifact_invalid")
    try:
        payload = artifact.read_bytes()
        if len(payload) > QUALIFICATION_MAX_BYTES:
            raise VerificationError("qualification_artifact_too_large")
        value = json.loads(payload)
    except VerificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("qualification_artifact_invalid") from exc
    return _sanitize_qualification_rejection(value)


def _write_qualification_rejection(
    root: Path,
    *,
    profile: dict[str, object],
    event_type: str,
    top_level_fields: list[dict[str, str]],
    nested_object_fields: list[dict[str, object]],
    rejection_code: str,
) -> dict[str, object]:
    """Write verifier-owned fake evidence; production never receives this path."""
    _validate_task_summary_root(root)
    safe = _sanitize_qualification_rejection(
        {
            "schema": "responses_stream_rejection_v1",
            "event_type": event_type,
            "top_level_fields": top_level_fields,
            "nested_object_fields": nested_object_fields,
            "validator_profile": profile,
            "rejection": {"outcome": "validator_rejected", "code": rejection_code},
        }
    )
    payload = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    if len(payload) > QUALIFICATION_MAX_BYTES:
        raise VerificationError("qualification_artifact_too_large")
    artifact = root / QUALIFICATION_ARTIFACT_NAME
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(artifact, flags, 0o600)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("short qualification artifact write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(artifact, 0o600, follow_symlinks=False)
        directory_descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except FileExistsError as exc:
        raise VerificationError("qualification_artifact_overwrite") from exc
    except (OSError, ValueError) as exc:
        raise VerificationError("qualification_artifact_write_failed") from exc
    return safe


def _assert_fake_qualification_artifact_absent(root: Path) -> None:
    if _read_qualification_rejection(root) is not None:
        raise VerificationError("fake_rejection_artifact_present")


def _retain_sanitized_qualification_rejection(
    result: dict[str, object], reread: dict[str, object] | None
) -> dict[str, object]:
    """Keep the inner sanitized result authoritative across temp-root cleanup."""
    retained = result.get("qualification_rejection")
    if retained is not None:
        retained = _sanitize_qualification_rejection(retained)
        if reread is not None and reread != retained:
            raise VerificationError("qualification_evidence_inconsistent")
    else:
        retained = reread
    result["qualification_rejection"] = retained
    return result


_SUMMARY_SCHEMA = "qualification_preclassification_v1"
_SUMMARY_STAGES = frozenset(COMPOSITION_STAGES)
_SUMMARY_FAILURE_CATEGORIES = frozenset(
    {
        "configuration_rejected",
        "argument_rejected",
        "argument_separator_rejected",
        "argument_or_configuration_rejected",
        "dummy_auth_environment_rejected",
        "workdir_rejected",
        "custom_provider_auth_rejected",
        "loopback_connection_failed",
        "loopback_request_failed",
        "web_search_config_rejected",
        "app_server_channel_closed",
        "mock_stream_rejected",
        "mock_stream_closed_early",
        "mock_stream_idle_timeout",
        "mock_completed_event_rejected",
        "mock_response_failed",
        "mock_http_status_rejected",
        "incomplete_event_sequence",
        "turn_failed",
        "error_event",
        "nonzero_after_turn_completed",
        "unclassified",
        "other",
    }
)

_BOUNDARY_COUNT_CLASSES = frozenset({"0", "1", "2", "other"})
_BOUNDARY_STATUS_CLASSES = frozenset({"1xx", "2xx", "3xx", "4xx", "5xx", "other"})
_BOUNDARY_CONTENT_CLASSES = frozenset({"sse", "json", "other", "none"})
_BOUNDARY_TERMINAL_SHAPES = frozenset({"empty_array", "nonempty_array", "missing", "other"})
_BOUNDARY_USAGE_SHAPES = frozenset({"valid", "missing", "invalid", "other"})
_BOUNDARY_STATES = frozenset(
    {"not_reached", "entered", "transformed", "rejected", "succeeded", "unknown"}
)
_BOUNDARY_EVENT_CLASSES = frozenset(
    {
        "response.created",
        "response.in_progress",
        "response.reasoning_part.added",
        "response.reasoning_text.delta",
        "response.reasoning_text.done",
        "response.reasoning_part.done",
        "response.completed",
        "response.output_item.added",
        "response.output_item.done",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.delta",
        "response.output_text.done",
        "error",
        "other",
    }
)
_SUMMARY_STATUS_CLASSES = frozenset({"1xx", "2xx", "3xx", "4xx", "5xx", "other"})
_SUMMARY_CONTENT_TYPES = frozenset({"sse", "json", "other", "none"})
_SUMMARY_GATEWAY_ERROR_CODE_CLASSES = frozenset(
    {
        "none",
        "input_tool_item_not_supported",
        "codex_tool_roundtrip_invalid",
        "replay_reference_not_found",
        "replay_route_mismatch",
        "route_capability_not_supported",
        "request_policy_invalid",
        "encrypted_reasoning_replay_not_allowed",
        "reasoning_visible_invalid",
        "reasoning_visible_too_large",
        "other",
    }
)
_SUMMARY_GATEWAY_ERROR_PARAM_CLASSES = frozenset(
    {"none", "input", "stream", "tools", "tool_choice", "other"}
)
_SUMMARY_GATEWAY_ERROR_PARAM_FIELDS = frozenset(
    {
        "none",
        "type",
        "id",
        "status",
        "name",
        "namespace",
        "arguments",
        "call_id",
        "output",
        "input",
        "tools",
        "tool_choice",
        "stream",
        "other",
    }
)
_SUMMARY_LOCAL_ERROR_CODE_CLASSES = _LOCAL_ERROR_CODE_CLASSES
_SUMMARY_LOCAL_REJECTION_STAGES = _LOCAL_REJECTION_STAGES
_SUMMARY_LOCAL_BOUNDARY_STATES = _LOCAL_BOUNDARY_STATES
_SUMMARY_TOOL_CHOICE_CLASSES = _LOCAL_TOOL_CHOICE_CLASSES
_SUMMARY_TOOL_TYPES = frozenset(
    {"function", "custom", "namespace", "tool_search", "web_search", "other"}
)
_SUMMARY_INPUT_TYPES = frozenset(
    {
        "message",
        "reasoning",
        "additional_tools",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "other",
    }
)
_SUMMARY_FIELD_TYPES = frozenset(
    {"null", "boolean", "integer", "number", "string", "object", "array", "other"}
)
_SUMMARY_FUNCTION_FIELDS = frozenset(
    {
        "type",
        "id",
        "status",
        "name",
        "namespace",
        "arguments",
        "call_id",
        "output",
        "caller",
        "output_index",
        "sequence_number",
        "other",
    }
)
_SUMMARY_BOOL_KEYS = frozenset(
    {
        "disconnect",
        "truncated",
        "handler_error",
        "path_error",
        "normal_close",
        "zero_pending",
        "query_ok",
        "artifact_present",
        "artifact_equal",
        "artifact_digest_present",
    }
)
_SUMMARY_COUNT_KEYS = frozenset(
    {
        "request_count",
        "response_count",
        "inference_count",
        "row_count",
        "reservation_finalized",
        "reservation_released",
        "reservation_pending",
        "ledger_finalized",
        "ledger_failed",
        "ledger_estimated",
        "ledger_pending",
    }
)
_SUMMARY_BOUNDARIES = frozenset({"gateway", "local", "qwen", "accounting"})


def _safe_summary_count(value: object) -> str:
    if type(value) is int and 0 <= value <= 2:
        return str(value)
    return "other"


def _safe_summary_status_classes(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:8]:
        if type(item) is int and 100 <= item <= 599:
            result.append(f"{item // 100}xx")
        else:
            result.append("other")
    return result


def _safe_summary_content_classes(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item if item in _SUMMARY_CONTENT_TYPES else "other" for item in value[:8]]


def _safe_summary_error_classes(
    value: object, response_statuses: object, allowed: frozenset[str]
) -> list[str]:
    statuses = response_statuses if isinstance(response_statuses, list) else []
    ordinal_count = len(statuses)
    raw = value if isinstance(value, list) else []
    if len(raw) != ordinal_count:
        if raw:
            raw = ["other"] * ordinal_count
        else:
            raw = [
                "none"
                if type(status) is int and status < 400
                else "other"
                for status in statuses
            ]
    return [
        item if isinstance(item, str) and item in allowed else "other"
        for item in raw[:2]
    ]


def _safe_summary_tool_counts(value: object) -> dict[str, int | str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int | str] = {}
    for tool_type, count in value.items():
        safe_type = (
            tool_type
            if isinstance(tool_type, str) and tool_type in _SUMMARY_TOOL_TYPES
            else "other"
        )
        safe_count = count if type(count) is int and 0 <= count <= 64 else "other"
        result[safe_type] = safe_count
    return result


def _safe_summary_field_types(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value[:32]:
        if not isinstance(item, dict):
            result.append({"name": "other", "type": "other"})
            continue
        name = item.get("name")
        field_type = item.get("type")
        result.append(
            {
                "name": name
                if isinstance(name, str) and name in _SUMMARY_FUNCTION_FIELDS
                else "other",
                "type": field_type
                if isinstance(field_type, str) and field_type in _SUMMARY_FIELD_TYPES
                else "other",
            }
        )
    return sorted(result, key=lambda item: (item["name"], item["type"]))


def _safe_summary_input_item_error_projection(value: object) -> dict[str, object]:
    """Rebuild one input-error observation from a fixed, value-free schema."""
    default = _empty_input_item_error_projection()
    if not isinstance(value, dict):
        return default
    shape = value.get("input_item_error_shape_class")
    default["input_item_error_shape_class"] = (
        shape if isinstance(shape, str) and shape in _SAFE_INPUT_ERROR_SHAPES else "other"
    )
    json_type = value.get("item_json_type_class")
    default["item_json_type_class"] = (
        json_type
        if isinstance(json_type, str) and json_type in _SUMMARY_FIELD_TYPES
        else "other"
    )
    item_type = value.get("item_type_class")
    default["item_type_class"] = (
        item_type
        if isinstance(item_type, str) and item_type in _SAFE_INPUT_ITEM_TYPES
        else "other"
    )
    field_name = value.get("rejected_field_name_class")
    default["rejected_field_name_class"] = (
        field_name
        if isinstance(field_name, str)
        and (field_name in _SAFE_INPUT_ITEM_FIELDS or field_name in {"none", "other"})
        else "other"
    )
    fields = value.get("rejected_item_fields")
    safe_fields: set[tuple[str, str]] = set()
    if isinstance(fields, list):
        for item in fields[:32]:
            if not isinstance(item, dict):
                safe_fields.add(("other", "other"))
                continue
            name = item.get("name")
            field_type = item.get("type")
            safe_fields.add(
                (
                    name if isinstance(name, str) and name in _SAFE_INPUT_ITEM_FIELDS else "other",
                    field_type
                    if isinstance(field_type, str) and field_type in _SUMMARY_FIELD_TYPES
                    else "other",
                )
            )
    default["rejected_item_fields"] = [
        {"name": name, "type": field_type}
        for name, field_type in sorted(safe_fields)
    ][:32]
    for name in (
        "index_syntactically_bounded",
        "index_in_range",
        "selected_item_object",
        "rejected_field_present",
        "reasoning_item_type_is_reasoning",
        "reasoning_unexpected_semantic_fields_present",
        "reasoning_exact_allowed_key_set_match",
        "reasoning_exactly_one_candidate_placeholder",
        "reasoning_placeholder_precedes_function_pair",
        "exact_empty_reasoning_placeholder",
    ):
        default[name] = value.get(name) is True
    for name, allowed in (
        ("reasoning_id_state", _SAFE_REASONING_ID_STATES),
        ("reasoning_content_state", _SAFE_REASONING_ARRAY_STATES),
        ("reasoning_summary_state", _SAFE_REASONING_ARRAY_STATES),
        ("reasoning_encrypted_content_state", _SAFE_REASONING_ENCRYPTED_STATES),
    ):
        candidate = value.get(name)
        default[name] = candidate if isinstance(candidate, str) and candidate in allowed else "other"
    return default


def _safe_summary_input_item_error_projections(
    value: object, response_statuses: object
) -> list[dict[str, object]]:
    statuses = response_statuses if isinstance(response_statuses, list) else []
    projections = value if isinstance(value, list) else []
    if len(projections) != len(statuses):
        projections = [_empty_input_item_error_projection() for _ in statuses]
    return [_safe_summary_input_item_error_projection(item) for item in projections[:2]]


def _safe_summary_bool(value: object) -> bool:
    return value is True


def _safe_summary_section(
    *,
    request_count: object,
    response_statuses: object,
    content_types: object,
    booleans: dict[str, object],
) -> dict[str, object]:
    section: dict[str, object] = {
        "request_count": _safe_summary_count(request_count),
        "response_count": _safe_summary_count(
            len(response_statuses) if isinstance(response_statuses, list) else "other"
        ),
        "status_classes": _safe_summary_status_classes(response_statuses),
        "content_type_classes": _safe_summary_content_classes(content_types),
    }
    for name in sorted(_SUMMARY_BOOL_KEYS & set(booleans)):
        section[name] = _safe_summary_bool(booleans[name])
    return section


def _safe_preclassification_summary(
    *,
    stage: object,
    codex_failure_category: object,
    gateway_requests: object,
    gateway_status: object,
    local_requests: object,
    local_status: object,
    qwen_status: object,
    request_projections: object,
    accounting_statuses: object,
    qualification_rejection: object,
    artifact_equal: object,
    signed_identity_facts: object = None,
) -> dict[str, object]:
    gateway = gateway_status if isinstance(gateway_status, dict) else {}
    local = local_status if isinstance(local_status, dict) else {}
    qwen = qwen_status if isinstance(qwen_status, dict) else {}
    accounting = accounting_statuses if isinstance(accounting_statuses, dict) else {}
    category = (
        codex_failure_category
        if isinstance(codex_failure_category, str)
        and codex_failure_category in _SUMMARY_FAILURE_CATEGORIES
        else "other"
    )
    safe_stage = stage if isinstance(stage, str) and stage in _SUMMARY_STAGES else "other"
    projections = request_projections if isinstance(request_projections, list) else []
    request_profile_classes = [
        _safe_roundtrip_projection_class(projection)
        for projection in projections[:2]
    ]
    accounting_section = {
        "query_ok": accounting.get("query_ok") is True,
        "row_count": _safe_summary_count(
            accounting.get("reservation_finalized", 0)
            + accounting.get("reservation_released", 0)
            if all(
                type(accounting.get(name)) is int
                for name in ("reservation_finalized", "reservation_released")
            )
            else "other"
        ),
    }
    for name in sorted(
        {
            "reservation_finalized",
            "reservation_released",
            "reservation_pending",
            "ledger_finalized",
            "ledger_failed",
            "ledger_estimated",
            "ledger_pending",
        }
    ):
        accounting_section[name] = _safe_summary_count(accounting.get(name, "other"))
    accounting_section["zero_pending"] = all(
        accounting_section[name] == "0"
        for name in ("reservation_pending", "ledger_pending")
    )
    second_projection = projections[1] if len(projections) > 1 else {}
    second_projection = (
        second_projection if isinstance(second_projection, dict) else {}
    )
    first_projection = projections[0] if projections else {}
    first_projection = (
        first_projection if isinstance(first_projection, dict) else {}
    )
    return {
        "schema": _SUMMARY_SCHEMA,
        "stage": safe_stage,
        "codex_failure_category": category,
        "gateway": _safe_summary_section(
            request_count=gateway_requests,
            response_statuses=gateway.get("response_statuses"),
            content_types=gateway.get("response_content_type_classes"),
            booleans={
                "disconnect": gateway.get("downstream_closed_early"),
                "truncated": gateway.get("upstream_truncated"),
                "handler_error": gateway.get("handler_error"),
            },
        ),
        "local": _safe_summary_section(
            request_count=local_requests,
            response_statuses=local.get("response_statuses"),
            content_types=local.get("response_content_type_classes"),
            booleans={
                "disconnect": local.get("downstream_closed_early"),
                "truncated": local.get("upstream_truncated"),
                "handler_error": local.get("handler_error"),
            },
        ),
        "qwen": {
            "inference_count": _safe_summary_count(qwen.get("inference_calls")),
            "compiler_count": _safe_summary_count(qwen.get("compiler_calls")),
            "status_classes": _safe_summary_status_classes(
                qwen.get("inference_statuses")
            ),
            "compiler_status_classes": _safe_summary_status_classes(
                qwen.get("compiler_statuses")
            ),
            "content_type_classes": _safe_summary_content_classes(
                qwen.get("inference_content_type_classes")
            ),
            "compiler_content_type_classes": _safe_summary_content_classes(
                qwen.get("compiler_content_type_classes")
            ),
            "path_error": qwen.get("path_rejections") not in (0, False),
            "normal_close": qwen.get("stream_normal_close") is True,
            "handler_error": qwen.get("handler_error") is True,
            "truncated": qwen.get("upstream_truncated") is True,
        },
        "request_profile_classes": request_profile_classes,
        "first_request_input_item_type_sequence": [
            item
            if isinstance(item, str) and item in _SUMMARY_INPUT_TYPES
            else "other"
            for item in first_projection.get("input_item_type_sequence", [])[:128]
        ]
        if isinstance(first_projection.get("input_item_type_sequence"), list)
        else [],
        "first_request_top_level_tool_type_counts": _safe_summary_tool_counts(
            first_projection.get("top_level_tool_type_counts")
        ),
        "first_request_tool_choice_class": (
            first_projection.get("tool_choice_class")
            if isinstance(first_projection.get("tool_choice_class"), str)
            and first_projection.get("tool_choice_class") in _SUMMARY_TOOL_CHOICE_CLASSES
            else "malformed_other"
        ),
        "gateway_error_code_classes": _safe_summary_error_classes(
            gateway.get("error_code_classes"),
            gateway.get("response_statuses"),
            _SUMMARY_GATEWAY_ERROR_CODE_CLASSES,
        ),
        "gateway_error_param_classes": _safe_summary_error_classes(
            gateway.get("error_param_classes"),
            gateway.get("response_statuses"),
            _SUMMARY_GATEWAY_ERROR_PARAM_CLASSES,
        ),
        "gateway_error_param_field_classes": _safe_summary_error_classes(
            gateway.get("error_param_field_classes"),
            gateway.get("response_statuses"),
            _SUMMARY_GATEWAY_ERROR_PARAM_FIELDS,
        ),
        "gateway_input_item_error_projections": _safe_summary_input_item_error_projections(
            gateway.get("input_item_error_projections"),
            gateway.get("response_statuses"),
        ),
        "local_error_code_classes": _safe_summary_error_classes(
            local.get("local_error_code_classes"),
            local.get("response_statuses"),
            _SUMMARY_LOCAL_ERROR_CODE_CLASSES,
        ),
        "local_error_stage_classes": _safe_local_stage_classes(
            local.get("local_error_stage_classes"),
            local.get("response_statuses"),
        ),
        "local_error_param_classes": _safe_summary_error_classes(
            local.get("error_param_classes"),
            local.get("response_statuses"),
            _SUMMARY_GATEWAY_ERROR_PARAM_CLASSES,
        ),
        "local_error_param_field_classes": _safe_summary_error_classes(
            local.get("error_param_field_classes"),
            local.get("response_statuses"),
            _SUMMARY_GATEWAY_ERROR_PARAM_FIELDS,
        ),
        "local_boundary_states": _safe_local_boundary_states(
            local.get("local_boundary_states")
        ),
        "local_signed_identity_facts": _safe_signed_identity_projections(
            signed_identity_facts,
            local.get("response_statuses"),
        ),
        "second_request_input_item_type_sequence": [
            item
            if isinstance(item, str) and item in _SUMMARY_INPUT_TYPES
            else "other"
            for item in second_projection.get("input_item_type_sequence", [])[:128]
        ]
        if isinstance(second_projection.get("input_item_type_sequence"), list)
        else [],
        "second_request_top_level_tool_type_counts": _safe_summary_tool_counts(
            second_projection.get("top_level_tool_type_counts")
        ),
        "second_function_call_fields": _safe_summary_field_types(
            second_projection.get("function_call_fields")
        ),
        "second_function_call_output_fields": _safe_summary_field_types(
            second_projection.get("function_call_output_fields")
        ),
        "qualification_rejection": {
            "present": isinstance(qualification_rejection, dict),
            "artifact_equal": artifact_equal is True,
            "artifact_digest_present": isinstance(qualification_rejection, dict),
        },
        "accounting": accounting_section,
    }


def _validate_task_summary_root(root: Path) -> None:
    try:
        root_stat = root.lstat()
        common = os.path.commonpath((str(root.resolve()), "/tmp"))
    except (OSError, ValueError) as exc:
        raise VerificationError("qualification_summary_root_invalid") from exc
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_IMODE(root_stat.st_mode) != 0o700
        or root_stat.st_uid != os.getuid()
        or common != "/tmp"
        or root.is_symlink()
    ):
        raise VerificationError("qualification_summary_root_invalid")


def _sanitize_preclassification_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "stage", "codex_failure_category", "gateway", "local", "qwen",
        "request_profile_classes", "gateway_error_code_classes",
        "gateway_error_param_classes", "gateway_error_param_field_classes",
        "gateway_input_item_error_projections",
        "local_error_code_classes", "local_error_param_classes",
        "local_error_param_field_classes", "local_error_stage_classes",
        "local_boundary_states",
        "local_signed_identity_facts",
        "second_request_input_item_type_sequence",
        "second_request_top_level_tool_type_counts", "second_function_call_fields",
        "second_function_call_output_fields", "qualification_rejection", "accounting",
        "first_request_input_item_type_sequence",
        "first_request_top_level_tool_type_counts",
        "first_request_tool_choice_class",
    }:
        raise VerificationError("qualification_summary_invalid")
    if value["schema"] != _SUMMARY_SCHEMA:
        raise VerificationError("qualification_summary_invalid")
    if value["stage"] not in _SUMMARY_STAGES or value["codex_failure_category"] not in _SUMMARY_FAILURE_CATEGORIES:
        raise VerificationError("qualification_summary_invalid")
    request_profile_classes = value["request_profile_classes"]
    if (
        not isinstance(request_profile_classes, list)
        or len(request_profile_classes) > 2
        or any(
            not isinstance(profile, str)
            or profile not in {
                "top_level_function_pair_without_additional_tools",
                "other",
            }
            for profile in request_profile_classes
        )
    ):
        raise VerificationError("qualification_summary_invalid")
    if value["first_request_tool_choice_class"] not in _SUMMARY_TOOL_CHOICE_CLASSES:
        raise VerificationError("qualification_summary_invalid")
    for field, allowed, boundary in (
        (
            "gateway_error_code_classes",
            _SUMMARY_GATEWAY_ERROR_CODE_CLASSES,
            "gateway",
        ),
        (
            "gateway_error_param_classes",
            _SUMMARY_GATEWAY_ERROR_PARAM_CLASSES,
            "gateway",
        ),
        (
            "gateway_error_param_field_classes",
            _SUMMARY_GATEWAY_ERROR_PARAM_FIELDS,
            "gateway",
        ),
        ("local_error_code_classes", _SUMMARY_LOCAL_ERROR_CODE_CLASSES, "local"),
        ("local_error_stage_classes", _SUMMARY_LOCAL_REJECTION_STAGES, "local"),
        ("local_error_param_classes", _SUMMARY_GATEWAY_ERROR_PARAM_CLASSES, "local"),
        (
            "local_error_param_field_classes",
            _SUMMARY_GATEWAY_ERROR_PARAM_FIELDS,
            "local",
        ),
    ):
        classes = value[field]
        if (
            not isinstance(classes, list)
            or len(classes) > 2
            or (
                value[boundary]["response_count"] != "other"
                and value[boundary]["response_count"] != str(len(classes))
            )
            or any(not isinstance(item, str) or item not in allowed for item in classes)
        ):
            raise VerificationError("qualification_summary_invalid")
    input_error_projections = value["gateway_input_item_error_projections"]
    gateway_response_count = value["gateway"]["response_count"]
    if (
        not isinstance(input_error_projections, list)
        or len(input_error_projections) > 2
        or (
            gateway_response_count != "other"
            and gateway_response_count != str(len(input_error_projections))
        )
    ):
        raise VerificationError("qualification_summary_invalid")
    expected_input_error_keys = {
        "input_item_error_shape_class",
        "item_json_type_class",
        "item_type_class",
        "rejected_item_fields",
        "rejected_field_name_class",
        "index_syntactically_bounded",
        "index_in_range",
        "selected_item_object",
        "rejected_field_present",
        "reasoning_item_type_is_reasoning",
        "reasoning_id_state",
        "reasoning_content_state",
        "reasoning_summary_state",
        "reasoning_encrypted_content_state",
        "reasoning_unexpected_semantic_fields_present",
        "reasoning_exact_allowed_key_set_match",
        "reasoning_exactly_one_candidate_placeholder",
        "reasoning_placeholder_precedes_function_pair",
        "exact_empty_reasoning_placeholder",
    }
    for projection in input_error_projections:
        if not isinstance(projection, dict) or set(projection) != expected_input_error_keys:
            raise VerificationError("qualification_summary_invalid")
        if (
            projection["input_item_error_shape_class"] not in _SAFE_INPUT_ERROR_SHAPES
            or projection["item_json_type_class"] not in _SUMMARY_FIELD_TYPES
            or projection["item_type_class"] not in _SAFE_INPUT_ITEM_TYPES
            or projection["rejected_field_name_class"] not in _SAFE_INPUT_ITEM_FIELDS
            | {"none", "other"}
            or projection["reasoning_id_state"] not in _SAFE_REASONING_ID_STATES
            or projection["reasoning_content_state"] not in _SAFE_REASONING_ARRAY_STATES
            or projection["reasoning_summary_state"] not in _SAFE_REASONING_ARRAY_STATES
            or projection["reasoning_encrypted_content_state"] not in _SAFE_REASONING_ENCRYPTED_STATES
            or any(
                type(projection[name]) is not bool
                for name in (
                    "index_syntactically_bounded",
                    "index_in_range",
                    "selected_item_object",
                    "rejected_field_present",
                    "reasoning_item_type_is_reasoning",
                    "reasoning_unexpected_semantic_fields_present",
                    "reasoning_exact_allowed_key_set_match",
                    "reasoning_exactly_one_candidate_placeholder",
                    "reasoning_placeholder_precedes_function_pair",
                    "exact_empty_reasoning_placeholder",
                )
            )
        ):
            raise VerificationError("qualification_summary_invalid")
        fields = projection["rejected_item_fields"]
        if (
            not isinstance(fields, list)
            or len(fields) > 32
            or any(
                not isinstance(item, dict)
                or set(item) != {"name", "type"}
                or item["name"] not in _SAFE_INPUT_ITEM_FIELDS | {"other"}
                or item["type"] not in _SUMMARY_FIELD_TYPES
                for item in fields
            )
            or len({(item["name"], item["type"]) for item in fields}) != len(fields)
            or fields != sorted(fields, key=lambda item: (item["name"], item["type"]))
        ):
            raise VerificationError("qualification_summary_invalid")
    input_types = value["second_request_input_item_type_sequence"]
    if (
        not isinstance(input_types, list)
        or len(input_types) > 128
        or any(not isinstance(item, str) or item not in _SUMMARY_INPUT_TYPES for item in input_types)
    ):
        raise VerificationError("qualification_summary_invalid")
    for field in (
        "first_request_input_item_type_sequence",
    ):
        first_input_types = value[field]
        if (
            not isinstance(first_input_types, list)
            or len(first_input_types) > 128
            or any(
                not isinstance(item, str) or item not in _SUMMARY_INPUT_TYPES
                for item in first_input_types
            )
        ):
            raise VerificationError("qualification_summary_invalid")
    first_tool_counts = value["first_request_top_level_tool_type_counts"]
    if (
        not isinstance(first_tool_counts, dict)
        or any(
            not isinstance(tool_type, str)
            or tool_type not in _SUMMARY_TOOL_TYPES
            or not (type(count) is int and 0 <= count <= 64 or count == "other")
            for tool_type, count in first_tool_counts.items()
        )
    ):
        raise VerificationError("qualification_summary_invalid")
    tool_counts = value["second_request_top_level_tool_type_counts"]
    if (
        not isinstance(tool_counts, dict)
        or any(
            not isinstance(tool_type, str)
            or tool_type not in _SUMMARY_TOOL_TYPES
            or not (type(count) is int and 0 <= count <= 64 or count == "other")
            for tool_type, count in tool_counts.items()
        )
    ):
        raise VerificationError("qualification_summary_invalid")
    for field in ("second_function_call_fields", "second_function_call_output_fields"):
        fields = value[field]
        if (
            not isinstance(fields, list)
            or len(fields) > 32
            or any(
                not isinstance(item, dict)
                or set(item) != {"name", "type"}
                or item["name"] not in _SUMMARY_FUNCTION_FIELDS
                or item["type"] not in _SUMMARY_FIELD_TYPES
                for item in fields
            )
            or len({item["name"] for item in fields}) != len(fields)
            or fields != sorted(fields, key=lambda item: (item["name"], item["type"]))
        ):
            raise VerificationError("qualification_summary_invalid")
    for boundary in ("gateway", "local"):
        section = value[boundary]
        if not isinstance(section, dict) or set(section) - {
            "request_count", "response_count", "status_classes", "content_type_classes",
            "disconnect", "truncated", "handler_error",
        }:
            raise VerificationError("qualification_summary_invalid")
        if any(
            section.get(name) not in {"0", "1", "2", "other"}
            for name in ("request_count", "response_count")
        ) or not isinstance(section.get("status_classes"), list) or not isinstance(section.get("content_type_classes"), list):
            raise VerificationError("qualification_summary_invalid")
        if any(item not in _SUMMARY_STATUS_CLASSES for item in section["status_classes"]):
            raise VerificationError("qualification_summary_invalid")
        if any(item not in _SUMMARY_CONTENT_TYPES for item in section["content_type_classes"]):
            raise VerificationError("qualification_summary_invalid")
        if any(type(section.get(name)) is not bool for name in ("disconnect", "truncated", "handler_error")):
            raise VerificationError("qualification_summary_invalid")
    boundary_states = value["local_boundary_states"]
    if (
        not isinstance(boundary_states, dict)
        or set(boundary_states) != {"tool_policy", "observation", "constitution", "upstream"}
        or any(state not in _SUMMARY_LOCAL_BOUNDARY_STATES for state in boundary_states.values())
    ):
        raise VerificationError("qualification_summary_invalid")
    signed_identity_facts = value["local_signed_identity_facts"]
    if not isinstance(signed_identity_facts, list) or len(signed_identity_facts) > 2:
        raise VerificationError("qualification_summary_invalid")
    for fact in signed_identity_facts:
        if not isinstance(fact, dict) or set(fact) != _LOCAL_SIGNED_IDENTITY_FACT_KEYS:
            raise VerificationError("qualification_summary_invalid")
        if any(
            type(fact[name]) is not bool
            for name in _LOCAL_SIGNED_IDENTITY_FACT_KEYS
            if name not in {"required_header_cardinality_class", "signed_identity_class"}
        ):
            raise VerificationError("qualification_summary_invalid")
        if fact["required_header_cardinality_class"] not in _LOCAL_SIGNED_HEADER_CARDINALITY_CLASSES:
            raise VerificationError("qualification_summary_invalid")
        if fact["signed_identity_class"] not in _LOCAL_SIGNED_IDENTITY_CLASSES:
            raise VerificationError("qualification_summary_invalid")
    qwen = value["qwen"]
    if not isinstance(qwen, dict) or set(qwen) != {
        "inference_count", "compiler_count", "status_classes",
        "compiler_status_classes", "content_type_classes",
        "compiler_content_type_classes", "path_error", "normal_close",
        "handler_error", "truncated",
    }:
        raise VerificationError("qualification_summary_invalid")
    if qwen["inference_count"] not in {"0", "1", "2", "other"} or qwen["compiler_count"] not in {"0", "1", "2", "other"} or any(
        item not in _SUMMARY_STATUS_CLASSES for item in qwen["status_classes"]
    ) or any(item not in _SUMMARY_STATUS_CLASSES for item in qwen["compiler_status_classes"]
    ) or any(item not in _SUMMARY_CONTENT_TYPES for item in qwen["content_type_classes"]
    ) or any(item not in _SUMMARY_CONTENT_TYPES for item in qwen["compiler_content_type_classes"]):
        raise VerificationError("qualification_summary_invalid")
    if any(type(qwen[name]) is not bool for name in ("path_error", "normal_close", "handler_error", "truncated")):
        raise VerificationError("qualification_summary_invalid")
    rejection = value["qualification_rejection"]
    if not isinstance(rejection, dict) or set(rejection) != {"present", "artifact_equal", "artifact_digest_present"} or any(type(rejection[name]) is not bool for name in rejection):
        raise VerificationError("qualification_summary_invalid")
    accounting = value["accounting"]
    accounting_names = {
        "query_ok", "row_count", "reservation_finalized", "reservation_released",
        "reservation_pending", "ledger_finalized", "ledger_failed", "ledger_estimated",
        "ledger_pending", "zero_pending",
    }
    if not isinstance(accounting, dict) or set(accounting) != accounting_names:
        raise VerificationError("qualification_summary_invalid")
    if any(accounting[name] not in {"0", "1", "2", "other"} for name in accounting_names - {"query_ok", "zero_pending"}) or any(type(accounting[name]) is not bool for name in ("query_ok", "zero_pending")):
        raise VerificationError("qualification_summary_invalid")
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _write_preclassification_summary(root: Path, summary: object) -> dict[str, object]:
    _validate_task_summary_root(root)
    safe = _sanitize_preclassification_summary(summary)
    payload = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    if len(payload) > QUALIFICATION_SUMMARY_MAX_BYTES:
        raise VerificationError("qualification_summary_too_large")
    path = root / QUALIFICATION_SUMMARY_NAME
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError("short summary write")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(path, 0o600, follow_symlinks=False)
        directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise VerificationError("qualification_summary_overwrite") from exc
    except (OSError, ValueError) as exc:
        raise VerificationError("qualification_summary_write_failed") from exc
    return safe


def _read_preclassification_summary(root: Path) -> dict[str, object] | None:
    _validate_task_summary_root(root)
    path = root / QUALIFICATION_SUMMARY_NAME
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise VerificationError("qualification_summary_invalid") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.getuid()
        or path.is_symlink()
    ):
        raise VerificationError("qualification_summary_invalid")
    try:
        payload = path.read_bytes()
        if len(payload) > QUALIFICATION_SUMMARY_MAX_BYTES:
            raise VerificationError("qualification_summary_too_large")
        return _sanitize_preclassification_summary(json.loads(payload))
    except VerificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("qualification_summary_invalid") from exc


def _safe_qualification_failure_code(exception: BaseException) -> str:
    """Return a fixed code without exposing arbitrary exception text."""
    if isinstance(exception, VerificationError):
        candidate = str(exception)
        if (
            re.fullmatch(r"[a-z0-9_]{1,128}", candidate) is not None
            and candidate.startswith(("qualification_", "composed_tool_roundtrip_", "unexpected_"))
        ):
            return candidate
    return "qualification_failure_localization"


def _qualification_count_class(value: object) -> str:
    if type(value) is int and 0 <= value <= 2:
        return str(value)
    return "other"


def _qualification_turn_count_error(counts: tuple[object, object, object]) -> VerificationError:
    gateway, local, qwen = counts
    return VerificationError(
        "qualification_turn_counts_"
        f"g{_qualification_count_class(gateway)}_"
        f"l{_qualification_count_class(local)}_"
        f"q{_qualification_count_class(qwen)}"
    )


_SAFE_FUNCTION_PROJECTION_FIELDS = frozenset(
    {
        "type",
        "id",
        "status",
        "name",
        "namespace",
        "arguments",
        "call_id",
        "output",
        "caller",
        "output_index",
        "sequence_number",
    }
)
_SAFE_INPUT_ITEM_TYPES = frozenset(
    {
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "additional_tools",
        "compaction",
        "other",
    }
)
_SAFE_INPUT_ITEM_FIELDS = frozenset(
    {
        "type",
        "id",
        "status",
        "role",
        "content",
        "summary",
        "encrypted_content",
        "call_id",
        "name",
        "arguments",
        "namespace",
        "caller",
        "output",
        "input",
        "phase",
        "internal_chat_message_metadata_passthrough",
    }
)
_SAFE_INPUT_ERROR_SHAPES = frozenset({"item", "field", "other"})
_SAFE_REASONING_PLACEHOLDER_BASE_FIELDS = frozenset(
    {"type", "content", "summary", "encrypted_content"}
)
_SAFE_REASONING_PLACEHOLDER_FIELDS = _SAFE_REASONING_PLACEHOLDER_BASE_FIELDS | {"id"}
_SAFE_REASONING_ID_STATES = frozenset({"absent", "null", "other"})
_SAFE_REASONING_ARRAY_STATES = frozenset(
    {"empty_array", "nonempty_array", "absent", "malformed"}
)
_SAFE_REASONING_ENCRYPTED_STATES = frozenset(
    {"null", "absent", "non_null", "malformed"}
)


def _safe_json_type_class(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "other"


def _safe_function_projection_fields(item: object) -> list[dict[str, str]]:
    if not isinstance(item, dict):
        return []
    fields = [
        {
            "name": (
                name if name in _SAFE_FUNCTION_PROJECTION_FIELDS else "other"
            ),
            "type": _safe_json_type_class(field_value),
        }
        for name, field_value in item.items()
        if isinstance(name, str)
    ]
    return sorted(fields, key=lambda field: (field["name"], field["type"]))[:32]


def _classify_local_tool_choice(payload: object) -> str:
    """Classify only the bounded top-level Responses tool_choice shape."""
    if not isinstance(payload, dict):
        return "malformed_other"
    if "tool_choice" not in payload:
        return "absent"
    choice = payload.get("tool_choice")
    if isinstance(choice, str):
        if choice in {"auto", "none"}:
            return "automatic_none"
        if choice == "required":
            return "required"
        if choice in {"tool_search", "web_search"}:
            return "explicit_disabled_search"
        return "malformed_other"
    if not isinstance(choice, dict):
        return "malformed_other"

    # Choices are intentionally exact-shape, rather than recursively walking an
    # arbitrary object that could smuggle a second authority source.
    if set(choice) in ({"type"}, {"type", "mode"}):
        choice_type = choice.get("type")
        mode = choice.get("mode")
        if set(choice) == {"type"} and choice_type == "required":
            return "required"
        if choice_type in {"auto", "none"} and (
            set(choice) == {"type"}
            or (set(choice) == {"type", "mode"} and mode in {"auto", "none"})
        ):
            return "automatic_none"
        if set(choice) == {"type"} and choice_type in {"tool_search", "web_search"}:
            return "explicit_disabled_search"
        if choice_type == "allowed_tools" and mode in {"auto", "none"}:
            return "automatic_none"
        return "malformed_other"

    if set(choice) != {"type", "name"}:
        return "malformed_other"
    choice_type = choice.get("type")
    choice_name = choice.get("name")
    if choice_type not in {"function", "custom"} or not isinstance(choice_name, str):
        return "malformed_other"
    if not _LOCAL_TOOL_NAME_RE.fullmatch(choice_name):
        return "malformed_other"
    tools = payload.get("tools")
    if not isinstance(tools, list) or len(tools) > 128:
        return "malformed_other"
    matches = 0
    for tool in tools:
        if not isinstance(tool, dict):
            return "malformed_other"
        tool_type = tool.get("type")
        if tool_type in {"function", "custom"} and (
            not isinstance(tool.get("name"), str)
            or not _LOCAL_TOOL_NAME_RE.fullmatch(tool["name"])
        ):
            return "malformed_other"
        if tool_type == choice_type and tool.get("name") == choice_name:
            matches += 1
        elif tool_type not in {"function", "custom", "tool_search", "web_search"}:
            return "malformed_other"
    return "explicit_retained_local" if matches == 1 else "malformed_other"


def _empty_input_item_error_projection() -> dict[str, object]:
    return {
        "input_item_error_shape_class": "other",
        "item_json_type_class": "other",
        "item_type_class": "other",
        "rejected_item_fields": [],
        "rejected_field_name_class": "other",
        "index_syntactically_bounded": False,
        "index_in_range": False,
        "selected_item_object": False,
        "rejected_field_present": False,
        "reasoning_item_type_is_reasoning": False,
        "reasoning_id_state": "other",
        "reasoning_content_state": "malformed",
        "reasoning_summary_state": "malformed",
        "reasoning_encrypted_content_state": "malformed",
        "reasoning_unexpected_semantic_fields_present": False,
        "reasoning_exact_allowed_key_set_match": False,
        "reasoning_exactly_one_candidate_placeholder": False,
        "reasoning_placeholder_precedes_function_pair": False,
        "exact_empty_reasoning_placeholder": False,
    }


def _safe_reasoning_array_state(item: dict[str, object], field: str) -> str:
    if field not in item:
        return "absent"
    value = item[field]
    if not isinstance(value, list):
        return "malformed"
    return "empty_array" if not value else "nonempty_array"


def _safe_reasoning_placeholder_facts(item: object) -> dict[str, object]:
    if not isinstance(item, dict):
        return {
            "reasoning_item_type_is_reasoning": False,
            "reasoning_id_state": "other",
            "reasoning_content_state": "malformed",
            "reasoning_summary_state": "malformed",
            "reasoning_encrypted_content_state": "malformed",
            "reasoning_unexpected_semantic_fields_present": False,
            "reasoning_exact_allowed_key_set_match": False,
            "exact_empty_reasoning_placeholder": False,
        }
    item_type_is_reasoning = item.get("type") == "reasoning"
    if "id" not in item:
        id_state = "absent"
    elif item.get("id") is None:
        id_state = "null"
    else:
        id_state = "other"
    if "encrypted_content" not in item:
        encrypted_state = "absent"
    elif item.get("encrypted_content") is None:
        encrypted_state = "null"
    elif isinstance(item.get("encrypted_content"), str):
        encrypted_state = "non_null"
    else:
        encrypted_state = "malformed"
    unexpected = bool(set(item) - _SAFE_REASONING_PLACEHOLDER_FIELDS)
    exact_keys = set(item) in {
        _SAFE_REASONING_PLACEHOLDER_BASE_FIELDS,
        _SAFE_REASONING_PLACEHOLDER_FIELDS,
    }
    exact = (
        item_type_is_reasoning
        and id_state in {"absent", "null"}
        and _safe_reasoning_array_state(item, "content") == "empty_array"
        and _safe_reasoning_array_state(item, "summary") == "empty_array"
        and encrypted_state == "null"
        and exact_keys
    )
    return {
        "reasoning_item_type_is_reasoning": item_type_is_reasoning,
        "reasoning_id_state": id_state,
        "reasoning_content_state": _safe_reasoning_array_state(item, "content"),
        "reasoning_summary_state": _safe_reasoning_array_state(item, "summary"),
        "reasoning_encrypted_content_state": encrypted_state,
        "reasoning_unexpected_semantic_fields_present": unexpected,
        "reasoning_exact_allowed_key_set_match": exact_keys,
        "exact_empty_reasoning_placeholder": exact,
    }


def _reasoning_placeholder_candidate_indexes(items: object) -> list[int]:
    if not isinstance(items, list):
        return []
    return [
        index
        for index, item in enumerate(items)
        if _safe_reasoning_placeholder_facts(item)["exact_empty_reasoning_placeholder"]
    ]


def _reasoning_adjacent_function_pair_indexes(items: object) -> list[int]:
    if not isinstance(items, list):
        return []
    return [
        index
        for index in range(len(items) - 1)
        if (
            isinstance(items[index], dict)
            and items[index].get("type") == "function_call"
            and isinstance(items[index + 1], dict)
            and items[index + 1].get("type") == "function_call_output"
        )
    ]


def _reasoning_adjacent_custom_pair_indexes(items: object) -> list[int]:
    if not isinstance(items, list):
        return []
    return [
        index
        for index in range(len(items) - 1)
        if (
            isinstance(items[index], dict)
            and items[index].get("type") == "custom_tool_call"
            and isinstance(items[index + 1], dict)
            and items[index + 1].get("type") == "custom_tool_call_output"
        )
    ]


def _safe_input_item_error_projection(
    param: object, request_body: bytes
) -> dict[str, object]:
    """Correlate one transient input parameter with a request, retaining no index/value."""
    result = _empty_input_item_error_projection()
    if not isinstance(param, str):
        return result
    item_match = re.fullmatch(r"input\[([0-9]+)\]", param)
    field_match = re.fullmatch(
        r"input\[([0-9]+)\]\.([A-Za-z_][A-Za-z0-9_]{0,63})", param
    )
    if item_match is None and field_match is None:
        return result
    result["input_item_error_shape_class"] = (
        "field" if field_match is not None else "item"
    )
    digits = (field_match or item_match).group(1)
    bounded = len(digits) <= 3
    index = int(digits) if bounded else None
    result["index_syntactically_bounded"] = bounded and index is not None and index <= 128
    try:
        payload = json.loads(request_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    items = payload.get("input") if isinstance(payload, dict) else None
    selected: object = None
    in_range = (
        isinstance(items, list)
        and index is not None
        and 0 <= index < len(items)
    )
    result["index_in_range"] = in_range
    if in_range:
        assert isinstance(index, int)
        selected = items[index]
    result["selected_item_object"] = isinstance(selected, dict)
    result["item_json_type_class"] = _safe_json_type_class(selected)
    selected_reasoning_facts = _empty_input_item_error_projection()
    if isinstance(selected, dict):
        item_type = selected.get("type")
        result["item_type_class"] = (
            item_type
            if isinstance(item_type, str) and item_type in _SAFE_INPUT_ITEM_TYPES
            else "other"
        )
        fields = {
            (
                name if name in _SAFE_INPUT_ITEM_FIELDS else "other",
                _safe_json_type_class(value),
            )
            for name, value in selected.items()
            if isinstance(name, str)
        }
        result["rejected_item_fields"] = sorted(
            ({"name": name, "type": field_type} for name, field_type in fields),
            key=lambda field: (field["name"], field["type"]),
        )[:32]
        if field_match is not None:
            field_name = field_match.group(2)
            result["rejected_field_name_class"] = (
                field_name
                if field_name in _SAFE_INPUT_ITEM_FIELDS
                else "other"
            )
            result["rejected_field_present"] = field_name in selected
        else:
            result["rejected_field_name_class"] = "none"
        reasoning_facts = _safe_reasoning_placeholder_facts(selected)
        result.update(reasoning_facts)
        selected_reasoning_facts = reasoning_facts
    candidate_indexes = _reasoning_placeholder_candidate_indexes(items)
    pair_indexes = _reasoning_adjacent_function_pair_indexes(items)
    custom_pair_indexes = _reasoning_adjacent_custom_pair_indexes(items)
    result["reasoning_exactly_one_candidate_placeholder"] = len(candidate_indexes) == 1
    result["reasoning_placeholder_precedes_function_pair"] = (
        len(candidate_indexes) == 1
        and len(pair_indexes) == 1
        and not custom_pair_indexes
        and candidate_indexes[0] + 1 == pair_indexes[0]
    )
    result["exact_empty_reasoning_placeholder"] = (
        selected_reasoning_facts["exact_empty_reasoning_placeholder"] is True
        and len(candidate_indexes) == 1
        and len(pair_indexes) == 1
        and not custom_pair_indexes
        and candidate_indexes[0] + 1 == pair_indexes[0]
    )
    return result


@dataclass(frozen=True, slots=True)
class CapturedRequest:
    path: str
    body: bytes
    headers: dict[str, str]
    method: str = "POST"
    header_name_counts: tuple[tuple[str, int], ...] = ()


def _safe_roundtrip_request_projection(body: bytes) -> dict[str, object]:
    """Project one transient request to allowlisted type/count facts only."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "top_level_tool_type_counts": {},
            "input_item_type_sequence": [],
            "stream_class": "invalid",
            "tool_choice_class": "malformed_other",
            "function_call_fields": [],
            "function_call_output_fields": [],
        }
    if not isinstance(payload, dict):
        return {
            "top_level_tool_type_counts": {},
            "input_item_type_sequence": [],
            "stream_class": "invalid",
            "tool_choice_class": "malformed_other",
            "function_call_fields": [],
            "function_call_output_fields": [],
        }
    tools = payload.get("tools")
    counts: dict[str, int] = {}
    if isinstance(tools, list):
        for tool in tools[:64]:
            tool_type = tool.get("type") if isinstance(tool, dict) else None
            safe_type = (
                tool_type
                if isinstance(tool_type, str)
                and tool_type in {"function", "custom", "namespace", "tool_search", "web_search"}
                else "other"
            )
            counts[safe_type] = min(counts.get(safe_type, 0) + 1, 64)
    input_items = payload.get("input")
    item_types: list[str] = []
    safe_items: list[object] = []
    if isinstance(input_items, list):
        for item in input_items[:128]:
            safe_items.append(item)
            item_type = item.get("type") if isinstance(item, dict) else None
            item_types.append(
                item_type
                if isinstance(item_type, str)
                and item_type
                in {
                    "message",
                    "reasoning",
                    "additional_tools",
                    "function_call",
                    "function_call_output",
                    "custom_tool_call",
                    "custom_tool_call_output",
                }
                else "other"
            )
    stream = payload.get("stream")
    pair_indices = [
        index
        for index in range(len(item_types) - 1)
        if item_types[index : index + 2]
        == ["function_call", "function_call_output"]
    ]
    function_call_fields: list[dict[str, str]] = []
    function_call_output_fields: list[dict[str, str]] = []
    if len(pair_indices) == 1:
        pair_index = pair_indices[0]
        function_call_fields = _safe_function_projection_fields(safe_items[pair_index])
        function_call_output_fields = _safe_function_projection_fields(
            safe_items[pair_index + 1]
        )
    function_call = (
        safe_items[pair_indices[0]]
        if len(pair_indices) == 1 and isinstance(safe_items[pair_indices[0]], dict)
        else None
    )
    function_output = (
        safe_items[pair_indices[0] + 1]
        if len(pair_indices) == 1 and isinstance(safe_items[pair_indices[0] + 1], dict)
        else None
    )
    function_item_id = function_call.get("id") if isinstance(function_call, dict) else None
    call_id = function_call.get("call_id") if isinstance(function_call, dict) else None
    output_call_id = function_output.get("call_id") if isinstance(function_output, dict) else None
    return {
        "top_level_tool_type_counts": dict(sorted(counts.items())),
        "input_item_type_sequence": item_types,
        "function_call_fields": function_call_fields,
        "function_call_output_fields": function_call_output_fields,
        "function_item_id_state": (
            "present"
            if isinstance(function_item_id, str)
            else "null"
            if function_item_id is None and isinstance(function_call, dict) and "id" in function_call
            else "absent"
            if function_call is not None
            else "none"
        ),
        "function_item_id_prefix_class": (
            "codex_prefixed"
            if isinstance(function_item_id, str)
            and function_item_id.partition("_")[0]
            and function_item_id.partition("_")[2]
            else "other"
            if isinstance(function_item_id, str)
            else "none"
        ),
        "function_call_id_state": (
            "present_valid"
            if isinstance(call_id, str) and 1 <= len(call_id) <= 256
            else "absent_or_invalid"
            if function_call is not None
            else "none"
        ),
        "adjacent_matching_output": (
            isinstance(call_id, str)
            and call_id == output_call_id
            and isinstance(function_output, dict)
        ),
        "stream_class": (
            "true" if stream is True else "false" if stream is False else "other"
        ),
        "tool_choice_class": _classify_local_tool_choice(payload),
    }


def _safe_gateway_error_code_class(value: object) -> str:
    if value == "responses_input_tool_item_not_supported":
        return "input_tool_item_not_supported"
    if value == "responses_codex_tool_roundtrip_invalid":
        return "codex_tool_roundtrip_invalid"
    if value == "responses_codex_replay_reference_not_found":
        return "replay_reference_not_found"
    if value == "responses_codex_replay_route_mismatch":
        return "replay_route_mismatch"
    if value == "responses_codex_encrypted_reasoning_replay_not_allowed":
        return "encrypted_reasoning_replay_not_allowed"
    if value == "responses_codex_reasoning_visible_invalid":
        return "reasoning_visible_invalid"
    if value == "responses_codex_reasoning_visible_too_large":
        return "reasoning_visible_too_large"
    if value in {
        "responses_route_capability_not_supported",
        "responses_route_capability_missing",
        "responses_function_tool_capability_not_supported",
        "responses_custom_tool_capability_not_supported",
        "responses_codex_streaming_tool_events_not_allowed",
        "responses_codex_compaction_capability_not_supported",
    }:
        return "route_capability_not_supported"
    if value in {
        "responses_tool_policy_invalid",
        "responses_disabled_tool_choice",
        "responses_codex_envelope_invalid",
        "responses_codex_client_tools_invalid",
        "responses_function_call_output_invalid",
        "responses_function_call_output_too_large",
        "responses_custom_tool_call_output_invalid",
        "responses_custom_tool_call_output_too_large",
        "responses_input_invalid",
    }:
        return "request_policy_invalid"
    return "other"


def _safe_gateway_error_param_class(value: object) -> str:
    if not isinstance(value, str):
        return "other"
    for prefix, safe_class in (
        ("input", "input"),
        ("stream", "stream"),
        ("tools", "tools"),
        ("tool_choice", "tool_choice"),
    ):
        if value == prefix or value.startswith(f"{prefix}[") or value.startswith(f"{prefix}."):
            return safe_class
    return "other"


def _safe_gateway_error_param_field_class(value: object) -> str:
    if not isinstance(value, str):
        return "other"
    if value in {"input", "stream", "tools", "tool_choice"}:
        return "none"
    leaf = value.rsplit(".", 1)[-1]
    return (
        leaf
        if leaf in _SUMMARY_GATEWAY_ERROR_PARAM_FIELDS
        and leaf not in {"none", "other", "input", "tools", "tool_choice", "stream"}
        else "other"
    )


def _safe_roundtrip_projection_class(value: object) -> str:
    if not isinstance(value, dict) or value.get("stream_class") != "true":
        return "other"
    counts = value.get("top_level_tool_type_counts")
    input_types = value.get("input_item_type_sequence")
    if not isinstance(counts, dict) or not isinstance(input_types, list):
        return "other"
    if any(
        not isinstance(tool_type, str)
        or tool_type not in {"function", "custom", "namespace", "tool_search", "web_search", "other"}
        or type(count) is not int
        or count < 0
        or count > 64
        for tool_type, count in counts.items()
    ):
        return "other"
    if any(
        not isinstance(item_type, str)
        or item_type
        not in {
            "message",
            "reasoning",
            "additional_tools",
            "function_call",
            "function_call_output",
            "custom_tool_call",
            "custom_tool_call_output",
            "other",
        }
        for item_type in input_types
    ):
        return "other"
    has_adjacent_function_pair = any(
        input_types[index : index + 2] == ["function_call", "function_call_output"]
        for index in range(len(input_types) - 1)
    )
    has_bounded_top_level_tool = (
        counts.get("function", 0) + counts.get("custom", 0) > 0
        and counts.get("other", 0) == 0
    )
    if (
        has_bounded_top_level_tool
        and has_adjacent_function_pair
        and "additional_tools" not in input_types
    ):
        return "top_level_function_pair_without_additional_tools"
    return "other"


_SAFE_SSE_EVENT_TYPES = frozenset(
    {
        "response.created",
        "response.completed",
        "response.in_progress",
        "response.reasoning_part.added",
        "response.reasoning_text.delta",
        "response.reasoning_text.done",
        "response.reasoning_part.done",
        "response.output_item.added",
        "response.output_item.done",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.delta",
        "response.output_text.done",
        "error",
        "other",
    }
)
_SAFE_ERROR_FIELD_NAMES = frozenset(
    {"type", "message", "code", "param", "sequence_number", "request_id"}
)
_SAFE_ERROR_VALUE_CLASSES = frozenset(
    {
        "invalid_request_error", "authentication_error", "permission_error",
        "rate_limit_error", "server_error", "provider_error",
        "provider_request_error", "provider_http_error", "provider_timeout",
        "provider_response_parse_error", "provider_configuration_error",
        "codex_0149_request_invalid", "codex_0149_identity_shape",
    }
)
_SAFE_GATEWAY_ERROR_CODE_CLASSES = frozenset(
    {
        "none",
        "input_tool_item_not_supported",
        "codex_tool_roundtrip_invalid",
        "replay_reference_not_found",
        "replay_route_mismatch",
        "route_capability_not_supported",
        "request_policy_invalid",
        "encrypted_reasoning_replay_not_allowed",
        "reasoning_visible_invalid",
        "reasoning_visible_too_large",
        "other",
    }
)
_SAFE_GATEWAY_ERROR_PARAM_CLASSES = frozenset(
    {"none", "input", "stream", "tools", "tool_choice", "other"}
)
_SAFE_RAW_METADATA_KEY_CLASSES = {
    "session_id": "session",
    "thread_id": "thread",
    "root_turn_id": "root_turn",
    "turn_id": "turn",
    "x-codex-installation-id": "installation",
    "x-codex-window-id": "window",
    "x-codex-turn-metadata": "turn_metadata",
}
_SAFE_PRIVACY_BODY_PATH_CLASSES = frozenset(
    {
        "prompt_cache_key",
        "instructions",
        "metadata",
        "reasoning",
        "tools",
        "tool_choice",
        "input_non_internal",
        "other",
    }
)
_SSE_CAPTURE_LIMIT = 64 * 1024
_ERROR_CAPTURE_LIMIT = 16 * 1024
_SSE_EVENT_RUN_LIMIT = 128
_SSE_EVENT_COUNT_LIMIT = _SSE_CAPTURE_LIMIT
_PINNED_CAPTURE_SSE_STRUCTURE = {
    "invalid": False,
    "event_counts": {"response.completed": 1, "response.created": 1},
    "event_trace": [
        {"event": "response.created", "count": 1},
        {"event": "response.completed", "count": 1},
    ],
    "event_trace_overflow": False,
    "done_sentinel": False,
    "duplicates": False,
    "unknown_events": False,
    "error_event": False,
    "error_field_names": [],
    "error_code_class": "unknown",
    "error_type_class": "unknown",
    "event_vocabulary_reviewed": True,
    "response_completed": True,
    "response_field_names": {
        "response.created": ["id", "model", "object", "status"],
        "response.completed": ["id", "model", "object", "output", "status", "usage"],
    },
    "response_id_relation": True,
    "created_status_in_progress": True,
    "completed_status_completed": True,
    "model_matches": True,
    "completed_output_empty": True,
    "completed_usage_valid": True,
    "terminal_output_shape": "empty_array",
    "first_event_before_upstream_completion": True,
    "normal_close": True,
    "downstream_closed_early": False,
}
_FAKE_STANDARD_SSE_STRUCTURE = {
    "invalid": False,
    "event_counts": {
        "response.completed": 1,
        "response.content_part.added": 1,
        "response.content_part.done": 1,
        "response.created": 1,
        "response.in_progress": 1,
        "response.output_item.added": 1,
        "response.output_item.done": 1,
        "response.output_text.delta": 1,
        "response.output_text.done": 1,
    },
    "event_trace": [
        {"event": "response.created", "count": 1},
        {"event": "response.in_progress", "count": 1},
        {"event": "response.output_item.added", "count": 1},
        {"event": "response.content_part.added", "count": 1},
        {"event": "response.output_text.delta", "count": 1},
        {"event": "response.output_text.done", "count": 1},
        {"event": "response.content_part.done", "count": 1},
        {"event": "response.output_item.done", "count": 1},
        {"event": "response.completed", "count": 1},
    ],
    "event_trace_overflow": False,
    "done_sentinel": False,
    "duplicates": False,
    "unknown_events": False,
    "error_event": False,
    "error_field_names": [],
    "error_code_class": "unknown",
    "error_type_class": "unknown",
    "event_vocabulary_reviewed": True,
    "response_completed": True,
    "response_field_names": {
        "response.completed": ["id", "model", "object", "output", "status", "usage"],
        "response.created": ["id", "model", "object", "status"],
        "response.in_progress": ["id", "model", "object", "status"],
    },
    "response_id_relation": True,
    "created_status_in_progress": True,
    "completed_status_completed": True,
    "model_matches": True,
    "completed_output_empty": False,
    "completed_usage_valid": True,
    "terminal_output_shape": "nonempty_array",
    "first_event_before_upstream_completion": True,
    "normal_close": True,
    "downstream_closed_early": False,
}


class _SSEStructuralRecorder:
    """Retain only bounded event names and response object field names."""

    def __init__(self, *, expected_model: str = CODEX_MODEL) -> None:
        self._expected_model = expected_model
        self._buffer = bytearray()
        self._event_name: str | None = None
        self._event_unknown = False
        self._data = bytearray()
        self._event_runs: list[dict[str, object]] = []
        self._event_counts: dict[str, int] = {}
        self._event_trace_overflow = False
        self._response_field_names: dict[str, set[str]] = {}
        self._created_id: str | None = None
        self._response_id_relation = False
        self._created_status_in_progress = False
        self._completed_status_completed = False
        self._model_matches = False
        self._completed_output_empty = False
        self._terminal_output_shape = "missing"
        self._completed_usage_valid = False
        self._done_sentinel = False
        self._unknown_events = False
        self._error_event = False
        self._error_field_names: set[str] = set()
        self._error_code_class = "unknown"
        self._error_type_class = "unknown"
        self._response_completed = False
        self._first_event_before_upstream_completion = False
        self._normal_close = False
        self._downstream_closed_early = False
        self._invalid = False

    def mark_first_event_before_upstream_completion(self, value: bool = True) -> None:
        self._first_event_before_upstream_completion = value

    def mark_normal_close(self, value: bool = True) -> None:
        self._normal_close = value

    def mark_downstream_closed_early(self, value: bool = True) -> None:
        self._downstream_closed_early = value

    def feed(self, chunk: bytes) -> None:
        if self._invalid:
            return
        if len(self._buffer) + len(chunk) > _SSE_CAPTURE_LIMIT:
            self._invalid = True
            self._buffer.clear()
            self._data.clear()
            return
        self._buffer.extend(chunk)
        self._consume_lines()

    def finish(self) -> None:
        if self._invalid:
            return
        if self._buffer:
            self._buffer.extend(b"\n")
            self._consume_lines()
        if self._event_name is not None or self._data:
            self._finish_event()

    def _consume_lines(self) -> None:
        while b"\n" in self._buffer:
            line, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            line = line.rstrip(b"\r")
            if not line:
                self._finish_event()
            elif line.startswith(b"event:"):
                self._event_name, self._event_unknown = self._safe_name(line[6:])
            elif line.startswith(b"data:"):
                value = line[5:]
                if value.startswith(b" "):
                    value = value[1:]
                if len(self._data) + len(value) > _SSE_CAPTURE_LIMIT:
                    self._invalid = True
                    self._data.clear()
                    self._buffer.clear()
                    return
                self._data.extend(value)

    @staticmethod
    def _safe_name(raw: bytes) -> tuple[str, bool]:
        try:
            value = raw.decode("ascii").strip()
        except UnicodeDecodeError:
            return "other", True
        if value in _SAFE_SSE_EVENT_TYPES and value != "other":
            return value, False
        return "other", value != "other"

    def _finish_event(self) -> None:
        data = bytes(self._data)
        event_name = self._event_name
        event_unknown = self._event_unknown
        self._data.clear()
        self._event_name = None
        self._event_unknown = False
        if data == b"[DONE]":
            self._done_sentinel = True
            return
        if not data:
            return
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._invalid = True
            return
        if not isinstance(payload, dict):
            self._invalid = True
            return
        payload_type = payload.get("type")
        if event_name is None:
            try:
                payload_type_bytes = payload_type.encode("ascii") if isinstance(payload_type, str) else b""
            except UnicodeEncodeError:
                payload_type_bytes = b""
            event_name, event_unknown = self._safe_name(payload_type_bytes)
        event_name = event_name or "other"
        count = self._event_counts.get(event_name, 0)
        self._event_counts[event_name] = min(count + 1, _SSE_EVENT_COUNT_LIMIT)
        if self._event_runs and self._event_runs[-1]["event"] == event_name:
            self._event_runs[-1]["count"] = int(self._event_runs[-1]["count"]) + 1
        elif len(self._event_runs) < _SSE_EVENT_RUN_LIMIT:
            self._event_runs.append({"event": event_name, "count": 1})
        else:
            self._event_trace_overflow = True
        self._unknown_events = self._unknown_events or event_unknown
        self._error_event = self._error_event or event_name == "error"
        self._response_completed = self._response_completed or event_name == "response.completed"
        if event_name == "error":
            error_object = payload.get("error")
            error_object = error_object if isinstance(error_object, dict) else payload
            self._error_field_names.update(
                key for key in error_object if key in _SAFE_ERROR_FIELD_NAMES
            )
            for field, target in (("code", "_error_code_class"), ("type", "_error_type_class")):
                value = error_object.get(field)
                if isinstance(value, str) and value in _SAFE_ERROR_VALUE_CLASSES:
                    setattr(self, target, value)
                else:
                    setattr(self, target, "unknown")
        response = payload.get("response")
        if isinstance(response, dict):
            fields = {
                key
                for key in response
                if isinstance(key, str)
                and len(key) <= 64
                and all(33 <= ord(char) <= 126 for char in key)
            }
            self._response_field_names.setdefault(event_name, set()).update(fields)
            response_id = response.get("id")
            id_shape = (
                isinstance(response_id, str)
                and response_id.startswith("resp_")
                and len(response_id) <= 256
                and all(33 <= ord(char) <= 126 for char in response_id)
            )
            model_matches = response.get("model") == self._expected_model
            if event_name == "response.created":
                self._created_id = response_id if id_shape else None
                self._created_status_in_progress = response.get("status") == "in_progress"
                self._model_matches = model_matches
            elif event_name == "response.completed":
                self._response_id_relation = (
                    self._created_id is not None
                    and id_shape
                    and response_id == self._created_id
                )
                self._completed_status_completed = response.get("status") == "completed"
                self._model_matches = self._model_matches and model_matches
                self._completed_output_empty = response.get("output") == []
                output = response.get("output")
                if output == []:
                    self._terminal_output_shape = "empty_array"
                elif isinstance(output, list):
                    self._terminal_output_shape = "nonempty_array"
                elif output is None:
                    self._terminal_output_shape = "missing"
                else:
                    self._terminal_output_shape = "other"
                usage = response.get("usage")
                self._completed_usage_valid = (
                    isinstance(usage, dict)
                    and all(
                        type(usage.get(field)) is int and usage[field] >= 0
                        for field in ("input_tokens", "output_tokens", "total_tokens")
                    )
                )
                self._created_id = None

    def snapshot(self) -> dict[str, object]:
        self.finish()
        event_counts = dict(sorted(self._event_counts.items()))
        return {
            "invalid": self._invalid,
            "event_counts": event_counts,
            "event_trace": [dict(run) for run in self._event_runs],
            "event_trace_overflow": self._event_trace_overflow,
            "done_sentinel": self._done_sentinel,
            "duplicates": any(
                self._event_counts.get(event, 0) > 1
                for event in ("response.created", "response.completed")
            ),
            "unknown_events": self._unknown_events,
            "error_event": self._error_event,
            "error_field_names": sorted(self._error_field_names),
            "error_code_class": self._error_code_class,
            "error_type_class": self._error_type_class,
            "event_vocabulary_reviewed": not self._unknown_events and not self._error_event,
            "response_completed": self._response_completed,
            "response_field_names": {
                event: sorted(fields)
                for event, fields in sorted(self._response_field_names.items())
            },
            "response_id_relation": self._response_id_relation,
            "created_status_in_progress": self._created_status_in_progress,
            "completed_status_completed": self._completed_status_completed,
            "model_matches": self._model_matches,
            "completed_output_empty": self._completed_output_empty,
            "completed_usage_valid": self._completed_usage_valid,
            "terminal_output_shape": self._terminal_output_shape,
            "first_event_before_upstream_completion": self._first_event_before_upstream_completion,
            "normal_close": self._normal_close,
            "downstream_closed_early": self._downstream_closed_early,
        }


def _assert_pinned_capture_sse_structure(structure: dict[str, object]) -> None:
    if structure != _PINNED_CAPTURE_SSE_STRUCTURE:
        raise VerificationError("gateway_sse_schema_mismatch")


def _assert_new_pinned_capture_sse_structure(
    relay: _ForwardingRelay, start_index: int, *, missing_code: str, mismatch_code: str
) -> None:
    structures = relay.status()["sse_structures"]
    if not isinstance(structures, list) or len(structures) <= start_index:
        response_statuses = relay.status()["response_statuses"]
        if isinstance(response_statuses, list) and response_statuses:
            status = response_statuses[-1]
            if isinstance(status, int) and status >= 500:
                raise VerificationError(f"{missing_code}_http_5xx")
            if isinstance(status, int) and status >= 400:
                raise VerificationError(f"{missing_code}_http_4xx")
        raise VerificationError(missing_code)
    structure = structures[-1]
    if not isinstance(structure, dict):
        raise VerificationError(mismatch_code)
    try:
        _assert_pinned_capture_sse_structure(structure)
    except VerificationError:
        raise VerificationError(mismatch_code) from None


def _stream_has_valid_completion(structure: object) -> bool:
    if isinstance(structure, dict) and "normalization_status" in structure:
        return structure.get("valid_completion") is True
    if not isinstance(structure, dict) or structure.get("invalid") is not False:
        return False
    trace = structure.get("event_trace")
    sequence = structure.get("event_sequence")
    counts = structure.get("event_counts")
    response_completed = structure.get("response_completed") is True
    if not isinstance(trace, list) and isinstance(sequence, list):
        response_completed = "response.completed" in sequence
    return (
        response_completed
        and isinstance(counts, dict)
        and counts.get("response.created") == 1
        and counts.get("response.completed") == 1
        and structure.get("response_id_relation") is True
        and structure.get("created_status_in_progress") is True
        and structure.get("completed_status_completed") is True
        and structure.get("model_matches") is True
        and structure.get("terminal_output_shape") in {"empty_array", "nonempty_array"}
        and structure.get("completed_usage_valid") is True
        and structure.get("first_event_before_upstream_completion") is True
        and structure.get("normal_close") is True
        and structure.get("error_event") is not True
        and structure.get("event_trace_overflow") is False
    )


def _stream_observation(
    *,
    boundary: str,
    status: int | None,
    content_type_class: str | None,
    structure: object,
    client_completed: bool,
    failure_code: str | None = None,
) -> dict[str, object]:
    response_completed = (
        structure.get("response_completed") is True
        if isinstance(structure, dict)
        else False
    )
    return {
        "boundary": boundary,
        "http_status_class": (
            f"{status // 100}xx" if isinstance(status, int) else "unknown"
        ),
        "content_type_class": content_type_class or "unknown",
        "structure": structure,
        "client_completed": client_completed,
        "failure_code": failure_code,
        "response_completed": response_completed,
        "valid_completion": _stream_has_valid_completion(structure),
    }


def _relay_failure_code(status: object, current: str | None = None) -> str | None:
    if isinstance(status, dict) and status.get("handler_error") is True:
        return "handler_error"
    return current


def _stream_observation_is_ambiguous(observation: dict[str, object]) -> bool:
    if "normalization_status" in observation:
        return (
            observation.get("normalization_status") != "complete"
            or observation.get("normalization_reason") != "none"
            or observation.get("failure_code") != "none"
            or observation.get("handler_error") is True
            or observation.get("upstream_truncated") is True
            or observation.get("error_event") is True
            or observation.get("http_status_class") != "2xx"
            or observation.get("content_type_class") != "sse"
            or observation.get("response_completed") is True
            and not _terminal_completion_valid(observation)
        )
    structure = observation.get("structure")
    return (
        observation.get("failure_code") is not None
        or observation.get("handler_error") is True
        or observation.get("upstream_truncated") is True
        or observation.get("error_event") is True
        or observation.get("http_status_class") != "2xx"
        or observation.get("content_type_class") != "sse"
        or not isinstance(structure, dict)
        or structure.get("invalid") is not False
        or structure.get("normal_close") is not True
        or (
            observation.get("response_completed") is True
            and observation.get("valid_completion") is not True
        )
    )


@dataclass(frozen=True, slots=True)
class _SafeSSEOrdinal:
    """Immutable, content-free projection of one bounded SSE ordinal."""

    present: bool
    invalid: bool
    valid_completion: bool
    event_counts: tuple[tuple[str, int | str], ...]
    event_trace: tuple[tuple[str, int | str], ...]
    event_trace_overflow: bool
    created_exactly_once: bool
    completed_exactly_once: bool
    response_id_relation: bool
    created_status_in_progress: bool
    completed_status_completed: bool
    model_matches: bool
    terminal_output_shape: str
    completed_usage_valid: bool
    completed_usage_shape: str
    duplicates: bool
    unknown_events: bool
    error_event: bool
    normal_close: bool
    downstream_closed_early: bool
    handler_error: bool
    upstream_truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "present": self.present,
            "invalid": self.invalid,
            "valid_completion": self.valid_completion,
            "event_counts": dict(self.event_counts),
            "event_trace": [
                {"event": event, "count": count} for event, count in self.event_trace
            ],
            "event_trace_overflow": self.event_trace_overflow,
            "created_exactly_once": self.created_exactly_once,
            "completed_exactly_once": self.completed_exactly_once,
            "response_id_relation": self.response_id_relation,
            "created_status_in_progress": self.created_status_in_progress,
            "completed_status_completed": self.completed_status_completed,
            "model_matches": self.model_matches,
            "terminal_output_shape": self.terminal_output_shape,
            "completed_usage_valid": self.completed_usage_valid,
            "completed_usage_shape": self.completed_usage_shape,
            "duplicates": self.duplicates,
            "unknown_events": self.unknown_events,
            "error_event": self.error_event,
            "normal_close": self.normal_close,
            "downstream_closed_early": self.downstream_closed_early,
            "handler_error": self.handler_error,
            "upstream_truncated": self.upstream_truncated,
        }


@dataclass(frozen=True, slots=True)
class _SafeBoundarySection:
    request_count: str
    response_count: str
    response_status_classes: tuple[str, ...]
    content_type_classes: tuple[str, ...]
    sse_structure_count: str
    ordinals: tuple[_SafeSSEOrdinal, ...]
    handler_error: bool
    upstream_truncated: bool
    downstream_closed_early: bool
    normal_close: bool
    error_code_classes: tuple[str, ...] = ()
    error_param_classes: tuple[str, ...] = ()
    error_stage_classes: tuple[str, ...] = ()
    boundary_states: tuple[tuple[str, str], ...] = ()
    signed_identity_facts: tuple[tuple[tuple[str, object], ...], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "request_count": self.request_count,
            "response_count": self.response_count,
            "response_status_classes": list(self.response_status_classes),
            "content_type_classes": list(self.content_type_classes),
            "sse_structure_count": self.sse_structure_count,
            "ordinals": [ordinal.to_dict() for ordinal in self.ordinals],
            "handler_error": self.handler_error,
            "upstream_truncated": self.upstream_truncated,
            "downstream_closed_early": self.downstream_closed_early,
            "normal_close": self.normal_close,
            "error_code_classes": list(self.error_code_classes),
            "error_param_classes": list(self.error_param_classes),
            "error_stage_classes": list(self.error_stage_classes),
            "boundary_states": dict(self.boundary_states),
            "signed_identity_facts": [dict(facts) for facts in self.signed_identity_facts],
        }


@dataclass(frozen=True, slots=True)
class _SafeBoundarySnapshot:
    """Deep-sanitized immutable snapshot retained across verifier assertions."""

    gateway: _SafeBoundarySection
    local: _SafeBoundarySection
    qwen: _SafeBoundarySection
    qwen_inference_count: str
    qwen_successful_count: str
    qwen_compiler_count: str
    accounting: tuple[tuple[str, str | bool], ...]
    codex_exit_success: bool
    codex_provenance_class: str

    def to_dict(self, *, outcome: str, assertion_class: str) -> dict[str, object]:
        return {
            "schema": "composed_boundary_snapshot_v1",
            "outcome": outcome,
            "assertion_class": assertion_class,
            "gateway": self.gateway.to_dict(),
            "local": self.local.to_dict(),
            "qwen": {
                **self.qwen.to_dict(),
                "inference_count": self.qwen_inference_count,
                "successful_count": self.qwen_successful_count,
                "compiler_count": self.qwen_compiler_count,
            },
            "accounting": dict(self.accounting),
            "codex": {
                "exit_success": self.codex_exit_success,
                "provenance_class": self.codex_provenance_class,
            },
        }


class _BoundaryDiagnosticError(VerificationError):
    """Verification failure carrying only a previously sanitized snapshot."""

    def __init__(self, code: str, snapshot: _SafeBoundarySnapshot) -> None:
        self.code = code
        self.snapshot = snapshot
        super().__init__(code)


def _safe_count_class(value: object) -> str:
    return str(value) if type(value) is int and 0 <= value <= 2 else "other"


def _safe_boundary_status_classes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 2:
        return ("other",) if value else ()
    result: list[str] = []
    for status in value:
        result.append(
            f"{status // 100}xx"
            if type(status) is int and 100 <= status <= 599
            else "other"
        )
    return tuple(result)


def _safe_boundary_content_classes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 2:
        return ("other",) if value else ()
    return tuple(
        content if isinstance(content, str) and content in _BOUNDARY_CONTENT_CLASSES else "other"
        for content in value
    )


def _safe_snapshot_event_entries(value: object) -> tuple[tuple[str, int | str], ...]:
    if not isinstance(value, dict) or len(value) > _SSE_EVENT_RUN_LIMIT:
        return (("other", "other"),) if value else ()
    entries: list[tuple[str, int | str]] = []
    for event, count in sorted(value.items(), key=lambda item: str(item[0])):
        safe_event = event if isinstance(event, str) and event in _BOUNDARY_EVENT_CLASSES else "other"
        safe_count = count if type(count) is int and 0 <= count <= _SSE_EVENT_COUNT_LIMIT else "other"
        entries.append((safe_event, safe_count))
    return tuple(entries)


def _safe_snapshot_trace(value: object) -> tuple[tuple[str, int | str], ...]:
    if not isinstance(value, list) or len(value) > _SSE_EVENT_RUN_LIMIT:
        return (("other", "other"),) if value else ()
    entries: list[tuple[str, int | str]] = []
    for item in value:
        if not isinstance(item, dict):
            entries.append(("other", "other"))
            continue
        event = item.get("event")
        count = item.get("count")
        safe_event = event if isinstance(event, str) and event in _BOUNDARY_EVENT_CLASSES else "other"
        safe_count = count if type(count) is int and 0 <= count <= _SSE_EVENT_COUNT_LIMIT else "other"
        entries.append((safe_event, safe_count))
    return tuple(entries)


def _safe_sse_ordinal(
    structures: object,
    index: int,
    *,
    handler_error: bool = False,
    upstream_truncated: bool = False,
) -> _SafeSSEOrdinal:
    if not isinstance(structures, list) or index >= len(structures) or not isinstance(structures[index], dict):
        return _SafeSSEOrdinal(
            False, False, False, (), (), False, False, False, False, False, False,
            False, "missing", False, "missing", False, False, False, False, False, handler_error,
            upstream_truncated,
        )
    structure = structures[index]
    counts = structure.get("event_counts")
    count_map = counts if isinstance(counts, dict) else {}
    return _SafeSSEOrdinal(
        True,
        structure.get("invalid") is True,
        _stream_has_valid_completion(structure),
        _safe_snapshot_event_entries(counts),
        _safe_snapshot_trace(structure.get("event_trace")),
        structure.get("event_trace_overflow") is True,
        count_map.get("response.created") == 1,
        count_map.get("response.completed") == 1,
        structure.get("response_id_relation") is True,
        structure.get("created_status_in_progress") is True,
        structure.get("completed_status_completed") is True,
        structure.get("model_matches") is True,
        (
            "missing"
            if "terminal_output_shape" not in structure
            else structure.get("terminal_output_shape")
            if structure.get("terminal_output_shape") in _BOUNDARY_TERMINAL_SHAPES
            else "other"
        ),
        structure.get("completed_usage_valid") is True,
        (
            "missing"
            if "completed_usage_valid" not in structure
            else "valid"
            if structure.get("completed_usage_valid") is True
            else "invalid"
        ),
        structure.get("duplicates") is True,
        structure.get("unknown_events") is True,
        structure.get("error_event") is True,
        structure.get("normal_close") is True,
        structure.get("downstream_closed_early") is True,
        handler_error,
        upstream_truncated,
    )


def _safe_boundary_class_list(
    value: object, mapper: Callable[[object], str]
) -> tuple[str, ...]:
    raw = value if isinstance(value, (list, tuple)) else ()
    return tuple(mapper(item) for item in raw[:2])


def _safe_boundary_identity_facts(value: object) -> tuple[tuple[tuple[str, object], ...], ...]:
    raw = value if isinstance(value, list) else ()
    result: list[tuple[tuple[str, object], ...]] = []
    for item in raw[:2]:
        facts: dict[str, object] = {
            name: False
            for name in _LOCAL_SIGNED_IDENTITY_FACT_KEYS
            if name not in {"required_header_cardinality_class", "signed_identity_class"}
        }
        facts["required_header_cardinality_class"] = "other"
        facts["signed_identity_class"] = "other"
        if isinstance(item, dict):
            for name in facts:
                if name in {"required_header_cardinality_class", "signed_identity_class"}:
                    continue
                facts[name] = item.get(name) is True
            cardinality = item.get("required_header_cardinality_class")
            facts["required_header_cardinality_class"] = (
                cardinality
                if cardinality in _LOCAL_SIGNED_HEADER_CARDINALITY_CLASSES
                else "other"
            )
            identity_class = item.get("signed_identity_class")
            facts["signed_identity_class"] = (
                identity_class
                if identity_class in _LOCAL_SIGNED_IDENTITY_CLASSES
                else "other"
            )
        result.append(tuple(sorted(facts.items())))
    return tuple(result)


def _safe_boundary_stage_class(value: object) -> str:
    if isinstance(value, str) and value in _LOCAL_REJECTION_STAGES:
        return value
    return _safe_local_rejection_stage(value)


def _qwen_inference_boundary_status(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result = dict(value)
    result["response_statuses"] = value.get("inference_statuses", [])
    result["response_content_type_classes"] = value.get(
        "inference_content_type_classes", []
    )
    return result


def _safe_boundary_section(
    status: object,
    request_count: object,
    *,
    local_boundary: bool = False,
    error_code_classes: object = (),
    error_param_classes: object = (),
    error_stage_classes: object = (),
    boundary_states: object = (),
    signed_identity_facts: object = (),
) -> _SafeBoundarySection:
    value = status if isinstance(status, dict) else {}
    structures = value.get("sse_structures")
    structure_count = len(structures) if isinstance(structures, list) else "other"
    return _SafeBoundarySection(
        _safe_count_class(request_count),
        _safe_count_class(
            len(value.get("response_statuses"))
            if isinstance(value.get("response_statuses"), list)
            else "other"
        ),
        _safe_boundary_status_classes(value.get("response_statuses")),
        _safe_boundary_content_classes(value.get("response_content_type_classes")),
        _safe_count_class(structure_count),
        tuple(
            _safe_sse_ordinal(
                structures,
                index,
                handler_error=value.get("handler_error") is True,
                upstream_truncated=value.get("upstream_truncated") is True,
            )
            for index in range(min(2, len(structures) if isinstance(structures, list) else 0))
        ),
        value.get("handler_error") is True,
        value.get("upstream_truncated") is True,
        value.get("downstream_closed_early") is True,
        value.get("stream_normal_close") is True,
        _safe_boundary_class_list(
            error_code_classes,
            _safe_local_error_code_class
            if local_boundary
            else _safe_gateway_error_code_class,
        ),
        _safe_boundary_class_list(error_param_classes, _safe_gateway_error_param_class),
        _safe_boundary_class_list(error_stage_classes, _safe_boundary_stage_class),
        tuple(
            (name, state if state in _BOUNDARY_STATES else "unknown")
            for name in ("tool_policy", "observation", "constitution", "upstream")
            for state in (
                boundary_states.get(name, "unknown")
                if isinstance(boundary_states, dict)
                else "unknown",
            )
        ),
        _safe_boundary_identity_facts(signed_identity_facts),
    )


def _safe_boundary_snapshot(
    *,
    gateway_status: object,
    gateway_request_count: object,
    local_status: object,
    local_request_count: object,
    qwen_status: object,
    accounting_statuses: object,
    codex_provenance: object = None,
    codex_exit_success: bool = False,
) -> _SafeBoundarySnapshot:
    gateway = gateway_status if isinstance(gateway_status, dict) else {}
    local = local_status if isinstance(local_status, dict) else {}
    qwen = _qwen_inference_boundary_status(qwen_status)
    accounting = accounting_statuses if isinstance(accounting_statuses, dict) else {}
    accounting_values: list[tuple[str, str | bool]] = []
    for name in (
        "reservation_finalized", "reservation_released", "reservation_pending",
        "ledger_finalized", "ledger_failed", "ledger_estimated", "ledger_pending",
    ):
        accounting_values.append((name, _safe_count_class(accounting.get(name))))
    accounting_values.extend(
        (
            ("query_ok", accounting.get("query_ok") is True),
            (
                "zero_pending",
                accounting.get("reservation_pending") == 0
                and accounting.get("ledger_pending") == 0,
            ),
        )
    )
    provenance_class = "unknown"
    if isinstance(codex_provenance, dict):
        provenance_class = (
            "task_local_exact_npm"
            if codex_provenance.get("source_class") == "task_local_exact_npm"
            and codex_provenance.get("verified_binary_is_invoked") is True
            else "other"
        )
    return _SafeBoundarySnapshot(
        _safe_boundary_section(
            gateway,
            gateway_request_count,
            error_code_classes=gateway.get("error_code_classes"),
            error_param_classes=gateway.get("error_param_classes"),
        ),
        _safe_boundary_section(
            local,
            local_request_count,
            local_boundary=True,
            error_code_classes=local.get("local_error_code_classes"),
            error_param_classes=local.get("error_param_classes"),
            error_stage_classes=local.get("local_error_stage_classes"),
            boundary_states=local.get("local_boundary_states"),
            signed_identity_facts=local.get("signed_identity_facts"),
        ),
        _safe_boundary_section(qwen, qwen.get("inference_calls")),
        _safe_count_class(qwen.get("inference_calls")),
        _safe_count_class(qwen.get("successful_calls")),
        _safe_count_class(qwen.get("compiler_calls")),
        tuple(accounting_values),
        codex_exit_success,
        provenance_class,
    )


def _safe_boundary_snapshot_validate(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "outcome", "assertion_class", "gateway", "local", "qwen", "accounting", "codex"
    } or value["schema"] != "composed_boundary_snapshot_v1":
        raise VerificationError("boundary_snapshot_invalid")
    if value["outcome"] not in {
        "local_turn2_rejected_before_qwen",
        "local_invoked_qwen_turn2_qwen_rejected_or_failed",
        "qwen_turn2_completed_local_stream_invalid",
        "local_qwen_turn2_completed_gateway_stream_invalid",
        "producer_boundaries_valid_verifier_expectation_wrong",
        "full_two_turn_path_succeeded",
        "other",
    }:
        raise VerificationError("boundary_snapshot_invalid")
    if not isinstance(value["assertion_class"], str) or value["assertion_class"] not in {
        "none", "gateway_sse_invalid", "local_sse_invalid", "qwen_sse_invalid",
        "lifecycle_invalid", "boundary_invalid", "accounting_invalid", "other",
    }:
        raise VerificationError("boundary_snapshot_invalid")
    # Rebuild only fixed, bounded keys; reject any extra or malformed nested data.
    for section_name in ("gateway", "local", "qwen"):
        section = value[section_name]
        if not isinstance(section, dict):
            raise VerificationError("boundary_snapshot_invalid")
        required = {
            "request_count", "response_count", "response_status_classes", "content_type_classes",
            "sse_structure_count", "ordinals", "handler_error", "upstream_truncated",
            "downstream_closed_early", "normal_close", "error_code_classes", "error_param_classes",
            "error_stage_classes", "boundary_states", "signed_identity_facts",
        }
        if section_name == "qwen":
            required |= {"inference_count", "successful_count", "compiler_count"}
        if set(section) != required:
            raise VerificationError("boundary_snapshot_invalid")
        for key in ("request_count", "response_count", "sse_structure_count"):
            if section[key] not in _BOUNDARY_COUNT_CLASSES:
                raise VerificationError("boundary_snapshot_invalid")
        for key in ("response_status_classes", "content_type_classes", "error_code_classes", "error_param_classes", "error_stage_classes"):
            if not isinstance(section[key], list) or len(section[key]) > 2 or any(not isinstance(item, str) for item in section[key]):
                raise VerificationError("boundary_snapshot_invalid")
        if any(item not in _BOUNDARY_STATUS_CLASSES for item in section["response_status_classes"]):
            raise VerificationError("boundary_snapshot_invalid")
        if any(item not in _BOUNDARY_CONTENT_CLASSES for item in section["content_type_classes"]):
            raise VerificationError("boundary_snapshot_invalid")
        if any(item not in (_SUMMARY_GATEWAY_ERROR_CODE_CLASSES | _SUMMARY_LOCAL_ERROR_CODE_CLASSES) for item in section["error_code_classes"]):
            raise VerificationError("boundary_snapshot_invalid")
        if any(item not in _SUMMARY_GATEWAY_ERROR_PARAM_CLASSES for item in section["error_param_classes"]):
            raise VerificationError("boundary_snapshot_invalid")
        if any(item not in _SUMMARY_LOCAL_REJECTION_STAGES for item in section["error_stage_classes"]):
            raise VerificationError("boundary_snapshot_invalid")
        if any(
            type(section[name]) is not bool
            for name in (
                "handler_error",
                "upstream_truncated",
                "downstream_closed_early",
                "normal_close",
            )
        ):
            raise VerificationError("boundary_snapshot_invalid")
        if not isinstance(section["boundary_states"], dict) or set(section["boundary_states"]) - {
            "tool_policy", "observation", "constitution", "upstream"
        }:
            raise VerificationError("boundary_snapshot_invalid")
        if any(state not in _BOUNDARY_STATES for state in section["boundary_states"].values()):
            raise VerificationError("boundary_snapshot_invalid")
        signed_identity_facts = section["signed_identity_facts"]
        if not isinstance(signed_identity_facts, list) or len(signed_identity_facts) > 2:
            raise VerificationError("boundary_snapshot_invalid")
        for fact in signed_identity_facts:
            if not isinstance(fact, dict) or set(fact) != _LOCAL_SIGNED_IDENTITY_FACT_KEYS:
                raise VerificationError("boundary_snapshot_invalid")
            if any(
                type(fact[name]) is not bool
                for name in _LOCAL_SIGNED_IDENTITY_FACT_KEYS
                if name not in {"required_header_cardinality_class", "signed_identity_class"}
            ):
                raise VerificationError("boundary_snapshot_invalid")
            if fact["required_header_cardinality_class"] not in _LOCAL_SIGNED_HEADER_CARDINALITY_CLASSES:
                raise VerificationError("boundary_snapshot_invalid")
            if fact["signed_identity_class"] not in _LOCAL_SIGNED_IDENTITY_CLASSES:
                raise VerificationError("boundary_snapshot_invalid")
        if not isinstance(section["ordinals"], list) or len(section["ordinals"]) > 2:
            raise VerificationError("boundary_snapshot_invalid")
        for ordinal in section["ordinals"]:
            if not isinstance(ordinal, dict) or set(ordinal) != {
                "present", "invalid", "valid_completion", "event_counts", "event_trace",
                "event_trace_overflow", "created_exactly_once", "completed_exactly_once",
                "response_id_relation", "created_status_in_progress", "completed_status_completed",
                "model_matches", "terminal_output_shape", "completed_usage_valid", "completed_usage_shape", "duplicates",
                "unknown_events", "error_event", "normal_close", "downstream_closed_early",
                "handler_error", "upstream_truncated",
            }:
                raise VerificationError("boundary_snapshot_invalid")
            if ordinal["terminal_output_shape"] not in _BOUNDARY_TERMINAL_SHAPES:
                raise VerificationError("boundary_snapshot_invalid")
            if ordinal["completed_usage_shape"] not in _BOUNDARY_USAGE_SHAPES:
                raise VerificationError("boundary_snapshot_invalid")
            if not isinstance(ordinal["event_counts"], dict) or len(ordinal["event_counts"]) > _SSE_EVENT_RUN_LIMIT:
                raise VerificationError("boundary_snapshot_invalid")
            if any(
                not isinstance(event, str)
                or event not in _BOUNDARY_EVENT_CLASSES
                or not (
                    type(count) is int
                    and 0 <= count <= _SSE_EVENT_COUNT_LIMIT
                    or count == "other"
                )
                for event, count in ordinal["event_counts"].items()
            ):
                raise VerificationError("boundary_snapshot_invalid")
            if not isinstance(ordinal["event_trace"], list) or len(ordinal["event_trace"]) > _SSE_EVENT_RUN_LIMIT:
                raise VerificationError("boundary_snapshot_invalid")
            if any(
                not isinstance(item, dict)
                or set(item) != {"event", "count"}
                or item["event"] not in _BOUNDARY_EVENT_CLASSES
                or not (
                    type(item["count"]) is int
                    and 0 <= item["count"] <= _SSE_EVENT_COUNT_LIMIT
                    or item["count"] == "other"
                )
                for item in ordinal["event_trace"]
            ):
                raise VerificationError("boundary_snapshot_invalid")
            if any(not isinstance(item, bool) for key, item in ordinal.items() if key not in {"event_counts", "event_trace", "terminal_output_shape", "completed_usage_shape"}):
                raise VerificationError("boundary_snapshot_invalid")
    qwen = value["qwen"]
    if not isinstance(qwen, dict) or set(qwen) != {
        "request_count", "response_count", "response_status_classes", "content_type_classes",
        "sse_structure_count", "ordinals", "handler_error", "upstream_truncated",
        "downstream_closed_early", "normal_close", "error_code_classes", "error_param_classes",
        "error_stage_classes", "boundary_states", "signed_identity_facts",
        "inference_count", "successful_count", "compiler_count",
    }:
        raise VerificationError("boundary_snapshot_invalid")
    for key in ("inference_count", "successful_count", "compiler_count"):
        if qwen[key] not in _BOUNDARY_COUNT_CLASSES:
            raise VerificationError("boundary_snapshot_invalid")
    accounting = value["accounting"]
    if not isinstance(accounting, dict) or set(accounting) != {
        "reservation_finalized", "reservation_released", "reservation_pending", "ledger_finalized",
        "ledger_failed", "ledger_estimated", "ledger_pending", "query_ok", "zero_pending",
    } or any(accounting[key] not in _BOUNDARY_COUNT_CLASSES for key in set(accounting) - {"query_ok", "zero_pending"}) or any(type(accounting[key]) is not bool for key in ("query_ok", "zero_pending")):
        raise VerificationError("boundary_snapshot_invalid")
    codex = value["codex"]
    if not isinstance(codex, dict) or set(codex) != {"exit_success", "provenance_class"} or type(codex["exit_success"]) is not bool or codex["provenance_class"] not in {"task_local_exact_npm", "unknown", "other"}:
        raise VerificationError("boundary_snapshot_invalid")
    return json.loads(json.dumps(value, separators=(",", ":"), sort_keys=True))


def _classify_boundary_snapshot(snapshot: _SafeBoundarySnapshot, *, assertion_failed: bool) -> str:
    gateway_second = snapshot.gateway.ordinals[1] if len(snapshot.gateway.ordinals) > 1 else None
    local_second = snapshot.local.ordinals[1] if len(snapshot.local.ordinals) > 1 else None
    qwen_second = snapshot.qwen.ordinals[1] if len(snapshot.qwen.ordinals) > 1 else None
    local_second_failed = (
        len(snapshot.local.response_status_classes) > 1
        and snapshot.local.response_status_classes[1] in {"4xx", "5xx"}
    )
    qwen_second_failed = (
        len(snapshot.qwen.response_status_classes) > 1
        and snapshot.qwen.response_status_classes[1] in {"4xx", "5xx"}
    )
    if local_second_failed and snapshot.qwen_inference_count in {"0", "1"}:
        return "local_turn2_rejected_before_qwen"
    if qwen_second_failed:
        return "local_invoked_qwen_turn2_qwen_rejected_or_failed"
    local_valid = local_second is not None and local_second.valid_completion
    qwen_valid = qwen_second is not None and qwen_second.valid_completion
    gateway_valid = gateway_second is not None and gateway_second.valid_completion
    if qwen_valid and not local_valid:
        return "qwen_turn2_completed_local_stream_invalid"
    if local_valid and qwen_valid and not gateway_valid:
        return "local_qwen_turn2_completed_gateway_stream_invalid"
    if local_valid and qwen_valid and gateway_valid and assertion_failed:
        return "producer_boundaries_valid_verifier_expectation_wrong"
    if local_valid and qwen_valid and gateway_valid and not assertion_failed:
        return "full_two_turn_path_succeeded"
    return "other"


def _safe_boundary_assertion_class(code: object) -> str:
    if code in {
        "composed_tool_roundtrip_gateway_sse_invalid",
        "composed_tool_roundtrip_gateway_lifecycle_invalid",
    }:
        return "gateway_sse_invalid" if code.endswith("sse_invalid") else "lifecycle_invalid"
    if code == "composed_tool_roundtrip_local_sse_invalid":
        return "local_sse_invalid"
    if code == "composed_tool_roundtrip_qwen_sse_invalid":
        return "qwen_sse_invalid"
    if code == "composed_tool_roundtrip_boundary_invalid":
        return "boundary_invalid"
    if code == "composed_tool_roundtrip_accounting_rows":
        return "accounting_invalid"
    return "none" if code is None else "other"


def _terminal_completion_valid(observation: dict[str, object]) -> bool:
    """Validate terminal semantics independently from event vocabulary."""
    if "normalization_status" in observation:
        positive_facts = (
            "response_id_relation", "created_status_in_progress",
            "completed_status_completed", "model_matches", "completed_usage_valid",
            "first_event_before_upstream_completion", "normal_close",
        )
        counts = observation.get("event_counts")
        positive = all(observation.get(field) is True for field in positive_facts)
        negative = all(
            observation.get(field) is False
            for field in (
                "handler_error", "upstream_truncated", "error_event",
                "event_trace_overflow",
            )
        )
        official = observation.get("official_client_completion")
        official_ok = official is None or official is True
        return (
            observation.get("normalization_status") == "complete"
            and observation.get("http_status_class") == "2xx"
            and observation.get("content_type_class") == "sse"
            and observation.get("response_completed") is True
            and isinstance(counts, dict)
            and counts.get("response.created") == 1
            and counts.get("response.completed") == 1
            and positive
            and observation.get("terminal_output_shape") in {"empty_array", "nonempty_array"}
            and official_ok
            and negative
        )
    return _stream_has_valid_completion(observation.get("structure"))


def _event_vocabulary_reviewed(observation: dict[str, object]) -> bool:
    return (
        observation.get("unknown_events") is False
        and observation.get("error_event") is not True
    )


def _classify_stream_differential(
    direct_qwen: dict[str, object],
    local_output: dict[str, object],
    gateway_output: dict[str, object],
) -> str:
    if any(
        _stream_observation_is_ambiguous(observation)
        for observation in (direct_qwen, local_output, gateway_output)
    ):
        return "ambiguous_stream_evidence"
    if not _terminal_completion_valid(direct_qwen):
        return "qwen_owned"
    if not _terminal_completion_valid(local_output):
        return "local_owned"
    if not _terminal_completion_valid(gateway_output):
        return "gateway_owned"
    if gateway_output.get("client_completed") is not True:
        return "official_client_observation"
    return "all_boundaries_completed"


def _classify_direct_stream(direct_qwen: dict[str, object]) -> str | None:
    if _stream_observation_is_ambiguous(direct_qwen):
        return "ambiguous_stream_evidence"
    if not _terminal_completion_valid(direct_qwen):
        return "qwen_owned"
    return None


_STREAM_BOUNDARIES = ("direct_qwen", "local_output", "gateway_output")
_STREAM_STATUS_CLASSES = frozenset({"2xx", "4xx", "5xx", "unknown"})
_STREAM_CONTENT_TYPES = frozenset({"sse", "json", "other", "unknown"})
_STREAM_DECISIONS = frozenset(
    {
        "ambiguous_stream_evidence",
        "qwen_owned",
        "local_owned",
        "local_qwen_owned",
        "gateway_owned",
        "official_client_observation",
        "all_boundaries_completed",
        "terminal_boundaries_completed",
    }
)
_STREAM_FAILURE_CODES = frozenset(
    {
        "none",
        "direct_qwen_client_stream_failed",
        "composed_client_stream_failed",
        "handler_error",
        "unknown_failure",
    }
)
_STREAM_TERMINAL_SHAPES = frozenset({"missing", "empty_array", "nonempty_array", "other"})
_STREAM_NORMALIZATION_STATUSES = frozenset({"complete", "degraded", "invalid"})
_STREAM_EVIDENCE_SOURCES = frozenset({"pinned_155l", "current_155r", "not_run"})
_STREAM_NORMALIZATION_REASONS = frozenset(
    {
        "none",
        "not_run",
        "missing_structure",
        "invalid_shape",
        "producer_status_invalid",
        "producer_content_type_invalid",
        "event_trace_invalid",
        "event_count_invalid",
        "trace_overflow",
        "inconsistent_completion",
        "error_event",
        "handler_error",
        "upstream_truncated",
        "non_sse",
        "unknown_failure",
    }
)


def _minimal_stream_summary(
    boundary: str, *, ran: bool, decision: str, reason: str
) -> dict[str, object]:
    status = "degraded" if not ran or reason == "missing_structure" else "invalid"
    return {
        "boundary": boundary,
        "ran": ran,
        "evidence_source": "current_155r" if ran else "not_run",
        "ran_current_invocation": ran,
        "http_status_class": "unknown",
        "content_type_class": "unknown",
        "event_trace": [],
        "event_counts": {},
        "invalid": True,
        "response_completed": False,
        "duplicates": False,
        "unknown_events": False,
        "error_event": False,
        "error_field_names": [],
        "error_code_class": "unknown",
        "error_type_class": "unknown",
        "event_vocabulary_reviewed": False,
        "done_sentinel": False,
        "response_id_relation": False,
        "created_status_in_progress": False,
        "completed_status_completed": False,
        "model_matches": False,
        "completed_output_empty": False,
        "completed_usage_valid": False,
        "terminal_output_shape": "missing",
        "first_event_before_upstream_completion": False,
        "normal_close": False,
        "downstream_closed_early": False,
        "handler_error": False,
        "upstream_truncated": False,
        "official_client_completion": False,
        "event_trace_overflow": False,
        "terminal_completion_valid": False,
        "valid_completion": False,
        "normalization_status": status,
        "normalization_reason": reason if reason in _STREAM_NORMALIZATION_REASONS else "invalid_shape",
        "failure_code": "unknown_failure" if ran else "none",
        "decision": decision,
    }


def _bounded_event_trace(
    structure: dict[str, object]
) -> tuple[list[dict[str, object]], dict[str, int], bool, str]:
    raw_trace = structure.get("event_trace")
    sequence = structure.get("event_sequence")
    reason = "none"
    trace: list[dict[str, object]] = []
    if isinstance(raw_trace, list):
        for run in raw_trace:
            if (
                not isinstance(run, dict)
                or not isinstance(run.get("event"), str)
                or run["event"] not in _SAFE_SSE_EVENT_TYPES
                or type(run.get("count")) is not int
                or run["count"] < 1
                or run["count"] > _SSE_EVENT_COUNT_LIMIT
            ):
                reason = "event_trace_invalid"
                trace = []
                break
            trace.append({"event": run["event"], "count": run["count"]})
        if len(trace) > _SSE_EVENT_RUN_LIMIT:
            trace = trace[:_SSE_EVENT_RUN_LIMIT]
            reason = "trace_overflow"
    elif isinstance(sequence, list):
        for event in sequence:
            if not isinstance(event, str) or event not in _SAFE_SSE_EVENT_TYPES:
                reason = "event_trace_invalid"
                trace = []
                break
            if trace and trace[-1]["event"] == event:
                trace[-1]["count"] = int(trace[-1]["count"]) + 1
            elif len(trace) < _SSE_EVENT_RUN_LIMIT:
                trace.append({"event": event, "count": 1})
            else:
                reason = "trace_overflow"
    else:
        return [], {}, False, "event_trace_invalid"
    counts: dict[str, int] = {}
    raw_counts = structure.get("event_counts")
    if isinstance(raw_counts, dict):
        for event, count in raw_counts.items():
            if (
                not isinstance(event, str)
                or event not in _SAFE_SSE_EVENT_TYPES
                or type(count) is not int
                or count < 0
                or count > _SSE_EVENT_COUNT_LIMIT
            ):
                reason = "event_count_invalid"
                counts = {}
                break
            counts[event] = count
    if not counts:
        for run in trace:
            event = str(run["event"])
            counts[event] = counts.get(event, 0) + int(run["count"])
    if isinstance(sequence, list) and reason == "none":
        sequence_counts = {event: sequence.count(event) for event in sorted(set(sequence)) if isinstance(event, str)}
        if counts != sequence_counts:
            reason = "event_count_invalid"
            counts = sequence_counts
    overflow = structure.get("event_trace_overflow")
    if type(overflow) is not bool:
        overflow = reason == "trace_overflow"
        if reason == "none":
            reason = "event_trace_invalid"
    if overflow is True and reason == "none":
        reason = "trace_overflow"
    return trace, counts, overflow, reason


def _safe_stream_summary(
    observation: object,
    *,
    decision: str,
    boundary: str | None = None,
    ran: bool = True,
) -> dict[str, object]:
    """Total, raw-free normalization of one producer observation."""
    if isinstance(observation, dict) and "normalization_status" in observation:
        normalized_boundary = boundary or observation.get("boundary")
        required = {
            "boundary", "ran", "evidence_source", "ran_current_invocation",
            "http_status_class", "content_type_class", "event_trace",
            "event_counts", "invalid", "response_completed", "duplicates", "unknown_events",
            "error_event", "error_field_names", "error_code_class", "error_type_class",
            "event_vocabulary_reviewed", "terminal_completion_valid",
            "done_sentinel", "response_id_relation", "created_status_in_progress",
            "completed_status_completed", "model_matches", "completed_output_empty",
            "completed_usage_valid", "terminal_output_shape", "first_event_before_upstream_completion",
            "normal_close", "downstream_closed_early", "handler_error", "upstream_truncated",
            "official_client_completion", "event_trace_overflow", "terminal_completion_valid", "valid_completion",
            "normalization_status", "normalization_reason", "failure_code", "decision",
        }
        trace = observation.get("event_trace")
        counts = observation.get("event_counts")
        safe_trace = (
            isinstance(trace, list)
            and len(trace) <= _SSE_EVENT_RUN_LIMIT
            and all(
                isinstance(run, dict)
                and set(run) == {"event", "count"}
                and isinstance(run["event"], str)
                and run["event"] in _SAFE_SSE_EVENT_TYPES
                and type(run["count"]) is int
                and 1 <= run["count"] <= _SSE_EVENT_COUNT_LIMIT
                for run in trace
            )
        )
        safe_counts = (
            isinstance(counts, dict)
            and all(
                isinstance(event, str)
                and event in _SAFE_SSE_EVENT_TYPES
                and type(count) is int
                and 0 <= count <= _SSE_EVENT_COUNT_LIMIT
                for event, count in counts.items()
            )
        )
        safe_booleans = (
            required.issubset(observation)
            and all(type(observation.get(field)) is bool for field in (
                "ran", "invalid", "response_completed", "duplicates", "unknown_events", "error_event", "event_vocabulary_reviewed",
                "ran_current_invocation",
                "done_sentinel", "response_id_relation", "created_status_in_progress",
                "completed_status_completed", "model_matches", "completed_output_empty",
                "completed_usage_valid", "first_event_before_upstream_completion", "normal_close",
                "downstream_closed_early", "handler_error", "upstream_truncated",
                "official_client_completion", "event_trace_overflow", "terminal_completion_valid", "valid_completion",
            ))
        )
        if (
            not isinstance(normalized_boundary, str)
            or normalized_boundary not in _STREAM_BOUNDARIES
            or not isinstance(observation.get("http_status_class"), str)
            or observation.get("http_status_class") not in _STREAM_STATUS_CLASSES
            or not isinstance(observation.get("content_type_class"), str)
            or observation.get("content_type_class") not in _STREAM_CONTENT_TYPES
            or not safe_trace
            or not safe_counts
            or not safe_booleans
            or not isinstance(observation.get("normalization_status"), str)
            or observation.get("normalization_status") not in _STREAM_NORMALIZATION_STATUSES
            or not isinstance(observation.get("normalization_reason"), str)
            or observation.get("normalization_reason") not in _STREAM_NORMALIZATION_REASONS
            or not isinstance(observation.get("failure_code"), str)
            or observation.get("failure_code") not in _STREAM_FAILURE_CODES
            or not isinstance(observation.get("terminal_output_shape"), str)
            or observation.get("terminal_output_shape") not in _STREAM_TERMINAL_SHAPES
            or not isinstance(observation.get("evidence_source"), str)
            or observation.get("evidence_source") not in _STREAM_EVIDENCE_SOURCES
            or not isinstance(observation.get("error_field_names"), list)
            or any(
                not isinstance(field, str) or field not in _SAFE_ERROR_FIELD_NAMES
                for field in observation.get("error_field_names", [])
            )
            or not isinstance(observation.get("error_code_class"), str)
            or observation.get("error_code_class") not in _COMPOSED_ERROR_CLASSES
            or not isinstance(observation.get("error_type_class"), str)
            or observation.get("error_type_class") not in _COMPOSED_ERROR_CLASSES
            or observation.get("ran") is not ran
            or (
                observation.get("evidence_source") == "pinned_155l"
                and observation.get("ran_current_invocation") is not False
            )
            or (
                observation.get("evidence_source") == "current_155r"
                and (
                    observation.get("ran") is not True
                    or observation.get("ran_current_invocation") is not True
                )
            )
            or (
                observation.get("evidence_source") == "not_run"
                and (
                    observation.get("ran") is not False
                    or observation.get("ran_current_invocation") is not False
                )
            )
        ):
            fallback_boundary = (
                normalized_boundary
                if isinstance(normalized_boundary, str)
                and normalized_boundary in _STREAM_BOUNDARIES
                else "direct_qwen"
            )
            return _minimal_stream_summary(
                fallback_boundary,
                ran=ran,
                decision=decision,
                reason="invalid_shape",
            )
        return {
            key: observation[key]
            for key in (
                "boundary", "ran", "http_status_class", "content_type_class", "event_trace",
                "event_counts", "invalid", "response_completed", "duplicates", "unknown_events", "error_event",
                "error_field_names", "error_code_class", "error_type_class",
                "evidence_source", "ran_current_invocation",
                "event_vocabulary_reviewed", "terminal_completion_valid",
                "done_sentinel", "response_id_relation", "created_status_in_progress",
                "completed_status_completed", "model_matches", "completed_output_empty",
                "completed_usage_valid", "terminal_output_shape", "first_event_before_upstream_completion",
                "normal_close", "downstream_closed_early", "handler_error", "upstream_truncated",
                "official_client_completion", "event_trace_overflow", "valid_completion",
                "normalization_status", "normalization_reason", "failure_code", "decision",
            )
        } | {
            "boundary": normalized_boundary,
            "ran": ran,
            "decision": decision,
            "event_trace": [{"event": run["event"], "count": run["count"]} for run in trace],
            "event_counts": {event: counts[event] for event in sorted(counts)},
        }
    if boundary not in _STREAM_BOUNDARIES:
        boundary = observation.get("boundary") if isinstance(observation, dict) else None
    if boundary not in _STREAM_BOUNDARIES:
        return _minimal_stream_summary("direct_qwen", ran=ran, decision=decision, reason="invalid_shape")
    if not ran:
        return _minimal_stream_summary(boundary, ran=False, decision=decision, reason="not_run")
    if not isinstance(observation, dict):
        return _minimal_stream_summary(boundary, ran=True, decision=decision, reason="invalid_shape")
    status_class = observation.get("http_status_class")
    content_type = observation.get("content_type_class")
    reason = "none"
    if not isinstance(status_class, str) or status_class not in _STREAM_STATUS_CLASSES:
        status_class = "unknown"
        reason = "producer_status_invalid"
    if not isinstance(content_type, str) or content_type not in _STREAM_CONTENT_TYPES:
        content_type = "unknown"
        reason = "producer_content_type_invalid"
    structure = observation.get("structure")
    if structure is None:
        return _minimal_stream_summary(boundary, ran=True, decision=decision, reason="missing_structure") | {
            "http_status_class": status_class,
            "content_type_class": content_type,
            "official_client_completion": observation.get("client_completed") is True,
        }
    if not isinstance(structure, dict):
        return _minimal_stream_summary(boundary, ran=True, decision=decision, reason="invalid_shape") | {
            "http_status_class": status_class,
            "content_type_class": content_type,
        }
    trace, counts, overflow, trace_reason = _bounded_event_trace(structure)
    if trace_reason != "none":
        reason = trace_reason
    bool_fields = (
        "invalid", "done_sentinel", "duplicates", "unknown_events", "error_event",
        "event_vocabulary_reviewed", "response_id_relation",
        "created_status_in_progress", "completed_status_completed", "model_matches",
        "completed_output_empty", "completed_usage_valid", "first_event_before_upstream_completion",
        "normal_close", "downstream_closed_early",
    )
    facts = {field: structure.get(field) is True for field in bool_fields}
    facts["duplicates"] = facts["duplicates"] or any(
        counts.get(event, 0) > 1 for event in ("response.created", "response.completed")
    )
    missing_facts = any(field not in structure for field in bool_fields)
    if missing_facts and reason == "none":
        reason = "invalid_shape"
    if facts["invalid"] and reason == "none":
        reason = "invalid_shape"
    trace_response_completed = "response.completed" in {run["event"] for run in trace}
    producer_response_completed = observation.get("response_completed")
    response_completed = (
        producer_response_completed
        if type(producer_response_completed) is bool
        else trace_response_completed
    )
    if (
        not overflow
        and type(producer_response_completed) is bool
        and producer_response_completed != trace_response_completed
    ):
        reason = "inconsistent_completion"
    failure_code = observation.get("failure_code")
    if failure_code is None:
        failure_code = "none"
    if not isinstance(failure_code, str) or failure_code not in _STREAM_FAILURE_CODES:
        failure_code = "unknown_failure"
    handler_error = observation.get("handler_error") is True
    upstream_truncated = observation.get("upstream_truncated") is True
    if handler_error:
        reason = "handler_error"
        failure_code = "handler_error"
    elif upstream_truncated:
        reason = "upstream_truncated"
        failure_code = "unknown_failure"
    elif facts["error_event"]:
        reason = "error_event"
    elif content_type != "sse" and reason == "none":
        reason = "non_sse"
    if overflow:
        reason = "trace_overflow"
    terminal_shape = structure.get("terminal_output_shape")
    if not isinstance(terminal_shape, str) or terminal_shape not in _STREAM_TERMINAL_SHAPES:
        terminal_shape = "missing"
        if reason == "none":
            reason = "invalid_shape"
    status = "complete" if reason == "none" and not facts["invalid"] else "degraded"
    if reason in {"invalid_shape", "event_trace_invalid", "event_count_invalid", "inconsistent_completion"}:
        status = "invalid"
    summary = {
        "boundary": boundary,
        "ran": True,
        "evidence_source": (
            observation.get("evidence_source")
            if observation.get("evidence_source") in _STREAM_EVIDENCE_SOURCES
            else "current_155r"
        ),
        "ran_current_invocation": True,
        "http_status_class": status_class,
        "content_type_class": content_type,
        "event_trace": trace,
        "event_counts": counts,
        "invalid": facts["invalid"],
        "response_completed": response_completed,
        "duplicates": facts["duplicates"],
        "unknown_events": facts["unknown_events"],
        "error_event": facts["error_event"],
        "error_field_names": sorted(
            field for field in structure.get("error_field_names", [])
            if isinstance(field, str) and field in _SAFE_ERROR_FIELD_NAMES
        ) if isinstance(structure.get("error_field_names"), list) else [],
        "error_code_class": (
            structure.get("error_code_class")
            if isinstance(structure.get("error_code_class"), str)
            and structure.get("error_code_class") in _COMPOSED_ERROR_CLASSES
            else "unknown"
        ),
        "error_type_class": (
            structure.get("error_type_class")
            if isinstance(structure.get("error_type_class"), str)
            and structure.get("error_type_class") in _COMPOSED_ERROR_CLASSES
            else "unknown"
        ),
        "event_vocabulary_reviewed": facts["event_vocabulary_reviewed"],
        "done_sentinel": facts["done_sentinel"],
        "response_id_relation": facts["response_id_relation"],
        "created_status_in_progress": facts["created_status_in_progress"],
        "completed_status_completed": facts["completed_status_completed"],
        "model_matches": facts["model_matches"],
        "completed_output_empty": facts["completed_output_empty"],
        "completed_usage_valid": facts["completed_usage_valid"],
        "terminal_output_shape": terminal_shape,
        "first_event_before_upstream_completion": facts["first_event_before_upstream_completion"],
        "normal_close": facts["normal_close"],
        "downstream_closed_early": facts["downstream_closed_early"],
        "handler_error": handler_error,
        "upstream_truncated": upstream_truncated,
        "official_client_completion": observation.get("client_completed") is True,
        "event_trace_overflow": overflow,
        "normalization_status": status,
        "normalization_reason": reason,
        "failure_code": failure_code,
        "decision": decision,
    }
    summary["terminal_completion_valid"] = (
        status == "complete"
        and status_class == "2xx"
        and content_type == "sse"
        and response_completed
        and counts.get("response.created") == 1
        and counts.get("response.completed") == 1
        and facts["response_id_relation"]
        and facts["created_status_in_progress"]
        and facts["completed_status_completed"]
        and facts["model_matches"]
        and summary["terminal_output_shape"] in {"empty_array", "nonempty_array"}
        and facts["completed_usage_valid"]
        and facts["first_event_before_upstream_completion"]
        and facts["normal_close"]
        and not facts["duplicates"]
        and not facts["error_event"]
        and not handler_error
        and not upstream_truncated
        and not overflow
        and summary["official_client_completion"] is True
    )
    summary["valid_completion"] = summary["terminal_completion_valid"]
    return summary


def _stream_summary_lines(result: object) -> tuple[str, ...]:
    source = result if isinstance(result, dict) else {}
    decision = source.get("decision")
    if not isinstance(decision, str) or decision not in _STREAM_DECISIONS:
        decision = "ambiguous_stream_evidence"
    ran_boundaries = source.get("ran_boundaries")
    if not isinstance(ran_boundaries, list) or any(
        not isinstance(boundary, str) or boundary not in _STREAM_BOUNDARIES
        for boundary in ran_boundaries
    ):
        ran_boundaries = []
    ran_set = set(ran_boundaries)
    summaries = []
    for boundary in _STREAM_BOUNDARIES:
        summaries.append(
            _safe_stream_summary(
                source.get(boundary),
                boundary=boundary,
                ran=boundary in ran_set,
                decision=decision,
            )
        )
    lines = [
        *(
            "STREAM_BOUNDARY "
            + json.dumps(summary, sort_keys=True, separators=(",", ":"))
            for summary in summaries
        )
    ]
    if "composed_path" in source:
        lines.append(
            "COMPOSED_PATH "
            + json.dumps(
                _safe_composed_path(source.get("composed_path"), decision=decision),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    lines.append("STREAM_DECISION " + json.dumps(decision, separators=(",", ":")))
    return tuple(lines)


_COMPOSED_COUNT_CLASSES = frozenset({"zero", "one", "many"})
_COMPOSED_PATH_STATUS_CLASSES = frozenset({"2xx", "4xx", "5xx", "unknown"})
_COMPOSED_ERROR_CLASSES = frozenset(_SAFE_ERROR_VALUE_CLASSES | {"unknown"})


def _count_class(value: object) -> str:
    if type(value) is not int or value < 0:
        return "unknown"
    return "zero" if value == 0 else "one" if value == 1 else "many"


def _last_status_class(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "unknown"
    status = value[-1]
    if type(status) is not int or status < 100 or status > 599:
        return "unknown"
    return f"{status // 100}xx" if status // 100 in {2, 4, 5} else "unknown"


def _last_content_class(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "unknown"
    content = value[-1]
    return content if content in {"sse", "json", "other"} else "unknown"


def _safe_composed_path(value: object, *, decision: str) -> dict[str, object]:
    if not isinstance(value, dict):
        value = {}
    count_fields = (
        "gateway_to_local_request_count_class",
        "gateway_to_local_response_count_class",
        "local_to_qwen_inference_call_count_class",
        "qwen_upstream_response_count_class",
    )
    status_fields = (
        "local_response_status_class",
        "qwen_upstream_status_class",
    )
    bool_fields = (
        "local_rejected", "local_handler_error", "local_upstream_truncated",
        "local_downstream_closed_early", "qwen_terminal_completion_valid",
        "qwen_handler_error", "qwen_upstream_truncated", "qwen_path_rejection",
        "gateway_error_event", "gateway_accounting_terminal",
        "local_terminal_completion_valid",
    )
    def choice(field: str, choices: frozenset[str]) -> str:
        candidate = value.get(field)
        return candidate if isinstance(candidate, str) and candidate in choices else "unknown"

    result = {field: choice(field, _COMPOSED_COUNT_CLASSES) for field in count_fields}
    result.update({
        field: choice(field, _COMPOSED_PATH_STATUS_CLASSES)
        for field in status_fields
    })
    result.update({field: value.get(field) is True for field in bool_fields})
    result.update({
        "local_response_content_type_class": (
            value.get("local_response_content_type_class")
            if isinstance(value.get("local_response_content_type_class"), str)
            and value.get("local_response_content_type_class") in {"sse", "json", "other", "unknown"}
            else "unknown"
        ),
        "qwen_upstream_content_type_class": (
            value.get("qwen_upstream_content_type_class")
            if isinstance(value.get("qwen_upstream_content_type_class"), str)
            and value.get("qwen_upstream_content_type_class") in {"sse", "json", "other", "unknown"}
            else "unknown"
        ),
        "gateway_error_code_class": (
            value.get("gateway_error_code_class")
            if isinstance(value.get("gateway_error_code_class"), str)
            and value.get("gateway_error_code_class") in _COMPOSED_ERROR_CLASSES
            else "unknown"
        ),
        "gateway_error_type_class": (
            value.get("gateway_error_type_class")
            if isinstance(value.get("gateway_error_type_class"), str)
            and value.get("gateway_error_type_class") in _COMPOSED_ERROR_CLASSES
            else "unknown"
        ),
        "gateway_error_field_names": sorted(
            field for field in value.get("gateway_error_field_names", [])
            if isinstance(field, str) and field in _SAFE_ERROR_FIELD_NAMES
        ) if isinstance(value.get("gateway_error_field_names"), list) else [],
        "decision": decision,
    })
    return result


def _composed_path_from_statuses(
    *,
    local_status: dict[str, object],
    gateway_status: dict[str, object],
    qwen_status: dict[str, object],
    qwen_before: dict[str, object] | None = None,
    local_output: dict[str, object],
    gateway_output: dict[str, object],
    accounting_verified: bool,
    decision: str,
) -> dict[str, object]:
    qwen_structures = qwen_status.get("sse_structures")
    qwen_structure = qwen_structures[-1] if isinstance(qwen_structures, list) and qwen_structures else None
    qwen_statuses = qwen_status.get("upstream_statuses")
    qwen_contents = qwen_status.get("sse_content_type_classes")
    if qwen_before is not None:
        before_statuses = qwen_before.get("upstream_statuses")
        before_contents = qwen_before.get("sse_content_type_classes")
        qwen_statuses = (
            qwen_statuses[len(before_statuses) :]
            if isinstance(before_statuses, list) and isinstance(qwen_statuses, list)
            else None
        )
        qwen_contents = (
            qwen_contents[len(before_contents) :]
            if isinstance(before_contents, list) and isinstance(qwen_contents, list)
            else None
        )
    qwen_terminal = (
        isinstance(qwen_structure, dict)
        and _stream_has_valid_completion(qwen_structure)
        and _last_status_class(qwen_statuses) == "2xx"
        and _last_content_class(qwen_contents) == "sse"
    )
    gateway_structures = gateway_status.get("sse_structures")
    gateway_structure = gateway_structures[-1] if isinstance(gateway_structures, list) and gateway_structures else {}
    error_fields = gateway_structure.get("error_field_names", []) if isinstance(gateway_structure, dict) else []
    return _safe_composed_path(
        {
            "gateway_to_local_request_count_class": _count_class(local_status.get("forwarded_count")),
            "gateway_to_local_response_count_class": _count_class(len(local_status.get("response_statuses", []))) if isinstance(local_status.get("response_statuses"), list) else "unknown",
            "local_response_status_class": _last_status_class(local_status.get("response_statuses")),
            "local_response_content_type_class": _last_content_class(local_status.get("response_content_type_classes")),
            "local_rejected": type(local_status.get("rejected_count")) is int and local_status["rejected_count"] > 0,
            "local_handler_error": local_status.get("handler_error") is True,
            "local_upstream_truncated": local_status.get("upstream_truncated") is True,
            "local_downstream_closed_early": local_status.get("downstream_closed_early") is True,
            "local_terminal_completion_valid": local_output.get("terminal_completion_valid") is True,
            "local_to_qwen_inference_call_count_class": _count_class(qwen_status.get("inference_calls")),
            "qwen_upstream_response_count_class": _count_class(len(qwen_statuses)) if isinstance(qwen_statuses, list) else "unknown",
            "qwen_upstream_status_class": _last_status_class(qwen_statuses),
            "qwen_upstream_content_type_class": _last_content_class(qwen_contents),
            "qwen_terminal_completion_valid": qwen_terminal,
            "qwen_handler_error": qwen_status.get("handler_error") is True,
            "qwen_upstream_truncated": qwen_status.get("upstream_truncated") is True,
            "qwen_path_rejection": type(qwen_status.get("path_rejections")) is int and qwen_status["path_rejections"] > 0,
            "gateway_error_event": gateway_structure.get("error_event") is True if isinstance(gateway_structure, dict) else False,
            "gateway_error_field_names": error_fields,
            "gateway_error_code_class": gateway_structure.get("error_code_class", "unknown") if isinstance(gateway_structure, dict) else "unknown",
            "gateway_error_type_class": gateway_structure.get("error_type_class", "unknown") if isinstance(gateway_structure, dict) else "unknown",
            "gateway_accounting_terminal": accounting_verified,
        },
        decision=decision,
    )


def _emit_stream_summary(lines: tuple[str, ...]) -> None:
    payload = "\n".join(lines) + "\n"
    sys.stdout.write(payload)


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


class _ForwardingRelay(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        local_port: int,
        *,
        capture_requests: bool = True,
        boundary_class: str = "local_output",
    ) -> None:
        super().__init__(server_address, _RelayHandler)
        self.local_port = local_port
        self.capture_requests = capture_requests
        self.boundary_class = boundary_class
        self.captured: list[CapturedRequest] = []
        self.response_statuses: list[int] = []
        self.response_status_classes: list[str] = []
        self.response_content_type_classes: list[str] = []
        self.response_path_classes: list[str] = []
        self.sse_structures: list[dict[str, object]] = []
        self.sse_boundaries: list[str] = []
        self.error_code_classes: list[str] = []
        self.error_param_classes: list[str] = []
        self.error_param_field_classes: list[str] = []
        self.input_item_error_projections: list[dict[str, object]] = []
        self.local_error_code_classes: list[str] = []
        self.local_error_stage_classes: list[str] = []
        self.forwarded = 0
        self.rejected = 0
        self.downstream_closed_early = False
        self.upstream_truncated = False
        self.handler_error = False
        self._capture_lock = threading.Lock()

    def handle_error(self, _request: object, _client_address: object) -> None:
        """Never emit stdlib handler tracebacks from the evidence relay."""
        with self._capture_lock:
            self.handler_error = True

    def remember(self, request: CapturedRequest) -> None:
        with self._capture_lock:
            self.captured.append(request)
            self.forwarded += 1

    def remember_response(
        self, status: int, path: str, content_type_class: str = "other"
    ) -> None:
        with self._capture_lock:
            self.response_statuses.append(status)
            self.response_path_classes.append(_safe_path_class(path))
            self.response_status_classes.append(f"{status // 100}xx")
            self.response_content_type_classes.append(content_type_class)

    def remember_sse_structure(self, structure: dict[str, object]) -> None:
        with self._capture_lock:
            self.sse_structures.append(structure)
            self.sse_boundaries.append(self.boundary_class)

    def remember_error_body(self, body: bytes, *, request_body: bytes) -> None:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        code_class = _safe_gateway_error_code_class(error.get("code"))
        param_class = _safe_gateway_error_param_class(error.get("param"))
        param_field_class = _safe_gateway_error_param_field_class(error.get("param"))
        input_item_projection = _safe_input_item_error_projection(
            error.get("param"), request_body
        )
        with self._capture_lock:
            self.error_code_classes.append(code_class)
            self.error_param_classes.append(param_class)
            self.error_param_field_classes.append(param_field_class)
            self.input_item_error_projections.append(input_item_projection)
            if self.boundary_class == "local_output":
                local_code = _safe_local_error_code_class(error.get("code"))
                self.local_error_code_classes.append(local_code)
                self.local_error_stage_classes.append(_safe_local_rejection_stage(local_code))

    def remember_no_error(self) -> None:
        with self._capture_lock:
            self.error_code_classes.append("none")
            self.error_param_classes.append("none")
            self.error_param_field_classes.append("none")
            self.input_item_error_projections.append(_empty_input_item_error_projection())
            if self.boundary_class == "local_output":
                self.local_error_code_classes.append("none")
                self.local_error_stage_classes.append("other")

    def mark_downstream_closed_early(self) -> None:
        with self._capture_lock:
            self.downstream_closed_early = True

    def mark_upstream_truncated(self) -> None:
        with self._capture_lock:
            self.upstream_truncated = True

    def status(self) -> dict[str, object]:
        with self._capture_lock:
            return {
                "response_statuses": list(self.response_statuses),
                "forwarded_count": self.forwarded,
                "rejected_count": self.rejected,
                "response_status_classes": list(self.response_status_classes),
                "response_content_type_classes": list(self.response_content_type_classes),
                "response_path_classes": list(self.response_path_classes),
                "sse_structures": list(self.sse_structures),
                "sse_boundaries": list(self.sse_boundaries),
                "error_code_classes": list(self.error_code_classes),
                "error_param_classes": list(self.error_param_classes),
                "error_param_field_classes": list(self.error_param_field_classes),
                "input_item_error_projections": [
                    dict(projection) for projection in self.input_item_error_projections
                ],
                "local_error_code_classes": _safe_local_error_classes(
                    self.local_error_code_classes,
                    self.response_statuses,
                ),
                "local_error_stage_classes": _safe_local_stage_classes(
                    self.local_error_stage_classes,
                    self.response_statuses,
                ),
                "local_boundary_states": _safe_local_boundary_states_from_codes(
                    _safe_local_error_classes(
                        self.local_error_code_classes,
                        self.response_statuses,
                    ),
                    self.response_statuses,
                ),
                "downstream_closed_early": self.downstream_closed_early,
                "upstream_truncated": self.upstream_truncated,
                "handler_error": self.handler_error,
            }

    def snapshot(self) -> tuple[CapturedRequest, ...]:
        with self._capture_lock:
            return tuple(self.captured)


class _RelayHandler(http.server.BaseHTTPRequestHandler):
    server: _ForwardingRelay

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _forward(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length < 0 or length > RELAY_BODY_LIMIT:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        headers = {
            key.lower(): value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        raw_header_items = (
            self.headers.raw_items()
            if hasattr(self.headers, "raw_items")
            else self.headers.items()
        )
        header_counts: dict[str, int] = {}
        for name, _value in raw_header_items:
            lowered = name.lower()
            header_counts[lowered] = header_counts.get(lowered, 0) + 1
        captured = CapturedRequest(
            path=self.path,
            body=body,
            headers=headers,
            method=self.command,
            header_name_counts=tuple(sorted(header_counts.items())),
        )
        if self.server.capture_requests:
            self.server.remember(captured)
        response_status: int | None = None
        headers_sent = False
        downstream_open = True
        try:
            with httpx.Client(timeout=300, follow_redirects=False) as client:
                with client.stream(
                    self.command,
                    f"http://127.0.0.1:{self.server.local_port}{self.path}",
                    headers=headers,
                    content=body,
                ) as response:
                    recorder = (
                        _SSEStructuralRecorder()
                        if response.headers.get("content-type", "").lower().startswith(
                            "text/event-stream"
                        )
                        else None
                    )
                    response_status = response.status_code
                    content_type = response.headers.get("content-type", "").lower()
                    content_type_class = (
                        "sse"
                        if content_type.startswith("text/event-stream")
                        else "json"
                        if "json" in content_type
                        else "other"
                    )
                    error_body = bytearray()
                    try:
                        self.send_response(response.status_code)
                        for key, value in response.headers.items():
                            if key.lower() not in {
                                "content-length",
                                "connection",
                                "transfer-encoding",
                            }:
                                self.send_header(key, value)
                        self.end_headers()
                        headers_sent = True
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                        downstream_open = False
                        self.server.mark_downstream_closed_early()
                    first_chunk = True
                    upstream_normal_close = False
                    try:
                        for chunk in response.iter_raw():
                            if recorder is not None:
                                if first_chunk:
                                    recorder.mark_first_event_before_upstream_completion()
                                recorder.feed(chunk)
                            elif response_status >= 400 and len(error_body) < _ERROR_CAPTURE_LIMIT:
                                remaining = _ERROR_CAPTURE_LIMIT - len(error_body)
                                error_body.extend(chunk[:remaining])
                            if downstream_open:
                                try:
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                                    downstream_open = False
                                    self.server.mark_downstream_closed_early()
                            first_chunk = False
                        upstream_normal_close = True
                    finally:
                        if recorder is not None:
                            recorder.mark_normal_close(upstream_normal_close)
                            if not downstream_open:
                                recorder.mark_downstream_closed_early()
                            self.server.remember_sse_structure(recorder.snapshot())
                            if response_status is not None and response_status >= 400:
                                self.server.remember_error_body(
                                    bytes(error_body), request_body=body
                                )
                            else:
                                self.server.remember_no_error()
                            del error_body
                        elif response_status is not None and response_status >= 400:
                            self.server.remember_error_body(
                                bytes(error_body), request_body=body
                            )
                            del error_body
                        elif response_status is not None:
                            self.server.remember_no_error()
        except httpx.HTTPError:
            self.server.mark_upstream_truncated()
            self.server.rejected += 1
            if response_status is not None:
                self.server.remember_response(response_status, self.path, content_type_class)
            if not headers_sent and downstream_open:
                try:
                    self.send_error(502)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    self.server.mark_downstream_closed_early()
            return
        if response_status is not None:
            self.server.remember_response(response_status, self.path, content_type_class)

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()


class _FailureServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, _FailureHandler)
        self.calls = 0
        self._calls_lock = threading.Lock()

    def record_call(self) -> None:
        with self._calls_lock:
            self.calls += 1


class _FailureHandler(http.server.BaseHTTPRequestHandler):
    server: _FailureServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        self.server.record_call()
        length = int(self.headers.get("content-length", "0"))
        if length > RELAY_BODY_LIMIT:
            self.send_error(413)
            return
        self.rfile.read(length)
        body = b'{"error":{"message":"synthetic provider failure","type":"server_error","code":"synthetic_failure"}}'
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.send_response(404)
        self.end_headers()


class _FakeQwenServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        token: str,
        *,
        tool_roundtrip_mode: bool = False,
        qualification_rejection_mode: bool = False,
        provider_failure_mode: bool = False,
        non_prefixed_tool_id: bool = False,
    ) -> None:
        super().__init__(server_address, _FakeQwenHandler)
        self.token = token
        self.tool_roundtrip_mode = tool_roundtrip_mode
        self.qualification_rejection_mode = qualification_rejection_mode
        self.provider_failure_mode = provider_failure_mode
        self.non_prefixed_tool_id = non_prefixed_tool_id
        self.calls = 0
        self.compiler_calls = 0
        self.inference_calls = 0
        self.stream_calls = 0
        self.tool_roundtrip_turns = 0
        self.tool_result_observed = 0
        self.function_lifecycle_count = 0
        self.message_lifecycle_count = 0
        self.first_event_sent = threading.Event()
        self._lock = threading.Lock()

    def record(self, *, compiler: bool, streaming: bool) -> None:
        with self._lock:
            self.calls += 1
            if compiler:
                self.compiler_calls += 1
            else:
                self.inference_calls += 1
                if streaming:
                    self.stream_calls += 1

    def record_tool_roundtrip_phase(self, *, has_one_tool_result: bool) -> None:
        with self._lock:
            self.tool_roundtrip_turns += 1
            if has_one_tool_result:
                self.tool_result_observed += 1
                self.message_lifecycle_count += 1
            else:
                self.function_lifecycle_count += 1

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "calls": self.calls,
                "compiler_calls": self.compiler_calls,
                "inference_calls": self.inference_calls,
                "stream_calls": self.stream_calls,
                "tool_roundtrip_mode": self.tool_roundtrip_mode,
                "qualification_rejection_mode": self.qualification_rejection_mode,
                "provider_failure_mode": self.provider_failure_mode,
                "tool_roundtrip_turns": self.tool_roundtrip_turns,
                "tool_result_observed": self.tool_result_observed,
                "function_lifecycle_count": self.function_lifecycle_count,
                "message_lifecycle_count": self.message_lifecycle_count,
                "first_event_sent": self.first_event_sent.is_set(),
            }


class _FakeQwenHandler(http.server.BaseHTTPRequestHandler):
    server: _FakeQwenServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _authorized(self) -> bool:
        return self.headers.get("authorization") == f"Bearer {self.server.token}"

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(401, {"error": {"code": "unauthorized"}})
            return
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": CODEX_MODEL, "object": "model"}]})
            return
        self._json(404, {"error": {"code": "not_found"}})

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self._json(400, {"error": {"code": "invalid_length"}})
            return None
        if length < 0 or length > RELAY_BODY_LIMIT:
            self._json(413, {"error": {"code": "body_too_large"}})
            return None
        return self.rfile.read(length)

    @staticmethod
    def _compiled_index(payload: dict[str, object]) -> str:
        messages = payload.get("messages")
        user = messages[-1].get("content") if isinstance(messages, list) and messages else None
        if not isinstance(user, str):
            raise ValueError("compiler_input")
        source_marker = "<source path='"
        source_start = user.find(source_marker)
        source_end = user.find("' sha256=", source_start + len(source_marker))
        sha_start = source_end + len("' sha256=")
        sha_end = user.find(" byte_length=", sha_start)
        length_start = sha_end + len(" byte_length=")
        source_close = user.find(">", length_start)
        candidates_marker = "<deterministic_candidates>\n"
        candidates_start = user.find(candidates_marker, source_close)
        candidates_end = user.find(
            "\n</deterministic_candidates>", candidates_start + len(candidates_marker)
        )
        if min(source_start, source_end, sha_end, source_close, candidates_start, candidates_end) < 0:
            raise ValueError("compiler_prompt")
        logical_path = user[source_start + len(source_marker) : source_end]
        source_hash = user[sha_start:sha_end]
        byte_length_text = user[length_start:source_close]
        if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
            raise ValueError("compiler_hash")
        candidates = json.loads(
            user[candidates_start + len(candidates_marker) : candidates_end]
        )
        if not isinstance(candidates, list):
            raise ValueError("compiler_candidates")
        dependencies = [
            {
                "path": item["path"],
                "reference_confidence": 0.9,
                "constitutional_priority": 1,
                "classification": "P2",
                "relationship": "bounded dependency",
                "evidence": "supplied candidate",
                "acquisition_urgency": "none",
            }
            for item in candidates
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        result = {
            "schema_version": "constitution-index-v1",
            "compiler_version": "compiler-v2",
            "prompt_policy_version": "constitutional-rank-v2",
            "model": payload.get("model"),
            "source_logical_path": logical_path,
            "source_sha256": source_hash,
            "source_byte_length": int(byte_length_text),
            "summary": "bounded fake rehearsal",
            "rules": [{
                "rule_id": "fake-rule",
                "strength": "must",
                "statement": "bounded rehearsal",
                "location": "source",
                "evidence": "supplied source",
            }],
            "roles": ["agent"],
            "authorities": ["local"],
            "source_of_truth_boundaries": ["gateway"],
            "ordering_constraints": [],
            "exceptions": [],
            "dependencies": dependencies,
            "reread_triggers": ["change"],
            "status": "success",
        }
        return json.dumps(result, separators=(",", ":"))

    @staticmethod
    def _response() -> dict[str, object]:
        return {
            "id": "fake-response",
            "object": "response",
            "created_at": 1,
            "status": "completed",
            "model": CODEX_MODEL,
            "output": [{
                "id": "fake-message",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "bounded fake response", "annotations": []}],
            }],
            "usage": {"input_tokens": 2, "output_tokens": 2, "total_tokens": 4},
        }

    @staticmethod
    def _function_arguments(
        payload: dict[str, object], *, tool_name: str | None = None
    ) -> str:
        tools = payload.get("tools")
        if not isinstance(tools, list):
            return "{}"
        declaration = next(
            (
                tool
                for tool in tools
                if isinstance(tool, dict)
                and tool.get("type") == "function"
                and (tool_name is None or tool.get("name") == tool_name)
            ),
            None,
        )
        if not isinstance(declaration, dict):
            return "{}"
        parameters = declaration.get("parameters")
        if not isinstance(parameters, dict):
            return "{}"
        properties = parameters.get("properties")
        required = parameters.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            return "{}"
        values: dict[str, object] = {}
        for name in required[:8]:
            schema = properties.get(name)
            schema_type = schema.get("type") if isinstance(schema, dict) else None
            values[name] = (
                "printf bounded fake tool"
                if schema_type == "string"
                else 1
                if schema_type == "integer"
                else False
                if schema_type == "boolean"
                else []
                if schema_type == "array"
                else {}
            )
        return json.dumps(values, separators=(",", ":"))

    def _stream(self, payload: dict[str, object]) -> None:
        if self.server.qualification_rejection_mode:
            self._stream_qualification_rejection(payload)
            return
        if self.server.tool_roundtrip_mode:
            input_items = payload.get("input")
            result_count = (
                sum(
                    1
                    for item in input_items
                    if isinstance(item, dict) and item.get("type") == "function_call_output"
                )
                if isinstance(input_items, list)
                else 0
            )
            if result_count > 1:
                self._json(400, {"error": {"code": "tool_result_cardinality"}})
                return
            if (
                (self.server.tool_roundtrip_turns == 0 and result_count != 0)
                or (self.server.tool_roundtrip_turns == 1 and result_count != 1)
                or self.server.tool_roundtrip_turns >= 2
            ):
                self._json(400, {"error": {"code": "tool_roundtrip_order"}})
                return
            self.server.record_tool_roundtrip_phase(has_one_tool_result=result_count == 1)
            if result_count == 0:
                self._stream_function(payload)
            else:
                self._stream_message()
            return
        self._stream_message()

    def _stream_qualification_rejection(self, payload: dict[str, object]) -> None:
        tool_name = next(
            (
                tool.get("name")
                for tool in payload.get("tools", [])
                if isinstance(tool, dict)
                and tool.get("type") == "function"
                and tool.get("name") in {"shell_command", "exec_command"}
            ),
            None,
        )
        if not isinstance(tool_name, str):
            self._json(400, {"error": {"code": "known_local_tool_missing"}})
            return
        self._write_stream_events(
            (
                (
                    "response.created",
                    {
                        "type": "response.created",
                        "sequence_number": 0,
                        "response": {
                            "id": "resp_qualification",
                            "object": "response",
                            "status": "in_progress",
                            "model": CODEX_MODEL,
                        },
                    },
                ),
                (
                    "response.output_item.added",
                    {
                        "type": "response.output_item.added",
                        "sequence_number": 1,
                        "output_index": 0,
                        "item": {
                            "type": "function_call",
                            "id": "qualification_function",
                            "status": "in_progress",
                            "name": tool_name,
                            "arguments": "",
                            "call_id": "qualification_call",
                            "caller": None,
                            "namespace": "functions",
                        },
                    },
                ),
            )
        )

    def _stream_function(self, payload: dict[str, object]) -> None:
        tool_name = next(
            (
                tool.get("name")
                for tool in payload.get("tools", [])
                if isinstance(tool, dict)
                and tool.get("type") == "function"
                and tool.get("name") in {"shell_command", "exec_command"}
            ),
            None,
        )
        if not isinstance(tool_name, str):
            self._json(400, {"error": {"code": "known_local_tool_missing"}})
            return
        arguments = self._function_arguments(payload, tool_name=tool_name)
        stream_item_id = (
            "function1" if self.server.non_prefixed_tool_id else "function_1"
        )
        events = (
            (
                "response.created",
                {
                    "type": "response.created",
                    "sequence_number": 0,
                    "response": {
                        "id": "resp_function",
                        "object": "response",
                        "status": "in_progress",
                        "model": CODEX_MODEL,
                    },
                },
            ),
            (
                "response.in_progress",
                {
                    "type": "response.in_progress",
                    "sequence_number": 1,
                    "response": {
                        "id": "resp_function",
                        "object": "response",
                        "status": "in_progress",
                        "model": CODEX_MODEL,
                    },
                },
            ),
            (
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "sequence_number": 2,
                    "item": {
                        "type": "function_call",
                        "id": stream_item_id,
                        "status": "in_progress",
                        "namespace": None,
                        "name": tool_name,
                        "arguments": "",
                        "call_id": "call_1",
                        "caller": None,
                    },
                },
            ),
            (
                "response.function_call_arguments.delta",
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": stream_item_id,
                    "output_index": 0,
                    "sequence_number": 3,
                    "delta": arguments,
                },
            ),
            (
                "response.function_call_arguments.done",
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": stream_item_id,
                    "output_index": 0,
                    "sequence_number": 4,
                    "name": tool_name,
                    "arguments": arguments,
                },
            ),
            (
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "sequence_number": 5,
                    "item": {
                        "type": "function_call",
                        "id": stream_item_id,
                        "status": "completed",
                        "namespace": None,
                        "name": tool_name,
                        "arguments": arguments,
                        "call_id": "call_1",
                        "caller": None,
                    },
                },
            ),
            (
                "response.completed",
                {
                    "type": "response.completed",
                    "sequence_number": 6,
                    "response": {
                        "id": "resp_function",
                        "object": "response",
                        "status": "completed",
                        "model": CODEX_MODEL,
                        "output": [
                            {
                                "type": "function_call",
                                "id": "parser_function_1",
                                "status": "completed",
                                "namespace": None,
                                "name": tool_name,
                                "arguments": arguments,
                                "call_id": "parser_call_1",
                            }
                        ],
                        "usage": {
                            "input_tokens": 2,
                            "input_tokens_details": {
                                "cached_tokens": 0,
                                "input_tokens_per_turn": [2],
                                "cached_tokens_per_turn": [0],
                            },
                            "output_tokens": 2,
                            "output_tokens_details": {
                                "reasoning_tokens": 0,
                                "tool_output_tokens": 0,
                                "output_tokens_per_turn": [2],
                                "tool_output_tokens_per_turn": [0],
                            },
                            "total_tokens": 4,
                        },
                    },
                },
            ),
        )
        self._write_stream_events(events)

    def _stream_message(self) -> None:
        stream_item_id = "fake-stream-message"
        created = {
            "type": "response.created",
            "sequence_number": 0,
            "response": {
                "id": "resp_capture",
                "object": "response",
                "status": "in_progress",
                "model": CODEX_MODEL,
            },
        }
        events = (
            ("response.created", created),
            (
                "response.in_progress",
                {
                    "type": "response.in_progress",
                    "sequence_number": 1,
                    "response": {
                        "id": "resp_capture",
                        "object": "response",
                        "status": "in_progress",
                        "model": CODEX_MODEL,
                    },
                },
            ),
            (
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "sequence_number": 2,
                    "output_index": 0,
                    "item": {
                        "type": "message",
                        "id": stream_item_id,
                        "status": "in_progress",
                        "role": "assistant",
                        "content": [],
                        "phase": None,
                    },
                },
            ),
            (
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "sequence_number": 3,
                    "item_id": stream_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {
                        "type": "output_text",
                        "text": "",
                        "annotations": [],
                        "logprobs": [],
                    },
                },
            ),
            (
                "response.output_text.delta",
                {
                    "type": "response.output_text.delta",
                    "sequence_number": 4,
                    "item_id": stream_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "bounded fake response",
                    "logprobs": [],
                },
            ),
            (
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "sequence_number": 5,
                    "item_id": stream_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "text": "bounded fake response",
                    "logprobs": [],
                },
            ),
            (
                "response.content_part.done",
                {
                    "type": "response.content_part.done",
                    "sequence_number": 6,
                    "item_id": stream_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {
                        "type": "output_text",
                        "text": "bounded fake response",
                        "annotations": [],
                        "logprobs": None,
                    },
                },
            ),
            (
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "sequence_number": 7,
                    "output_index": 0,
                    "item": {
                        "type": "message",
                        "id": stream_item_id,
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "bounded fake response",
                                "annotations": [],
                                "logprobs": None,
                            }
                        ],
                        "phase": None,
                        "summary": [],
                    },
                },
            ),
            (
                "response.completed",
                {
                    "type": "response.completed",
                    "sequence_number": 8,
                    "response": {
                        "id": "resp_capture",
                        "object": "response",
                        "status": "completed",
                        "model": CODEX_MODEL,
                        "output": [
                            {
                                "id": "fake-message",
                                "type": "message",
                                "status": "completed",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "bounded fake response",
                                        "annotations": [],
                                        "logprobs": None,
                                    }
                                ],
                                "phase": None,
                            }
                        ],
                        "usage": {
                            "input_tokens": 2,
                            "input_tokens_details": {
                                "cached_tokens": 0,
                                "input_tokens_per_turn": [2],
                                "cached_tokens_per_turn": [0],
                            },
                            "output_tokens": 2,
                            "output_tokens_details": {
                                "reasoning_tokens": 0,
                                "tool_output_tokens": 0,
                                "output_tokens_per_turn": [2],
                                "tool_output_tokens_per_turn": [0],
                            },
                            "total_tokens": 4,
                        },
                    },
                },
            ),
        )
        self._write_stream_events(events)

    def _write_stream_events(
        self, events: tuple[tuple[str, dict[str, object]], ...]
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for index, (event, payload) in enumerate(events):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode())
            self.wfile.flush()
            if index == 0:
                self.server.first_event_sent.set()
                time.sleep(0.05)

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"error": {"code": "unauthorized"}})
            return
        body = self._read_body()
        if body is None:
            return
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": {"code": "invalid_json"}})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": {"code": "invalid_json"}})
            return
        if self.path == "/v1/chat/completions":
            try:
                content = self._compiled_index(payload)
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                self._json(400, {"error": {"code": "compiler_input"}})
                return
            self.server.record(compiler=True, streaming=False)
            self._json(200, {"id": "fake-compiler", "choices": [{"message": {"content": content}}]})
            return
        if self.path == "/v1/responses":
            streaming = payload.get("stream") is True
            self.server.record(compiler=False, streaming=streaming)
            if self.server.provider_failure_mode:
                self._json(503, {"error": {"code": "provider_transport_failure"}})
                return
            if streaming:
                self._stream(payload)
            else:
                self._json(200, self._response())
            return
        self._json(404, {"error": {"code": "not_found"}})


class _QwenRelayServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        endpoint: str,
        relay_token: str,
        qwen_token: str,
    ) -> None:
        super().__init__(server_address, _QwenRelayHandler)
        self.endpoint = endpoint
        self.relay_token = relay_token
        self.qwen_token = qwen_token
        self.calls = 0
        self.compiler_calls = 0
        self.inference_calls = 0
        self.successful_calls = 0
        self.health_calls = 0
        self.models_calls = 0
        self.bad_inbound_auth = False
        self.auth_replaced = False
        self.internal_headers = False
        self.internal_body = False
        self.tool_types: set[str] = set()
        self.outbound_header_names: set[str] = set()
        self.request_path_classes: set[str] = set()
        self.upstream_statuses: list[int] = []
        self.inference_statuses: list[int] = []
        self.compiler_statuses: list[int] = []
        self.path_rejections = 0
        self.path_rejection_classes: set[str] = set()
        self.sse_structures: list[dict[str, object]] = []
        self.stream_first_event_before_upstream_completion = False
        self.stream_normal_close = False
        self.sse_content_type_classes: list[str] = []
        self.inference_content_type_classes: list[str] = []
        self.compiler_content_type_classes: list[str] = []
        self.downstream_closed_early = False
        self.upstream_truncated = False
        self.handler_error = False
        self._lock = threading.Lock()

    def handle_error(self, _request: object, _client_address: object) -> None:
        """Keep relay disconnects out of stderr and out of evidence output."""
        with self._lock:
            self.handler_error = True

    def record_request(
        self,
        *,
        path: str,
        compiler: bool,
        payload: object,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        with self._lock:
            self.calls += 1
            self.request_path_classes.add(_safe_path_class(path))
            if compiler:
                self.compiler_calls += 1
            else:
                self.inference_calls += 1
            if headers.get("authorization") != f"Bearer {self.relay_token}":
                self.bad_inbound_auth = True
            self.internal_headers = self.internal_headers or any(
                name.startswith("x-slaif-") or name.startswith("x-internal-")
                for name in headers
            )
            self.internal_body = self.internal_body or any(
                marker in body
                for marker in (b"x-slaif-", b"x-internal-", self.relay_token.encode("utf-8"))
            )
            if isinstance(payload, dict) and isinstance(payload.get("tools"), list):
                self.tool_types.update(
                    item["type"]
                    for item in payload["tools"]
                    if isinstance(item, dict) and isinstance(item.get("type"), str)
                )
            self.outbound_header_names.update(
                {"accept", "accept-encoding", "authorization", "content-type"}
            )
            self.auth_replaced = self.auth_replaced or headers.get("authorization") != f"Bearer {self.qwen_token}"

    def record_upstream_status(
        self,
        status: int,
        *,
        inference: bool = False,
        compiler: bool = False,
    ) -> None:
        with self._lock:
            self.upstream_statuses.append(status)
            if inference:
                self.inference_statuses.append(status)
            if compiler:
                self.compiler_statuses.append(status)

    def record_path_rejection(self, path: str) -> None:
        with self._lock:
            self.path_rejections += 1
            self.path_rejection_classes.add(_safe_path_class(path))

    def record_success(self) -> None:
        with self._lock:
            self.successful_calls += 1

    def record_probe(self, path: str, headers: dict[str, str]) -> None:
        with self._lock:
            if path == "/health":
                self.health_calls += 1
            elif path == "/v1/models":
                self.models_calls += 1
            if headers.get("authorization") != f"Bearer {self.relay_token}":
                self.bad_inbound_auth = True
            self.internal_headers = self.internal_headers or any(
                name.startswith("x-slaif-") or name.startswith("x-internal-")
                for name in headers
            )
            self.outbound_header_names.update({"accept", "accept-encoding", "authorization"})
            self.auth_replaced = self.auth_replaced or headers.get("authorization") != f"Bearer {self.qwen_token}"

    def record_stream_first_event(self) -> None:
        with self._lock:
            self.stream_first_event_before_upstream_completion = True

    def record_stream_normal_close(self) -> None:
        with self._lock:
            self.stream_normal_close = True

    def record_downstream_closed_early(self) -> None:
        with self._lock:
            self.downstream_closed_early = True

    def record_upstream_truncated(self) -> None:
        with self._lock:
            self.upstream_truncated = True

    def remember_sse_structure(self, structure: dict[str, object]) -> None:
        with self._lock:
            self.sse_structures.append(structure)

    def remember_content_type(
        self,
        content_type: str,
        *,
        inference: bool = False,
        compiler: bool = False,
    ) -> None:
        with self._lock:
            content_type_class = (
                "sse"
                if content_type.startswith("text/event-stream")
                else "json"
                if "json" in content_type
                else "other"
            )
            self.sse_content_type_classes.append(content_type_class)
            if inference:
                self.inference_content_type_classes.append(content_type_class)
            if compiler:
                self.compiler_content_type_classes.append(content_type_class)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "calls": self.calls,
                "compiler_calls": self.compiler_calls,
                "inference_calls": self.inference_calls,
                "successful_calls": self.successful_calls,
                "health_calls": self.health_calls,
                "models_calls": self.models_calls,
                "bad_inbound_auth": self.bad_inbound_auth,
                "auth_replaced": self.auth_replaced,
                "internal_headers": self.internal_headers,
                "internal_body": self.internal_body,
                "tool_types": sorted(self.tool_types),
                "outbound_header_names": sorted(self.outbound_header_names),
                "request_path_classes": sorted(self.request_path_classes),
                "upstream_statuses": list(self.upstream_statuses),
                "inference_statuses": list(self.inference_statuses),
                "compiler_statuses": list(self.compiler_statuses),
                "path_rejections": self.path_rejections,
                "path_rejection_classes": sorted(self.path_rejection_classes),
                "first_event_before_upstream_completion": self.stream_first_event_before_upstream_completion,
                "stream_normal_close": self.stream_normal_close,
                "sse_structures": list(self.sse_structures),
                "sse_content_type_classes": list(self.sse_content_type_classes),
                "inference_content_type_classes": list(self.inference_content_type_classes),
                "compiler_content_type_classes": list(self.compiler_content_type_classes),
                "downstream_closed_early": self.downstream_closed_early,
                "upstream_truncated": self.upstream_truncated,
                "handler_error": self.handler_error,
            }


def _qwen_target(endpoint: str, path: str) -> str:
    endpoint_parts = urlsplit(endpoint)
    request_parts = urlsplit(path)
    request_path = request_parts.path
    if request_parts.fragment or len(request_parts.query) > 256:
        raise VerificationError("qwen_relay_path_invalid")
    query = f"?{request_parts.query}" if request_parts.query else ""
    origin = f"{endpoint_parts.scheme}://{endpoint_parts.netloc}"
    if request_path == "/health":
        return origin + "/health" + query
    if request_path in {"/v1/models", "/v1/responses", "/v1/chat/completions"}:
        return endpoint.rstrip("/") + request_path[3:] + query
    raise VerificationError("qwen_relay_path_invalid")


class _QwenRelayHandler(http.server.BaseHTTPRequestHandler):
    server: _QwenRelayServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/__155f_status" and not urlsplit(self.path).query:
            body = json.dumps(self.server.status(), separators=(",", ":")).encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if urlsplit(self.path).path not in {"/health", "/v1/models"}:
            self.send_error(404)
            return
        inbound_headers = {
            key.lower(): value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        self.server.record_probe(self.path, inbound_headers)
        if inbound_headers.get("authorization") != f"Bearer {self.server.relay_token}":
            self.send_error(401)
            return
        self._forward_upstream("GET", self.path, inbound_headers, b"")

    def _forward_upstream(
        self,
        method: str,
        path: str,
        inbound_headers: dict[str, str],
        body: bytes,
        *,
        inference: bool = False,
    ) -> int | None:
        try:
            target = _qwen_target(self.server.endpoint, path)
        except VerificationError:
            self.server.record_path_rejection(path)
            self.send_error(404)
            return None
        outbound_headers = {
            name: inbound_headers[name]
            for name in ("content-type", "accept", "accept-encoding")
            if name in inbound_headers
        }
        outbound_headers["authorization"] = f"Bearer {self.server.qwen_token}"
        response_status: int | None = None
        headers_sent = False
        downstream_open = True
        try:
            with httpx.Client(timeout=300, follow_redirects=False) as client:
                with client.stream(method, target, headers=outbound_headers, content=body) as response:
                    self.server.remember_content_type(
                        response.headers.get("content-type", "").lower(),
                        inference=inference,
                        compiler=method == "POST" and not inference,
                    )
                    recorder = (
                        _SSEStructuralRecorder()
                        if response.headers.get("content-type", "").lower().startswith(
                            "text/event-stream"
                        )
                        else None
                    )
                    response_status = response.status_code
                    try:
                        self.send_response(response.status_code)
                        for key, value in response.headers.items():
                            if key.lower() not in {
                                "content-length",
                                "connection",
                                "transfer-encoding",
                            }:
                                self.send_header(key, value)
                        self.end_headers()
                        headers_sent = True
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                        downstream_open = False
                        self.server.record_downstream_closed_early()
                    first_chunk = True
                    upstream_normal_close = False
                    try:
                        for chunk in response.iter_raw():
                            if first_chunk:
                                self.server.record_stream_first_event()
                                if recorder is not None:
                                    recorder.mark_first_event_before_upstream_completion()
                            if recorder is not None:
                                recorder.feed(chunk)
                            if downstream_open:
                                try:
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                                    downstream_open = False
                                    self.server.record_downstream_closed_early()
                            first_chunk = False
                        upstream_normal_close = True
                    finally:
                        if upstream_normal_close:
                            self.server.record_stream_normal_close()
                        if recorder is not None:
                            recorder.mark_normal_close(upstream_normal_close)
                            if not downstream_open:
                                recorder.mark_downstream_closed_early()
                            self.server.remember_sse_structure(recorder.snapshot())
                    self.server.record_upstream_status(
                        response.status_code,
                        inference=inference,
                        compiler=method == "POST" and not inference,
                    )
        except httpx.HTTPError:
            self.server.record_upstream_truncated()
            if response_status is not None:
                self.server.record_upstream_status(
                    response_status,
                    inference=inference,
                    compiler=method == "POST" and not inference,
                )
            if not headers_sent and downstream_open:
                try:
                    self.send_error(502)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    self.server.record_downstream_closed_early()
            return None
        return response_status

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length < 0 or length > RELAY_BODY_LIMIT:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        inbound_headers = {
            key.lower(): value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        compiler = isinstance(payload, dict) and isinstance(payload.get("messages"), list)
        self.server.record_request(
            path=self.path,
            compiler=compiler,
            payload=payload,
            headers=inbound_headers,
            body=body,
        )
        if inbound_headers.get("authorization") != f"Bearer {self.server.relay_token}":
            self.send_error(401)
            return
        if not self.server.qwen_token:
            self.send_error(503)
            return
        status = self._forward_upstream(
            "POST",
            self.path,
            inbound_headers,
            body,
            inference=(not compiler and _safe_path_class(self.path) == "v1_responses"),
        )
        if status is not None and 200 <= status < 300:
            self.server.record_success()


def _qwen_relay_main() -> int:
    try:
        port = int(os.environ["SLAIF_155F_QWEN_RELAY_PORT"])
        endpoint = os.environ["SLAIF_155F_QWEN_BASE_URL"]
        relay_token = os.environ[QWEN_RELAY_TOKEN_ENV]
        qwen_token = os.environ[QWEN_TOKEN_ENV]
    except (KeyError, ValueError):
        return 2
    server = _QwenRelayServer(
        ("127.0.0.1", port),
        endpoint=endpoint,
        relay_token=relay_token,
        qwen_token=qwen_token,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


def _start_qwen_relay(
    port: int,
    *,
    runtime: RuntimeReference | None = None,
    endpoint: str | None = None,
    qwen_token: str | None = None,
    relay_token: str,
) -> subprocess.Popen[bytes]:
    source: Path | None = None
    if runtime is not None:
        endpoint = runtime.endpoint
        source = runtime.credential_source
    if not endpoint or not qwen_token:
        if source is None:
            raise VerificationError("qwen_relay_configuration")
        qwen_token = ""
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT),
        "SLAIF_155F_QWEN_BASE_URL": endpoint,
        "SLAIF_155F_QWEN_RELAY_PORT": str(port),
        QWEN_RELAY_TOKEN_ENV: relay_token,
    }
    selected_env = (
        "SLAIF_155F_QWEN_BASE_URL",
        "SLAIF_155F_QWEN_RELAY_PORT",
        QWEN_RELAY_TOKEN_ENV,
        QWEN_TOKEN_ENV,
    )
    if source is None:
        env[QWEN_TOKEN_ENV] = qwen_token
    return _start_process(
        [sys.executable, str(Path(__file__).resolve()), "--qwen-relay"],
        cwd=REPO_ROOT,
        env=env,
        source=source,
        selected_env=selected_env,
    )


def _qwen_relay_status(port: int) -> dict[str, object]:
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/__155f_status", timeout=10)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise VerificationError("qwen_relay_status_unavailable") from exc
    if response.status_code != 200 or not isinstance(payload, dict):
        raise VerificationError("qwen_relay_status_invalid")
    return payload


def _start_relay(
    local_port: int, *, capture_requests: bool = True, boundary_class: str = "local_output"
) -> tuple[_ForwardingRelay, threading.Thread]:
    relay = _ForwardingRelay(
        ("127.0.0.1", 0),
        local_port,
        capture_requests=capture_requests,
        boundary_class=boundary_class,
    )
    thread = threading.Thread(target=relay.serve_forever, name="155ah-relay", daemon=True)
    thread.start()
    return relay, thread


def _start_failure_server() -> tuple[_FailureServer, threading.Thread]:
    server = _FailureServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, name="155ah-failure", daemon=True)
    thread.start()
    return server, thread


def _start_fake_qwen(
    *,
    tool_roundtrip_mode: bool = False,
    qualification_rejection_mode: bool = False,
    provider_failure_mode: bool = False,
    non_prefixed_tool_id: bool = False,
) -> tuple[_FakeQwenServer, threading.Thread, str]:
    token = "fake-qwen-token"
    server = _FakeQwenServer(
        ("127.0.0.1", 0),
        token,
        tool_roundtrip_mode=tool_roundtrip_mode,
        qualification_rejection_mode=qualification_rejection_mode,
        provider_failure_mode=provider_failure_mode,
        non_prefixed_tool_id=non_prefixed_tool_id,
    )
    thread = threading.Thread(target=server.serve_forever, name="155ah-fake-qwen", daemon=True)
    thread.start()
    return server, thread, token


def _run_codex_tool_roundtrip_direct_fake(*, root: Path, codex_binary: Path) -> dict[str, object]:
    """Unit smoke: run Codex directly against the opt-in fake Qwen."""
    import scripts.capture_codex_protocol as capture

    fake, thread, token = _start_fake_qwen(tool_roundtrip_mode=True)
    try:
        home = root / "codex-home"
        work = root / "codex-work"
        catalog = root / "codex-catalog.json"
        home.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        environment = capture._isolated_environment(home)
        environment["SLAIF_CODEX_CAPTURE_API_KEY"] = token
        capture._write_0149_model_catalog(
            codex_binary,
            catalog,
            environment=environment,
            model=CODEX_MODEL,
        )
        result = _run(
            capture._exec_command_0149(
                codex_binary,
                workdir=work,
                port=fake.server_address[1],
                model=CODEX_MODEL,
                model_catalog=catalog,
                output_path=root / "codex-output.json",
                ephemeral=True,
            ),
            cwd=REPO_ROOT,
            env=environment,
            timeout=180,
        )
        if result.returncode != 0:
            raise VerificationError("fake_tool_roundtrip_codex_failed")
        status = fake.status()
        if (
            status["tool_roundtrip_turns"] != 2
            or status["tool_result_observed"] != 1
            or status["function_lifecycle_count"] != 1
            or status["message_lifecycle_count"] != 1
        ):
            raise VerificationError("fake_tool_roundtrip_counts_invalid")
        return {
            "codex_exit_success": True,
            "tool_roundtrip_turns": 2,
            "tool_result_observed": 1,
            "function_lifecycle_count": 1,
            "message_lifecycle_count": 1,
        }
    finally:
        fake.shutdown()
        fake.server_close()
        thread.join(timeout=10)


def _start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    source: Path | None = None,
    selected_env: tuple[str, ...] = (),
) -> subprocess.Popen[bytes]:
    if source is None:
        return subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    names = selected_env or (
        "PYTHONPATH",
        "SLAIF_155F_LOCAL_SERVICE_TOKEN",
        "SLAIF_155F_LOCAL_SIGNING_SECRET",
        "SLAIF_155F_LOCAL_UV_ENV",
    )
    assignments = " ".join(f'{name}="${{{name}}}"' for name in names)
    selected = (
        "set +x; . \"$SLAIF_155F_CREDENTIAL_SOURCE\" >/dev/null 2>&1; "
        "test -n \"${QWEN3090_API_KEY:-}\"; "
        f'exec /usr/bin/env -i PATH="${{PATH:-/usr/bin:/bin}}" {assignments} "$@"'
    )
    launcher = [
        "bash",
        "-c",
        selected,
        "155f-local-launch",
        *command,
    ]
    local_env = dict(env)
    local_env["SLAIF_155F_CREDENTIAL_SOURCE"] = str(source)
    return subprocess.Popen(
        launcher,
        cwd=cwd,
        env=local_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_http(url: str, *, expected: set[int] = {200}, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=5, follow_redirects=False)
            if response.status_code in expected:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise VerificationError("service_ready_timeout")


def _relay_request(
    relay: _ForwardingRelay, path: str, headers: dict[str, str], body: bytes
) -> int:
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(
                f"http://127.0.0.1:{relay.server_address[1]}{path}",
                headers=headers,
                content=body,
            )
            status = response.status_code
    except httpx.HTTPError as exc:
        raise VerificationError("relay_replay_failed") from exc
    return status


def _localize_ordinary_response_failure(
    relay: _ForwardingRelay,
    qwen_relay_port: int | None,
    exception: BaseException | None = None,
) -> VerificationError:
    relay_status = relay.status()
    response_statuses = relay_status["response_statuses"]
    path_classes = relay_status["response_path_classes"]
    if qwen_relay_port is not None:
        try:
            qwen_status = _qwen_relay_status(qwen_relay_port)
        except VerificationError:
            return VerificationError("ordinary_response_qwen_status_unavailable")
        if qwen_status["path_rejections"]:
            return VerificationError("ordinary_response_qwen_path_404")
        if 404 in qwen_status["upstream_statuses"]:
            return VerificationError("ordinary_response_fake_qwen_404")
    if response_statuses and response_statuses[-1] == 404:
        if path_classes and path_classes[-1] == "v1_responses":
            return VerificationError("ordinary_response_local_404")
        return VerificationError("ordinary_response_gateway_relay_404")
    if response_statuses and response_statuses[-1] == 200:
        known_errors = {
            "APIResponseValidationError": "ordinary_response_gateway_response_schema",
            "APIStatusError": "ordinary_response_gateway_response_status",
            "BadRequestError": "ordinary_response_gateway_response_bad_request",
        }
        return VerificationError(
            known_errors.get(
                type(exception).__name__ if exception is not None else "",
                "ordinary_response_failed",
            )
        )
    return VerificationError("ordinary_response_failed")


def _localize_constitution_failure(
    relay: _ForwardingRelay,
    qwen_relay_port: int | None,
    exception: BaseException | None = None,
    before: dict[str, object] | None = None,
    relay_response_count_before: int | None = None,
) -> VerificationError:
    if qwen_relay_port is None:
        return VerificationError("constitution_root_first_failed")
    try:
        qwen_status = _qwen_relay_status(qwen_relay_port)
    except VerificationError:
        return VerificationError("constitution_qwen_status_unavailable")
    if before is None:
        before = {
            "calls": 0,
            "compiler_calls": 0,
            "inference_calls": 0,
            "path_rejections": 0,
            "upstream_statuses": [],
        }
    try:
        if any(
            type(qwen_status[key]) is not int or type(before[key]) is not int
            or qwen_status[key] < before[key]
            for key in ("calls", "compiler_calls", "inference_calls", "path_rejections")
        ):
            return VerificationError("constitution_qwen_counter_invalid")
        before_statuses = before["upstream_statuses"]
        current_statuses = qwen_status["upstream_statuses"]
        if not isinstance(before_statuses, list) or not isinstance(current_statuses, list):
            return VerificationError("constitution_qwen_counter_invalid")
        delta = {
            key: qwen_status[key] - before[key]
            for key in ("calls", "compiler_calls", "inference_calls", "path_rejections")
        }
        upstream_delta = current_statuses[len(before_statuses) :]
    except (KeyError, TypeError):
        return VerificationError("constitution_qwen_counter_invalid")
    if delta["path_rejections"]:
        return VerificationError("constitution_qwen_path_404")
    if delta["calls"] <= 0:
        relay_status = relay.status()
        response_statuses = relay_status["response_statuses"]
        if relay_response_count_before is not None and len(response_statuses) <= relay_response_count_before:
            return VerificationError("constitution_gateway_before_local")
        if response_statuses and response_statuses[-1] >= 500:
            return VerificationError("constitution_local_http_5xx")
        if response_statuses and response_statuses[-1] >= 400:
            return VerificationError("constitution_local_http_4xx")
        return VerificationError("constitution_local_before_qwen")
    if delta["compiler_calls"] <= 0:
        if delta["inference_calls"] > 0:
            relay_status = relay.status()
            response_statuses = relay_status["response_statuses"]
            if response_statuses and response_statuses[-1] >= 500:
                return VerificationError("constitution_local_http_5xx")
            if response_statuses and response_statuses[-1] >= 400:
                return VerificationError("constitution_local_http_4xx")
            if response_statuses and response_statuses[-1] == 200:
                known_errors = {
                    "APIResponseValidationError": "constitution_gateway_response_schema",
                    "APIStatusError": "constitution_gateway_response_status",
                    "BadRequestError": "constitution_gateway_response_bad_request",
                }
                return VerificationError(
                    known_errors.get(
                        type(exception).__name__ if exception is not None else "",
                        "constitution_gateway_response_rejected",
                    )
                )
            return VerificationError("constitution_local_response_rejected")
        return VerificationError("constitution_inference_without_compiler")
    if any(status >= 400 for status in upstream_delta):
        return VerificationError("constitution_qwen_upstream_error")
    return VerificationError("constitution_local_compiler_rejected")


def _observe_project_safely(payload: dict[str, object]) -> dict[str, object]:
    local_source = str(LOCAL_ROOT / "src")
    sys.path.insert(0, local_source)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        from slaif_local_coding.config import ObservationPolicy
        from slaif_local_coding.constitution.detector import observe_request_for_pipeline
        from slaif_local_coding.constitution.models import ObservationContext, TrustClass

        observed, _sources, _dependencies = observe_request_for_pipeline(
            payload,
            ObservationContext(
                endpoint="/v1/responses",
                route_id="qwen38-vision-codex",
                model=CODEX_MODEL,
                streaming=False,
                discriminator_trust=TrustClass.ABSENT,
            ),
            ObservationPolicy(),
        )
        evidence_types = sorted(
            {
                evidence.type.value
                for root in observed.roots
                for evidence in root.evidence
            }
        )
        return {
            "root_count": len(observed.roots),
            "project_root_observed": any(
                evidence_type == "project_instructions" for evidence_type in evidence_types
            ),
            "evidence_types": evidence_types,
            "observation_complete": observed.complete,
        }
    except (ImportError, OSError, TypeError, ValueError, AttributeError) as exc:
        raise VerificationError("constitution_detector_failed") from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        if sys.path and sys.path[0] == local_source:
            del sys.path[0]


def _qwen_counter_delta(
    before: dict[str, object], after: dict[str, object]
) -> dict[str, object]:
    keys = ("calls", "compiler_calls", "inference_calls", "path_rejections")
    if any(
        type(before.get(key)) is not int
        or type(after.get(key)) is not int
        or after[key] < before[key]
        for key in keys
    ):
        raise VerificationError("constitution_qwen_counter_invalid")
    before_statuses = before.get("upstream_statuses")
    after_statuses = after.get("upstream_statuses")
    if not isinstance(before_statuses, list) or not isinstance(after_statuses, list):
        raise VerificationError("constitution_qwen_counter_invalid")
    return {
        **{key: after[key] - before[key] for key in keys},
        "upstream_statuses": after_statuses[len(before_statuses) :],
    }


def _replay_request(relay: _ForwardingRelay, request: CapturedRequest) -> int:
    return _relay_request(relay, request.path, request.headers, request.body)


async def _verify_accounting(database_url: str, keys: tuple[SeededKey, SeededKey], raw_markers: tuple[str, ...]) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    total_rows = 0
    try:
        async with sessions() as session:
            for key in keys:
                gateway_key = await session.get(GatewayKey, key.gateway_key_id)
                reservations = list((await session.execute(select(QuotaReservation).where(QuotaReservation.gateway_key_id == key.gateway_key_id))).scalars())
                ledgers = list((await session.execute(select(UsageLedger).where(UsageLedger.gateway_key_id == key.gateway_key_id))).scalars())
                if gateway_key is None or not reservations or len(reservations) != len(ledgers):
                    raise VerificationError("accounting_rows_incomplete")
                total_rows += len(reservations)
                if gateway_key.tokens_reserved_total != 0 or any(row.status != "finalized" for row in reservations):
                    non_failure = [row for row in reservations if row.requested_model != FAILURE_MODEL]
                    if gateway_key.tokens_reserved_total != 0 or any(
                        row.status != "finalized" for row in non_failure
                    ) or any(row.status == "pending" for row in reservations):
                        raise VerificationError("accounting_not_terminal")
                for reservation in reservations:
                    if reservation.quota_mode != "strict_bounded" or reservation.external_tool_capabilities != [] or reservation.external_tool_destination_ids != [] or reservation.external_tool_provider is not None or reservation.external_tool_route_id is not None:
                        raise VerificationError("accounting_external_facts")
                for ledger in ledgers:
                    encoded = json.dumps({"response_metadata": ledger.response_metadata, "usage_raw": ledger.usage_raw, "error_message": ledger.error_message}, default=str)
                    if any(marker in encoded for marker in raw_markers):
                        raise VerificationError("accounting_raw_identity_leak")
                    if any("external_tool" in key_name.lower() or "hold" in key_name.lower() or "fee" in key_name.lower() for key_name in _metadata_keys(ledger.response_metadata)):
                        raise VerificationError("accounting_external_metadata")
                    if ledger.accounting_status not in {"finalized", "failed"}:
                        raise VerificationError("accounting_status_incomplete")
                    if ledger.requested_model != FAILURE_MODEL and ledger.accounting_status != "finalized":
                        raise VerificationError("success_ledger_not_finalized")
                    if ledger.total_tokens < 0 or (ledger.actual_cost_eur is not None and ledger.actual_cost_eur < 0):
                        raise VerificationError("accounting_values_invalid")
                successful_ledgers = [
                    ledger for ledger in ledgers if ledger.requested_model != FAILURE_MODEL
                ]
                if gateway_key.requests_used_total != len(successful_ledgers):
                    raise VerificationError("accounting_request_counter_mismatch")
                if gateway_key.tokens_used_total != sum(
                    ledger.total_tokens for ledger in successful_ledgers
                ):
                    raise VerificationError("accounting_token_counter_mismatch")
                actual_cost = sum(
                    (ledger.actual_cost_eur or 0) for ledger in successful_ledgers
                )
                if gateway_key.cost_used_eur != actual_cost:
                    raise VerificationError("accounting_cost_counter_mismatch")
    finally:
        await engine.dispose()
    return total_rows


async def _safe_roundtrip_accounting_status_counts(
    database_url: str, key: SeededKey
) -> dict[str, int | bool]:
    """Read only bounded terminal status counts for safe failure localization."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.models import QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    result: dict[str, int | bool] = {
        "query_ok": False,
        "reservation_finalized": 0,
        "reservation_pending": 0,
        "reservation_released": 0,
        "ledger_finalized": 0,
        "ledger_failed": 0,
        "ledger_estimated": 0,
        "ledger_pending": 0,
    }
    try:
        async with sessions() as session:
            reservations = list(
                (
                    await session.execute(
                        select(QuotaReservation.status).where(
                            QuotaReservation.gateway_key_id == key.gateway_key_id
                        )
                    )
                ).scalars()
            )
            ledgers = list(
                (
                    await session.execute(
                        select(UsageLedger.accounting_status).where(
                            UsageLedger.gateway_key_id == key.gateway_key_id
                        )
                    )
                ).scalars()
            )
            for status in reservations:
                if status == "finalized":
                    result["reservation_finalized"] += 1
                elif status == "pending":
                    result["reservation_pending"] += 1
                elif status == "released":
                    result["reservation_released"] += 1
            for status in ledgers:
                if status == "finalized":
                    result["ledger_finalized"] += 1
                elif status == "failed":
                    result["ledger_failed"] += 1
                elif status == "pending":
                    result["ledger_pending"] += 1
            result["query_ok"] = True
    finally:
        await engine.dispose()
    return result


async def _verify_qualification_accounting(
    database_url: str, key: SeededKey, admitted_turn_count: int
) -> dict[str, int | bool]:
    """Verify rows for admitted turns, not raw Gateway request attempts."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    result: dict[str, int | bool] = {
        "query_ok": False,
        "reservation_rows": 0,
        "ledger_rows": 0,
        "reservation_finalized": 0,
        "reservation_released": 0,
        "ledger_finalized": 0,
        "ledger_failed": 0,
        "ledger_estimated": 0,
        "reservation_pending": 0,
        "ledger_pending": 0,
    }
    try:
        async with sessions() as session:
            gateway_key = await session.get(GatewayKey, key.gateway_key_id)
            reservations = list(
                (
                    await session.execute(
                        select(QuotaReservation)
                        .where(QuotaReservation.gateway_key_id == key.gateway_key_id)
                        .order_by(QuotaReservation.created_at)
                    )
                ).scalars()
            )
            ledgers = list(
                (
                    await session.execute(
                        select(UsageLedger)
                        .where(UsageLedger.gateway_key_id == key.gateway_key_id)
                        .order_by(UsageLedger.created_at)
                    )
                ).scalars()
            )
            result["reservation_rows"] = len(reservations)
            result["ledger_rows"] = len(ledgers)
            if (
                gateway_key is None
                or admitted_turn_count not in (0, 1, 2)
                or len(reservations) != admitted_turn_count
                or len(ledgers) != admitted_turn_count
                or len(reservations) != len(ledgers)
                or gateway_key.tokens_reserved_total != 0
            ):
                return result
            if admitted_turn_count == 0:
                result["query_ok"] = True
                return result
            for reservation in reservations:
                if reservation.status == "finalized":
                    result["reservation_finalized"] += 1
                elif reservation.status == "released":
                    result["reservation_released"] += 1
                elif reservation.status == "pending":
                    result["reservation_pending"] += 1
                else:
                    return result
            for ledger in ledgers:
                if ledger.accounting_status == "finalized":
                    result["ledger_finalized"] += 1
                elif ledger.accounting_status == "failed":
                    result["ledger_failed"] += 1
                elif ledger.accounting_status == "estimated":
                    result["ledger_estimated"] += 1
                elif ledger.accounting_status == "pending":
                    result["ledger_pending"] += 1
                else:
                    return result
            if not _qualification_terminal_sequence_valid(
                [reservation.status for reservation in reservations],
                [ledger.accounting_status for ledger in ledgers],
                admitted_turn_count,
            ) or any(
                reservation.quota_mode != "strict_bounded"
                or reservation.external_tool_capabilities != []
                or reservation.external_tool_destination_ids != []
                or reservation.external_tool_provider is not None
                or reservation.external_tool_route_id is not None
                for reservation in reservations
            ):
                return result
            result["query_ok"] = True
    finally:
        await engine.dispose()
    return result


def _qualification_terminal_sequence_valid(
    reservation_statuses: list[str], ledger_statuses: list[str], turn_count: int
) -> bool:
    """Accept finalized or released/failed terminal outcomes, never pending rows."""
    if (
        turn_count not in (0, 1, 2)
        or len(reservation_statuses) != turn_count
        or len(ledger_statuses) != turn_count
        or any(status not in {"finalized", "released"} for status in reservation_statuses)
        or any(status not in {"finalized", "failed", "estimated"} for status in ledger_statuses)
        or reservation_statuses.count("finalized") + reservation_statuses.count("released") != turn_count
        or ledger_statuses.count("finalized")
        + ledger_statuses.count("failed")
        + ledger_statuses.count("estimated")
        != turn_count
    ):
        return False
    if turn_count == 0:
        return True
    if not all(
        reservation_statuses[index] == "finalized"
        and ledger_statuses[index] == "finalized"
        for index in range(turn_count - 1)
    ):
        return False
    return (reservation_statuses[-1], ledger_statuses[-1]) in {
        ("finalized", "finalized"),
        ("released", "failed"),
        ("finalized", "estimated"),
    }


async def _verify_failure_accounting(database_url: str, key: SeededKey) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            gateway_key = await session.get(GatewayKey, key.gateway_key_id)
            reservations = list(
                (
                    await session.execute(
                        select(QuotaReservation).where(
                            QuotaReservation.gateway_key_id == key.gateway_key_id
                        )
                    )
                ).scalars()
            )
            ledgers = list(
                (
                    await session.execute(
                        select(UsageLedger).where(UsageLedger.gateway_key_id == key.gateway_key_id)
                    )
                ).scalars()
            )
            if gateway_key is None or len(reservations) != 1 or len(ledgers) != 1:
                raise VerificationError("failure_accounting_rows_incomplete")
            released = [row for row in reservations if row.status == "released"]
            reservation = reservations[0]
            if (
                len(released) != 1
                or gateway_key.tokens_reserved_total != 0
                or reservation.quota_mode != "strict_bounded"
                or reservation.external_tool_capabilities != []
                or reservation.external_tool_destination_ids != []
                or reservation.external_tool_provider is not None
                or reservation.external_tool_route_id is not None
            ):
                raise VerificationError("failure_reservation_not_released")
            failure_ledgers = [row for row in ledgers if row.accounting_status == "failed"]
            metadata_keys = _metadata_keys(ledgers[0].response_metadata)
            if (
                len(failure_ledgers) != 1
                or any(
                    "external_tool" in key.lower()
                    or "tool_fee" in key.lower()
                    or "hold" in key.lower()
                    for key in metadata_keys
                )
            ):
                raise VerificationError("failure_ledger_not_terminal")
    finally:
        await engine.dispose()


def _metadata_keys(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _metadata_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _metadata_keys(child)


@dataclass(frozen=True, slots=True)
class LocalMetrics:
    ingress_responses: int
    compiler_attempts: int
    cache_hits: int
    cache_misses: int
    rehydration_hits: int
    rehydration_injected: int
    tool_policy_drops: int
    upstream_failures: int


def _metric_total(metrics_text: str, metric_name: str, *, label_filter: str | None = None) -> int:
    total = 0
    for line in metrics_text.splitlines():
        if not line or line.startswith("#") or not line.startswith(metric_name):
            continue
        if not (line[len(metric_name) :].startswith(" ") or line[len(metric_name) :].startswith("{")):
            continue
        if label_filter is not None and label_filter not in line:
            continue
        try:
            total += int(float(line.rsplit(" ", 1)[1]))
        except (ValueError, IndexError):
            raise VerificationError("local_metrics_invalid")
    return total


def _local_metrics(port: int) -> LocalMetrics:
    try:
        response = httpx.get(f"http://127.0.0.1:{port}{LOCAL_METRICS_URL_PATH}", timeout=10)
    except httpx.HTTPError as exc:
        raise VerificationError("local_metrics_unavailable") from exc
    if response.status_code != 200:
        raise VerificationError("local_metrics_unavailable")
    text = response.text
    return LocalMetrics(
        ingress_responses=_metric_total(
            text, "slaif_requests_total", label_filter='status="200"'
        ),
        compiler_attempts=_metric_total(text, "slaif_constitution_compiler_attempts_total"),
        cache_hits=_metric_total(text, "slaif_constitution_cache_hits_total"),
        cache_misses=_metric_total(text, "slaif_constitution_cache_misses_total"),
        rehydration_hits=_metric_total(
            text, "slaif_constitution_rehydration_total", label_filter='state="hit"'
        ),
        rehydration_injected=_metric_total(
            text, "slaif_constitution_rehydration_total", label_filter='reason="rehydrated"'
        ),
        tool_policy_drops=_metric_total(
            text,
            "slaif_responses_tool_policy_total",
            label_filter='reason="disabled_codex_search_removed"',
        ),
        upstream_failures=_metric_total(text, "slaif_upstream_failures_total"),
    )


def _successful_relay_count(statuses: tuple[int, ...] | list[int]) -> int:
    """Count only the fixed 200 response class accepted as provider forwarding."""
    return sum(status == 200 for status in statuses)


def _verify_repository_cleanup() -> None:
    try:
        dirty = _git("status", "--porcelain", cwd=LOCAL_ROOT)
    except VerificationError:
        raise
    except Exception:
        raise VerificationError("repository_cleanup_failed") from None
    if dirty:
        raise VerificationError("local_dependency_changed")
    try:
        local_venv = (LOCAL_ROOT / ".venv").exists()
        local_bytecode = (LOCAL_ROOT / "src/slaif_local_coding/__pycache__").exists()
    except OSError:
        raise VerificationError("repository_cleanup_failed") from None
    if local_venv:
        raise VerificationError("local_checkout_venv_present_after_cleanup")
    if local_bytecode:
        raise VerificationError("local_bytecode_present_after_cleanup")


def _assert_local_bound_privacy(
    requests: tuple[CapturedRequest, ...],
    *,
    raw_aliases: set[str],
    service_token: str,
) -> None:
    """Reject raw client aliases in Local-bound data, allowing signed fields."""
    service_authorization = f"Bearer {service_token}"
    for request in requests:
        if any(alias.encode("utf-8") in request.body for alias in raw_aliases):
            raise VerificationError("raw_client_alias_forwarded")
        for name, value in request.headers.items():
            if name.lower().startswith("x-slaif-"):
                continue
            if name.lower() == "authorization" and value == service_authorization:
                continue
            if any(alias in value for alias in raw_aliases):
                raise VerificationError("raw_client_alias_forwarded")


def _safe_local_bound_privacy_findings(
    requests: tuple[CapturedRequest, ...],
    raw_aliases_by_turn: tuple[dict[str, set[str]], ...],
    *,
    service_token: str,
) -> list[dict[str, object]]:
    """Compare every source/target turn pair and retain safe classifications."""
    findings: list[dict[str, object]] = []

    def contains_alias(value: object, aliases: set[str]) -> bool:
        if isinstance(value, dict):
            return any(contains_alias(child, aliases) for child in value.values())
        if isinstance(value, list):
            return any(contains_alias(child, aliases) for child in value)
        return isinstance(value, str) and any(alias in value for alias in aliases)

    def body_path_class(payload: dict[str, object], aliases: set[str]) -> str | None:
        for field in (
            "prompt_cache_key",
            "instructions",
            "metadata",
            "reasoning",
            "tools",
            "tool_choice",
        ):
            if field in payload and contains_alias(payload[field], aliases):
                return field
        input_items = payload.get("input")
        if isinstance(input_items, list):
            input_without_internal = [
                {
                    key: child
                    for key, child in item.items()
                    if key != "internal_chat_message_metadata_passthrough"
                }
                if isinstance(item, dict)
                else item
                for item in input_items
            ]
            if contains_alias(input_without_internal, aliases):
                return "input_non_internal"
        body_without_known = {
            key: value
            for key, value in payload.items()
            if key not in {
                "client_metadata",
                "prompt_cache_key",
                "instructions",
                "metadata",
                "reasoning",
                "tools",
                "tool_choice",
                "input",
            }
        }
        return "other" if contains_alias(body_without_known, aliases) else None

    for target_turn, request in enumerate(requests):
        for source_turn, aliases_by_class in enumerate(raw_aliases_by_turn):
            if not aliases_by_class:
                continue
            for alias_class, aliases in aliases_by_class.items():
                try:
                    payload = json.loads(request.body)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = None
                if not isinstance(payload, dict):
                    payload = {}
                client_metadata = payload.get("client_metadata")
                if isinstance(client_metadata, dict) and contains_alias(
                    client_metadata, aliases
                ):
                    findings.append(
                        {
                            "source_turn": source_turn,
                            "target_turn": target_turn,
                            "location_class": "top_level_client_metadata",
                            "alias_key_class": alias_class,
                        }
                    )
                    continue
                internal_found = False
                input_items = payload.get("input")
                if isinstance(input_items, list):
                    for item in input_items:
                        if isinstance(item, dict) and contains_alias(
                            item.get("internal_chat_message_metadata_passthrough"), aliases
                        ):
                            internal_found = True
                            break
                if internal_found:
                    findings.append(
                        {
                            "source_turn": source_turn,
                            "target_turn": target_turn,
                            "location_class": "input_internal_chat_message_metadata_passthrough",
                            "alias_key_class": alias_class,
                        }
                    )
                    continue
                safe_body_path_class = body_path_class(payload, aliases)
                if safe_body_path_class is not None:
                    findings.append(
                        {
                            "source_turn": source_turn,
                            "target_turn": target_turn,
                            "location_class": "other_json_body_path",
                            "body_path_class": safe_body_path_class,
                            "alias_key_class": alias_class,
                        }
                    )
                    continue
                service_authorization = f"Bearer {service_token}"
                for name, value in request.headers.items():
                    if name.lower().startswith("x-slaif-"):
                        continue
                    if name.lower() == "authorization" and value == service_authorization:
                        continue
                    if any(alias in value for alias in aliases):
                        findings.append(
                            {
                                "source_turn": source_turn,
                                "target_turn": target_turn,
                                "location_class": "non_x_slaif_header",
                                "alias_key_class": alias_class,
                            }
                        )
                        break
                del payload
    return findings


def _assert_required_evidence(
    evidence: dict[str, object], *, require_post_cleanup_model: bool = True
) -> None:
    required = (
        "session_a1_a2_equal",
        "session_b_different",
        "session_second_key_different",
        "cache_reuse_observed",
        "rehydration_observed",
        "exact_replay_rejected",
        "failure_rollback_observed",
        "provider_counts_observed",
        "postgres_rows_observed",
        "hosted_tools_stripped",
        "privacy_observed",
    )
    if require_post_cleanup_model:
        required += ("post_cleanup_model_ok",)
    if any(evidence.get(name) is not True for name in required):
        raise VerificationError("required_composed_evidence_missing")
    if type(evidence.get("provider_calls")) is not int or evidence["provider_calls"] <= 0:
        raise VerificationError("provider_call_count_missing")
    if type(evidence.get("qwen_calls")) is not int or evidence["qwen_calls"] <= 0:
        raise VerificationError("qwen_call_count_missing")
    if evidence["provider_calls"] != evidence["qwen_calls"]:
        raise VerificationError("provider_call_count_mismatch")
    if type(evidence.get("relay_calls")) is not int or evidence["relay_calls"] <= 0:
        raise VerificationError("relay_call_count_missing")
    if type(evidence.get("local_forwarded_calls")) is not int or evidence["local_forwarded_calls"] <= 0:
        raise VerificationError("local_forward_count_missing")
    if evidence["relay_calls"] != evidence["local_forwarded_calls"]:
        raise VerificationError("local_forward_count_mismatch")


def _run_composed_impl(
    root: Path,
    runtime: RuntimeReference | None,
    codex_binary: Path,
    *,
    fake_qwen: bool = False,
    tracker: StageTracker | None = None,
) -> dict[str, object]:
    import scripts.capture_codex_protocol as capture
    from openai import OpenAI

    tracker = tracker or StageTracker()
    container = ""
    pulled = False
    fake_qwen_server: _FakeQwenServer | None = None
    fake_qwen_thread: threading.Thread | None = None
    fake_qwen_token: str | None = None
    try:
        postgres_url, container, pulled = _start_postgres(root, tracker=tracker)
    except VerificationError:
        raise
    except Exception as exc:
        raise tracker.unexpected_composed(exc) from None
    gateway = local = None
    qwen_relay = None
    relay = failure_server = None
    relay_thread = failure_thread = None
    gateway_facing_relay = None
    gateway_facing_relay_thread = None
    gateway_port = _free_port()
    local_port = 18031
    qwen_relay_port = _free_port()
    qwen_relay_token = secrets.token_urlsafe(32)
    service_token = secrets.token_urlsafe(32)
    signing_secret = secrets.token_urlsafe(32)
    derivation_secret = secrets.token_urlsafe(32)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    gateway_env = _gateway_environment(
        postgres_url,
        gateway_port=gateway_port,
        service_token=service_token,
        signing_secret=signing_secret,
        derivation_secret=derivation_secret,
        encryption_key=encryption_key,
    )
    tracker.set("migration")
    env_for_migration = dict(os.environ, **gateway_env)
    env_for_migration.pop("TEST_DATABASE_URL", None)
    migration = _run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env_for_migration,
        timeout=120,
    )
    if migration.returncode != 0:
        raise VerificationError("migration_failed")
    tracker.set("relay_start")
    relay, relay_thread = _start_relay(local_port)
    tracker.set("failure_provider_start")
    failure_server, failure_thread = _start_failure_server()
    if fake_qwen:
        tracker.set("qwen_relay_start")
        fake_qwen_server, fake_qwen_thread, fake_qwen_token = _start_fake_qwen()
    previous_environment = os.environ.copy()
    tracker.set("database_seed")
    os.environ.update(gateway_env)
    try:
        seeded = asyncio.run(_seed_database(postgres_url, relay_port=relay.server_address[1], failure_port=failure_server.server_address[1]))
    finally:
        os.environ.clear()
        os.environ.update(previous_environment)
    key_one, key_two, failure_key = seeded
    local_config = _local_config(
        root,
        local_port=local_port,
        qwen_relay_port=qwen_relay_port,
        qwen_relay_token=qwen_relay_token,
    )
    local_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(LOCAL_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(root / "local-pycache"),
        "SLAIF_155F_LOCAL_SERVICE_TOKEN": service_token,
        "SLAIF_155F_LOCAL_SIGNING_SECRET": signing_secret,
        "UV_PROJECT_ENVIRONMENT": str(root / "local-venv"),
        QWEN_RELAY_TOKEN_ENV: qwen_relay_token,
    }
    if (LOCAL_ROOT / ".venv").exists():
        raise VerificationError("local_checkout_venv_present_before_start")
    try:
        tracker.set("qwen_relay_start")
        qwen_relay = _start_qwen_relay(
            qwen_relay_port,
            runtime=None if fake_qwen else runtime,
            endpoint=(
                f"http://127.0.0.1:{fake_qwen_server.server_address[1]}/v1"
                if fake_qwen_server is not None
                else None
            ),
            qwen_token=fake_qwen_token,
            relay_token=qwen_relay_token,
        )
        tracker.set("qwen_relay_ready")
        _wait_http(f"http://127.0.0.1:{qwen_relay_port}/__155f_status")
        tracker.set("local_start")
        local = _start_process(
            ["uv", "run", "--project", str(LOCAL_ROOT), "--frozen", "slaif-local-coding", "--config", str(local_config)],
            cwd=LOCAL_ROOT,
            env=local_env,
        )
        if (LOCAL_ROOT / ".venv").exists():
            raise VerificationError("local_checkout_venv_created")
        tracker.set("gateway_start")
        gateway = _start_process(
            [sys.executable, "-m", "uvicorn", "slaif_gateway.main:app", "--host", "127.0.0.1", "--port", str(gateway_port), "--no-access-log", "--log-level", "warning"],
            cwd=REPO_ROOT,
            env=gateway_env,
        )
        tracker.set("local_health")
        _wait_http(f"http://127.0.0.1:{local_port}/healthz")
        tracker.set("local_readiness")
        _wait_http(f"http://127.0.0.1:{local_port}/readyz")
        tracker.set("gateway_health")
        _wait_http(f"http://127.0.0.1:{gateway_port}/healthz")
        gateway_facing_relay, gateway_facing_relay_thread = _start_relay(
            gateway_port, capture_requests=False, boundary_class="gateway_output"
        )
        client = OpenAI(api_key=key_one.plaintext, base_url=f"http://127.0.0.1:{gateway_port}/v1", max_retries=0)
        session_a = str(uuid.uuid4())
        session_b = str(uuid.uuid4())
        installation = str(uuid.uuid4())
        raw_aliases = {session_a, session_b, installation}

        def metadata(session: str) -> dict[str, str]:
            turn = str(uuid.uuid4())
            window = str(uuid.uuid4())
            raw_aliases.update({session, turn, window})
            return {
                "session_id": session,
                "thread_id": session,
                "root_turn_id": turn,
                "turn_id": turn,
                "x-codex-installation-id": installation,
                "x-codex-window-id": window,
            }

        def request_body(text: str, session: str, *, image: bool = False) -> dict[str, object]:
            content: list[dict[str, str]] = [{"type": "input_text", "text": text}]
            if image:
                content.append({"type": "input_image", "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="})
            return {
                "model": CODEX_MODEL,
                "input": [{"type": "message", "role": "user", "content": content}],
                "extra_body": {"client_metadata": metadata(session)},
            }

        baseline = _local_metrics(local_port)
        relay_start = len(relay.response_statuses)
        tracker.set("gateway_models")
        models = client.models.list()
        if not any(item.id == CODEX_MODEL for item in models.data):
            raise VerificationError("gateway_model_visibility_failed")
        tracker.set("ordinary_response")
        try:
            client.responses.create(
                **request_body("155f ordinary", session_a),
                tools=[{"type": "function", "name": "local_lookup", "description": "local", "parameters": {"type": "object"}}],
            )
        except Exception as exception:
            raise _localize_ordinary_response_failure(
                relay, qwen_relay_port, exception
            ) from None
        tracker.set("stream_response")
        streamed = client.responses.create(
            **request_body("155f stream", session_a),
            stream=True,
        )
        stream_events = list(streamed)
        if not any(getattr(event, "type", None) == "response.completed" for event in stream_events):
            raise VerificationError("stream_completion_event_missing")
        if fake_qwen:
            stream_structures = relay.status()["sse_structures"]
            if not isinstance(stream_structures, list) or not stream_structures:
                raise VerificationError("gateway_sse_schema_missing")
            structure = stream_structures[-1]
            if not isinstance(structure, dict):
                raise VerificationError("gateway_sse_schema_invalid")
            _assert_pinned_capture_sse_structure(structure)
        tracker.set("image_response")
        client.responses.create(
            **request_body("155f image", session_a, image=True),
        )
        project_text = "# AGENTS.md instructions for /synthetic\n\n<INSTRUCTIONS>\nMUST use bounded synthetic policy.\n</INSTRUCTIONS>"
        project_body = {
            "model": CODEX_MODEL,
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": project_text}]}],
            "tools": [
                {
                    "type": "tool_search",
                    "description": "synthetic candidate",
                    "execution": "client",
                    "parameters": {},
                },
                {
                    "type": "web_search",
                    "external_web_access": False,
                    "search_content_types": ["text"],
                },
            ],
            "extra_body": {"client_metadata": metadata(session_a)},
        }
        constitution_observation = _observe_project_safely(project_body)
        if (
            constitution_observation["root_count"] != 1
            or constitution_observation["project_root_observed"] is not True
            or constitution_observation["observation_complete"] is not True
        ):
            raise VerificationError("constitution_detector_miss")
        tracker.set("constitution_root_first")
        constitution_relay_before = len(relay.status()["response_statuses"])
        constitution_qwen_before = _qwen_relay_status(qwen_relay_port)
        try:
            client.responses.create(**project_body)
        except Exception as exc:
            raise _localize_constitution_failure(
                relay,
                qwen_relay_port,
                exc,
                constitution_qwen_before,
                constitution_relay_before,
            ) from None
        constitution_qwen_after = _qwen_relay_status(qwen_relay_port)
        constitution_qwen_delta = _qwen_counter_delta(
            constitution_qwen_before, constitution_qwen_after
        )
        if (
            constitution_qwen_delta["calls"] <= 0
            or constitution_qwen_delta["compiler_calls"] <= 0
            or constitution_qwen_delta["inference_calls"] <= 0
            or constitution_qwen_delta["path_rejections"] != 0
            or any(status >= 400 for status in constitution_qwen_delta["upstream_statuses"])
        ):
            raise VerificationError("constitution_qwen_delta_invalid")
        tracker.set("constitution_root_reuse")
        client.responses.create(**project_body)
        tracker.set("zero_root_rehydration")
        no_root_body = {
            **request_body("155f zero root", session_a),
        }
        client.responses.create(**no_root_body)

        home = root / "codex-home"
        work = root / "codex-work"
        catalog = root / "codex-catalog.json"
        home.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        codex_env = capture._isolated_environment(home)
        codex_env["OPENAI_API_KEY"] = key_one.plaintext
        codex_env["SLAIF_CODEX_CAPTURE_API_KEY"] = key_one.plaintext
        capture._write_0149_model_catalog(codex_binary, catalog, environment=codex_env, model=CODEX_MODEL)
        codex_gateway_port = gateway_facing_relay.server_address[1]
        first_index = len(relay.snapshot())
        first_sse_structure_index = len(gateway_facing_relay.status()["sse_structures"])
        tracker.set("codex_session_a")
        first = _run(capture._exec_command_0149(codex_binary, workdir=work, port=codex_gateway_port, model=CODEX_MODEL, model_catalog=catalog, output_path=root / "codex-out-1", ephemeral=False), cwd=REPO_ROOT, env=codex_env, timeout=180)
        if first.returncode != 0:
            if fake_qwen:
                _assert_new_pinned_capture_sse_structure(
                    gateway_facing_relay,
                    first_sse_structure_index,
                    missing_code="codex_session_a_gateway_sse_missing",
                    mismatch_code="codex_session_a_gateway_sse_mismatch",
                )
            category = capture.classify_codex_failure(first.stderr, first.stdout)
            allowed_categories = {
                "configuration_rejected",
                "argument_rejected",
                "argument_separator_rejected",
                "argument_or_configuration_rejected",
                "dummy_auth_environment_rejected",
                "loopback_request_failed",
                "loopback_connection_failed",
                "workdir_rejected",
                "custom_provider_auth_rejected",
                "mock_stream_rejected",
                "mock_stream_closed_early",
                "mock_stream_idle_timeout",
                "mock_completed_event_rejected",
                "mock_response_failed",
                "mock_http_status_rejected",
                "turn_failed",
                "error_event",
                "incomplete_event_sequence",
                "nonzero_after_turn_completed",
                "unclassified",
            }
            raise VerificationError(
                f"codex_session_a_{category if category in allowed_categories else 'unclassified'}"
            )
        if fake_qwen:
            _assert_new_pinned_capture_sse_structure(
                gateway_facing_relay,
                first_sse_structure_index,
                missing_code="codex_session_a_gateway_sse_missing",
                mismatch_code="codex_session_a_gateway_sse_mismatch",
            )
        thread = capture._session_capture_thread_id(first.stdout)
        first_capture = relay.snapshot()[first_index:]
        if len(first_capture) != 1:
            raise VerificationError("codex_session_a_request_count")
        second_index = len(relay.snapshot())
        second_sse_structure_index = len(gateway_facing_relay.status()["sse_structures"])
        tracker.set("codex_session_a_resume")
        second = _run(capture._exec_resume_command_0149(codex_binary, workdir=work, port=codex_gateway_port, model=CODEX_MODEL, model_catalog=catalog, output_path=root / "codex-out-2", thread_id=thread), cwd=work, env=codex_env, timeout=180)
        if second.returncode != 0:
            raise VerificationError("codex_session_resume_failed")
        if fake_qwen:
            _assert_new_pinned_capture_sse_structure(
                gateway_facing_relay,
                second_sse_structure_index,
                missing_code="codex_session_resume_gateway_sse_missing",
                mismatch_code="codex_session_resume_gateway_sse_mismatch",
            )
        second_capture = relay.snapshot()[second_index:]
        if len(second_capture) != 1:
            raise VerificationError("codex_session_resume_request_count")
        third_index = len(relay.snapshot())
        third_sse_structure_index = len(gateway_facing_relay.status()["sse_structures"])
        tracker.set("codex_session_b")
        third = _run(capture._exec_command_0149(codex_binary, workdir=work, port=codex_gateway_port, model=CODEX_MODEL, model_catalog=catalog, output_path=root / "codex-out-3", ephemeral=False), cwd=REPO_ROOT, env=codex_env, timeout=180)
        if third.returncode != 0:
            raise VerificationError("codex_session_b_failed")
        if fake_qwen:
            _assert_new_pinned_capture_sse_structure(
                gateway_facing_relay,
                third_sse_structure_index,
                missing_code="codex_session_b_gateway_sse_missing",
                mismatch_code="codex_session_b_gateway_sse_mismatch",
            )
        third_capture = relay.snapshot()[third_index:]
        if len(third_capture) != 1:
            raise VerificationError("codex_session_b_request_count")
        session_a1 = first_capture[0].headers.get("x-slaif-session")
        session_a2 = second_capture[0].headers.get("x-slaif-session")
        session_b_value = third_capture[0].headers.get("x-slaif-session")
        if not session_a1 or session_a1 != session_a2:
            raise VerificationError("signed_session_a_relationship_failed")
        if not session_b_value or session_b_value == session_a1:
            raise VerificationError("signed_session_b_isolation_failed")
        tracker.set("replay_and_tamper")
        replay_status = _replay_request(relay, first_capture[0])
        if replay_status != 409:
            raise VerificationError("exact_replay_not_rejected")
        bad_signature = dict(first_capture[0].headers)
        bad_signature["x-slaif-signature"] = "v1=" + "0" * 64
        if _relay_request(relay, first_capture[0].path, bad_signature, first_capture[0].body) != 403:
            raise VerificationError("signature_tamper_not_rejected")
        if _relay_request(relay, first_capture[0].path, first_capture[0].headers, first_capture[0].body + b" ") != 403:
            raise VerificationError("body_tamper_not_rejected")
        if _relay_request(relay, "/v1/chat/completions", first_capture[0].headers, first_capture[0].body) != 403:
            raise VerificationError("path_tamper_not_rejected")
        if _relay_request(relay, first_capture[0].path + "?tamper=1", first_capture[0].headers, first_capture[0].body) != 403:
            raise VerificationError("query_tamper_not_rejected")
        tracker.set("second_gateway_key")
        second_client = OpenAI(api_key=key_two.plaintext, base_url=f"http://127.0.0.1:{gateway_port}/v1", max_retries=0)
        second_key_index = len(relay.snapshot())
        second_client.responses.create(**request_body("155f second key", session_a))
        second_key_capture = relay.snapshot()[second_key_index:]
        if len(second_key_capture) != 1 or second_key_capture[0].headers.get("x-slaif-session") in {None, session_a1}:
            raise VerificationError("signed_session_second_key_isolation_failed")
        tracker.set("preprovider_negatives")
        over_quota_before = len(relay.snapshot())
        try:
            second_client.responses.create(**request_body("155f over quota", session_a))
        except Exception:
            pass
        else:
            raise VerificationError("over_quota_not_rejected")
        if len(relay.snapshot()) != over_quota_before:
            raise VerificationError("over_quota_forwarded")
        invalid_key_before = len(relay.snapshot())
        try:
            OpenAI(api_key="sk-slaif-invalid", base_url=f"http://127.0.0.1:{gateway_port}/v1", max_retries=0).models.list()
        except Exception:
            pass
        else:
            raise VerificationError("invalid_key_not_rejected")
        if len(relay.snapshot()) != invalid_key_before:
            raise VerificationError("invalid_key_forwarded")
        malformed_before = len(relay.snapshot())
        try:
            client.responses.create(
                model=CODEX_MODEL,
                input=request_body("155f malformed aliases", session_a)["input"],
                extra_body={"client_metadata": {"session_id": session_a, "thread_id": str(uuid.uuid4())}},
            )
        except Exception:
            pass
        else:
            raise VerificationError("unequal_aliases_not_rejected")
        if len(relay.snapshot()) != malformed_before:
            raise VerificationError("unequal_aliases_forwarded")
        try:
            client.responses.create(**{**request_body("155f hosted", session_a), "tools": [{"type": "web_search"}], "tool_choice": "required"})
        except Exception:
            pass
        else:
            raise VerificationError("hosted_tool_choice_not_rejected")
        adapter_required_before = len(relay.snapshot())
        try:
            client.responses.create(
                **{
                    **request_body("155f adapter required", session_a),
                    "tools": [{"type": "tool_search"}, {"type": "web_search"}],
                    "tool_choice": "required",
                }
            )
        except Exception:
            pass
        else:
            raise VerificationError("adapter_required_not_rejected")
        if len(relay.snapshot()) != adapter_required_before:
            raise VerificationError("adapter_required_forwarded")
        tracker.set("controlled_provider_failure")
        local_before_failure = _local_metrics(local_port)
        before_failure = len(relay.snapshot())
        failure_client = OpenAI(
            api_key=failure_key.plaintext,
            base_url=f"http://127.0.0.1:{gateway_port}/v1",
            max_retries=0,
        )
        try:
            failure_client.responses.create(
                model=FAILURE_MODEL,
                input=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "155f failure"}],
                    }
                ],
            )
        except Exception:
            pass
        else:
            raise VerificationError("synthetic_failure_not_observed")
        if len(relay.snapshot()) != before_failure or failure_server.calls != 1:
            raise VerificationError("failure_provider_call_count_invalid")
        local_after_failure = _local_metrics(local_port)
        if local_after_failure != local_before_failure:
            raise VerificationError("failure_reached_local_cache")
        tracker.set("accounting")
        asyncio.run(_verify_failure_accounting(postgres_url, failure_key))
        relay_statuses = relay.response_statuses[relay_start:]
        local_forwarded_calls = local_after_failure.ingress_responses - baseline.ingress_responses
        relay_calls = _successful_relay_count(relay_statuses)
        database_rows = asyncio.run(
            _verify_accounting(
                postgres_url,
                (key_one, key_two),
                (session_a, session_b, installation),
            )
        )
        if database_rows != relay_calls:
            raise VerificationError("accounting_row_count_mismatch")
        tracker.set("local_metrics")
        final_metrics = _local_metrics(local_port)
        if final_metrics.cache_hits <= baseline.cache_hits or final_metrics.rehydration_hits <= baseline.rehydration_hits or final_metrics.rehydration_injected <= baseline.rehydration_injected:
            raise VerificationError("cache_rehydration_evidence_missing")
        if final_metrics.tool_policy_drops <= baseline.tool_policy_drops:
            raise VerificationError("hosted_tool_strip_evidence_missing")
        if final_metrics.ingress_responses <= baseline.ingress_responses:
            raise VerificationError("provider_metrics_missing")
        tracker.set("qwen_wire_evidence")
        qwen_status = _qwen_relay_status(qwen_relay_port)
        if (
            type(qwen_status.get("calls")) is not int
            or qwen_status["calls"] <= 0
            or qwen_status.get("successful_calls") != qwen_status["calls"]
            or qwen_status.get("compiler_calls", 0) <= 0
            or qwen_status.get("inference_calls", 0) <= 0
            or qwen_status.get("bad_inbound_auth") is not False
            or qwen_status.get("auth_replaced") is not True
            or qwen_status.get("internal_headers") is not False
            or qwen_status.get("internal_body") is not False
            or set(qwen_status.get("tool_types", [])) & {"tool_search", "web_search"}
            or set(qwen_status.get("outbound_header_names", []))
            - {"authorization", "content-type", "accept", "accept-encoding"}
        ):
            raise VerificationError("qwen_relay_boundary_failed")
        if fake_qwen and (
            fake_qwen_server is None
            or not fake_qwen_server.first_event_sent.is_set()
            or fake_qwen_server.compiler_calls <= 0
            or fake_qwen_server.inference_calls <= 0
        ):
            raise VerificationError("fake_qwen_wire_evidence_missing")
        provider_calls = final_metrics.ingress_responses - baseline.ingress_responses
        if provider_calls <= 0:
            raise VerificationError("provider_call_count_missing")
        tracker.set("privacy")
        _assert_local_bound_privacy(
            relay.snapshot(), raw_aliases=raw_aliases, service_token=service_token
        )
        if any(
            key.plaintext.encode() in request.body
            or key.plaintext in request.headers.get("authorization", "")
            for key in (key_one, key_two)
            for request in relay.snapshot()
        ):
            raise VerificationError("gateway_key_forwarded_to_local")
        evidence = {
            "session_a1_a2_equal": True,
            "session_b_different": True,
            "session_second_key_different": True,
            "cache_reuse_observed": True,
            "rehydration_observed": True,
            "exact_replay_rejected": True,
            "failure_rollback_observed": True,
            "provider_counts_observed": True,
            "postgres_rows_observed": True,
            "hosted_tools_stripped": True,
            "privacy_observed": True,
            "post_cleanup_model_ok": False,
            "provider_calls": qwen_status["calls"],
            "relay_calls": relay_calls,
            "qwen_calls": qwen_status["calls"],
            "local_forwarded_calls": local_forwarded_calls,
            "fake_rehearsal": fake_qwen,
            "constitution_detector_root_count": constitution_observation["root_count"],
            "constitution_detector_project_root": constitution_observation["project_root_observed"],
            "constitution_detector_evidence_types": constitution_observation["evidence_types"],
            "constitution_detector_complete": constitution_observation["observation_complete"],
            "constitution_qwen_delta_calls": constitution_qwen_delta["calls"],
            "constitution_qwen_delta_compiler_calls": constitution_qwen_delta["compiler_calls"],
            "constitution_qwen_delta_inference_calls": constitution_qwen_delta["inference_calls"],
        }
        return evidence
    finally:
        primary = sys.exc_info()[1]
        primary_stage = tracker.current
        try:
            tracker.set("process_cleanup")
            for process in (local, gateway, qwen_relay):
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            for server, thread in (
                (relay, relay_thread),
                (gateway_facing_relay, gateway_facing_relay_thread),
                (failure_server, failure_thread),
            ):
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    thread.join(timeout=10)
            if fake_qwen_server is not None:
                fake_qwen_server.shutdown()
                fake_qwen_server.server_close()
            if fake_qwen_thread is not None:
                fake_qwen_thread.join(timeout=10)
            tracker.set("container_cleanup")
            if container:
                _docker("rm", "-f", container, timeout=30)
            if pulled:
                _docker("rmi", "postgres:16", timeout=60)
            tracker.set("repository_cleanup")
            _verify_repository_cleanup()
        except Exception:
            if primary is not None:
                if isinstance(primary, VerificationError):
                    raise primary
                if primary_stage in COMPOSITION_STAGES:
                    tracker.current = primary_stage
                    raise VerificationError(f"unexpected_{primary_stage}") from None
                raise VerificationError("unexpected_unknown_stage") from None
            raise
        if primary is not None and primary_stage in COMPOSITION_STAGES:
            tracker.current = primary_stage


def _run_direct_stream_diagnostic(
    root: Path, runtime: RuntimeReference
) -> dict[str, object]:
    from openai import OpenAI

    del root
    port = _free_port()
    relay_token = secrets.token_urlsafe(32)
    relay = None
    client_completed = False
    failure_code: str | None = None
    try:
        relay = _start_qwen_relay(port, runtime=runtime, relay_token=relay_token)
        _wait_http(f"http://127.0.0.1:{port}/__155f_status")
        client = OpenAI(
            api_key=relay_token,
            base_url=f"http://127.0.0.1:{port}/v1",
            max_retries=0,
        )
        try:
            stream = client.responses.create(
                model=CODEX_MODEL,
                input=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "bounded differential"}],
                    }
                ],
                stream=True,
            )
            for _event in stream:
                pass
            client_completed = True
        except Exception:
            failure_code = "direct_qwen_client_stream_failed"
        status = _qwen_relay_status(port)
        structures = status.get("sse_structures")
        structure = structures[-1] if isinstance(structures, list) and structures else None
        statuses = status.get("upstream_statuses")
        content_types = status.get("sse_content_type_classes")
        observation = _stream_observation(
            boundary="direct_qwen",
            status=statuses[-1] if isinstance(statuses, list) and statuses else None,
            content_type_class=(
                content_types[-1]
                if isinstance(content_types, list) and content_types
                else None
            ),
            structure=structure,
            client_completed=client_completed,
            failure_code=_relay_failure_code(status, failure_code),
        )
        observation["handler_error"] = status.get("handler_error") is True
        observation["upstream_truncated"] = status.get("upstream_truncated") is True
        return observation
    finally:
        _stop_process(relay)


def _run_composed_codex_tool_roundtrip(
    *,
    root: Path,
    codex_binary: Path,
    key: SeededKey,
    postgres_url: str,
    relay: _ForwardingRelay,
    gateway_output: _ForwardingRelay,
    fake_qwen_server: _FakeQwenServer | None,
    qwen_port: int,
    local_port: int,
    service_token: str,
    signing_secret: str,
    tracker: StageTracker,
    qualification_hook: bool = False,
    qualification_rejection_mode: bool = False,
    non_prefixed_tool_id: bool = False,
) -> dict[str, object]:
    import scripts.capture_codex_protocol as capture

    home = root / "codex-home"
    work = root / "codex-work"
    catalog = root / "codex-catalog.json"
    home.mkdir(mode=0o700)
    work.mkdir(mode=0o700)
    (work / "SYNTHETIC_TASK.md").write_text(
        "bounded local tool task\n", encoding="utf-8"
    )
    environment = capture._isolated_environment(home)
    environment["SLAIF_CODEX_CAPTURE_API_KEY"] = key.plaintext
    capture._write_0149_model_catalog(
        codex_binary,
        catalog,
        environment=environment,
        model=CODEX_MODEL,
    )
    try:
        local_metrics_before = _local_metrics(local_port)
    except VerificationError:
        local_metrics_before = None
    tracker.set("tool_codex_execution")
    result = _run(
        capture._exec_command_0149(
            codex_binary,
            workdir=work,
            port=gateway_output.server_address[1],
            model=CODEX_MODEL,
            model_catalog=catalog,
            output_path=root / "codex-output.json",
            ephemeral=True,
            instruction=(
                "Use one local shell command to read SYNTHETIC_TASK.md, then report completion."
            ),
        ),
        cwd=REPO_ROOT,
        env=environment,
        timeout=180,
    )
    if result.returncode != 0:
        tracker.set("tool_roundtrip_codex_failure_projection")
        codex_failure_category = capture.classify_codex_failure(
            result.stderr, result.stdout
        )
        tracker.set("tool_roundtrip_gateway_snapshot")
        gateway_status = gateway_output.status()
        gateway_requests = gateway_output.snapshot()
        tracker.set("tool_roundtrip_local_snapshot")
        local_status = relay.status()
        try:
            local_metrics_after = _local_metrics(local_port)
        except VerificationError:
            local_metrics_after = None
        local_status["local_boundary_states"] = _safe_local_boundary_states_from_codes(
            local_status.get("local_error_code_classes"),
            local_status.get("response_statuses"),
            local_metrics_before,
            local_metrics_after,
        )
        local_requests_snapshot = relay.snapshot()
        signed_identity_facts = [
            _safe_signed_identity_projection(
                request,
                service_token=service_token,
                signing_secret=signing_secret,
            )
            for request in local_requests_snapshot[:2]
        ]
        local_status["signed_identity_facts"] = signed_identity_facts
        tracker.set("tool_roundtrip_qwen_projection")
        qwen_status = _qwen_relay_status(qwen_port)
        fake_status = fake_qwen_server.status() if fake_qwen_server is not None else {}
        tracker.set("tool_roundtrip_request_projection")
        request_projections = [
            _safe_roundtrip_request_projection(request.body)
            for request in gateway_requests
        ]
        tracker.set("tool_roundtrip_accounting_projection")
        try:
            accounting_statuses = asyncio.run(
                _safe_roundtrip_accounting_status_counts(postgres_url, key)
            )
        except Exception:
            accounting_statuses = {
                "query_ok": False,
                "reservation_finalized": 0,
                "reservation_pending": 0,
                "reservation_released": 0,
                "ledger_finalized": 0,
                "ledger_failed": 0,
                "ledger_estimated": 0,
                "ledger_pending": 0,
            }
        boundary_snapshot = _safe_boundary_snapshot(
            gateway_status=gateway_status,
            gateway_request_count=len(gateway_requests),
            local_status=local_status,
            local_request_count=len(local_requests_snapshot),
            qwen_status=qwen_status,
            accounting_statuses=accounting_statuses,
            codex_provenance={
                "source_class": "task_local_exact_npm",
                "verified_binary_is_invoked": codex_binary is not None,
            },
            codex_exit_success=False,
        )
        tracker.set("tool_roundtrip_qualification_artifact")
        qualification_rejection = None
        if qualification_hook and qualification_rejection_mode:
            qualification_rejection = _write_qualification_rejection(
                root,
                profile={
                    "codex_reasoning_events": True,
                    "codex_0149_function_tool_events": True,
                    "codex_streaming_tool_events": True,
                    "codex_encrypted_reasoning_replay": False,
                    "web_search": False,
                    "declared_client_tools_class": "bounded",
                    "web_search_max_tool_calls_class": "none",
                },
                event_type="response.output_item.added",
                top_level_fields=[
                    {"name": "item", "type": "object"},
                    {"name": "output_index", "type": "integer"},
                    {"name": "sequence_number", "type": "integer"},
                    {"name": "type", "type": "string"},
                ],
                nested_object_fields=[
                    {
                        "name": "item",
                        "fields": [
                            {"name": "arguments", "type": "string"},
                            {"name": "call_id", "type": "string"},
                            {"name": "caller", "type": "null"},
                            {"name": "id", "type": "string"},
                            {"name": "name", "type": "string"},
                            {"name": "namespace", "type": "string"},
                            {"name": "status", "type": "string"},
                            {"name": "type", "type": "string"},
                        ],
                    }
                ],
                rejection_code="responses_stream_event_not_supported",
            )
        elif qualification_hook:
            qualification_rejection = _read_qualification_rejection(root)
        if qualification_hook:
            summary = _safe_preclassification_summary(
                stage=tracker.current,
                codex_failure_category=codex_failure_category,
                gateway_requests=len(gateway_requests),
                gateway_status=gateway_status,
                local_requests=len(local_requests_snapshot),
                local_status=local_status,
                qwen_status=qwen_status,
                request_projections=request_projections,
                accounting_statuses=accounting_statuses,
                qualification_rejection=qualification_rejection,
                artifact_equal=qualification_rejection is not None,
                signed_identity_facts=signed_identity_facts,
            )
            _write_preclassification_summary(root, summary)
        tracker.set("tool_roundtrip_failure_decision")
        failure_code = _localize_composed_codex_failure(
            codex_failure_category=codex_failure_category,
            gateway_requests=len(gateway_requests),
            gateway_statuses=gateway_status.get("response_statuses"),
            gateway_structures=gateway_status.get("sse_structures"),
            local_requests=len(local_requests_snapshot),
            local_statuses=local_status.get("response_statuses"),
            request_projections=request_projections,
            gateway_error_code_classes=gateway_status.get("error_code_classes"),
            gateway_error_param_classes=gateway_status.get("error_param_classes"),
            qwen_status=qwen_status,
            fake_status=fake_status,
            accounting_statuses=accounting_statuses,
        )
        if non_prefixed_tool_id:
            second_projection = (
                request_projections[1]
                if len(request_projections) > 1
                else {}
            )
            return {
                "codex_exit_success": False,
                "failure_code": failure_code,
                "gateway_request_count": len(gateway_requests),
                "local_request_count": len(local_requests_snapshot),
                "qwen_inference_count": qwen_status.get("inference_calls"),
                "selected_tool_call": {
                    "tool_type": "function",
                    "item_id_state": second_projection.get(
                        "function_item_id_state", "other"
                    ),
                    "item_id_prefix_class": second_projection.get(
                        "function_item_id_prefix_class", "other"
                    ),
                    "call_id_state": second_projection.get(
                        "function_call_id_state", "other"
                    ),
                    "adjacent_matching_output": second_projection.get(
                        "adjacent_matching_output", False
                    ),
                },
                "gateway_error_code_classes": [
                    _safe_gateway_error_code_class(value)
                    for value in gateway_status.get("error_code_classes", [])
                ],
                "gateway_error_param_classes": [
                    _safe_gateway_error_param_class(value)
                    for value in gateway_status.get("error_param_classes", [])
                ],
                "gateway_error_param_field_classes": [
                    value
                    if value in _SUMMARY_GATEWAY_ERROR_PARAM_FIELDS
                    else "other"
                    for value in gateway_status.get("error_param_field_classes", [])
                ],
                "gateway_input_item_error_projections": [
                    _safe_summary_input_item_error_projection(value)
                    for value in gateway_status.get("input_item_error_projections", [])
                ],
                "accounting": {
                    "reservation_finalized": accounting_statuses.get(
                        "reservation_finalized", 0
                    ),
                    "reservation_released": accounting_statuses.get(
                        "reservation_released", 0
                    ),
                    "ledger_finalized": accounting_statuses.get("ledger_finalized", 0),
                    "ledger_failed": accounting_statuses.get("ledger_failed", 0),
                    "pending": accounting_statuses.get("reservation_pending", 0)
                    + accounting_statuses.get("ledger_pending", 0),
                },
            }
        if qualification_hook:
            local_requests = local_requests_snapshot
            turn_counts = (
                len(gateway_requests),
                len(local_requests),
                qwen_status.get("inference_calls"),
            )
            turn_count_mismatch = (
                any(count not in (1, 2) for count in turn_counts)
                or len(set(turn_counts)) != 1
            )
            # A recognized second Gateway rejection is the bounded diagnostic
            # evidence for the expected g2/l1/q1 topology.  Preserve its
            # status/error/profile summary instead of replacing it with the
            # generic count mismatch that motivated this continuation.
            if turn_count_mismatch and not (
                turn_counts == (2, 1, 1)
                and failure_code.startswith(
                    "composed_tool_roundtrip_second_turn_gateway_"
                )
            ):
                raise _qualification_turn_count_error(turn_counts)
            function_call_output_count = 0
            for request in local_requests:
                try:
                    payload = json.loads(request.body)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise VerificationError("qualification_body_invalid") from exc
                items = payload.get("input") if isinstance(payload, dict) else None
                if isinstance(items, list):
                    function_call_output_count += sum(
                        1
                        for item in items
                        if isinstance(item, dict)
                        and item.get("type") == "function_call_output"
                    )
                del payload
            qualification_accounting = asyncio.run(
                _verify_qualification_accounting(
                    postgres_url,
                    key,
                    turn_counts[1],
                )
            )
            if (
                qualification_accounting.get("query_ok") is not True
            ):
                raise VerificationError("qualification_accounting_incomplete")
            accounting_rows = (
                qualification_accounting["reservation_finalized"]
                + qualification_accounting["reservation_released"]
            )
            return {
                "codex_exit_success": False,
                "qualification_rejection": qualification_rejection,
                "gateway_to_local_turns": turn_counts[0],
                "local_to_qwen_inference_turns": turn_counts[2],
                "function_call_output_count": function_call_output_count,
                "accounting_rows": accounting_rows,
                "accounting_reservation_released": qualification_accounting[
                    "reservation_released"
                ],
                "accounting_ledger_failed": qualification_accounting["ledger_failed"],
                "failure_code": failure_code,
                "boundary_snapshot": boundary_snapshot.to_dict(
                    outcome=_classify_boundary_snapshot(
                        boundary_snapshot, assertion_failed=True
                    ),
                    assertion_class=_safe_boundary_assertion_class(failure_code),
                ),
                "qualification_summary": (
                    _read_preclassification_summary(root)
                    if qualification_hook
                    else None
                ),
            }
        del accounting_statuses, codex_failure_category, request_projections
        return {
            "codex_exit_success": False,
            "failure_code": failure_code,
            "boundary_snapshot": boundary_snapshot.to_dict(
                outcome=_classify_boundary_snapshot(
                    boundary_snapshot, assertion_failed=True
                ),
                assertion_class=_safe_boundary_assertion_class(failure_code),
            ),
        }

    tracker.set("tool_roundtrip_boundary_capture")
    gateway_requests = gateway_output.snapshot()
    local_requests = relay.snapshot()
    gateway_status = gateway_output.status()
    local_status = relay.status()
    try:
        local_metrics_after = _local_metrics(local_port)
    except VerificationError:
        local_metrics_after = None
    local_status["local_boundary_states"] = _safe_local_boundary_states_from_codes(
        local_status.get("local_error_code_classes"),
        local_status.get("response_statuses"),
        local_metrics_before,
        local_metrics_after,
    )
    signed_identity_facts = [
        _safe_signed_identity_projection(
            request,
            service_token=service_token,
            signing_secret=signing_secret,
        )
        for request in local_requests[:2]
    ]
    local_status["signed_identity_facts"] = signed_identity_facts
    qwen_status = _qwen_relay_status(qwen_port)
    accounting_statuses: dict[str, int | bool]
    try:
        accounting_statuses = asyncio.run(_safe_roundtrip_accounting_status_counts(postgres_url, key))
    except Exception:
        accounting_statuses = {
            "query_ok": False,
            "reservation_finalized": 0,
            "reservation_pending": 0,
            "reservation_released": 0,
            "ledger_finalized": 0,
            "ledger_failed": 0,
            "ledger_estimated": 0,
            "ledger_pending": 0,
        }
    boundary_snapshot = _safe_boundary_snapshot(
        gateway_status=gateway_status,
        gateway_request_count=len(gateway_requests),
        local_status=local_status,
        local_request_count=len(local_requests),
        qwen_status=qwen_status,
        accounting_statuses=accounting_statuses,
        codex_provenance={
            "source_class": "task_local_exact_npm",
            "verified_binary_is_invoked": codex_binary is not None,
        },
        codex_exit_success=True,
    )
    if len(local_requests) != 2 or len(gateway_requests) != 2:
        raise _BoundaryDiagnosticError("composed_tool_roundtrip_request_count", boundary_snapshot)
    tool_result_counts: list[int] = []
    for request in local_requests:
        try:
            payload = json.loads(request.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _BoundaryDiagnosticError(
                "composed_tool_roundtrip_body_invalid", boundary_snapshot
            ) from exc
        items = payload.get("input") if isinstance(payload, dict) else None
        tool_result_counts.append(
            sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("type") == "function_call_output"
            )
            if isinstance(items, list)
            else 0
        )
        del payload
    if tool_result_counts != [0, 1]:
        raise _BoundaryDiagnosticError("composed_tool_roundtrip_tool_result_count", boundary_snapshot)

    tracker.set("tool_roundtrip_privacy_aliases")
    raw_aliases_by_turn: list[dict[str, set[str]]] = []
    raw_aliases: set[str] = set()
    for request in gateway_requests:
        try:
            payload = json.loads(request.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _BoundaryDiagnosticError(
                "composed_tool_roundtrip_gateway_body_invalid", boundary_snapshot
            ) from exc
        aliases_by_class: dict[str, set[str]] = {}
        metadata = payload.get("client_metadata") if isinstance(payload, dict) else None
        if isinstance(metadata, dict):
            for metadata_key, value in metadata.items():
                alias_class = _SAFE_RAW_METADATA_KEY_CLASSES.get(metadata_key)
                if alias_class is not None and isinstance(value, str):
                    aliases_by_class.setdefault(alias_class, set()).add(value)
                    raw_aliases.add(value)
        raw_aliases_by_turn.append(aliases_by_class)
        del payload
    privacy_findings = _safe_local_bound_privacy_findings(
        local_requests,
        tuple(raw_aliases_by_turn),
        service_token=service_token,
    )
    if privacy_findings:
        finding = privacy_findings[0]
        location = finding.get("location_class")
        body_path = finding.get("body_path_class")
        alias_class = finding.get("alias_key_class")
        source_turn = finding.get("source_turn")
        target_turn = finding.get("target_turn")
        if (
            type(source_turn) is not int
            or type(target_turn) is not int
            or not 0 <= source_turn < len(raw_aliases_by_turn)
            or not 0 <= target_turn < len(local_requests)
            or location not in {
                "top_level_client_metadata",
                "input_internal_chat_message_metadata_passthrough",
                "other_json_body_path",
                "non_x_slaif_header",
            }
            or (
                location == "other_json_body_path"
                and body_path not in _SAFE_PRIVACY_BODY_PATH_CLASSES
            )
            or alias_class not in set(_SAFE_RAW_METADATA_KEY_CLASSES.values())
        ):
            raise _BoundaryDiagnosticError(
                "composed_tool_roundtrip_privacy_invalid", boundary_snapshot
            )
        raise _BoundaryDiagnosticError(
            f"composed_tool_roundtrip_privacy_source_{source_turn}_target_{target_turn}_"
            f"{location}_{body_path if location == 'other_json_body_path' else 'none'}_{alias_class}",
            boundary_snapshot,
        )
    try:
        _assert_local_bound_privacy(
            local_requests,
            raw_aliases=raw_aliases,
            service_token=service_token,
        )
    except VerificationError:
        raise _BoundaryDiagnosticError(
            "composed_tool_roundtrip_privacy_invalid", boundary_snapshot
        ) from None
    del privacy_findings, raw_aliases, raw_aliases_by_turn
    tracker.set("tool_roundtrip_signed_identity_headers")
    signed_header_facts = [
        {
            "service_bearer": request.headers.get("authorization")
            == f"Bearer {service_token}",
            "session_header_class": (
                "opaque"
                if isinstance(request.headers.get("x-slaif-session"), str)
                and len(request.headers["x-slaif-session"]) <= 256
                else "missing_or_invalid"
            ),
            "signature_header_class": (
                "v1_hex"
                if isinstance(request.headers.get("x-slaif-signature"), str)
                and request.headers["x-slaif-signature"].startswith("v1=")
                and len(request.headers["x-slaif-signature"]) == 67
                and all(
                    char in "0123456789abcdef"
                    for char in request.headers["x-slaif-signature"][3:]
                )
                else "missing_or_invalid"
            ),
        }
        for request in local_requests
    ]
    if any(
        not fact["service_bearer"]
        or fact["session_header_class"] != "opaque"
        or fact["signature_header_class"] != "v1_hex"
        for fact in signed_header_facts
    ):
        raise _BoundaryDiagnosticError(
            "composed_tool_roundtrip_signed_headers_invalid", boundary_snapshot
        )
    del signed_header_facts
    tracker.set("tool_roundtrip_signed_key_forwarding")
    if any(
        key.plaintext.encode("utf-8") in request.body
        or key.plaintext in request.headers.get("authorization", "")
        for request in local_requests
    ):
        raise _BoundaryDiagnosticError(
            "composed_tool_roundtrip_gateway_key_forwarded", boundary_snapshot
        )

    tracker.set("tool_roundtrip_sse_validation")
    fake_status = fake_qwen_server.status() if fake_qwen_server is not None else {}
    try:
        _assert_two_turn_sse_structures(
            gateway_status.get("sse_structures"),
            error_code="composed_tool_roundtrip_gateway_sse_invalid",
        )
        if fake_qwen_server is not None:
            _assert_function_then_message_structure(gateway_status.get("sse_structures"))
        else:
            _assert_protected_function_then_message_structure(
                gateway_status.get("sse_structures")
            )
        _assert_two_turn_sse_structures(
            local_status.get("sse_structures"),
            error_code="composed_tool_roundtrip_local_sse_invalid",
        )
        tracker.set("tool_roundtrip_qwen_boundary")
        _assert_two_turn_sse_structures(
            qwen_status.get("sse_structures"),
            error_code="composed_tool_roundtrip_qwen_sse_invalid",
        )
    except VerificationError as exc:
        raise _BoundaryDiagnosticError(str(exc), boundary_snapshot) from None
    if (
        local_status.get("response_statuses") != [200, 200]
        or gateway_status.get("response_statuses") != [200, 200]
        or local_status.get("handler_error") is True
        or local_status.get("downstream_closed_early") is True
        or local_status.get("upstream_truncated") is True
        or gateway_status.get("handler_error") is True
        or gateway_status.get("downstream_closed_early") is True
        or gateway_status.get("upstream_truncated") is True
        or qwen_status.get("inference_calls") != 2
        or qwen_status.get("successful_calls") != 2
        or qwen_status.get("handler_error") is True
        or qwen_status.get("upstream_truncated") is True
        or qwen_status.get("downstream_closed_early") is True
        or not set(qwen_status.get("tool_types", [])).issubset({"function", "custom"})
        or (
            fake_qwen_server is not None
            and (
                fake_status.get("tool_roundtrip_turns") != 2
                or fake_status.get("tool_result_observed") != 1
                or fake_status.get("function_lifecycle_count") != 1
                or fake_status.get("message_lifecycle_count") != 1
            )
        )
    ):
        raise _BoundaryDiagnosticError("composed_tool_roundtrip_boundary_invalid", boundary_snapshot)
    tracker.set("tool_roundtrip_accounting")
    accounting_rows = asyncio.run(_verify_accounting(postgres_url, (key,), ()))
    if accounting_rows != 2:
        raise _BoundaryDiagnosticError("composed_tool_roundtrip_accounting_rows", boundary_snapshot)
    return {
        "codex_exit_success": True,
        "gateway_to_local_turns": 2,
        "local_to_qwen_inference_turns": 2,
        "function_call_output_count": 1,
        "function_lifecycle_count": 1,
        "message_lifecycle_count": 1,
        "accounting_rows": accounting_rows,
        "boundary_snapshot": boundary_snapshot.to_dict(
            outcome="full_two_turn_path_succeeded",
            assertion_class="none",
        ),
    }


def _assert_two_turn_sse_structures(
    structures: object, *, error_code: str
) -> None:
    if (
        not isinstance(structures, list)
        or len(structures) != 2
        or any(
            not isinstance(structure, dict)
            or structure.get("invalid") is not False
            or not _stream_has_valid_completion(structure)
            or not isinstance(structure.get("event_counts"), dict)
            or structure["event_counts"].get("response.created") != 1
            or structure["event_counts"].get("response.completed") != 1
            or structure.get("duplicates") is not False
            or structure.get("unknown_events") is not False
            or structure.get("error_event") is not False
            or structure.get("response_completed") is not True
            or structure.get("completed_usage_valid") is not True
            or structure.get("normal_close") is not True
            or structure.get("downstream_closed_early") is not False
            for structure in structures
        )
    ):
        raise VerificationError(error_code)


def _localize_composed_codex_failure(
    *,
    codex_failure_category: str,
    gateway_requests: int,
    gateway_statuses: object,
    gateway_structures: object,
    local_requests: int,
    local_statuses: object,
    request_projections: object,
    gateway_error_code_classes: object,
    gateway_error_param_classes: object,
    qwen_status: dict[str, object],
    fake_status: dict[str, object],
    accounting_statuses: dict[str, int | bool],
) -> str:
    """Map one failed fake roundtrip to a fixed, bounded boundary code."""
    launch_categories = {
        "configuration_rejected",
        "argument_rejected",
        "argument_separator_rejected",
        "argument_or_configuration_rejected",
        "dummy_auth_environment_rejected",
        "workdir_rejected",
        "custom_provider_auth_rejected",
        "loopback_connection_failed",
    }
    stream_categories = {
        "mock_stream_rejected",
        "mock_stream_closed_early",
        "mock_stream_idle_timeout",
        "mock_completed_event_rejected",
        "mock_response_failed",
        "incomplete_event_sequence",
    }

    def bounded_count(value: object) -> int | None:
        return value if type(value) is int and 0 <= value <= 2 else None

    def statuses(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            f"{status // 100}xx" if type(status) is int and 100 <= status <= 599 else "other"
            for status in value[:8]
        ]

    def failed_at(value: list[str], index: int) -> bool:
        return index < len(value) and value[index] in {"4xx", "5xx"}

    def safe_structures(value: object) -> list[dict[str, bool]]:
        if not isinstance(value, list):
            return []
        return [
            {
                "invalid": item.get("invalid") is True,
                "error_event": item.get("error_event") is True,
            }
            for item in value[:4]
            if isinstance(item, dict)
        ]

    def safe_error_class(value: object, *, parameter: bool = False) -> str:
        if parameter:
            return value if value in _SAFE_GATEWAY_ERROR_PARAM_CLASSES else "other"
        return value if value in _SAFE_GATEWAY_ERROR_CODE_CLASSES else "other"

    def safe_projection(value: object) -> str:
        try:
            return _safe_roundtrip_projection_class(value)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError):
            return "other"

    category = codex_failure_category if isinstance(codex_failure_category, str) else "other"
    gateway_count = bounded_count(gateway_requests)
    local_count = bounded_count(local_requests)
    gateway_codes = statuses(gateway_statuses)
    local_codes = statuses(local_statuses)
    gateway_shapes = safe_structures(gateway_structures)
    safe_qwen = qwen_status if isinstance(qwen_status, dict) else {}
    safe_fake = fake_status if isinstance(fake_status, dict) else {}
    safe_accounting = accounting_statuses if isinstance(accounting_statuses, dict) else {}
    if category in launch_categories or gateway_count == 0:
        return "composed_tool_roundtrip_launch_config"
    qwen_codes = statuses(safe_qwen.get("inference_statuses"))
    if qwen_codes and qwen_codes[0] in {"4xx", "5xx"}:
        return "composed_tool_roundtrip_first_qwen_rejection"
    local_first_failed = (
        local_count is not None and local_count >= 1 and failed_at(local_codes, 0)
    )
    gateway_first_failed = (
        gateway_count == 1
        and (not gateway_codes or failed_at(gateway_codes, 0))
    ) or (
        gateway_shapes
        and gateway_shapes[0]["error_event"]
    )
    if local_first_failed:
        return "composed_tool_roundtrip_first_local_rejection"
    if gateway_first_failed:
        code_class = "other"
        param_class = "other"
        if isinstance(gateway_error_code_classes, list) and gateway_error_code_classes:
            code_class = safe_error_class(gateway_error_code_classes[0])
        if isinstance(gateway_error_param_classes, list) and gateway_error_param_classes:
            param_class = safe_error_class(gateway_error_param_classes[0], parameter=True)
        projections = request_projections if isinstance(request_projections, list) else []
        projection_class = safe_projection(projections[0]) if projections else "other"
        ownership = "post_local" if local_count is not None and local_count >= 1 else "pre_local"
        return (
            f"composed_tool_roundtrip_first_gateway_{ownership}_"
            f"{code_class}_{param_class}_{projection_class}"
        )
    if (
        local_count is not None
        and local_count >= 2
        and failed_at(local_codes, 1)
    ):
        return "composed_tool_roundtrip_second_turn_local_rejection"
    if (
        gateway_count is not None
        and gateway_count >= 2
        and failed_at(gateway_codes, 1)
    ):
        code_class = "other"
        param_class = "other"
        projection_class = "other"
        if isinstance(gateway_error_code_classes, list) and len(gateway_error_code_classes) > 1:
            code_class = safe_error_class(gateway_error_code_classes[1])
        if isinstance(gateway_error_param_classes, list) and len(gateway_error_param_classes) > 1:
            param_class = safe_error_class(gateway_error_param_classes[1], parameter=True)
        if isinstance(request_projections, list) and len(request_projections) > 1:
            projection_class = safe_projection(request_projections[1])
        return (
            "composed_tool_roundtrip_second_turn_gateway_"
            f"{code_class}_{param_class}_{projection_class}"
        )
    if codex_failure_category in stream_categories or any(
        structure["invalid"]
        for structure in gateway_shapes
    ):
        return "composed_tool_roundtrip_codex_stream_parse"
    # Keep the remaining facts in the bounded decision input so a future
    # reviewer can distinguish a final-message failure without retaining data.
    _ = (
        safe_qwen.get("inference_calls"),
        safe_qwen.get("successful_calls"),
        safe_fake.get("function_lifecycle_count"),
        safe_fake.get("message_lifecycle_count"),
        safe_accounting.get("reservation_finalized"),
        safe_accounting.get("ledger_finalized"),
        safe_accounting.get("ledger_failed"),
    )
    return "composed_tool_roundtrip_final_message_failure"


def _assert_function_then_message_structure(structures: object) -> None:
    if not isinstance(structures, list) or len(structures) != 2:
        raise VerificationError("composed_tool_roundtrip_lifecycle_missing")
    first, second = structures
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise VerificationError("composed_tool_roundtrip_lifecycle_invalid")
    first_counts = first.get("event_counts")
    second_counts = second.get("event_counts")
    if not isinstance(first_counts, dict) or not isinstance(second_counts, dict):
        raise VerificationError("composed_tool_roundtrip_lifecycle_invalid")
    def count(counts: dict[object, object], event: str) -> int | None:
        value = counts.get(event, 0)
        return value if type(value) is int and 0 <= value <= _SSE_EVENT_COUNT_LIMIT else None

    if (
        count(first_counts, "response.output_item.added") != 1
        or count(first_counts, "response.function_call_arguments.done") != 1
        or count(first_counts, "response.output_item.done") != 1
        or (count(first_counts, "response.function_call_arguments.delta") or 0) < 1
        or count(first_counts, "response.output_text.delta") != 0
        or count(first_counts, "response.output_text.done") != 0
        or count(first_counts, "response.content_part.added") != 0
        or count(first_counts, "response.content_part.done") != 0
        or count(second_counts, "response.output_item.added") != 1
        or count(second_counts, "response.content_part.added") != 1
        or (count(second_counts, "response.output_text.delta") or 0) < 1
        or count(second_counts, "response.output_text.done") != 1
        or count(second_counts, "response.content_part.done") != 1
        or count(second_counts, "response.output_item.done") != 1
        or count(second_counts, "response.function_call_arguments.delta") != 0
        or count(second_counts, "response.function_call_arguments.done") != 0
    ):
        raise VerificationError("composed_tool_roundtrip_lifecycle_invalid")


def _assert_protected_function_then_message_structure(structures: object) -> None:
    """Require the function/message lifecycle while permitting reviewed reasoning items."""
    if not isinstance(structures, list) or len(structures) != 2:
        raise VerificationError("composed_tool_roundtrip_lifecycle_missing")
    first, second = structures
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise VerificationError("composed_tool_roundtrip_lifecycle_invalid")

    def count(structure: dict[str, object], event: str) -> int | None:
        counts = structure.get("event_counts")
        if not isinstance(counts, dict):
            return None
        value = counts.get(event, 0)
        return value if type(value) is int and 0 <= value <= _SSE_EVENT_COUNT_LIMIT else None

    if (
        count(first, "response.output_item.added") is None
        or count(first, "response.output_item.added") < 1
        or count(first, "response.output_item.done") is None
        or count(first, "response.output_item.done") < 1
        or count(first, "response.function_call_arguments.delta") is None
        or count(first, "response.function_call_arguments.delta") < 1
        or count(first, "response.function_call_arguments.done") != 1
        or count(first, "response.output_item.added") < count(first, "response.function_call_arguments.done")
        or count(first, "response.content_part.added") != 0
        or count(first, "response.content_part.done") != 0
        or count(first, "response.output_text.delta") != 0
        or count(first, "response.output_text.done") != 0
        or count(second, "response.function_call_arguments.delta") != 0
        or count(second, "response.function_call_arguments.done") != 0
        or count(second, "response.output_item.added") is None
        or count(second, "response.output_item.added") < 1
        or count(second, "response.content_part.added") != 1
        or count(second, "response.output_text.delta") is None
        or count(second, "response.output_text.delta") < 1
        or count(second, "response.output_text.done") != 1
        or count(second, "response.content_part.done") != 1
        or count(second, "response.output_item.done") is None
        or count(second, "response.output_item.done") < 1
    ):
        raise VerificationError("composed_tool_roundtrip_lifecycle_invalid")


def _run_composed_stream_diagnostic(
    root: Path,
    runtime: RuntimeReference | None,
    *,
    fake_qwen: bool = False,
    tool_roundtrip_mode: bool = False,
    qualification_rejection_mode: bool = False,
    provider_failure_mode: bool = False,
    codex_binary: Path | None = None,
    tracker: StageTracker | None = None,
    qualification_hook: bool = False,
    non_prefixed_tool_id: bool = False,
) -> dict[str, object]:
    from openai import OpenAI

    tracker = tracker or StageTracker()
    tracker.set("postgres_image")
    try:
        postgres_url, container, pulled = _start_postgres(root, tracker=tracker)
    except VerificationError:
        raise
    except Exception as exc:
        raise tracker.unexpected_composed(exc) from None
    gateway_port = _free_port()
    local_port = 18031
    qwen_port = _free_port()
    service_token = secrets.token_urlsafe(32)
    signing_secret = secrets.token_urlsafe(32)
    derivation_secret = secrets.token_urlsafe(32)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    gateway_env = _gateway_environment(
        postgres_url,
        gateway_port=gateway_port,
        service_token=service_token,
        signing_secret=signing_secret,
        derivation_secret=derivation_secret,
        encryption_key=encryption_key,
    )
    env_for_migration = dict(os.environ, **gateway_env)
    env_for_migration.pop("TEST_DATABASE_URL", None)
    relay = failure_server = qwen_relay = local = gateway = gateway_output = None
    fake_qwen_server: _FakeQwenServer | None = None
    fake_qwen_thread: threading.Thread | None = None
    fake_qwen_token: str | None = None
    relay_thread = failure_thread = gateway_output_thread = None
    try:
        tracker.set("migration")
        migration = _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env_for_migration,
            timeout=120,
        )
        if migration.returncode != 0:
            raise VerificationError("differential_migration_failed")
        tracker.set("relay_start")
        relay, relay_thread = _start_relay(local_port)
        tracker.set("failure_provider_start")
        if tool_roundtrip_mode:
            failure_server = failure_thread = None
        else:
            failure_server, failure_thread = _start_failure_server()
        if fake_qwen:
            tracker.set("qwen_relay_start")
            fake_qwen_server, fake_qwen_thread, fake_qwen_token = _start_fake_qwen(
                tool_roundtrip_mode=tool_roundtrip_mode,
                qualification_rejection_mode=qualification_rejection_mode,
                provider_failure_mode=provider_failure_mode,
                non_prefixed_tool_id=non_prefixed_tool_id,
            )
        previous_environment = os.environ.copy()
        tracker.set("database_seed")
        os.environ.update(gateway_env)
        try:
            seeded = asyncio.run(
                _seed_database(
                    postgres_url,
                    relay_port=relay.server_address[1],
                    failure_port=(
                        failure_server.server_address[1]
                        if failure_server is not None
                        else relay.server_address[1]
                    ),
                    differential=True,
                    tool_roundtrip_only=tool_roundtrip_mode,
                )
            )
        finally:
            os.environ.clear()
            os.environ.update(previous_environment)
        key = seeded[0]
        qwen_token = secrets.token_urlsafe(32)
        tracker.set("qwen_relay_start")
        qwen_relay = _start_qwen_relay(
            qwen_port,
            runtime=None if fake_qwen else runtime,
            endpoint=(
                f"http://127.0.0.1:{fake_qwen_server.server_address[1]}/v1"
                if fake_qwen_server is not None
                else None
            ),
            qwen_token=fake_qwen_token,
            relay_token=qwen_token,
        )
        tracker.set("qwen_relay_ready")
        _wait_http(f"http://127.0.0.1:{qwen_port}/__155f_status")
        tracker.set("local_config")
        local_config = _local_config(
            root,
            local_port=local_port,
            qwen_relay_port=qwen_port,
            qwen_relay_token=qwen_token,
        )
        local_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(LOCAL_ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(root / "local-pycache"),
            SERVICE_TOKEN_ENV: service_token,
            SIGNING_SECRET_ENV: signing_secret,
            "UV_PROJECT_ENVIRONMENT": str(root / "local-venv"),
            QWEN_RELAY_TOKEN_ENV: qwen_token,
        }
        if (LOCAL_ROOT / ".venv").exists():
            raise VerificationError("local_checkout_venv_present_before_start")
        tracker.set("local_start")
        local = _start_process(
            [
                "uv",
                "run",
                "--project",
                str(LOCAL_ROOT),
                "--frozen",
                "slaif-local-coding",
                "--config",
                str(local_config),
            ],
            cwd=LOCAL_ROOT,
            env=local_env,
        )
        tracker.set("gateway_start")
        gateway = _start_process(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "slaif_gateway.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(gateway_port),
                "--no-access-log",
                "--log-level",
                "warning",
            ],
            cwd=REPO_ROOT,
            env=gateway_env,
        )
        tracker.set("local_health")
        _wait_http(f"http://127.0.0.1:{local_port}/healthz")
        tracker.set("local_readiness")
        _wait_http(f"http://127.0.0.1:{local_port}/readyz")
        tracker.set("gateway_health")
        _wait_http(f"http://127.0.0.1:{gateway_port}/healthz")
        tracker.set("gateway_start")
        gateway_output, gateway_output_thread = _start_relay(
            gateway_port,
            capture_requests=tool_roundtrip_mode,
            boundary_class="gateway_output",
        )
        if tool_roundtrip_mode:
            if codex_binary is None:
                raise VerificationError("composed_tool_roundtrip_setup_invalid")
            return _run_composed_codex_tool_roundtrip(
                root=root,
                codex_binary=codex_binary,
                key=key,
                postgres_url=postgres_url,
                relay=relay,
                gateway_output=gateway_output,
                fake_qwen_server=fake_qwen_server,
                qwen_port=qwen_port,
                local_port=local_port,
                service_token=service_token,
                signing_secret=signing_secret,
                tracker=tracker,
                qualification_hook=qualification_hook,
                qualification_rejection_mode=qualification_rejection_mode,
                non_prefixed_tool_id=non_prefixed_tool_id,
            )
        client = OpenAI(
            api_key=key.plaintext,
            base_url=f"http://127.0.0.1:{gateway_output.server_address[1]}/v1",
            max_retries=0,
        )
        qwen_status_before = _qwen_relay_status(qwen_port)
        session = str(uuid.uuid4())
        metadata = {
            "session_id": session,
            "thread_id": session,
            "root_turn_id": str(uuid.uuid4()),
            "turn_id": str(uuid.uuid4()),
            "x-codex-installation-id": str(uuid.uuid4()),
            "x-codex-window-id": str(uuid.uuid4()),
        }
        tracker.set("client_stream")
        client_completed = False
        failure_code: str | None = None
        try:
            stream = client.responses.create(
                model=CODEX_MODEL,
                input=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "bounded differential"}],
                    }
                ],
                stream=True,
                extra_body={"client_metadata": metadata},
            )
            for _event in stream:
                pass
            client_completed = True
        except Exception:
            failure_code = "composed_client_stream_failed"
        tracker.set("boundary_capture")
        local_status = relay.status()
        gateway_status = gateway_output.status()
        qwen_status = _qwen_relay_status(qwen_port)
        qwen_failure_code = _relay_failure_code(qwen_status)
        local_structures = local_status.get("sse_structures")
        gateway_structures = gateway_status.get("sse_structures")
        local_output = _stream_observation(
            boundary="local_output",
            status=(
                local_status["response_statuses"][-1]
                if local_status.get("response_statuses")
                else None
            ),
            content_type_class=(
                local_status["response_content_type_classes"][-1]
                if local_status.get("response_content_type_classes")
                else None
            ),
            structure=(
                local_structures[-1]
                if isinstance(local_structures, list) and local_structures
                else None
            ),
            client_completed=True,
            failure_code=_relay_failure_code(local_status, qwen_failure_code),
        )
        local_output["handler_error"] = local_status.get("handler_error") is True
        local_output["upstream_truncated"] = local_status.get("upstream_truncated") is True
        gateway_observation = _stream_observation(
            boundary="gateway_output",
            status=(
                gateway_status["response_statuses"][-1]
                if gateway_status.get("response_statuses")
                else None
            ),
            content_type_class=(
                gateway_status["response_content_type_classes"][-1]
                if gateway_status.get("response_content_type_classes")
                else None
            ),
            structure=(
                gateway_structures[-1]
                if isinstance(gateway_structures, list) and gateway_structures
                else None
            ),
            client_completed=client_completed,
            failure_code=_relay_failure_code(gateway_status, failure_code),
        )
        gateway_observation["handler_error"] = gateway_status.get("handler_error") is True
        gateway_observation["upstream_truncated"] = gateway_status.get("upstream_truncated") is True
        tracker.set("accounting")
        accounting_verified = False
        try:
            asyncio.run(
                _verify_accounting(
                    postgres_url,
                    (key,),
                    (session, metadata["root_turn_id"], metadata["turn_id"], metadata["x-codex-installation-id"], metadata["x-codex-window-id"]),
                )
            )
            accounting_verified = True
        except VerificationError:
            accounting_verified = False
        return {
            "local_output": local_output,
            "gateway_output": gateway_observation,
            "accounting_verified": accounting_verified,
            "qwen_status": qwen_status,
            "qwen_status_before": qwen_status_before,
            "local_status": local_status,
            "gateway_status": gateway_status,
        }
    finally:
        primary = sys.exc_info()[1]
        primary_stage = tracker.current
        try:
            tracker.set("process_cleanup")
            _stop_process(local)
            _stop_process(gateway)
            _stop_process(qwen_relay)
            for server, thread in (
                (relay, relay_thread),
                (gateway_output, gateway_output_thread),
                (failure_server, failure_thread),
            ):
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    thread.join(timeout=10)
            if fake_qwen_server is not None:
                fake_qwen_server.shutdown()
                fake_qwen_server.server_close()
            if fake_qwen_thread is not None:
                fake_qwen_thread.join(timeout=10)
            tracker.set("container_cleanup")
            if container:
                _docker("rm", "-f", container, timeout=30)
            if pulled:
                _docker("rmi", "postgres:16", timeout=60)
            tracker.set("repository_cleanup")
            _verify_repository_cleanup()
        except Exception:
            if primary is not None:
                if isinstance(primary, VerificationError):
                    raise primary
                tracker.current = primary_stage
                raise tracker.unexpected_composed(primary) from None
            raise tracker.unexpected_composed(primary) from None
        if primary is not None and not isinstance(primary, VerificationError):
            tracker.current = primary_stage
            raise tracker.unexpected_composed(primary) from None


def run_codex_tool_roundtrip_fake(*, root: Path, codex_binary: Path) -> dict[str, object]:
    """Required fake gate: Codex through Gateway, Local, relay, and fake Qwen."""
    provenance = _verify_codex_task_local_provenance(root, codex_binary)
    result = _run_composed_stream_diagnostic(
        root,
        None,
        fake_qwen=True,
        tool_roundtrip_mode=True,
        codex_binary=codex_binary,
    )
    result["codex_provenance"] = provenance
    return result


def run_codex_tool_roundtrip_non_prefixed_reproduction() -> dict[str, object]:
    """Reproduce Codex 0.149 ID stripping against the uncorrected Gateway."""
    _verify_commit_topology()
    _verify_fixtures()
    with tempfile.TemporaryDirectory(prefix="slaif-155aj-reproduction-", dir="/tmp") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        codex_binary = _install_codex(root)
        return _run_composed_stream_diagnostic(
            root,
            None,
            fake_qwen=True,
            tool_roundtrip_mode=True,
            codex_binary=codex_binary,
            non_prefixed_tool_id=True,
        )


def _run_dedicated_codex_tool_roundtrip(
    *,
    fake_qwen: bool,
    qualification_hook: bool,
    qualification_rejection_mode: bool = False,
    provider_failure_mode: bool = False,
) -> dict[str, object]:
    """Run one dedicated Codex tool roundtrip, with optional disposable hook."""
    _verify_commit_topology()
    runtime = None if fake_qwen else _read_runtime_reference()
    _verify_fixtures()
    if not fake_qwen:
        _verify_local_signed_identity_matrix()
        _source_qwen_credential_only_for_local(runtime)
        _verify_protected_model_health(runtime)
    with tempfile.TemporaryDirectory(prefix="slaif-155aj-qualification-", dir="/tmp") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        _validate_local_config(root, runtime)
        codex_binary = _install_codex(root)
        codex_provenance = _verify_codex_task_local_provenance(root, codex_binary)
        try:
            result = _run_composed_stream_diagnostic(
                root,
                runtime,
                fake_qwen=fake_qwen,
                tool_roundtrip_mode=True,
                qualification_rejection_mode=qualification_rejection_mode,
                provider_failure_mode=provider_failure_mode,
                codex_binary=codex_binary,
                qualification_hook=qualification_hook,
                tracker=StageTracker(),
            )
        except _BoundaryDiagnosticError as exception:
            result = {
                "codex_exit_success": False,
                "failure_code": exception.code,
                "boundary_snapshot": exception.snapshot.to_dict(
                    outcome=_classify_boundary_snapshot(
                        exception.snapshot, assertion_failed=True
                    ),
                    assertion_class=_safe_boundary_assertion_class(exception.code),
                ),
            }
        except Exception as exception:
            summary = _read_preclassification_summary(root) if qualification_hook else None
            if qualification_hook and summary is not None:
                result = {
                    "codex_exit_success": False,
                    "failure_code": _safe_qualification_failure_code(exception),
                    "qualification_rejection": _read_qualification_rejection(root),
                    "qualification_summary": summary,
                }
            else:
                if isinstance(exception, VerificationError):
                    raise
                raise VerificationError(_safe_qualification_failure_code(exception)) from None
        result["codex_provenance"] = codex_provenance
        reread_rejection = _read_qualification_rejection(root)
        reread_summary = _read_preclassification_summary(root) if qualification_hook else None
        retained_summary = result.get("qualification_summary")
        if retained_summary is not None:
            retained_summary = _sanitize_preclassification_summary(retained_summary)
            if reread_summary is not None and reread_summary != retained_summary:
                raise VerificationError("qualification_summary_inconsistent")
        elif reread_summary is not None:
            retained_summary = reread_summary
        elif qualification_hook and result.get("codex_exit_success") is not True:
            raise VerificationError("qualification_summary_missing")
        if fake_qwen and qualification_hook and qualification_rejection_mode:
            if (
                result.get("codex_exit_success") is not False
                or result.get("qualification_rejection") is None
            ):
                raise VerificationError("forced_fake_rejection_missing")
        elif fake_qwen and qualification_hook:
            if result.get("codex_exit_success") is True:
                _assert_fake_qualification_artifact_absent(root)
                if reread_summary is not None:
                    raise VerificationError("fake_summary_present")
            elif reread_rejection is None and reread_summary is None:
                raise VerificationError("qualification_evidence_missing")
        elif qualification_hook and result.get("codex_exit_success") is not True and reread_rejection is None and result.get("qualification_rejection") is None:
            if reread_summary is None:
                raise VerificationError("qualification_evidence_missing")
        _retain_sanitized_qualification_rejection(result, reread_rejection)
        if qualification_hook:
            result["qualification_summary"] = retained_summary
    if not fake_qwen:
        post_runtime = _read_runtime_reference()
        _source_qwen_credential_only_for_local(post_runtime)
        _verify_protected_model_health(post_runtime)
    if not fake_qwen and qualification_hook and result.get("codex_exit_success") is not True:
        if result.get("qualification_rejection") is None and result.get("qualification_summary") is None:
            raise VerificationError("qualification_retained_evidence_missing")
    return result


def run_codex_tool_roundtrip_qualification(*, fake_qwen: bool = False) -> dict[str, object]:
    """Run one dedicated Codex tool roundtrip with the disposable rejection hook."""
    return _run_dedicated_codex_tool_roundtrip(
        fake_qwen=fake_qwen,
        qualification_hook=True,
    )


def run_codex_tool_roundtrip_forced_fake_rejection() -> dict[str, object]:
    """Run the real composed fake path with one deliberately invalid event."""
    return _run_dedicated_codex_tool_roundtrip(
        fake_qwen=True,
        qualification_hook=True,
        qualification_rejection_mode=True,
    )


def run_codex_tool_roundtrip_fake_provider_failure() -> dict[str, object]:
    """Run the composed fake path with an upstream transport failure."""
    return _run_dedicated_codex_tool_roundtrip(
        fake_qwen=True,
        qualification_hook=True,
        provider_failure_mode=True,
    )


def run_codex_tool_roundtrip_protected(*, fake_qwen: bool = False) -> dict[str, object]:
    """Permanent hook-free dedicated runner for the decisive protected roundtrip."""
    return _run_dedicated_codex_tool_roundtrip(
        fake_qwen=fake_qwen,
        qualification_hook=False,
    )


def run_stream_differential() -> dict[str, object]:
    _verify_commit_topology()
    runtime = _read_runtime_reference()
    _verify_fixtures()
    with tempfile.TemporaryDirectory(prefix="slaif-155aj-", dir="/tmp") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        _validate_local_config(root, runtime)
        direct_qwen = _safe_stream_summary(
            _run_direct_stream_diagnostic(root, runtime),
            boundary="direct_qwen",
            ran=True,
            decision="ambiguous_stream_evidence",
        )
        direct_decision = _classify_direct_stream(direct_qwen)
        if direct_decision is not None:
            direct_qwen["decision"] = direct_decision
            return {
                "decision": direct_decision,
                "ran_boundaries": ["direct_qwen"],
                "direct_qwen": direct_qwen,
            }
        composed = _run_composed_stream_diagnostic(root, runtime)
    local_output = _safe_stream_summary(
        composed.get("local_output"),
        boundary="local_output",
        ran=True,
        decision="ambiguous_stream_evidence",
    )
    gateway_output = _safe_stream_summary(
        composed.get("gateway_output"),
        boundary="gateway_output",
        ran=True,
        decision="ambiguous_stream_evidence",
    )
    if not isinstance(local_output, dict) or not isinstance(gateway_output, dict):
        return {
            "decision": "ambiguous_stream_evidence",
            "ran_boundaries": ["direct_qwen", "local_output", "gateway_output"],
            "direct_qwen": direct_qwen,
            "local_output": local_output,
            "gateway_output": gateway_output,
        }
    decision = _classify_stream_differential(direct_qwen, local_output, gateway_output)
    if decision == "all_boundaries_completed" and composed.get("accounting_verified") is not True:
        raise VerificationError("differential_accounting_missing")
    for observation in (direct_qwen, local_output, gateway_output):
        observation["decision"] = decision
    return {
        "decision": decision,
        "ran_boundaries": ["direct_qwen", "local_output", "gateway_output"],
        "direct_qwen": direct_qwen,
        "local_output": local_output,
        "gateway_output": gateway_output,
        "accounting_verified": composed.get("accounting_verified") is True,
    }


def _classify_composed_path(
    path: dict[str, object],
    local_output: dict[str, object],
    gateway_output: dict[str, object],
) -> str:
    count_fields = (
        "gateway_to_local_request_count_class",
        "gateway_to_local_response_count_class",
        "local_to_qwen_inference_call_count_class",
        "qwen_upstream_response_count_class",
    )
    if any(path.get(field) not in _COMPOSED_COUNT_CLASSES for field in count_fields):
        return "ambiguous_stream_evidence"
    if any(path.get(field) == "many" for field in count_fields):
        return "ambiguous_stream_evidence"
    local_request_count = path["gateway_to_local_request_count_class"]
    local_response_failed = (
        path["local_response_status_class"] == "unknown"
        or path["local_rejected"] is True
        or path["local_handler_error"] is True
        or path["local_upstream_truncated"] is True
        or path["local_downstream_closed_early"] is True
        or not _terminal_completion_valid(local_output)
    )
    qwen_failed = (
        path["local_to_qwen_inference_call_count_class"] == "one"
        and (
            path["qwen_upstream_response_count_class"] != "one"
            or path["qwen_upstream_status_class"] != "2xx"
            or path["qwen_upstream_content_type_class"] != "sse"
            or path["qwen_terminal_completion_valid"] is not True
            or path["qwen_handler_error"] is True
            or path["qwen_upstream_truncated"] is True
            or path["qwen_path_rejection"] is True
        )
    )
    if local_request_count == "zero":
        return "gateway_owned"
    if (
        local_request_count == "one"
        and path["local_to_qwen_inference_call_count_class"] == "zero"
        and local_response_failed
    ):
        return "local_owned"
    if qwen_failed and local_response_failed:
        return "local_qwen_owned"
    if path["qwen_terminal_completion_valid"] is True and local_response_failed:
        return "local_owned"
    if (
        _terminal_completion_valid(local_output)
        and (
            path["gateway_error_event"] is True
            or not _terminal_completion_valid(gateway_output)
        )
    ):
        return "gateway_owned"
    if (
        _terminal_completion_valid(local_output)
        and _terminal_completion_valid(gateway_output)
        and gateway_output.get(
            "official_client_completion", gateway_output.get("client_completed")
        ) is True
        and path["gateway_accounting_terminal"] is True
    ):
        return "terminal_boundaries_completed"
    return "ambiguous_stream_evidence"


def _classify_composed_boundaries(
    local_output: dict[str, object],
    gateway_output: dict[str, object],
    composed_path: dict[str, object] | None = None,
) -> str:
    if composed_path is not None:
        return _classify_composed_path(composed_path, local_output, gateway_output)
    if _stream_observation_is_ambiguous(local_output) or _stream_observation_is_ambiguous(
        gateway_output
    ):
        return "ambiguous_stream_evidence"
    if not _terminal_completion_valid(local_output):
        return "local_owned"
    if not _terminal_completion_valid(gateway_output):
        return "gateway_owned"
    if gateway_output.get("official_client_completion") is not True:
        return "official_client_observation"
    return "terminal_boundaries_completed"


def _run_composed_only_impl(
    *, fake_qwen: bool, tracker: StageTracker
) -> dict[str, object]:
    """Run only the composed boundary using the immutable direct baseline."""
    tracker.set("topology")
    _verify_commit_topology()
    tracker.set("runtime_reference")
    runtime = None if fake_qwen else _read_runtime_reference()
    tracker.set("fixtures")
    _verify_fixtures()
    tracker.set("pinned_direct_baseline")
    direct_qwen = _read_pinned_direct_baseline()
    if not _terminal_completion_valid(direct_qwen):
        raise VerificationError("pinned_direct_terminal_invalid")
    if not fake_qwen:
        tracker.set("protected_postcheck")
        _verify_protected_model_health(runtime)
    with tempfile.TemporaryDirectory(prefix="slaif-155aj-", dir="/tmp") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        tracker.set("local_config")
        _validate_local_config(root, runtime)
        composed = _run_composed_stream_diagnostic(
            root,
            runtime,
            fake_qwen=fake_qwen,
            tracker=tracker,
        )
    local_output = _safe_stream_summary(
        composed.get("local_output"),
        boundary="local_output",
        ran=True,
        decision="ambiguous_stream_evidence",
    )
    gateway_output = _safe_stream_summary(
        composed.get("gateway_output"),
        boundary="gateway_output",
        ran=True,
        decision="ambiguous_stream_evidence",
    )
    composed_path = _composed_path_from_statuses(
        local_status=composed.get("local_status", {}),
        gateway_status=composed.get("gateway_status", {}),
        qwen_status=composed.get("qwen_status", {}),
        qwen_before=composed.get("qwen_status_before"),
        local_output=local_output,
        gateway_output=gateway_output,
        accounting_verified=composed.get("accounting_verified") is True,
        decision="ambiguous_stream_evidence",
    )
    decision = _classify_composed_boundaries(
        local_output, gateway_output, composed_path
    )
    composed_path = _safe_composed_path(composed_path, decision=decision)
    if decision == "terminal_boundaries_completed" and composed.get("accounting_verified") is not True:
        decision = "ambiguous_stream_evidence"
    if not fake_qwen:
        tracker.set("protected_postcheck")
        _verify_protected_model_health(runtime)
    for observation in (direct_qwen, local_output, gateway_output):
        observation["decision"] = decision
    return {
        "decision": decision,
        "ran_boundaries": ["direct_qwen", "local_output", "gateway_output"],
        "direct_qwen": direct_qwen,
        "local_output": local_output,
        "gateway_output": gateway_output,
        "composed_path": composed_path,
        "accounting_verified": composed.get("accounting_verified") is True,
    }


def run_composed_only(*, fake_qwen: bool = False) -> dict[str, object]:
    tracker = StageTracker()
    try:
        return _run_composed_only_impl(
            fake_qwen=fake_qwen,
            tracker=tracker,
        )
    except VerificationError:
        raise
    except Exception as exc:
        raise tracker.unexpected_composed(exc) from None


def _run_composed(
    root: Path,
    runtime: RuntimeReference | None,
    codex_binary: Path,
    *,
    fake_qwen: bool = False,
) -> dict[str, object]:
    tracker = StageTracker()
    try:
        return _run_composed_impl(
            root,
            runtime,
            codex_binary,
            fake_qwen=fake_qwen,
            tracker=tracker,
        )
    except VerificationError:
        raise
    except Exception:
        raise tracker.unexpected() from None


def run(*, fake_qwen: bool = False) -> dict[str, object]:
    stage = "topology"
    try:
        _verify_commit_topology()
        stage = "runtime_reference"
        runtime = None if fake_qwen else _read_runtime_reference()
        stage = "fixtures"
        _verify_fixtures()
        stage = "protected_preflight"
        if not fake_qwen:
            _verify_protected_model_health(runtime)
            _source_qwen_credential_only_for_local(runtime)
            with tempfile.TemporaryDirectory(prefix="slaif-155aj-", dir="/tmp") as temporary:
                root = Path(temporary)
                root.chmod(0o700)
                stage = "local_config_preflight"
                _validate_local_config(root, runtime)
                stage = "codex_install"
                codex_binary = _install_codex(root)
                stage = "exact_capture_preflight"
                import scripts.capture_codex_protocol as capture

                live = capture.capture_live_0149_session(
                    codex_binary=codex_binary,
                    expected_version=CODEX_VERSION,
                    model=CODEX_MODEL,
                    profile="responses-session-relationship-v3",
                )
                if capture.canonical_json_bytes(live) != SESSION_FIXTURE.read_bytes():
                    raise VerificationError("exact_relationship_fixture_mismatch")
                stage = "composition"
                result = _run_composed(
                    root,
                    runtime,
                    codex_binary,
                    fake_qwen=fake_qwen,
                )
        if not fake_qwen:
            stage = "protected_postcheck"
            _verify_protected_model_health(runtime)
            result["post_cleanup_model_ok"] = True
        stage = "evidence"
        _assert_required_evidence(result, require_post_cleanup_model=not fake_qwen)
        return result
    except VerificationError:
        raise
    except Exception:
        raise VerificationError(f"unexpected_{stage}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qwen-relay", action="store_true")
    parser.add_argument("--fake-rehearsal", action="store_true")
    parser.add_argument("--stream-differential", action="store_true")
    parser.add_argument("--composed-only", action="store_true")
    parser.add_argument("--composed-only-fake", action="store_true")
    parser.add_argument("--tool-roundtrip-fake", action="store_true")
    parser.add_argument("--tool-roundtrip-qualification", action="store_true")
    parser.add_argument("--tool-roundtrip-qualification-fake", action="store_true")
    parser.add_argument("--tool-roundtrip-qualification-fake-rejection", action="store_true")
    parser.add_argument("--tool-roundtrip-qualification-fake-provider-failure", action="store_true")
    parser.add_argument("--tool-roundtrip-protected", action="store_true")
    parser.add_argument("--tool-roundtrip-protected-fake", action="store_true")
    arguments = parser.parse_args()
    if arguments.qwen_relay:
        return _qwen_relay_main()
    if arguments.stream_differential:
        try:
            result = run_stream_differential()
        except VerificationError as exc:
            print(f"RESULT=BLOCKED code={exc}")
            return 1
        except Exception:
            print("RESULT=BLOCKED code=unexpected_stream_differential")
            return 1
        try:
            _emit_stream_summary(_stream_summary_lines(result))
        except VerificationError as exc:
            print(f"RESULT=BLOCKED code={exc}")
            return 1
        return 0
    if arguments.tool_roundtrip_fake:
        try:
            _verify_commit_topology()
            with tempfile.TemporaryDirectory(
                prefix="slaif-155aj-tool-roundtrip-", dir="/tmp"
            ) as temporary:
                root = Path(temporary)
                root.chmod(0o700)
                codex_binary = _install_codex(root)
                run_codex_tool_roundtrip_fake(root=root, codex_binary=codex_binary)
            print("FAKE_TOOL_ROUNDTRIP=OK turns=2 tool_result=1 function=1 message=1")
        except VerificationError as exc:
            print(f"RESULT=BLOCKED code={exc}")
            return 1
        return 0
    if (
        arguments.tool_roundtrip_qualification
        or arguments.tool_roundtrip_qualification_fake
        or arguments.tool_roundtrip_qualification_fake_rejection
        or arguments.tool_roundtrip_qualification_fake_provider_failure
    ):
        try:
            if arguments.tool_roundtrip_qualification_fake_rejection:
                result = run_codex_tool_roundtrip_forced_fake_rejection()
            elif arguments.tool_roundtrip_qualification_fake_provider_failure:
                result = run_codex_tool_roundtrip_fake_provider_failure()
            else:
                result = run_codex_tool_roundtrip_qualification(
                    fake_qwen=arguments.tool_roundtrip_qualification_fake
                )
            rejection = result.get("qualification_rejection")
            summary = result.get("qualification_summary")
            if (
                result.get("codex_exit_success") is True
                and rejection is None
                and summary is None
            ):
                print(
                    "QUALIFICATION=PASSED turns=2 function=1 message=1 accounting_rows=2"
                )
            else:
                if summary is None:
                    raise VerificationError("qualification_evidence_missing")
                summary = _sanitize_preclassification_summary(summary)
                evidence: dict[str, object] = {
                    "failure_code": _safe_qualification_failure_code(
                        VerificationError(str(result.get("failure_code", "qualification_failed")))
                    ),
                    "summary": summary,
                }
                if "codex_provenance" in result:
                    evidence["codex_provenance"] = _safe_codex_provenance(
                        result["codex_provenance"]
                    )
                if rejection is not None:
                    evidence["rejection"] = _sanitize_qualification_rejection(rejection)
                outcome = "REJECTED" if rejection is not None else "FAILED"
                print(
                    f"QUALIFICATION={outcome} "
                    + json.dumps(evidence, sort_keys=True, separators=(",", ":"))
                )
                return 1
        except VerificationError as exc:
            print(f"RESULT=BLOCKED code={exc}")
            return 1
        return 0
    if arguments.tool_roundtrip_protected or arguments.tool_roundtrip_protected_fake:
        try:
            _verify_155aj_obligation_manifest()
            result = run_codex_tool_roundtrip_protected(
                fake_qwen=arguments.tool_roundtrip_protected_fake
            )
            if result.get("codex_exit_success") is True:
                print("PROTECTED_TOOL_ROUNDTRIP=OK turns=2 function=1 message=1 accounting_rows=2")
            else:
                snapshot = _safe_boundary_snapshot_validate(
                    result.get("boundary_snapshot")
                )
                evidence = {
                    "failure_code": _safe_qualification_failure_code(
                        VerificationError(str(result.get("failure_code", "protected_tool_roundtrip_failed")))
                    ),
                    "boundary_snapshot": snapshot,
                }
                print(
                    "PROTECTED_TOOL_ROUNDTRIP=FAILED "
                    + json.dumps(evidence, sort_keys=True, separators=(",", ":"))
                )
                return 1
        except VerificationError as exc:
            print(f"RESULT=BLOCKED code={exc}")
            return 1
        return 0
    if (
        arguments.composed_only
        or arguments.composed_only_fake
    ):
        try:
            result = run_composed_only(
                fake_qwen=(
                    arguments.composed_only_fake
                ),
            )
            _emit_stream_summary(_stream_summary_lines(result))
        except VerificationError as exc:
            print(f"RESULT=BLOCKED code={exc}")
            return 1
        except Exception:
            print("RESULT=BLOCKED code=unexpected_composed_only")
            return 1
        return 0
    try:
        result = run(fake_qwen=arguments.fake_rehearsal)
        _assert_required_evidence(
            result, require_post_cleanup_model=not arguments.fake_rehearsal
        )
    except VerificationError as exc:
        print(f"RESULT=BLOCKED code={exc}")
        return 1
    except Exception:
        print("RESULT=BLOCKED code=unexpected_failure")
        return 1
    del result
    if arguments.fake_rehearsal:
        print("FAKE_REHEARSAL=OK")
    else:
        print("RESULT=OK status=real_composed_acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
