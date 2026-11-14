# OAP 224-aa — Final Report (governance CI repair under the one-time human-authorized exception)

## Commit topology

- Activation commit: `a5a20788` (sole parent
  `21c77fd2548e48b7af1b259cdea12cdda235c8e7`, the z SELF) —
  committed the root-authored aa order and the exact
  `oap/active` = `224-aa` pointer unchanged, FIRST.
- Immutable order:
  `oap/orders/224-aa-governance-ci-repair.md`, SHA256
  `d95e98700134cc6af72019f89e99e0f562c569a582a42e008077882cebd0026c`.
- Human authorization (recorded verbatim in the order, 2026-11-14
  UTC): “Approving whatever you need to finish that work” — ONE
  narrowly scoped `224-aa` exception on the existing PR; no general
  change to future OAP identifiers.
- Implementation head (sole SELF parent): `03f28d55`
  ("224-aa: one-time human-authorized 224-aa identifier exception in
  the governance test (exact shape, 224-ab still refused),
  protocol/README exception notes, and the operator-runbook
  delete-command typo repair"; 5 files).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file. No merge; PR #383
  (`oap/224-demo-web`, base `main`) left open for strategic review.

## The confirmed z CI failure — reproduced locally against z head

- Hosted evidence (from the order): z final CI run
  `43598428853`, unit job `132457802089` FAILURE — 1 failed /
  7,960 passed / 1 skipped; the only failure
  `tests/unit/test_oap_governance.py::test_active_identifier_resolves_exactly_one_matching_order`;
  all other nine exact-head checks SUCCESS.
- Local reproduction: a throwaway detached worktree at the exact z
  SELF `21c77fd2548e48b7af1b259cdea12cdda235c8e7`, running the
  governance file alone, failed with the EXACT hosted assertion:
  `assert '# OAP Work O...legal suffix)' == '# OAP Work Order — 224-z'`
  — the strategic-root z heading carries the parenthetical
  `(FINAL legal suffix)` while the strict title check requires the
  bare `# OAP Work Order — 224-z`. The activated z order is
  immutable, so the heading cannot be edited; the worktree was
  removed after the reproduction.

## The narrow repair (order "Allowed edits ONLY")

1. `tests/unit/test_oap_governance.py`
   - `_active_identifier` now validates against the explicitly
     bounded shape `(?:[0-9]{3}-[a-z]|224-aa)`: the normal
     `NNN-a`..`NNN-z` law is unchanged, and `224-aa` is the ONE
     accepted exceptional identifier. `224-ab`, `224-az`,
     `225-aa`, `224-aaa`, double newlines, `22-aa`, `0224-a`,
     `224-a1`, trailing spaces and the empty payload are all still
     refused (pinned by the new
     `test_active_identifier_shape_law_with_224aa_exception`).
   - The strict first-line title equality
     (`# OAP Work Order — {identifier}`) and the exactly-one-order
     resolution are UNCHANGED; the active `224-aa` resolves to
     exactly one order whose first line is exactly
     `# OAP Work Order — 224-aa`.
   - The new-PR gate is unaffected: `224-aa` does not end in `-a`
     (its last two bytes are `aa`), and the aa order is
     `PR mode: AMEND_EXISTING_PR`.
2. `OAP-COMMUNICATION-coding-agent.md` (Section 6): one dated
   "One-time human-authorized exception (2026-11-14)" note scoping
   the exception to objective 224 and stating that no other
   two-letter suffix is valid and the law for future objectives is
   unchanged.
3. `oap/orders/README.md` and `oap/reports/README.md`: one dated
   line each admitting the single exceptional `224-aa-*.md`
   order/report and refusing any other two-letter-suffix
   identifier.
4. `docs/demo-admin.md` CURRENT operator runbook only (two command
   typos; the demo-admin CLI implements exactly
   create/list/enable/disable/reset-password — no delete command
   exists):
   - item 2 now lists "create/list/enable/disable/reset-password";
   - item 8 (Stop / clean up) now says "Disable the fake-admin
     accounts (disable-last-account ⇒ zero active ⇒ 404 everywhere;
     the CLI has no delete command), run worker cleanup …".
   - No historical stage section was touched.

No product/runtime GUI, sanitizer, auth, accounting, worker or
schema changes; no CSS polish. No activated order or earlier report
was modified.

## Verification evidence

- z-head reproduction: see above (exact hosted assertion
  reproduced, then the worktree removed).
- Focused governance tests on the aa state:
  `tests/unit/test_oap_governance.py` 10/10 passed (9 pre-existing +
  1 new shape-law test), real pytest exit 0.
- Immutability re-verified after all edits: z order SHA256
  `bbaabd7edea2824bfd5a1de9060bbc7d4899b7497da38986b4cdfbb54cfe821d`
  and z report SHA256
  `763a7694e76c77220bc13652f53045018cf54fe234a41727e261ff58e2739a5d`
  — byte-identical to the values recorded in the aa order.
- `scripts/check_documentation.py`: OK (137 files). Ruff clean on
  the touched test file.
- Per the order: the full unit/PG/browser/CodeQL matrix is left to
  the final hosted CI at this exact SELF head; the z accepted owned
  PG/Chromium evidence is reused and no unchanged local matrix was
  rerun (the only functional change is the test-file identifier
  law, covered by the focused run).

## Limitations and honesty notes

- The z order heading parenthetical remains in the immutable z
  order; the check no longer applies to it because the active
  pointer is `224-aa` and the aa order heading is exact. If a future
  round ever re-activated `224-z`, that strict-title failure would
  resurface — disclosed rather than worked around.
- The exception is scoped to the EXACT bytes `224-aa`; it creates
  no general two-letter-suffix allowance (protocol + both READMEs +
  the test law all say so).
- No merge, no Objective225 activation, no helper agents, no
  control FIFO reads beyond the consumed activation OK.
