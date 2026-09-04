# Objective 155-aj — final hook-free acceptance

RESULT=FAILED

Reason: the unchanged pinned Codex 0.148 candidate test reached its isolated
private test environment but stopped before candidate behavior at the fixed
`postgres_start_failed` stage. The required pre-protected gate therefore did
not pass. No protected request was sent.

## OAP topology

- PR: #291, branch `oap/155-local-coding-signed-server-module`, base `main`
  at `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Starting/report head: `a9625753716325bc0ef6a75689bf42bddbfbd03d`.
- Starting report parent: `3cce1a7612fc9919adf26df9952baabaf703c348`.
- Activation head: `efadf5e1038dc042a596414282c5383deab80c8e`, whose parent is
  the starting report head.
- Candidate implementation head: `e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4`.
- Report publication commit: `SELF`; its first parent is the candidate
  implementation head and its only changed path is this report.
- The exact `oap/active` selector and 155-aj order remain unchanged and match
  the authoritative order bytes.

## Implementation scope

The candidate removes the Objective-155 qualification writer and invocation
from `app/slaif_gateway/services/responses_gateway.py`. The production stream
validator, forwarding, replay, identity, accounting, route, and provider
semantics were not changed. The verifier retains only its task-local,
verifier-owned synthetic evidence support.

Changed implementation/test paths before this report:

- `app/slaif_gateway/services/responses_gateway.py`
- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`
- `tests/unit/test_oap_governance.py`

The production diff against functional head `3cce1a7` is deletion-only for the
qualification machinery. The source gate found no `SLAIF_155X_` or production
qualification writer in `app/`.

## Observed gates

- Ruff over `app`, `tests`, and the verifier: passed.
- Focused verifier, Responses streaming, replay, Local server, and OAP
  governance suites: passed.
- Fake dedicated tool roundtrip: passed, two turns with one function and one
  message lifecycle.
- Fake hook-free qualification: passed, two turns and two accounting rows.
- Fake provider failure: emitted bounded nonzero `QUALIFICATION=FAILED` with
  one inference and one released/failed accounting pair.
- Fake validator failure: emitted bounded nonzero `QUALIFICATION=REJECTED`
  with verifier-owned write-once evidence; no production artifact writer was
  involved.
- Topology and actual Local verifier matrix: passed for 16 bounded rows,
  including both legacy punctuation cases; body/signature tamper and replay
  negatives passed.
- All ten PR checks passed on candidate head `e503f96` before the failed
  0.148 gate.

The unchanged pinned candidate test was executed in a read-only-root
`bwrap` namespace with only the task-local executable supplied at the hard-
coded `/usr/bin/codex` path. The package name/version, task-local executable,
and `codex-cli 0.148.0` version were verified. The test collected 14 cases;
13 passed, while the live-plumbing case failed before candidate execution at
the safe infrastructure class `postgres_start_failed`. The host
`/usr/bin/codex` version was unchanged. This is not claimed as candidate
behavior or compatibility evidence.

## Section-2 snapshot obligation matrix

The following concrete passing parameterized/unit tests provide the bounded
predicate coverage. The failed 0.148 infrastructure gate is separate.

| Obligation | Passing test |
|---|---|
| non-list/missing/wrong/excessive structure count | `test_boundary_snapshot_rejects_raw_or_malformed_nested_facts` |
| absent ordinal 0/1 and invalid flag | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| missing/duplicate created/completed events | `test_sse_structure_rejects_order_duplicates_done_and_wrong_status` |
| response-ID relationship | `test_stream_summary_rejects_response_completed_sequence_mismatch` |
| created/completed status and model | `test_sse_structure_rejects_order_duplicates_done_and_wrong_status` |
| missing/invalid output and usage | `test_stream_completion_gate_rejects_missing_terminal_event_and_invalid_bounds` |
| duplicate and unknown events | `test_sse_structure_rejects_unknown_event_type`, `test_sse_structure_rejects_order_duplicates_done_and_wrong_status` |
| error event, overflow, abnormal close, early close | `test_error_event_projection_keeps_only_finite_safe_facts`, `test_trace_overflow_preserves_producer_completion_fact`, `test_forwarding_relay_records_upstream_truncation_without_normal_close` |
| handler error and upstream truncation | `test_relay_handle_error_is_safe_and_fail_closed`, `test_safe_stream_summary_records_handler_and_truncation_without_private_text` |
| function/reasoning/message lifecycle mismatch | `test_composed_tool_roundtrip_requires_function_then_message_gateway_lifecycle`, `test_codex_0149_reasoning_lifecycle_rejects_orphans_duplicates_and_reordering`, `test_codex_0149_message_lifecycle_rejects_reordering_and_wrong_terminal_shapes` |
| snapshot schema/cardinality/tamper/privacy | `test_boundary_snapshot_rejects_raw_or_malformed_nested_facts`, `test_normalized_summary_rebuild_discards_unexpected_extra_keys` |
| failure survival and CLI emission | `test_dedicated_runner_preserves_boundary_snapshot_after_temp_cleanup`, `test_outer_dedicated_runner_retains_summary_after_localizer_exception`, `test_qualification_cli_direct_stdout_is_one_bounded_line` |
| `local_turn2_rejected_before_qwen` | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| `local_invoked_qwen_turn2_qwen_rejected_or_failed` | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| `qwen_turn2_completed_local_stream_invalid` | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| `local_qwen_turn2_completed_gateway_stream_invalid` | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| `producer_boundaries_valid_verifier_expectation_wrong` | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| `full_two_turn_path_succeeded` | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |
| closed `other` outcome | `test_boundary_snapshot_classification_has_fixed_downstream_outcomes` |

## Section-3 HMAC rotation evidence

Production replay code was unchanged. The passing replay suite includes:

- `test_hmac_rotation_verifies_old_rows_and_new_rows_by_row_version` — old
  v1 present/ID-less references and new v2 present/ID-less function references.
- `test_idless_function_call_uses_exact_same_key_call_hmac_row` — exact
  same-key call-digest linkage.
- `test_idless_call_digest_ambiguity_is_not_collapsed` — duplicate ambiguity.
- `test_hmac_rotation_fails_closed_when_old_secret_is_unavailable` — absent
  old material.
- `test_unavailable_stored_hmac_version_is_refused` — unavailable/version
  mismatch and active-material failure.
- `test_cross_key_expiry_name_and_route_mismatches_fail_closed` — key, tool,
  expiry, name, and route boundaries.
- `test_digest_lookup_failure_has_no_private_exception_chain` — no private
  values in failure evidence.

The existing custom-tool present/ID-less replay coverage and privacy-canary
assertions also passed in the same focused replay suite. No raw item/call ID,
digest, key, or privacy canary was emitted or persisted by this objective.

## Cleanup and disposition

The exact 155-aj disposable test roots, Codex installs, database/container
resources, listener, repository-local bytecode/cache state, and temporary
untracked setup files were removed. The exact 155-aj database and container
namespace were absent; the Local Coding checkout remained at its pinned clean
head and the host Codex executable remained unchanged. No protected runtime
reference was sourced, no protected endpoint was contacted, and no protected
prompt, response, credential, endpoint, identity, or raw stream value was
retained.

This failure is an environment gate at private PostgreSQL startup, not a
production compatibility conclusion. No acceptance, release, cutover, merge,
or post-failure correction is claimed. PR #291 remains unmerged for strategic
review.
