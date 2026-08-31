# Objective 155-s — real Codex tool-stream lifecycle and acceptance

RESULT=FAILED

Reason: the one authorized protected Codex 0.149 qualification reached Local
and protected Qwen once, then Gateway rejected `response.output_item.added`.
The safe validator profile recorded
`codex_streaming_tool_events=false` and
`declared_client_tools_class=none`; therefore the request did not prove the
required accepted Codex tool envelope. This is classified as qualification
harness/envelope activation insufficiency, not Local, Qwen, external-provider,
or ownership evidence. No production tool-lifecycle correction was made.

## OAP and Git topology

- Objective: `155-s`
- PR: `#291`
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `62f8063c9f4fc304f5b835741b1a263202285b56`
- Activation head: `62f8063c9f4fc304f5b835741b1a263202285b56`
- Final implementation head: `ce725def4b931c2bf86770d8c6bd75c7e37247ef`
- Report parent: `ce725def4b931c2bf86770d8c6bd75c7e37247ef`
- Report publication commit: `SELF`
- Report path: `oap/reports/155-s-real-codex-tool-stream-lifecycle-and-acceptance.md`
- No merge, auto-merge, release, cutover, or acceptance claim.

The activation commit remains immutable. The hook-free implementation changed
only the verifier topology pins and pure test coverage:

- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`
- `tests/unit/test_responses_codex_streaming_tools.py`

No product tool acceptance code, Local Coding code, or Qwen code was changed.

## Ordered execution ledger

| Stage | Result | Safe fact |
| --- | --- | --- |
| 155-s activation/topology | PASS | Exact active order and prior 155-r/005-m anchors were verified. |
| Pure/static reproduction | PASS | The exact pair-local combined profile rejected the tool item/delta branch while the preserved 155-r message stream remained accepted. |
| Qualification diagnostic head | PASS | All ten checks passed on the pushed diagnostic head. |
| One protected qualification | FAILED | Exactly one real Codex process request ran; Local and protected Qwen each saw one request/inference. Gateway emitted the typed stream rejection. |
| Safe rejection evidence | RETAINED | The canonical safe line below was emitted before task cleanup; it contains only bounded event/field/type/profile facts. |
| Legitimacy decision | NOT PROVEN | The profile had no active declared-tool gate, so the required accepted tool envelope was not established. No Local/Qwen/external ownership was inferred. |
| Final protected tool roundtrip | NOT RUN | No retry and no second protected request occurred. |

Exact safe qualification rejection line:

```text
QUALIFICATION_REJECTION {"event_type":"response.output_item.added","nested_object_fields":[{"fields":[{"name":"arguments","type":"string"},{"name":"call_id","type":"string"},{"name":"caller","type":"null"},{"name":"id","type":"string"},{"name":"name","type":"string"},{"name":"namespace","type":"null"},{"name":"status","type":"string"},{"name":"type","type":"string"}],"name":"item"}],"rejection":{"code":"responses_stream_event_not_supported","outcome":"validator_rejected"},"schema":"responses_stream_rejection_v1","top_level_fields":[{"name":"item","type":"object"},{"name":"output_index","type":"integer"},{"name":"sequence_number","type":"integer"},{"name":"type","type":"string"}],"validator_profile":{"codex_encrypted_reasoning_replay":false,"codex_streaming_tool_events":false,"declared_client_tools_class":"none","web_search":false,"web_search_max_tool_calls_class":"none"}}
```

No raw request/response body, tool arguments, prompt, completion, ID,
credential, endpoint, session, signature, or exception text is reported.

## Checks and cleanup

- Focused Responses streaming and verifier unit suites: passed locally.
- Full Ruff check over `app`, `tests`, and the verifier scripts: passed locally.
- Python compilation and diff checks: passed locally.
- All ten required checks passed on implementation head `ce725de...`.
- The exact mode-0600 runtime reference and credential source were removed.
- All exact 155-s disposable roots/processes/listeners/database state were
  cleaned; no `slaif-155s-*` task root remains.
- Documentation impact: no documentation files were changed; this report is
  the complete execution handoff.

The next continuation must correct the no-provider Codex tool-envelope
activation in pure/fake evidence before any new protected request. Neither
PR #291 nor Local PR #7 is merged by this round.
