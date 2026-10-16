# OAP Execution Report — Objective 186-a: README logo repair

Report status: IMMUTABLE (finalized at the exact final implementation head
`be8a3bb22db58ffb2cbb1a23dc5c21fdc3c00ef1`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first parent =
this implementation head; only this report path differs).

- Implementation head SHA: be8a3bb22db58ffb2cbb1a23dc5c21fdc3c00ef1
- Report publication commit: SELF

## 1. Work order and PR identity

- Work order: `oap/orders/186-a-readme-logo.md` (strategic-authored;
  committed unchanged by the activation commit); `oap/active` = `186-a`.
- PR: #324 `fix: use repository logo in README and documentation checks`
  — the unique 186 PR (CREATE_NEW_PR):
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/324.
- Branch: `oap/186-readme-logo`.
- Base: `main` at `fb3fa979e39cf00d3415e3e7be1811ee039f7701` (the human's
  README-only logo URL correction, directly on top of the 185 merge
  `312a31f`).
- Activation commit: `acac56275abba31221350433e3796977e8071047` (order +
  `oap/active` bytes unchanged).
- Commit chain on the branch: `fb3fa97` (base) → `acac562` (activation) →
  `be8a3bb` (implementation head, the single implementation commit).

## 2. Failure mode and repair

- Failure mode: the human's manual correction changed the README's
  external logo src from
  `https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg` to
  `https://slaif.si/assets/slaif-logo.svg`, while the documentation
  checker and one product-scope test still asserted the OLD external URL
  literal. Because the checker's brand-block validation runs against the
  real repository README, the stale fragment also cascaded into the
  synthetic-tree readiness tests. Failed main CI `38926388109`:
  Documentation hygiene required the old src; unit had 6 failures /
  4738 passes / 1 skip (5 as-of checks + the product-scope brand
  assertion).
- Reproduced on the new base before repairing: 6 unit failures
  (`test_documentation_asof.py::test_claim_phrase_with_valid_marker_and_prose_sha_passes`,
  `::test_archive_file_with_claim_and_no_marker_passes`,
  `::test_file_without_claim_phrase_and_without_marker_passes`,
  `::test_front_door_rules_silent_when_entry_points_absent`,
  `::test_real_repository_passes_all_structure_and_asof_rules`, and
  `test_product_scope_docs.py::test_product_scope_exists_and_readme_preserves_brand_and_link`)
  plus `DOCUMENTATION_CHECK=FAIL errors=1`.
- Repair (bounded, no redesign):
  - `README.md` (logo src only): the top centered brand block now
    references the tracked SVG by repository-relative path
    `app/slaif_gateway/web/static/img/slaif-logo.svg`, so GitHub rendering
    and cloned checkouts no longer depend on the external image host. The
    SLAIF homepage link, alt text, width, and centered position are
    preserved; no logo was added and no external asset was downloaded.
  - `scripts/check_documentation.py`: the obsolete external-src literal is
    replaced with the intended local asset contract — the required
    `src="app/slaif_gateway/web/static/img/slaif-logo.svg"` fragment plus a
    real file-existence check. The logo must exist, be nonempty, and carry
    the lightweight `<svg` document marker (a marker check, not a full XML
    validator; the tracked asset was independently parsed as a valid XML
    root by strategy review). A missing logo or broken src now fails
    clearly. Brand position, SLAIF homepage link, and navigation
    requirements remain enforced; no skip, xfail, blanket disable, or
    allow-any-URL workaround; synthetic-tree/readiness semantics preserved
    (the brand block still validates the real repository README).
  - `tests/unit/test_product_scope_docs.py`: the brand assertion now
    matches the local asset contract (one line).
  - `tests/unit/test_documentation_logo.py` (new, focused regression):
    the tracked logo is a nonempty SVG; the real README brand block
    passes; broken src, missing file, empty file, and non-SVG file each
    fail clearly.

## 3. Test mapping — changed/new vs inherited

- New: `tests/unit/test_documentation_logo.py` — 7 cases
  (`test_tracked_logo_is_a_nonempty_svg`,
  `test_real_readme_brand_block_passes`,
  `test_broken_src_reference_fails`, `test_missing_logo_file_fails`,
  `test_empty_logo_file_fails`, `test_non_svg_logo_file_fails`).
- Changed (assertion only):
  `tests/unit/test_product_scope_docs.py::test_product_scope_exists_and_readme_preserves_brand_and_link`.
- Repaired by the README + checker fix (no test-file change needed): the
  five as-of tests listed in section 2 — they failed only because the
  real-repo README no longer carried the stale literal the checker
  required.
- Inherited/unchanged: the remainder of `test_documentation_asof.py`, all
  of `test_documentation_inventory.py` (contains no logo reference and is
  untouched), and all synthetic-tree/readiness semantics.

## 4. Executed evidence (focused, local)

- Reproduction (pre-repair, on the new base): 6 failures +
  `DOCUMENTATION_CHECK=FAIL errors=1`.
- Post-repair: `DOCUMENTATION_CHECK=OK files=93`; 36/36 tests across the
  four affected unit files (asof + product-scope + inventory + logo);
  Ruff clean on the changed Python; `git diff --check` clean.
- Strategic independent review at `be8a3bb`: all 36 affected tests PASS,
  docs 93 OK, Ruff and diff-check clean, SVG valid XML root, tracked blob
  unchanged, all four product paths accepted.
- Tracked SVG bytes unchanged: blob
  `0d114503215fa4c0227b51b22dcc975c4476fc60` (7,351 bytes, nonempty)
  before and after.
- Final-head GitHub CI at `be8a3bb`: all ten checks SUCCESS (Unit, lint,
  and migration head; PostgreSQL integration; OpenAI-compatible E2E;
  Playwright browser smoke; Docker Compose smoke; Documentation hygiene;
  CodeQL incl. Python and JS analyses).
- No DB/browser/provider matrix was run locally (not needed for this
  static change); the normal final-head GitHub CI is authoritative.

## 5. Scope and diff

4 files, +118/−13 against base `fb3fa97`:

- `README.md` — logo src line only (1 line).
- `scripts/check_documentation.py` — obsolete literal replaced by the
  `LOGO_SRC` constant + `brand_block_errors()` helper (existence,
  nonempty, `<svg` marker), called from `check()` in place of the inline
  block.
- `tests/unit/test_product_scope_docs.py` — 1-line assertion update.
- `tests/unit/test_documentation_logo.py` — new focused regression file.

Plus the OAP activation files (`oap/orders/186-a-readme-logo.md`,
`oap/active`) committed unchanged by the activation commit. No other
product path was touched.

## 6. Security, privacy, accounting, and honest limitations

- Bounded diff inspection: no runtime, financial, authorization, secret,
  dependency, workflow, schema, service, or accounting path is changed;
  the change is static documentation/checker territory.
- No external fetch, no live provider/model/email, no production data,
  no release/tag/deploy during this objective.
- The checker's SVG validity test is the lightweight `<svg` marker, not a
  full XML validation; the tracked asset's XML validity was established by
  independent parse (strategic review), and the bytes are unchanged.

## 7. Documentation impact statement

README only (the logo src line). No other documentation needed updates:
the checker and tests encode the brand contract, and existing runtime
contracts are unaffected. The order's permitted documentation path
(README.md) was the only doc changed.

## 8. Disclosed deviations

None. All edits are within the order's allowed paths (the optional
focused logo regression file is one of them). No prior order, report, or
`message.txt` was modified.

## 9. Merge state and pending items (not yet done)

- PR #324 is OPEN at implementation head
  `be8a3bb22db58ffb2cbb1a23dc5c21fdc3c00ef1` with all ten checks SUCCESS
  (verified at publication).
- Pending, and NOT claimed as done: final-SELF CI checks on this report
  commit; strategic independent review (report/topology/whole diff/all
  exact SELF checks); and the guarded merge by strategy as delegated merge
  authority. The coding agent never merges and never enables
  auto-merge.
