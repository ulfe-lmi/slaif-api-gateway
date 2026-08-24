# OAP Work Order — 152-e

PR mode: `AMEND_EXISTING_PR`
PR: `#287`
Branch: `oap/152-real-provider-accounting-qualification`
Current base: `main @ fa5423456ec21fadae066cb12960014ad00e1d8c`
Current remote PR head: `c04884a0afe0e6c5ce4c78b9890153e8060f4e17`
Updated truthful title: `obj152: add guarded real-provider accounting verifier`

## Objective and terminal intent

Reconcile Objective 152 and PR #287 with current `main` without rewriting its
immutable OAP history. Resolve the sole documentation conflict, preserve the
guarded verifier and its deterministic evidence, and produce a current-main,
mergeable terminal candidate that states the outcome exactly:

- verifier implementation and JSON/JSONB fix delivered;
- the one authorized 152-c live attempt failed after its first flow;
- the replacement eight-flow live qualification remains NOT RUN;
- real-provider accounting qualification remains incomplete.

This continuation does not authorize another provider call. The strategic
terminal decision, if this round and all final-head checks pass, is to merge
the useful verifier/evidence tooling while explicitly retaining the incomplete
live-evidence limitation. It is not permissible to describe Objective 152 as a
successful real-provider qualification.

## Verified current state

- Documentation PR #288 merged to `main` as
  `fa5423456ec21fadae066cb12960014ad00e1d8c`. It changed documentation,
  documentation checks, and documentation tests; it did not change Gateway
  runtime, migration, provider, accounting, or deployment code.
- PR #287 remains the unique Objective 152 PR. It is open, has no auto-merge,
  and its remote head is the immutable 152-d report commit
  `c04884a0afe0e6c5ce4c78b9890153e8060f4e17`.
- The 152-d implementation head is
  `69ca59d6f9c5cad9048e04a82ef5a72e23d78ba7`; the report commit has that
  implementation commit as first parent and changes only
  `oap/reports/152-d-asyncpg-jsonb-correlation-fix.md`.
- All ten checks on the 152-d report head succeeded. Those checks predate
  current `main` and must run again on the 152-e report head.
- GitHub reports PR #287 as `CONFLICTING`. A three-way merge shows exactly one
  conflict: `docs/real-provider-qualification.md`.
- Current `main` gives that document professional current-truth structure and
  explicitly falsifies Objective 140's uncorrelated database claims. The PR
  branch adds the 152-a through 152-d verifier, failed-live, and decoder-fix
  history. Both sets of truth must survive the resolution.
- PRs #224 and #250 are unrelated Dependabot work. Local Coding PR #7 is a
  separate repository/objective and must not be modified or started here.

## Required implementation

### 1. Preserve history and update the existing branch

- Fetch canonical GitHub state and verify the exact PR/base/head facts above.
- Work only on the existing Objective 152 branch/PR. Do not create a new PR.
- Commit this activated order and `oap/active` unchanged on the Objective 152
  branch as required by OAP.
- Merge `origin/main` at the exact verified current SHA into the Objective 152
  branch. Do not rebase, squash, amend historical commits, force-push, or
  otherwise rewrite any activated order/report or evidence commit.
- The merge must retain `origin/main` as an ancestor and preserve every 152-a
  through 152-d commit SHA.
- Main-branch files incorporated unchanged by the merge are authorized
  ancestry, not task-authored scope. Resolve only the actual conflict and do
  not opportunistically edit other main or PR files.

### 2. Resolve the qualification document truthfully

Resolve `docs/real-provider-qualification.md` into one coherent current-facing
document that:

- preserves current main's status/audience block and concise explanation of
  what complete qualification requires;
- preserves the exact Objective 140 limitations, including that its old
  verifier accepted no PostgreSQL connection/key identifier, performed no SQL
  query, emitted no correlatable Chat-stream usage/ID, and omitted Responses
  streaming;
- summarizes 152-a's exact-eight-flow guarded verifier and 152-b's isolation/
  bounded-output hardening without reproducing work-order prose;
- records 152-c as one failed authorized attempt: one OpenAI non-streaming Chat
  flow reached HTTP 200 and finalized in PostgreSQL, but the verifier stopped
  with `correlation_metadata_invalid`; the other seven flows were not run and
  no qualification followed;
- records 152-d as a verifier-only strict JSON/JSONB decoder/normalizer fix with
  no HTTP, SQL, credential, or provider execution;
- states prominently that no replacement live matrix ran after the fix and
  **real-provider accounting qualification: not complete**;
- points to immutable 152-c/152-d OAP reports for detailed historical evidence
  without rewriting those reports;
- preserves provider-credential replacement evidence as deterministic
  transport-test evidence, not provider header attestation; and
- makes no release, invoice, model-quality, performance, production, security,
  compliance, support, or SLA claim.

The merged result must continue to satisfy the documentation architecture from
PR #288: one H1, valid heading hierarchy, valid relative links/anchors, and
reachability from the documentation home.

### 3. Make PR metadata match the outcome

- Update PR #287's title to exactly
  `obj152: add guarded real-provider accounting verifier`.
- Replace or amend its body so it summarizes all 152-a through 152-e rounds,
  identifies 152-c as failed partial live evidence, identifies 152-d as the
  no-live verifier fix, and states that the eight-flow live qualification is
  incomplete.
- Keep the PR open, non-draft, with auto-merge disabled. The coding agent never
  merges.

### 4. Focused verification only

Run all verification with `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
`OPENROUTER_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, and
`RUN_UPSTREAM_TESTS` explicitly unset.

Required checks:

```text
git diff --check
python scripts/check_documentation.py
.venv/bin/python -m ruff check scripts/verify_real_provider_qualification.py tests/unit/test_real_provider_qualification_verifier.py tests/unit/test_documentation_inventory.py
.venv/bin/python -m pytest -q tests/unit/test_real_provider_qualification_verifier.py tests/unit/test_documentation_inventory.py tests/unit/test_documentation_contract_drift.py tests/unit/test_product_scope_docs.py
<guarded verifier dry run proving attempted_requests=0, real_provider_called=false, http_requests=0, sql_queries=0>
git merge-base --is-ancestor fa5423456ec21fadae066cb12960014ad00e1d8c HEAD
```

Do not run broad local suites, a provider preflight, a live verifier, Compose,
migrations, a SQL connection, or any network request other than GitHub
publication/check inspection. Standard GitHub CI/CodeQL must run on the final
report head.

## Exact task-authored paths

```text
docs/real-provider-qualification.md
oap/orders/152-e-main-reconciliation-and-terminal-merge-candidate.md
oap/reports/152-e-main-reconciliation-and-terminal-merge-candidate.md
oap/active
```

PR title/body updates are also authorized. Files inherited unchanged from the
exact current-main merge are not task-authored edits. No verifier, test,
application, migration, Compose, provider, accounting, configuration, or other
documentation file may be changed in this continuation.

## Anti-false-positive acceptance

- A clean textual merge that drops either PR #288's current-truth framing or
  the 152 failed-live/fix history fails this round.
- Rebase, squash, force-push, report rewrite, or replacement PR fails OAP
  history requirements.
- Green CI cannot be described as live provider qualification.
- The one successful 152-c SQL row cannot be promoted to an eight-flow result.
- Synthetic tests and guarded dry runs cannot be promoted to live evidence.
- Any credential read, provider/Gateway generation request, SQL connection,
  deployment action, or provider-cost spend fails scope.
- PR metadata that retains an unqualified “qualify real-provider evidence”
  success implication fails the truth gate.
- Final acceptance requires current `main` ancestry, mergeability, exact diff
  scope, report topology, and every final-head required check successful.

## Boundaries and non-goals

- No new real-provider authorization or run.
- No Local Coding integration, Codex 0.149 work, route/tool/identity changes,
  adapter generalization, module/facial work, or new objective.
- No production/shared database, provider credential, real email, deployment,
  release, tag, or external state mutation other than this PR's branch and
  metadata.
- No enterprise tenancy, SSO/SCIM, MFA/RBAC expansion, formal penetration test,
  certification, compliance, HA, invoice-grade billing, support, or SLA work.

## Publication and response duties

- Amend only PR #287; never merge or enable auto-merge.
- Publish exactly one immutable
  `oap/reports/152-e-main-reconciliation-and-terminal-merge-candidate.md` as
  the sole path in the final report-only commit.
- Record the literal implementation head, main merge parent/ancestry, resolved
  conflict path, PR metadata, focused checks, no-live evidence, final diff
  scope, and limitations. Use `Report publication commit: SELF`.
- Verify the report-only commit has the implementation head as first parent,
  changes only the 152-e report, and is the remote PR head. Then send exact
  `OK` to the response FIFO and resume the control FIFO.
