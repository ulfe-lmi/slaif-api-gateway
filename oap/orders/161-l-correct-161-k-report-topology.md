# OAP Work Order — 161-l

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 with a governance-only immutable correction for
the literal implementation-SHA error in the 161-k report. Re-establish OAP
report topology with a GitHub-verified activation head and report-only first
parent. Make no verifier, test, product, dependency, or documentation change
and run no Codex/Gateway/Local reproduction or control.

Publish RESULT=FAILED because the target assistant-history reproduction
remains unaccepted. Immutable 161-k remains unchanged; correct its false SHA
claim only in the new 161-l report. Do not combine the known provider-env fix
with this transcript repair.

## Exact reconciled state and protocol failure

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- Immutable 161-j report/start head:
  `592da3ec907b54ba48f0523fed31a9dac9c1dd91`.
- Actual 161-k activation-only implementation head from GitHub:
  `84b71243eaee24a045f7270bc877dc571822e537`.
- Immutable 161-k report/current PR head:
  `f20b9edf6a129cc85d11bfbe52be4bb12a5730bb`.
- Report path: `oap/reports/161-k-capture-helper-first-turn-control.md`.
- GitHub proves the actual 161-k activation commit changes only `oap/active`
  and the 161-k order and has 161-j report head as parent.
- GitHub proves the 161-k report commit changes only the 161-k report and has
  actual activation head `84b71243...` as its first parent.
- The immutable report instead records nonexistent implementation SHA
  `84b7124ff1ccb57ae25babca8c603a3aa52c9196` and falsely claims its report
  first parent is that literal value. GitHub returns no commit for that SHA.
- This violates the OAP SELF topology contract even though the actual commits'
  structure is otherwise report-only/correct. The report must not be amended,
  rewritten, or described as conformant.
- All ten checks pass on current report head `f20b9edf...`. PR #298 is open,
  non-draft, CLEAN/mergeable, has no reviews/threads/auto-merge, and is the
  unique Objective-161 PR.
- Final-head unit CI passed 3874 tests with 1 skip. Independent review corrected
  the prior 161-j focused count: 107 cases existed before 161-k; 161-k added no
  source/tests and reports 107/107 accurately.
- Remote main, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical PR
  #291, and frozen Local PR #7 remain unchanged/out of scope. Local PR #7 stays
  at report head `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation
  parent `64e50172ee02563e2b021554f6b0d345cc7dfdec`.

The technical 161-k stop remains factual and must be preserved:

- manual verifier provider env key: `SLAIF_CAPTURE_API_KEY`;
- exact capture helper and isolated environment key:
  `SLAIF_CODEX_CAPTURE_API_KEY`;
- provider semantic equality: false;
- private environment/package provenance/control run: not run;
- no production/protected traffic or source mutation.

This mismatch explains the previous pre-Gateway first-turn failures, but its
correction belongs to a later continuation after OAP topology is repaired.

## Exact allowed paths

Only these repository paths may change:

- `oap/active`
- `oap/orders/161-l-correct-161-k-report-topology.md`
- `oap/reports/161-l-correct-161-k-report-topology.md`

Do not change scripts, tests, app, fixtures, Local, replay/HMAC, DB/schema/
migrations, dependencies/requirements/lockfiles, CI, contracts, doctrine, or
docs. Do not create environment, DB, npm, Codex, Gateway, or Local processes.

## Required governance execution

1. Reconcile exact GitHub state above. Commit/push only unchanged strategic
   161-l order and `oap/active` to the existing PR branch.
2. After push, obtain the literal 40-hex activation head independently from
   local `git rev-parse HEAD`, remote branch ref, and `gh pr view` head. Require
   all three equal and require GitHub commit lookup succeeds.
3. Verify that activation commit has first parent exact current report head
   `f20b9edf...` and changes exactly the 161-l order and active pointer.
4. Run active OAP governance tests, `git diff --check`, exact allowed-path
   proof, and report-collision check. Run no broad/local product suite. Wait for
   all ten normal GitHub checks to succeed on the literal activation head.
5. Create the 161-l report only after the literal activation SHA is known.
   Insert it mechanically from the verified command output; do not type,
   expand from a short prefix, predict, or synthesize it.
6. Before commit, parse the report's `Implementation head SHA` and require it
   is exact 40-hex, equals local/remote/PR head, and resolves on GitHub.
7. Commit only the report. Verify its first parent equals the report's literal
   SHA and its changed path is only the 161-l report. Push and require it is the
   remote PR head before response `OK`.
8. Preserve every prior order/report byte-for-byte. Run no control,
   reproduction, environment setup, or provider-env correction.

Skipped, pending, missing, stale, or failed topology/check evidence is not a
pass. Any mismatch produces a truthful 161-l FAILED report only if that report
can itself satisfy the literal SELF topology contract; otherwise do not signal.

## Immutable report

Publish exactly:

`oap/reports/161-l-correct-161-k-report-topology.md`

The report must contain `RESULT=FAILED`, the mechanically obtained literal
implementation SHA, `Report publication commit: SELF`, exact current PR/main,
actual and falsely reported 161-k SHAs, actual 161-k parent/path topology,
161-l activation/report topology, all check states, corrected test counts,
provider-env mismatch/no-run facts, docs impact, privacy/scope confirmation,
and:

```text
OAP-TOPOLOGY-CORRECTED = YES|NO
PREFX-CAPTURE-HELPER-CONTROL-ACCEPTED = NO
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

Documentation checked, no update needed because this round changes only OAP
transcript. No secret/content/provider/accounting boundary changes. Coding
never merges/auto-merges and returns to the permanent control-wake helper.
