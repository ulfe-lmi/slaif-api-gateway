# OAP Objective 155-u report

RESULT=FAILED

Report publication commit: SELF

## Topology

- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main`
- 155-u activation head: `19d4b2f3d8ea7c26980eaab5f60b1125d0bd4cc8`
- 155-u activation parent: `9046ccda503d0393ab5df155fdf028810d1726f5`
- Immutable 155-t report head: `9046ccda503d0393ab5df155fdf028810d1726f5`
- Immutable 155-t report parent/implementation: `bb45e0813a15b41541c5b1ef48537fa835995106`
- 155-u qualification implementation head: `a3af8dca0f40c5a67b57556db25cb8d4e5c83828`
- No merge, release, or follow-on objective was performed.

## Pure and fake evidence

The qualification evidence-lifecycle correction makes a sanitized in-memory
rejection authoritative across temporary-root cleanup. A second artifact read
is used only for equality/absence validation; it cannot overwrite retained
evidence. Malformed, inconsistent, wrong-owner, wrong-mode, symlink, profile,
and bounded-count cases are covered by focused tests.

The actual forced-invalid fake composition passed its intended negative gate:
the real installed Codex 0.149 process traversed Gateway, Local, and fake Qwen,
the parser-safe malformed function item produced one bounded write-once
rejection artifact, and the CLI emitted only sanitized event/field/type classes
with a nonzero result. The valid hook-enabled fake qualification also passed
with two turns, one function lifecycle, one message lifecycle, two accounting
rows, and no artifact. These are provider-free rehearsals.

All ten required checks passed on qualification head `a3af8dca0f40c5a67b57556db25cb8d4e5c83828` before the protected attempt. Focused
verifier, capture, streaming, policy, replay, client, quota, Ruff, and
compilation checks passed.

## Protected result

Exactly one new protected qualification was attempted. It failed in the
verifier’s bounded `tool_roundtrip_failure_localization` stage with the fixed
code `unexpected_composed_tool_roundtrip_failure_localization_KeyError`.

Because the verifier failed before returning its bounded result, this report
does not claim a protected event shape, boundary ownership, Gateway/Local/Qwen
counts, terminal accounting outcome, or acceptance. No retry and no decisive
hook-free protected final run occurred. The failure is a verifier evidence
retention/localization defect, not a product or provider ownership conclusion.

## Cleanup and privacy

- The exact private runtime reference was removed without rendering its contents.
- No 155-u temporary roots or verifier/Local processes remain.
- No raw body, event value, identifier, argument/result, credential, endpoint,
  or private exception text was printed, persisted, or committed.
- Local Coding and Qwen were not modified.
- The repository is clean and the remote head equals the local report-preparation
  head before this report commit.

This result is not acceptance evidence. A continuation must first fix and
fake-test the bounded localization path, then obtain a newly authorized
protected diagnostic; no 155-u retry is authorized by this report.
