# OAP 155-v report

RESULT=FAILED

155-v completed the bounded failure-localization implementation and exactly one
authorized protected qualification attempt. The qualification failed in the
verifier's failure-localization path with the fixed code
`qualification_failure_localization`. No ownership, product acceptance, or
provider-boundary conclusion is inferred. The order's no-retry rule therefore
prevented a final protected run.

## OAP and Git topology

- Objective: `155-v`
- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `4e9a6bd5281f691b6e446b5e70a771d4ee1e19f5`
- Implementation head: `ce664052266b7a1cbd43b8083eaea22d3fa9c0fd`
- Activation parent/report: `5cc47a716d3a426ea0f87882951a1491c810dae7`
- Prior implementation parent: `a3af8dca0f40c5a67b57556db25cb8d4e5c83828`
- Report publication commit: SELF
- Report path: `oap/reports/155-v-failure-localization-summary-and-protected-closure.md`
- `oap/active`: `155-v`

The activation commit contained only `oap/active` and the exact 155-v order.
The implementation commit changed only:

- `app/slaif_gateway/services/responses_gateway.py`
- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`

Local Coding 005-m and Qwen were not modified. No merge, release, or cutover
was performed.

## Evidence

Pure focused verifier, affected Responses policy/streaming/replay/quota tests,
Ruff, and compilation passed. The pushed implementation head passed all ten
required checks, including unit/lint/migration, PostgreSQL, E2E, browser, Docker
Compose, documentation, CodeQL, and both analysis checks.

The three fake rehearsals ran through the composed Codex-to-Gateway-to-Local-
to-fake-Qwen path:

- forced validator failure: nonzero, sanitized rejection artifact and summary;
- provider failure: nonzero, summary-only evidence and no validator artifact;
- valid qualification: two turns, one function result, one message, two rows.

The protected qualification ran once, with no retry. Its safe evidence was:

- Gateway: one request/response, `2xx`, `sse`;
- Local: one request/response, `2xx`, `sse`;
- Qwen: one inference, `2xx`, `sse`, normal close;
- accounting query succeeded; one row class, reservation finalized class one,
  no pending class;
- one sanitized validator rejection artifact was retained;
- the verifier failed to retain a decisive ownership classification because
  its failure-localization path returned the fixed localization failure code.

The retained safe rejection artifact was:

```json
{"event_type":"response.output_item.done","nested_object_fields":[{"fields":[{"name":"arguments","type":"string"},{"name":"call_id","type":"string"},{"name":"caller","type":"null"},{"name":"id","type":"string"},{"name":"name","type":"string"},{"name":"namespace","type":"null"},{"name":"status","type":"string"},{"name":"type","type":"string"}],"name":"item"}],"rejection":{"code":"responses_stream_event_not_supported","outcome":"validator_rejected"},"schema":"responses_stream_rejection_v1","top_level_fields":[{"name":"item","type":"object"},{"name":"output_index","type":"integer"},{"name":"sequence_number","type":"integer"},{"name":"type","type":"string"}],"validator_profile":{"codex_0149_function_tool_events":true,"codex_encrypted_reasoning_replay":false,"codex_reasoning_events":true,"codex_streaming_tool_events":true,"declared_client_tools_class":"bounded","web_search":false,"web_search_max_tool_calls_class":"none"}}
```

The retained safe pre-classification summary was:

```json
{"accounting":{"ledger_estimated":"0","ledger_failed":"0","ledger_finalized":"0","ledger_pending":"0","query_ok":true,"reservation_finalized":"1","reservation_pending":"0","reservation_released":"0","row_count":"1","zero_pending":true},"codex_failure_category":"turn_failed","gateway":{"content_type_classes":["sse"],"disconnect":false,"handler_error":false,"request_count":"1","response_count":"1","status_classes":["2xx"],"truncated":false},"local":{"content_type_classes":["sse"],"disconnect":false,"handler_error":false,"request_count":"1","response_count":"1","status_classes":["2xx"],"truncated":false},"qualification_rejection":{"artifact_digest_present":true,"artifact_equal":true,"present":true},"qwen":{"content_type_classes":["sse"],"handler_error":false,"inference_count":"1","normal_close":true,"path_error":false,"status_classes":["2xx"],"truncated":false},"request_profile_class":"other","schema":"qualification_preclassification_v1","stage":"tool_roundtrip_qualification_artifact"}
```

These artifacts contain only allowlisted field/type classes, booleans, bounded
counts, status/content-type classes, and fixed codes. No credentials, endpoint,
IDs, prompts, arguments, results, bodies, headers, exception text, or raw SSE
were retained or reported.

Protected model/credential preflight and post-composed cleanup health checks
passed privately. The task-owned 155-v temporary root and runtime reference
were removed; zero `/tmp/slaif-155v-*` roots remained, and the repository was
clean before publication. No protected final run was attempted.

## Closure

This is a truthful failed qualification report. The verifier's fixed
`qualification_failure_localization` result is the terminal boundary fact; it
does not establish Gateway, Local, Qwen, or external-provider ownership. A
future continuation must repair the remaining evidence-localization defect
before any new protected diagnostic is authorized. No merge was performed.
