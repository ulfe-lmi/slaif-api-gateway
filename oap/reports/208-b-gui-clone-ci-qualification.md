# OAP Coding-Agent Report — 208-b

## Work order
- Identifier: 208-b
- Work-order file: `oap/orders/208-b-gui-clone-ci-qualification.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `11d8ce165b50bd6e19ee1326c825cfecd8f23e2d386cce42ffa60a924f27fb65`)
- `oap/active` pointer: value `208-b` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 208
- PR mode: AMEND_EXISTING_PR (PR 364 "Add reviewed key cloning to the
  admin GUI"; branch `oap/208-gui-key-clone`; base main at
  `09cbfb4795e279ef04e7a54f933afbeeaa7022b6`)
- Parent heads: A SELF `4335ecb014ecbdfbdf52b22ea0ea18456d9b1a15`;
  A order sha256 `ca86edff0f72dc1d1dec56d13e7c6f964afc9f8740e29a3b6fbdf735ba96f297`;
  A report (immutable) sha256
  `346f2dfec2a2abb3c7a04dd88ddcc51e8f9e9da60d79d0eb4c8f85b010479894`
- Implementation head SHA (literal):
  `81f096fa1b300d90e93450aa20b044fa6c57f1da` (single B implementation
  commit on top of A SELF)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

BOUNDED 208-b CI QUALIFICATION COMPLETE; FOCUSED LOCAL VERIFICATION
GREEN. Both demonstrated A final-head CI failures are repaired with
test-only changes plus removal of one genuinely unused tuple; no
product behavior change. GitHub CI on this B head is PENDING at
publication (treated as pending, not pass); the A report remains
immutable with its pending-at-publication statement, and the terminal A
failure is recorded here. The merge gate remains root-owned. No
release/tag/deploy claim, and no completion claim beyond the 208-b
scope (the approved full GUI round 207-219 continues; G05-G18 and the
final whole-GUI qualification remain later work). No real provider,
email, or production traffic was involved.

## Delivered (per order requirement)

1. **Structural main-as-composition guard (requirement 1).**
   `tests/unit/test_main_app_structure.py` no longer uses the brittle
   total-line ceiling (`assert len(source.splitlines()) < 84`). It now
   applies small standard-library AST structural checks
   (`_main_structure_violation`), preserving the existing
   health/route/openai-compat and no-business-orchestration string
   assertions:
   - first-party imports (plain `import` AND `from slaif_gateway import
     x` aliases treated as qualified module names) must stay outside
     the `services`/`db`/`workers`/`providers` layers; third-party
     imports are not judged;
   - every `include_router` call must target the `app` instance;
   - no inline route handlers: FastAPI and Starlette decorator forms
     (`get`/`post`/`put`/`delete`/`patch`/`options`/`head`/`websocket`/
     `api_route`/`route`/`websocket_route`) and direct handler
     registration (`add_api_route`, `add_route`, `add_websocket_route`,
     `add_api_websocket_route`) are rejected.
   Ordinary new router imports/includes pass without any ceiling
   change. A focused control test
   (`test_main_structure_guard_rejects_non_composition_shapes`) pins
   six rejected shapes (including the two reviewer-identified holes:
   `from slaif_gateway import services` and
   `app.add_api_websocket_route` inline registration) and one
   ordinary-composition positive (including a third-party
   `from unrelated_package import services` that must NOT be judged).
   No production refactor, no exhaustive call allowlist, no new
   framework; inference/auth/accounting law untouched.
2. **Dead tuple removal (requirement 2).**
   `app/slaif_gateway/api/admin_key_clone.py`: only the genuinely
   unused `_CLONE_FORM_FIELDS` tuple (demonstrated unused by repository
   search) is removed. Form parameters, validations, and the
   delivery-mode/schema/permission allowlists are unchanged; no other
   GUI behavior touched.
3. **Remaining A CI results checked (requirement 3).** Before pushing,
   the terminal A run `41243331544` was inspected in full: beyond the
   identified unit failure, the PostgreSQL integration job had 10
   further demonstrated failures, all in
   `tests/integration/test_admin_key_policy_207_postgres.py`
   (`duplicate key value violates unique constraint
   "uq_provider_configs_provider"`): CI collects the 208 clone module
   before the 207 policy module, and the 207 seed created the
   DB-unique provider rows unconditionally. Under the 208-b strategic
   scope clarification (routine fixture fixes stay in this order/PR),
   the 207 `_seed` provider/route creation now uses the same
   get-or-create repository pattern the 208 seed already used, so both
   modules coexist in either collection order. No production law, no
   state reset, no collection-order forcing; the 208 fixture needed no
   change. No materially different defect was discovered. The A
   immutable report was NOT altered.

## Exact changed paths (IMPL vs A SELF)

- `tests/unit/test_main_app_structure.py` (AST guard + control test)
- `app/slaif_gateway/api/admin_key_clone.py` (dead tuple only)
- `tests/integration/test_admin_key_policy_207_postgres.py` (seed
  get-or-create; authorized strategic scope clarification)
- `docs/verification/gui-cli-parity.md` (208-b chronology section)
- `docs/MISSING_GUI_FUNCTIONALITY.md` (delivery-update line + section 10
  pointer)
- `docs/verification/README.md` (newest-first 208-b entry)
- `oap/orders/208-b-gui-clone-ci-qualification.md` (exact bytes)
- `oap/active` (value `208-b`)

## Focused evidence (local; GitHub CI pending)

Newly run in B (owned outputs under `/tmp/slaif208/`,
`/tmp/slaif192-coding-venv`):

- `tests/unit/test_main_app_structure.py`: 6 PASS, 0 fail/error/skip
  (JUnit `unit-208b-3.xml`), including the new guard control case.
  Intermediate XMLs `unit-208b-1.xml`/`unit-208b-2.xml` record the
  guard-review iterations.
- OAP governance: 9 PASS, 0 skip (JUnit `unit-208b-gov2.xml`) with the
  208-b order committed byte-exact and `oap/active=208-b`.
- 207/208 coexistence in BOTH collection orders, each on a SEPARATE
  fresh qualified owned-PG fixture (owned `slaif185a-` container,
  loopback/tmpfs, env scrubbed, URL scrubbed from logs, exact-ID
  cleanup confirmed):
  - CI order (208 clone then 207 policy — the failing CI order):
    14 PASS / 0 fail / 0 skip (JUnit `pg-208b-ciorder.xml`; container
    `733cc7ea76b5` removed).
  - Reverse order (207 policy then 208 clone): 14 PASS / 0 fail /
    0 skip (JUnit `pg-208b-reverse.xml`; container `127a79e20e1a`
    removed).
  - 14 distinct cases per order (10 + 4), 28 executions total.
- Runner: `/tmp/slaif208/run-208b-coexist.py` (parameterized order,
  fresh `owned_pg_url` fixture, `TEST_DATABASE_URL` injection,
  DATABASE_URL/TEST_DATABASE_URL/upstream-key/Redis env scrubbed,
  `APP_ENV=test NO_COLOR=1 PYTHONPATH=app`).

Reused unchanged A evidence (NOT rerun, per order): 47 unit PASS
(`unit-208a-4.xml`), 4 owned-PG PASS (`pg-208a-1.xml`), 14 coexist
PASS (`pg-208a-coexist.xml`), 3 actual Chromium PASS
(`browser-208a-1.xml`). Those suites are unaffected by the B changes
other than the two test files and the one dead tuple listed above.
No local full unit/integration/browser/CLI matrix was run; no new DB,
container infrastructure, provider/mail, or package setup was added.

## Static and governance checks

- Ruff (venv) on the changed paths: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK files=135`.
- Governance 9/9 (above) — the 208-b order and active pointer satisfy
  the OAP invariants.

## CI chronology

- A run `41243331544` (head `4335ecb`, A SELF) TERMINAL FAILURE:
  - Unit, lint, and migration head (job `124661804858`): 1 FAILED,
    6687 PASS, 1 SKIPPED —
    `tests/unit/test_main_app_structure.py::test_main_app_only_wires_app_and_routes`
    on the line budget (`assert 87 < 84`); the skip is not a pass.
  - PostgreSQL integration (job `124661804846`): 10 FAILED, 524 PASS,
    9 SKIPPED — all 10 in the 207 module on the provider-slug unique
    constraint (order-dependent seed collision).
  - The other 8 final-A checks (Documentation hygiene, Docker Compose
    smoke, OpenAI-compatible E2E, Playwright browser smoke, CodeQL and
    the three analyses) succeeded at that head.
  - A logs preserved at `/tmp/slaif208/ci-final-unit.log` and
    `/tmp/slaif208/ci-final-pg-a.log` (URLs scrubbed where present).
- B implementation pushed only after that run was terminal (the
  no-push-until-parent-run-terminal condition). B final-head CI on
  `81f096fa1b300d90e93450aa20b044fa6c57f1da` is pending at publication
  (pending, not pass); root owns final-head checks, review, and merge.
- The A report was never altered to turn its failed CI into a pass;
  the A report's "pending at publication" statement stands as written
  for the A head, and the terminal A result is recorded in this report
  and in the living `gui-cli-parity.md` 208-b section.

## Privacy invariants

- No secret, token, key material, or credential value appears in the
  changed tests, docs, or this report; the 207/208 fixtures use their
  existing synthetic credentials and the seed password is a fixed
  test-only value already present in the 207 module.
- Owned-PG connection URLs are scrubbed from all runner output and
  logs; captures remain private.
- The removed tuple contained no secrets; the guard tests contain only
  structural source snippets and synthetic method names.
- No environment/credential dumps; no secret or content storage
  expansion; PostgreSQL accounting, replay ownership, review
  integrity/expiry/actor/delivery, and one-time-channel law are
  unchanged (no product behavior change).

## Deployment

No product behavior change (dead tuple removal only). Operator
instructions are the 208-a ones: ordinary API/assets rebuild and
restart; no schema migration, no existing-key migration, no production
action authorized.

## Documentation

- `docs/verification/gui-cli-parity.md`: new "208-b CI qualification
  and final-head chronology" section — terminal A result, bounded
  repair, newly-run focused evidence, reused A evidence, final-head
  pending status and operator notes. The 208-a section remains the
  historical A record.
- `docs/MISSING_GUI_FUNCTIONALITY.md`: delivery-update line notes the
  208-b same-PR CI qualification (test-only, no product behavior
  change); section 10 gains a "CI qualification (208-b, same PR)"
  pointer to the parity record.
- `docs/verification/README.md`: newest-first 208-b entry.
- PR 364 body updated before this report: header, evidence section,
  and limitations now incorporate the bounded 208-b CI qualification;
  the clone-feature description is unchanged.

## Pending and honest limitations

- GitHub CI on the B implementation head is pending at publication
  (pending, not pass); pending/skipped checks are not passes. The
  earlier unit run's 1 SKIPPED case remains a skip, not a pass.
- The A final-head CI failures are recorded honestly; the A report is
  immutable and still says "pending at publication" for the A head.
- The 207 seed change was validated in both collection orders on
  fresh fixtures (28 executions); it has not been through a full CI
  integration matrix locally by design (order forbids the local full
  matrix); the B final-head CI run is the remaining gate.
- G05-G18, the final whole-GUI field guidance/installed qualification,
  and objective 209 activation remain later work under the approved
  207-219 round.
- No merge, auto-merge, release, tag, or deployment was performed or
  authorized; root accepts, merges, verifies actual main, and records
  timing before any 209 activation.
