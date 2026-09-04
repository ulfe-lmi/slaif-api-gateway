# OAP Work Order — 155-p

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: c6b33c9d1527d35d987bf10f8276f30797bc892c

## Objective and reason

Restore the exact 155-o fake and protected safe artifact blocks omitted from its
immutable report, preserve the proven Local-Qwen ownership handoff, and close the
Gateway audit round without any protected request or product change.

The 155-o report is truthful about ownership and hashes but procedurally
incomplete: it contains a table rather than the order-required complete
byte-identical artifacts. Exact mode-0600 copies remain at the two strategic
task paths named below.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-o report
  head `c6b33c9d1527d35d987bf10f8276f30797bc892c`; first parent is
  `06752b1126545590a2e4232311fb92a52f663b41`, and only the exact 155-o report
  changed.
- All ten report-head checks pass.
- Local Coding PR #7 remains exact and open at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`.
- Gateway/Local worktrees and 155-o task state are clean.
- Exact retained safe artifacts:
  - `/tmp/slaif-155p-fake-artifact.log`, mode 0600;
  - `/tmp/slaif-155p-protected-artifact.log`, mode 0600.
- Their SHA-256 values must equal the immutable 155-o report's fake/protected
  hashes before use.
- No runtime reference or protected credential source exists or is required.

## Required work

1. Verify the 155-o report topology, artifact modes/ownership/hashes, and strict
   safe grammar without printing non-safe data.
2. Validate each artifact contains exactly:
   - three strict `STREAM_BOUNDARY` lines;
   - one strict `COMPOSED_PATH` line;
   - one `STREAM_DECISION` line;
   - only allowlisted normalized keys/enums/count classes.
3. Reject any forbidden raw/private marker, malformed JSON, extra line, duplicate
   boundary, arbitrary error value, or hash mismatch.
4. Publish one immutable 155-p report containing:
   - the complete fake artifact in one fenced text block;
   - the complete protected artifact in a second fenced text block;
   - byte-for-byte extraction comparisons against both source files;
   - the original protected decision exactly as captured;
   - the separate deterministic `local_qwen_owned` derivation from the retained
     hop facts after the enum-only correction;
   - exact request counts and the Local Coding handoff;
   - the 155-o procedural-omission correction.
5. Do not alter the 155-o report.

## Local Coding handoff to preserve

The safe evidence proves:

- Gateway-to-Local request count: one;
- Gateway-to-Local response count: zero;
- Local response status/content: unknown/unknown;
- Local relay rejected/handler/truncated/downstream-close: all false;
- Local-to-Qwen inference call count: one;
- Qwen upstream completed response count: zero;
- Qwen content type observed: SSE;
- Qwen terminal completion: false;
- Qwen handler/truncation/path-rejection: all false;
- Gateway emitted an error stream;
- protected accounting did not finalize;
- corrected owner: `local_qwen_owned`.

Gateway product code must not change. Local Coding must next instrument/correct
its protected Qwen stream consumption/termination and then return a green tested
head for Gateway acceptance.

## Acceptance

- Zero protected health calls, direct requests, composed requests, or full matrix.
- Zero Gateway/Local product or documentation changes.
- Exact artifact blocks compare byte-for-byte with retained sources.
- Report parent is the declared implementation head; report commit changes only
  the exact 155-p report.
- All report-head checks pass.
- Both retained `/tmp/slaif-155p-*-artifact.log` files are removed only after
  report publication/checks and verified absent.
- Gateway/Local worktrees remain clean; PRs remain open; no merge/auto-merge.

## Allowed paths

    oap/active
    oap/orders/155-p-restore-artifacts-and-local-handoff.md
    oap/reports/155-p-restore-artifacts-and-local-handoff.md

No scripts, tests, docs, product, Local repository, runtime, credential,
database, container, provider, protected service, release, or deployment changes
are authorized.

## Verification and publication

The activation commit contains only active/order. With no implementation code
change, that activation commit is the declared implementation head. Require its
checks green before report publication.

Publish one report-only immutable commit with literal implementation head and
`Report publication commit: SELF`. After publication make no repository
mutation; wait for all report-head checks, verify topology/remote head/
mergeability, delete only the two exact retained artifact files, signal exact
FIFO `OK`, and stop.

This report does not authorize Gateway merge, Objective 156, Local release work,
or any new protected request. Gateway Objective 155 remains sequencing-blocked
until a corrected Local Coding head returns.

