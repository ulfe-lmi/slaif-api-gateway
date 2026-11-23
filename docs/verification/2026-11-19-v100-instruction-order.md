# V100 instruction-order deployment verification — 2026-11-19

## Scope and provenance

Gateway engine: `0940d8a28f3a413d2a2cc6f4962c0efcafd71e13` (merged PR #391).
Client compatibility data: `codex-0.167.1`, revision 16. No gateway source,
profile-file, key or schema change was needed for this route update.

The backend operator reported installation and persistent autostart of an
external Qwen template on both original and repaired V100 paths, after 79
rendering and 21 live inference checks. Those counts are operator-reported;
the gateway-side verification below is independent. Host autostart and the
operator's complete test archive were not independently inspected from the
gateway host.

## Independent backend checks

Both API paths (ports 18021 and 18023) served template SHA-256
`18fec282bbb9161ac58936b0c13b34a8fc175fca44467ace5aa3802d5ce59514`.

Twelve checks passed, six per endpoint:

- Active template hash matched.
- Late developer instruction retained order and a separate system boundary.
- Late system instruction retained order and a separate system boundary.
- Live late-instruction following returned the expected synthetic answer with
  streaming completion and usage.
- The model emitted the requested synthetic function call and arguments.
- A supplied tool result followed by another late instruction returned the
  expected answer, without another tool call.

The renderer's existing developer-to-system conversion was accepted explicitly;
literal system/developer distinction is not claimed. Tool results were supplied
by the verifier; no actual tool was executed. These twelve checks did not
independently repeat the operator's vision or full reasoning matrix.

## Gateway activation and continuation

At 22:08:59 UTC, both enabled `/v1/responses` routes were changed in one audited
transaction:

| Public model | Old profile | New profile |
| --- | --- | --- |
| `qwen3.8-27b-V100` | `llama-cpp-qwen-v1` | `responses-passthrough-v1` |
| `qwen3.8-27b-V100-repaired` | `llama-cpp-qwen-v1` | `responses-passthrough-v1` |

Only the `upstream_llm` selector changed. Its new revision is 1 and SHA-256 is
`5084f47909d5b919ea329524bae2d382a772936034af7cba7290bbfdf1cc521a`.
Both updates produced audit records; other route capabilities were compared
unchanged. No restart or key rotation was required.

Four live gateway Responses requests passed, two per route:

| Model | First turn | Continuation |
| --- | --- | --- |
| V100 original | HTTP 200, tool call, 1,848 input / 75 output tokens | HTTP 200, expected answer, 1,987 input / 27 output tokens |
| V100 repaired | HTTP 200, tool call, 1,848 input / 115 output tokens | HTTP 200, expected answer, 2,027 input / 54 output tokens |

The first turn included a retained-summary-shaped user message followed by
developer instructions. The second replayed the provider-issued tool call,
supplied a synthetic result, and appended another developer instruction.
All four streams reached `response.completed`. The expected continuation
answer was verified. All four usage-ledger rows were independently checked as
successful and finalized, with token counts matching the returned usage.
No real client tool was executed.

Actual Codex-triggered compaction, full-context capacity and recovery of an
existing damaged user conversation were **not run** in this verification.
This evidence establishes the tested placement/tool-continuation path, not
unrestricted Codex compatibility or production certification.

## Reproduction and rollback

Follow the [V100 runbook](../runbooks/qwen-v100-llama-cpp.md). Keep deployment
backups and raw operational evidence outside the checkout; do not commit
credentials, private request contents or opaque replay identifiers.
The template and gateway selectors must be coordinated during rollback.
