# OAP 155-o report — hop evidence and error-owner closure

Status: `PARTIAL/BLOCKED`

Reason: the fake composed gate, legacy fake rehearsal, focused checks, and all
ten implementation-head checks passed. The sole authorized protected composed
request completed on implementation head `d2d72bd…`, and its retained safe hop
facts support `local_qwen_owned`. No Gateway product change was authorized or
made. No direct protected request or retry was run.

## Identity and topology

- PR: #291
- Repository: `ulfe-lmi/slaif-api-gateway`
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `e26ac23ce352d7318615a4b01f4662f2bc3a165b`
- Activation commit: `e201051303aa8cb43e2cfc102e58e4c153fc908f`
- Final implementation head: `06752b1126545590a2e4232311fb92a52f663b41`
- Protected diagnostic implementation head: `d2d72bd2916403e1c5149373d1391cfb912d2f27`
- Report publication commit: `SELF`
- Activation files were committed before implementation; the order bytes
  matched the strategic source.
- The prior 155-n report parent/path and report-only topology were verified.

## Changed allowed paths

Implementation changes were limited to:

- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`

The activation files and this report are the only OAP paths changed for this
round. No Local Coding repository file or Gateway product path was changed.

Documentation impact: no product or contract documentation changed; the
implementation is bounded verifier/test evidence tooling.

## Implementation and fake ledger

- Added bounded `COMPOSED_PATH` evidence with projected count classes, status
  classes, terminal/error/truncation facts, and accounting status.
- Added finite SSE error field-name and code/type classification; unexpected
  values become `unknown`, and message/detail values are never retained.
- Qwen upstream status/content counts use the delta captured immediately before
  the composed request, excluding readiness/model probes.
- Added and tested the `local_qwen_owned` decision enum.
- Preserved pinned direct evidence provenance through strict normalization as
  `evidence_source=pinned_155l`, `ran_current_invocation=false`.

Observed checks:

- Focused verifier unit suite: pass.
- Ruff: pass.
- Python compilation: pass.
- `git diff --check`: pass.
- Exact composed-only fake rehearsal: pass.
- Complete legacy fake rehearsal: pass.
- All ten checks on final implementation head `06752b1`: pass.
- Fake artifact/stdout equality: pass; stderr empty; artifact mode 0600 under
  a mode-0700 task root.
- Fake hop result: `terminal_boundaries_completed`.
- Final fake artifact SHA-256:
  `a75b0a627c4dcadd55cce59ab61b3d3425595f97ddfc038d70a97726d999be08`.

## Protected ledger

- Protected health/model preflight: pass.
- Direct protected diagnostic: not run (`0` requests).
- Composed-only protected requests: exactly one, on
  `d2d72bd2916403e1c5149373d1391cfb912d2f27`; no retry.
- Full protected Codex acceptance matrix: not run.
- Protected artifact/stdout equality: pass; stderr empty; artifact mode 0600.
- Protected artifact SHA-256:
  `267bc63db0da17eabd08c129f7df87f941b7165e3f037014a73e05e9937bb0d6`.
- The original protected CLI decision was `ambiguous_stream_evidence` because
  the then-current decision whitelist lacked `local_qwen_owned`. A later
  verifier-only enum correction deterministically reclassifies the retained
  safe hop facts as `local_qwen_owned`; protected traffic was not repeated.

Retained safe hop facts:

| Fact | Protected result |
| --- | --- |
| Gateway-to-Local requests | one |
| Gateway-to-Local responses | zero |
| Local response status/content | unknown / unknown |
| Local rejected/handler/truncated/downstream-close | false / false / false / false |
| Local-to-Qwen inference calls | one |
| Qwen upstream responses/status/content | zero / unknown / sse |
| Qwen terminal/handler/truncated/path rejection | false / false / false / false |
| Gateway error event | true |
| Gateway accounting terminal | false |
| Corrected safe ownership | `local_qwen_owned` |

The protected safe artifact contained only the fixed boundary schema and these
bounded hop facts. It contained no raw request/response values, credentials,
identities, endpoints, messages, or arbitrary exception text.

## Local Coding handoff

The evidence supports a Local Coding continuation, not a Gateway correction:
one Gateway-to-Local request reached the boundary, no Local response was
observed, one Local-to-Qwen inference call was recorded, and no Qwen upstream
response was recorded. The bounded Qwen terminal fact is false. This is the
exact safe `local_qwen_owned` handoff; no Local repository mutation was made.

## Privacy, accounting, and cleanup ledger

- No direct protected request, full matrix, Gateway correction, acceptance,
  release, deployment, cutover, merge, or auto-merge was performed.
- Fake disposable accounting finalized successfully. Protected accounting was
  not terminal and is not claimed as accepted.
- The retained protected and fake artifacts were kept through report
  publication; task roots, generated environments, logs, and artifacts are
  removed in final cleanup.
- Runtime reference and task credential source were never rendered and are
  removed in final cleanup.
- Gateway/Local tracked and ignored state remains clean; Local `.venv` remains
  absent.

## Required continuation

This is a truthful partial report with a Local Coding handoff. Any continuation
must independently review the safe hop evidence and obtain authorization before
any new protected request. This report is immutable.
