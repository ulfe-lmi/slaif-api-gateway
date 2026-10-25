# OAP Objective 195-b — final report: verification evidence count and test-layer corrections

Work order: `oap/orders/195-b-verification-evidence-correction.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `195-b`; order sha256
`9448e06f201b507c109f6288ae9ecadf88c1b654f86236393da584c1cef5c05d`).
Branch: `oap/195-list-filter-multiselection`, continuation base: the
195-a report SELF `5088bc0ab729f5f332e99011b0dee43fe40a0e53`
(first parent implementation
`e47c3a9810eddf9fbdbe53ac3e74b78ca31d6b2b`); remote `main` unchanged
at `c5437bef6811cdfad2b0be3c273e6071572cbaa3`.
PR mode: AMEND_EXISTING_PR (Objective 195 = exactly one PR, #348,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/348).
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: 81fb2bfcfa41a48388b47d9c89afba5d17fcd56f
Report publication commit: SELF

## Implementation commits (branch order, this round)

1. `81fb2bfcfa41a48388b47d9c89afba5d17fcd56f` — "Correct
   verification evidence counts and test-layer descriptions
   (195-b)": the strategic order (bytes verified unchanged, sha256
   above) + exact `oap/active` = `195-b` (5 bytes) + the corrected
   primary verification document (3 files; ZERO product/test source
   changes).

## Process honesty

This report closes the SAME continuously activated objective-195
execution round 195-b: the control `OK` for 195-b was delivered and
consumed exactly once (no re-signal, no new control reader before
publication, no profile/model/effort change, no new objective). All
195 implementation, prior commits, activated orders, and immutable
reports are preserved untouched; the 195-a order sha256
(`c8ab9ae9c4da40aed47118cd8e37b77fa4a64f3f295694769fb5cc32a661b47a`)
and the 195-a report sha256
(`0e241ada3049189504fc9de88b223c4ec1eb0ff827c2c1657b19efb4257887aa`)
were verified before and after this round — the 195-a report bytes
were NOT edited.

## What this round corrected (documentation only)

R1 — **CI-copy repair unit count, 32 -> 29.** The 195-a report and
the primary document claimed the CI-copy repair unit rerun had "32
passed" (`unit-cifix-1.xml`). Inspected evidence:
`/tmp/slaif195/unit-cifix-1.xml` contains **29 tests, 0
failures/errors/skips** (timestamp 2026-10-25T22:18:47Z), comprising
**28** new `test_admin_list_filters_195` cases plus **1**
pre-existing node
(`test_admin_records_routes::
test_admin_record_list_invalid_uuid_filters_are_safe`). The primary
document now says 29 with that composition; the 195-a report's "32
passed" assertion is hereby explicitly superseded by this
correction (its bytes remain immutable). The browser repair node is
separately **1 passed** (`browser-cifix-1.xml`); the two reruns are
distinct and are NOT summed or aggregated.

R2 — **Layer 2 heading vs actual mixed proof.** The 195-a report
labeled the 13-case integration layer "Real PostgreSQL 16 (no
HTTP/auth)" while describing real authenticated-HTTP uvicorn nodes
within it — a contradiction. The primary document's Layer 2 heading
now reads: "real PostgreSQL 16 (owned fixture): 10
repository/service-level cases + 3 real authenticated HTTP uvicorn
nodes", and the body separates the ten direct SQL/service cases (no
HTTP, no auth) from the three `test_http_*` cases (real authenticated
HTTP against a uvicorn-served app with real admin login). The 195-a
report's "no HTTP/auth" label is hereby explicitly superseded for
that layer by this correction (its bytes remain immutable).
Root's separate 2-case scope/limit regression probe remains described
as actual PG16 with no HTTP; the browser label-refresh mocked-lookup
qualification is preserved, and the resolvable older-record/search/
chip-lifecycle browser proofs remain real server + PG + Chromium.
Mocked unit ASGI is not described anywhere as real HTTP
authentication.

R3 — **Cited JUnit counts inspected once and kept accurate.**
Root-parsed values independently confirmed against the JUnit files
(all 0 failures/errors/skips): `unit-195-final` 96;
`unit-195-affected` 147; `integration-195-scope3` 13;
`root-probe-recheck` 2; `browser-195-new4` 4; `browser-195-usab2`
10; `browser-195-visual3` 9; `browser-195-visual4` 5 (overlapping
keys subset); `unit-cifix-1` 29; `browser-cifix-1` 1. No commands,
exits, or aggregates were fabricated; no new runtime test coverage
was added. The historical first-head CI failures and their bounded
copy fix remain honestly documented; the two unaffected tests are
described as pre-existing compatibility contracts (valid tests that
exposed the regression), not faulty tests.

## Focused verification (real process exits)

- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=120`, exit 0.
- `git diff --check`: exit 0.
- `tests/unit/test_oap_governance.py`: **9 passed**, exit 0.
- No unit/integration/browser/full-matrix/PG/container tests were
  repeated (documentation-only correction; order A2).

## CI status at publication (truthful)

- 195-a report head `5088bc0`: run completed 10/10 successful
  (2026-10-25 22:28:58 UTC) — verified on GitHub at this round's
  start.
- This round's implementation head `81fb2bf`: CI queued/in_progress
  at publication; the report commit (SELF, below) becomes the new PR
  head and its run is the pending final-head gate. Pending is
  reported as pending, not as a pass. Root owns final-head CI and
  the guarded merge.

## Docs impact statement

Updated: `docs/verification/2026-10-25-admin-list-multiselection.md`
only (R1 count 32 -> 29 with composition; R2 Layer 2 heading +
mixed-layer body split; R3 wording: compatibility-contract oracles,
observed 195-a SELF-head CI result, 195-b head pending). No other
doc, product, or test file changed.

## Safe boundary statement

- ZERO product changes: app, tests, styles, schema, models,
  migrations, dependencies, auth/session/CSRF, admission,
  accounting, quota, provider/backend/adapter, compatibility,
  capture, and transport are byte-identical to the 195-a SELF head
  (only approved docs/OAP paths differ).
- No new infrastructure; no production data/DB/SSH/deploy/release/
  tag; no real provider/model/email/credential use.
- One PR #348 and the report-only SELF topology preserved; remote
  `main` unchanged; no rebase or history rewrite.
- The coding agent never merged and did not enable auto-merge; PR
  #348 remains open for root's independent review, all final-head
  gates, guarded merge, and actual-main verification. No new
  objective is activated by this execution.
