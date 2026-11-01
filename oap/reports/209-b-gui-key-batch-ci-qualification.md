# OAP Coding-Agent Report — 209-b

## Work order
- Identifier: 209-b
- Work-order file: `oap/orders/209-b-gui-key-batch-ci-qualification.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `c3c684576e05034a9a986003ecc3c3343656bc170ecf75b7ef887b9682d8e1e1`,
  11,589 bytes)
- `oap/active` pointer: value `209-b` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 209
- PR mode: AMEND_EXISTING_PR (PR 365 "Add reviewed atomic key batch
  changes to the admin GUI"; branch `oap/209-gui-key-batch`; base main
  `a4ed3ae68851ecbe0cb6862106abc287f3d6af55`)
- A implementation head:
  `2aaf11d2714ec7e24c732293f3ef7088a2b1ba7c` (tree
  `475cd530e850ef5c0b2a7ef86b8fd841fc144a99`)
- A report-only SELF:
  `cadc9b30eca3f64b76ef38003235d25d5c96f0b0` (tree
  `967b412c2941c5af24bf1c0d0d0754fdadaa2f64`); first parent exactly A
  IMPL; only `oap/reports/209-a-gui-key-batch.md` differs (18,958 bytes,
  sha256 `0116767a272b60e44cbd3da4a8f53d2433916b8589a5a198b3d0194c92f29747`).
  The A report and A order remain immutable and were NOT edited.
- B implementation head SHA (literal):
  `bb7e82dd71d079f02d23bf65ce22879668f00a21` (tree
  `0572479fd660320d71a56ea1c27316b416f79cfd`; first parent exactly A
  SELF)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and B IMPL; SELF's first parent is B IMPL)

## Status

209-b COMPLETE; FOCUSED LOCAL VERIFICATION GREEN. The two demonstrated
blocking A final-head CI failures are qualified by minimal test-only
repairs on the SAME PR 365, and the factual qualification record is
corrected and consolidated in the same living documents. No
product/source/static/proxy/CLI/service/schema bytes change from A:
the exact 8 changed paths are 2 tests + 4 docs + the B order +
`oap/active` (root independently verified; app/nginx/deploy bytes
unchanged). GitHub CI on the B head is PENDING at publication (treated
as pending, not pass). The merge gate remains root-owned. No
release/tag/deploy claim and no completion claim beyond 209-b: the
whole-GUI goal remains incomplete (G06-G18 of
`docs/MISSING_GUI_FUNCTIONALITY.md` stay open; the final installed 219
is outstanding). No real provider, email, or production traffic was
involved.

## Delivered (per order requirement)

1. **Consumer registration (requirement 1).**
   `tests/unit/test_documentation_contract_drift.py` gains ONLY the
   demonstrated registration: the exact path
   `app/slaif_gateway/api/admin_key_batch.py` joins the finite
   consumer allowlist with a concise explanation that it is a UI-gate
   consumer - it reads `EXTERNAL_TOOL_FENCED` only to present and
   require the existing fresh apply-time acknowledgement when the
   reviewed input policy sets a fenced external-tool policy. The shared
   `KeyBatchService`/`KeyService` still own validation, current
   authorization, fences/holds and execution; this grants no runtime
   hosted-tool authority. Every existing consumer, the whole-tree
   scan, the operator-limit assertion, and the rejection of unlisted
   modules are preserved. No wildcard API allowlist, no skipped test,
   no contract duplication; the authoritative constant import is
   retained, not removed to evade the review guard.
2. **Wrapper count (requirement 2).**
   `tests/unit/test_admin_slaif_design.py` updates ONLY the
   demonstrated scroll-region count 23 -> 24 for the new batch review
   table. The per-wrapper `role="region"` / `tabindex="0"` / non-empty
   `aria-label` assertions and all other design tests are preserved;
   the product wrapper markup is unchanged (it was already correct).
3. **Factual qualification record (requirement 3).** Corrected and
   consolidated in the SAME `docs/verification/gui-cli-parity.md`
   (new 209-b section), its `README.md` index, a compact B status note
   in `docs/MISSING_GUI_FUNCTIONALITY.md` section 11, and a brief
   operator clarification in `docs/admin-usability.md` section 10.3.
   No second verification document, no repeated inventories. Recorded
   explicitly:
   - the actual A IMPL CI failure: run `41261553792`, unit job
     `124715694142`, terminal FAILURE at 2026-11-01T01:36:04Z with
     exactly two failed cases; both independently reproduced by root
     on the unchanged A SELF (two cases / two failures, closed exit
     1); and B's narrow guard qualification (the two affected modules
     27 PASS, including both cases).
   - the A report's immutable statement that no CI run existed on the
     209 head / CI pending at publication is SUPERSEDED by this actual
     GitHub evidence, not rewritten (the A report is byte-unchanged).
   - the A-era claim that core plans require at least one selected
     key is FALSE: `KeyBatchService.plan` permits an empty
     cohort/status selection and the strict schema's `selected_count`
     minimum is 0; the standard empty-state row is the valid display
     for that outcome; no service or parser change was made or is
     needed.
   - core membership is rechecked AFTER the last selected-key lock
     under the existing READ COMMITTED law; later joins are untouched;
     nothing implies serializability or a new lock guarantee.
   - A's native proof remains scoped as recorded, the final B-head CI
     is pending until actually green, and the whole-GUI goal remains
     incomplete.
   - real field-value snapshots are kept distinct from physical-byte
     equality, and the corrected 80/81 unit-receipt chronology stands
     (80 cases at `unit-209a-5.xml`; 81 cases at `unit-209a-6.xml` and
     `unit-209a-7.xml`).
   - the SAME PR 365 description was updated around the final G05
     feature and actual final evidence (209-b addendum appended; a
     metadata-only REST operation, no added commits). The title
     already reflects the final G05 feature.
4. **Order, pointer, report (requirement 4).** This order and exact
   `oap/active=209-b` are committed unchanged with the two test/doc
   corrections, and ONE new final report (this file) is published
   atomically.

## Exact changed paths (B IMPL vs A SELF)

- `tests/unit/test_documentation_contract_drift.py`
- `tests/unit/test_admin_slaif_design.py`
- `docs/verification/gui-cli-parity.md`
- `docs/verification/README.md`
- `docs/MISSING_GUI_FUNCTIONALITY.md`
- `docs/admin-usability.md`
- `oap/orders/209-b-gui-key-batch-ci-qualification.md` (byte-exact)
- `oap/active` (pointer `209-b`)

These 8 paths are the entire diff; no product/source/static/proxy/
CLI/service/schema bytes change from A (root independently verified
the app/nginx/deploy bytes unchanged).

## Focused evidence (local; GitHub CI pending)

- The two affected test modules (which include both failed cases) run
  ONCE after the fixes: 27 PASS / 0 fail / 0 error / 0 skip, 5.016 s
  (JUnit `unit-209b-1.xml`, sha256
  `3fd29cc3954f826444a4c4d476eef04a1a71cb3ddeaea69bf28caa626eb7efef`),
  including `test_external_tool_policy_contract_consumers_remain_
  allowlisted` and `test_table_wrappers_are_labeled_and_focusable`.
  No second subset run after the full modules passed.

## Reused unchanged A evidence (not rerun)

- 81 focused unit PASS / 0 skip (JUnit `unit-209a-7.xml`, 32.767 s;
  chronology: 80 cases at `unit-209a-5.xml`, 81 cases at
  `unit-209a-6.xml`), fake-persistence ASGI/Jinja scope as recorded in
  the A report.
- 119 admin-usability inventory PASS / 0 skip (JUnit
  `unit-209a-inventory.xml`).
- 73 related 208/main-structure/actions PASS / 0 skip (JUnit
  `related-209a.xml`).
- 6 owned-PostgreSQL PASS / 0 skip, 8.876 s (JUnit `pg-209a-1.xml`;
  qualified loopback/tmpfs fixture, exact-ID container cleanup).
- 20 CI collection-order coexistence PASS / 0 skip, 26.883 s (JUnit
  `pg-209a-coexist-ci.xml`: 6x209 + 4x208 + 10x207 on one session
  database; the reverse order reuses the 208-b owned-PG proof).
- 7 real Chromium / owned-PG PASS / 0 skip, 32.655 s (JUnit
  `browser-209a-3.xml`; actual uvicorn app, real stylesheet).
- JS component root on the final
  `web/static/js/key-batch.js` SHA
  `5a1362620fb65a78a78630c3262197180a9651b1bb9104490c4e359a5f5867fd`.

No unchanged local suites, PostgreSQL/browser/CLI/provider/Codex
matrices, or duplicate inventories were rerun for this B heading.

## Static and governance checks

- `tests/unit/test_oap_governance.py`: 9 PASS / 0 skip (JUnit
  `unit-209b-gov.xml`, sha256
  `bb286393dd636a98a4f93ed29ee1a77caca5cff2159d4b92c6a848ac21720a54`)
  with the 209-b order committed byte-exact and `oap/active=209-b`.
- Ruff clean on the current PR-changed Python files (small finite
  set); `scripts/check_documentation.py` reports
  `DOCUMENTATION_CHECK=OK` (135 files); `git diff --check` clean.

## CI chronology

- A IMPL CI (TERMINAL): run `41261553792`, unit job
  `124715694142`, completed FAILURE at 2026-11-01T01:36:04Z with
  exactly two failures:
  1. `tests/unit/test_documentation_contract_drift.py::
     test_external_tool_policy_contract_consumers_remain_allowlisted`
     (the new batch router imports the authoritative external-tool
     contract constant but was absent from the finite consumer
     allowlist);
  2. `tests/unit/test_admin_slaif_design.py::
     test_table_wrappers_are_labeled_and_focusable` (actual 24
     wrappers versus historical expected 23; the added batch wrapper
     already had its required role, keyboard focus, and accessible
     label).
  Root reproduced both locally on the unchanged A SELF before B's
  repairs.
- A SELF CI: started after A publication; PENDING at A publication
  (pending is not pass). Its product/tests are identical to A IMPL,
  so the demonstrated failures justified this repair without waiting
  for that report-only run to reproduce them. No other failure was
  invented; if another material final-head failure occurs, the actual
  evidence is inspected and routine in-scope qualification stays
  within this B order before report.
- B-head CI: PENDING at B publication; it is the normal required
  final-head gate (pending is not pass).
- The A report's "no CI run exists on this 209 head yet" statement is
  superseded, not rewritten, by the terminal A IMPL evidence above;
  the A report remains immutable.

## Privacy invariants

- No product bytes change from A; no wildcard API allowlist, skipped
  test, or contract duplication; no policy authority widens; no
  authentication/CSRF/fresh-confirmation bypass; provider secrets
  remain isolated; PostgreSQL accounting/replay ownership is
  untouched.
- A's negative/privacy/transaction evidence remains accepted for the
  unchanged product code.
- Boolean canary assertions only; no whole CI assertion-source
  expansions, secret values, raw request content, or environment/DSNs
  were printed in tests, logs, or this report.

## Deployment

Unchanged from 209-a: deploying 209 is an application upgrade (rebuild
the API/assets image and recreate/restart the API so the new batch
code runs) plus the reverse-proxy configuration update from the
shipped templates with `nginx -t` and reload in the SAME maintenance
window; a proxy-only edit needs just the reload. No database
migration, no existing-key change or rotation. 209-b changes no
deployment artifact.

## Documentation

- `docs/verification/gui-cli-parity.md`: new 209-b section (actual CI
  failure with run/job/time, root reproduction, superseding-not-
  rewriting the A pending-CI statement, the factual corrections, the
  bounded B repair, focused B evidence with hashes, reused A evidence,
  pending status and limitations).
- `docs/verification/README.md`: new top 209-b index entry.
- `docs/MISSING_GUI_FUNCTIONALITY.md` section 11: "CI qualification
  (209-b, same PR)" note; "Still open" reflects the 209-b boundary
  (nothing in 209-a or 209-b touches the remaining G items).
- `docs/admin-usability.md` section 10.3: zero-selection and
  READ-COMMITTED membership-recheck bullet.
- PR 365: body updated with the 209-b final-head CI qualification
  addendum (actual CI evidence, test-only repair, focused evidence,
  factual corrections).

## Pending and honest limitations

- GitHub CI on the B head is PENDING at publication; the final-head
  CI result and strategic review/merge remain the root's gates. No
  merge was performed by the coding agent.
- The A report's historical statements (CI pending at A publication;
  "the core requires at least one selected key") remain in the
  immutable A report, are superseded by this record and the 209-b
  docs section, and were never rewritten or removed.
- Component scope distinctions remain as recorded in the A report
  (synthetic fake-persistence unit vs owned-PostgreSQL vs real
  Chromium; JS component root on a mocked lookup); no full local
  matrix was run for this objective.
- The whole-GUI goal remains incomplete (G06-G18 open; final installed
  219 outstanding). No production, security, compliance, provider-
  behavior, or scale claim follows from this report.
