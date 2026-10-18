# OAP Objective 190-d — final report: canonical work-order header correction (metadata-only)

Work order: `oap/orders/190-d-canonical-order-header.md` (committed
unchanged in this implementation commit; `oap/active` = `190-d`).
Branch: `oap/190-codex-connector-tool-names`.
PR mode: AMEND_EXISTING_PR — PR #328, base `main`
`86ae51c929b85ace6ef257239e4e900e7488754f` (verified unchanged at
publication); predecessor implementation
`0375f0826e21b0d6db8eea2e1089e09b54bfb19c`, predecessor SELF
`0e8f57c933cd4f58aed92cbb322124207baf24cd`; root-qualified 190-b
runtime `3d5a694c74999249a892f62935dc40d3439fa524`. The coding agent
never merges; no auto-merge is enabled; root reviews independently.

Implementation head SHA: aac013e9a391a49d4d2dbd6eeb26f8743f2f0d2e
Report publication commit: SELF

## What changed (METADATA-ONLY)

Final-head CI run `39142207755` on the 190-c SELF head
`0e8f57c933cd4f58aed92cbb322124207baf24cd` completed with five of six
jobs successful (Documentation hygiene, Docker Compose smoke,
OpenAI-compatible E2E, Playwright browser smoke, PostgreSQL
integration) and exactly one failure: the `Unit, lint, and migration
head` job (4943 passed, 1 skipped, 1 failed), solely
`tests/unit/test_oap_governance.py::test_active_identifier_resolves_exactly_one_matching_order`.
Both tests repaired by 190-c now pass in that run. The failure cause
is not product or test code: the strategic 190-c order file's first
line was `# Objective 190-c — …` instead of the canonical literal
`# OAP Work Order — 190-c` that the live governance test requires of
the active order.

This continuation corrects the header contract at the metadata layer:

- publishes this order with the canonical first line
  `# OAP Work Order — 190-d` and moves `oap/active` to the exact
  5-byte value `190-d` (no trailing newline, matching prior
  convention);
- the immutable 190-c order and report remain byte-for-byte
  untouched; they are simply no longer the active selection, so the
  governance test now resolves the unique `190-d-*.md` order whose
  header satisfies the required literal;
- no code, test, profile DATA, package metadata, docs, dependency,
  schema, or CI/workflow change of any kind.

Diff scope: exactly two files — new
`oap/orders/190-d-canonical-order-header.md` (23 insertions) and
`oap/active` (1 line, `190-c` → `190-d`) — 24 insertions, 1 deletion,
no other file.

## Verification (this objective; focused, metadata-only)

- Read the live `tests/unit/test_oap_governance.py` (157 lines): the
  only active-order-dependent assertion is
  `test_active_identifier_resolves_exactly_one_matching_order`, which
  requires (a) `oap/active` to full-match `[0-9]{3}-[a-z]`, (b)
  exactly one `oap/orders/190-d-*.md`, and (c) its first line to
  equal `# OAP Work Order — 190-d`. All three hold. The new-PR
  declaration test is inert for non-`-a` identifiers.
- Focused run of ONLY `tests/unit/test_oap_governance.py` with
  `/tmp/slaif-181c-strategic-venv/bin/python -m pytest` and JUnit XML
  (`/tmp/slaif-181c/junit-governance-190d.xml`): XML-derived
  `tests=9, failures=0, errors=0, skipped=0` (0.157 s).
- `git diff --check` clean on the staged change.
- Unchanged-verification: `git diff` of `tests/`, `app/`,
  `pyproject.toml`, `.env.example`, `docs/` against preceding SELF
  `0e8f57c` is empty; `git diff 3d5a694 HEAD -- app/` (shared runtime
  and packaged profile) is empty, i.e. byte-identical to the
  root-qualified 190-b runtime.
- No local rerun of the green unit/PG/Gateway/wheel/browser matrices,
  per the order.

## Carried-forward evidence (historical, not reruns)

Explicitly dated historical, bound to the byte-unchanged runtime:
2026-10-18 190-b — 480/480 focused unit pass, 30/30
owned-PostgreSQL migration pass, 7/7 real-Gateway E2E pass, wheel
packaging proof, and root's independent installed-wheel proofs
(file3→file4→file3 policy proof, real CLI pin migration, six
real-HTTP all-197-name requests, owned-PG exact-name replay/HMAC,
accounting 6 requests/30 tokens, full-row preservation, immutable
process snapshot, six canary CLI proofs). 2026-10-18 190-c — 62/62
test-only focused unit pass. None were rerun for this metadata-only
fix; the real 197 names/types with synthetic schemas and the mock
backend remain fixture evidence, not an actual Codex/model/private
plugin test.

## Current GitHub state at publication (reconciled before push)

- PR #328: OPEN, `MERGEABLE`, no auto-merge request; branch
  `oap/190-codex-connector-tool-names`; remote head at commit time
  `0e8f57c933cd4f58aed92cbb322124207baf24cd`, becomes this SELF
  commit after push.
- `main` unchanged at
  `86ae51c929b85ace6ef257239e4e900e7488754f`; only unrelated PR #319
  also open.
- Final-head run `39142207755` (190-c SELF head): completed with
  conclusion `failure` solely from the unit job's governance header
  assertion described above; all other jobs successful. That
  failure is the demonstrated reason for this order.
- The final-head GitHub matrix for this commit runs normally after
  push and is required before root merge. Any checks pending at
  publication are pending, not passes; no pending or failed check is
  claimed as passed.

## Limitations and safety confirmations

- Metadata-only: no production source, profile DATA, packaging,
  docs, dependency, schema, workflow, provider, auth, signing,
  replay, or accounting change; proven by the empty diffs above.
- This change cannot alter trust, content retention,
  keys/credentials, permissions, PostgreSQL authoritative
  quota/accounting, or local/hosted tool separation; prior
  exact-name lowering/replay/HMAC, six finalized HTTP requests/30
  tokens, pin-migration full-row/audit/concurrency/rollback, and safe
  CLI evidence remain bound to the unchanged runtime. The existing
  runbook governs file replacement/restart, dry-run/apply/repeat, and
  data/binary rollback; no docs changes required.
- Untracked local files (`CODEX-SESSIONS.md`, `codex.sh`) and all
  earlier orders/reports preserved and byte-immutable; no
  reset/clean/stash/switch; no production DB, SSH, deploy, release,
  tag, email, or real provider/model call; no secret/environment
  dumps or new diagnostics; same objective 190, same PR #328; never
  merged, no second PR.
