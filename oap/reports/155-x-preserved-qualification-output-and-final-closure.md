# OAP 155-x report

RESULT=FAILED

155-x preserved the qualification CLI output directly, completed the ordered
fake gates, and executed exactly one protected qualification. The protected
qualification returned exit 1 / `QUALIFICATION=FAILED` with visible sanitized
summary evidence. Per the order, no retry and no hook-free final run occurred.

## OAP and Git topology

- Objective: `155-x`
- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting/activation head: `fe7d641352bedaad5bd217c17f03e61299742fb2`
- Prior 155-w report: `5385d066d2a869afd217e354996fe2027770a276`
- 155-w implementation: `b7b7f7ec00ec365fb245185a7e7588aa6c41ccbc`
- 155-x implementation head: `00a50beaa91caa524c98476e4c42d86ea0e22e55`
- Report publication commit: SELF
- Report path: `oap/reports/155-x-preserved-qualification-output-and-final-closure.md`
- Activation parent: `5385d066d2a869afd217e354996fe2027770a276`
- Implementation parent: `fe7d641352bedaad5bd217c17f03e61299742fb2`

The earlier immutable report chain remains unchanged: 155-t report
`9046ccda…`, 155-u report `5cc47a7…`, 155-v report `307a491e…`, and 155-w
report `5385d066…`. No prior report was rewritten. Local Coding 005-m and Qwen
were not modified. No merge or release was performed.

## Implementation and checks

The 155-x implementation aligned the operative topology/order/active/task/temp
anchors and qualification environment names with 155-x, while preserving only
historical 155-v/155-r evidence references. It added the direct CLI stdout
regression requiring exactly one bounded success line and empty stderr.

The changed implementation paths from the activation head were:

- `app/slaif_gateway/services/responses_gateway.py`
- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`

Focused verifier/strict-stream tests, Ruff, and compilation passed. The pushed
qualification head `00a50beaa91caa524c98476e4c42d86ea0e22e55` passed all ten
required checks: unit/lint/migration, PostgreSQL, E2E, browser, Docker Compose,
documentation, CodeQL, and both analysis checks.

The direct fake gates all passed with their bounded stdout visible and no
stderr: provider-failure summary-only (`QUALIFICATION=FAILED`), forced
validator rejection (`QUALIFICATION=REJECTED`), and valid fake qualification
(`QUALIFICATION=PASSED turns=2 function=1 message=1 accounting_rows=2`).

## Protected qualification

Exactly one protected qualification was invoked directly without stdout or
stderr redirection, piping, command substitution, or task-file retention. Its
visible safe result was:

```text
QUALIFICATION=FAILED
failure_code=qualification_turn_counts_g2_l1_q1
```

The sanitized pre-classification summary reported only these bounded facts:

```json
{"accounting":{"ledger_estimated":"0","ledger_failed":"0","ledger_finalized":"1","ledger_pending":"0","query_ok":true,"reservation_finalized":"1","reservation_pending":"0","reservation_released":"0","row_count":"1","zero_pending":true},"codex_failure_category":"turn_failed","gateway":{"content_type_classes":["sse","json"],"disconnect":false,"handler_error":false,"request_count":"2","response_count":"2","status_classes":["2xx","4xx"],"truncated":false},"local":{"content_type_classes":["sse"],"disconnect":false,"handler_error":false,"request_count":"1","response_count":"1","status_classes":["2xx"],"truncated":false},"qualification_rejection":{"artifact_digest_present":false,"artifact_equal":false,"present":false},"qwen":{"content_type_classes":["sse"],"handler_error":false,"inference_count":"1","normal_close":true,"path_error":false,"status_classes":["2xx"],"truncated":false},"request_profile_class":"other","schema":"qualification_preclassification_v1","stage":"tool_roundtrip_qualification_artifact"}
```

These facts show the bounded count mismatch and absence of a rejection
artifact; they do not establish a complete event contract, ownership result,
or accepted accounting result. No raw credentials, endpoint, IDs, prompts,
arguments, results, bodies, headers, exception text, or raw SSE were retained
or reported. No second protected request was sent.

## Cleanup and closure

The exact mode-0600 runtime reference was validated privately and removed.
Zero 155-x temporary roots and zero verifier, Qwen-relay, Local, or Uvicorn
task processes remained. The repository was clean before publication.

This is the single immutable truthful FAILED report for 155-x. A later
continuation must address the protected two-turn count mismatch using the
visible bounded evidence before any new protected diagnostic is authorized.
No merge was performed.
