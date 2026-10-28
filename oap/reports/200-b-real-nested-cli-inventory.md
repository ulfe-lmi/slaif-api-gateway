# OAP Objective 200-b — final report: real nested-command coverage in the documentation inventory checker

Work order: `oap/orders/200-b-real-nested-cli-inventory.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `200-b` (5 bytes, no trailing newline); order sha256
`337ce4d5cdfb4716e64d1b2975f62ea1240c8a561b936c43d903d35d084d5ac2`
(7,813 bytes), active pointer sha256
`48c33af99074833ddef5b7ffd475eded45577c1f436845f6af423a4b22c2a368`,
both verified before committing and re-verified in the implementation
commit).
Branch: `oap/200-replay-reference-maintenance`; base: `main`
`4c265bc3c9668a66bb1643915d442fb8c411ff11` (unchanged).
PR mode: AMEND_EXISTING_PR — the SAME unique PR #356 created by
200-a, https://github.com/ulfe-lmi/slaif-api-gateway/pull/356, base
`main`, title "Inspect retained Codex replay references and apply
reviewed expiry extensions" (OPEN/MERGEABLE at publication). The
coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: 8466d9364bd93175a8a370e8f5bc51d6af86b628
Report publication commit: SELF

## Predecessor state (immutable)

200-a is complete on this branch: implementation head
`9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f` and its report commit
`64338b08ee146f4a66658a1d27ef3b50dba7afef` (order sha256
`e3054c664a9c595e079dcd9bd43cfb5648ff27d6a87efa615fe6eb6567106f40`,
report sha256 `6a769f4cf80fffcb2c953d4f400a37306a808726facb3eb2f400ca13a6f459a0`).
The 200-a report's "known unresolved" documentation-inventory
failure is the historical state this round repairs; that report is
immutable and was NOT edited. Objective 199 remains terminal (PR #355
merged); 201-205 remain INERT; no other 200 suffix was activated. The
200-a response session was polled CLOSED with the exact response OK
and was never reopened or re-signaled.

## Implementation commit (this round)

1. `8466d9364bd93175a8a370e8f5bc51d6af86b628` — "Resolve the replay
   sub-app in the documentation inventory checker (200-b)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `200-b` + the bounded test-only repair and
   verification addendum listed below (4 files). First parent is the
   200-a report commit `64338b0`.

No product file was modified: `git diff
9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f <this implementation> --
app/` is EMPTY, so the schema/plan contract, service, repository, CLI
callbacks, source fingerprints, transaction/lock/clock/expiry/audit
logic, runtime replay, and all accounting code remain BYTE-UNCHANGED
from the verified 200-a implementation. No schema/migration/
dependency/workflow/UI change; no new functional feature; no release
action.

## Allowed diff (implementation commit, 4 files)

Tests (allowed path only):

- `tests/unit/test_documentation_inventory.py` — the
  command-inventory test's file-stem-only group heuristic is replaced
  by a small PURE STATIC source scan (no production imports; no
  settings, credentials, backend profiles, or providers loaded) that
  resolves each module's local `typer.Typer` instances against
  `app.add_typer(<alias>, name=...)` registrations in the same module
  OR in importing modules (single-name `from <dotted> import <name>
  [as <alias>]` forms). A sub-app whose Typer object is imported from
  a separate module resolves under its ACTUAL parent namespace:
  `cli/codex_replay.py` -> `codex replay`, so the checker now demands
  the real registered invocations `slaif-gateway codex replay
  inspect` / `... extend` (both present in `docs/cli-reference.md`)
  and can no longer fabricate `codex-replay` aliases. Both positional
  `@app.command("name")` and explicit `@app.command(name="name")`
  declarations are detected, so changing decorator spelling cannot
  remove coverage. In-file nested apps (`keys policy`, `keys
  external-tools`, `secrets generate`) and all top-level groups keep
  their previous resolution; the setting/schema/release/front-door
  checks are unchanged. Three focused self-contained regressions
  added in the same file on small temporary source fixtures: a
  registered separate-file nested app resolving to its parent
  namespace (both name spellings detected; an unregistered module
  keeps its stem group), a negative missing-documentation case, and a
  real-repository assertion that the inventory contains the two true
  `codex replay` invocations and no `codex-replay` alias.

Docs (allowed paths only):

- `docs/verification/2026-10-28-cli-replay-maintenance.md` — APPENDED
  "200-b ADDENDUM" (the 200-a text is unchanged): the resolved
  scanner limitation, the honest history of the rejected `name=`
  spelling workaround (tried during 200-a, strategically rejected as
  coverage-removing, reverted before 200-a publication), the new
  evidence, and product-byte preservation.
- `docs/cli-reference.md` — NOT changed: it already documented the
  true invocations in both the Codex command block and the checked
  complete command inventory; no operator-facing name correction was
  needed.

OAP: exact `oap/active` = `200-b` (5 bytes, no newline) and the
strategic order, both byte-verified unchanged at the implementation
head.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12) with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no
database, container, provider, client, SMTP, or Redis contact (this
repair is pure static test code). JUnit receipts under
`/tmp/slaif200a/` (disposable).

- Focused batch, one run: **52 passed, 0 failed / 0 errors / 0
  skipped**, exit 0 (`b-gov.xml`): updated
  `test_documentation_inventory` (16 = 13 pre-existing + 3 new),
  `test_oap_governance` (9), `test_documentation_contract_drift` (15,
  consumer guard unchanged), `test_cli_codex_replay` (12 actual-Typer
  registration/help proofs confirming the real `codex replay`
  names). Disjoint suites; no overlapping counts claimed.
- Product-byte preservation: `git diff
  9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f
  8466d9364bd93175a8a370e8f5bc51d6af86b628 -- app/` is EMPTY.
- The fourteen 200-a owned-PG-16 tests and root's independent
  real-reference-row expiry-wait test are existing 200-a/root
  evidence and were NOT rerun (no PG or replay matrix run for this
  inventory fix, per the order).
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
  files=127`; `git diff --check` clean.

## Security and privacy statements

- The repair is test-only static source text analysis; it loads no
  production settings, credentials, backend profiles, or providers,
  touches no database, network, or filesystem outside the test
  fixtures, and changes no runtime behavior, permission, or output.
- No secret or canary material is introduced; no product output
  path changed.

## Honest state and limitations

- Final-head CI is root-gated and its state is **PENDING** at this
  publication: head `8466d93` was pushed immediately before report
  publication. The 200-a head `9873a4a`'s final-head unit CI FAILED
  only on the now-repaired inventory case (all other checks passed or
  were pending per the 200-a handoff review); no CI result for the
  new heads is claimed here. The final new SELF must have all checks
  green before root merges.
- No owned-PG, provider, client, or SMTP qualification was run or
  invented for 200-b; 200-a synthetic evidence and root's
  independent tests stand as 200-a/root evidence.
- The all-11-DoD installed-executable transcript remains 205;
  objectives 201-205 remain INERT. No full-goal or release
  completion claim.
- Plan files and JUnit receipts under `/tmp/slaif200a/` are
  disposable execution state, not durable evidence.
- This report is immutable: later 200 suffixes do not edit it.
