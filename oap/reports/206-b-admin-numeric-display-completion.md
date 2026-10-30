# OAP Coding-Agent Report — 206-b

## Work order
- Identifier: 206-b
- Work-order file: `oap/orders/206-b-admin-numeric-display-completion.md`
  (committed unchanged in IMPL; sha256
  `4b52e2e86b561a298eae8c18327f2ed116daae4dc063e8b789d0c4ff0413c64f`)
- `oap/active` pointer: value `206-b` (no trailing newline), committed
  unchanged in IMPL; sha256
  `26481c2fecb811d2c7c09d4f3a9f20d041fe235801a00fd658465fe2b2249939`
- Numeric objective: 206
- PR mode: CONTINUE_EXISTING_PR (unique PR #362, base main at
  `8d60d098b51cddb6351c6b843feb1a46db115616`; starting head
  `7070bd45db499ee9a7155420ac322306910fea77` = the immutable 206-a
  report head)
- IMPL commit (literal): `f85f6c09ccc4191f12a8c48dd7bb1744add69726`
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status
Implementation COMPLETE within the order's allowed presentation
paths. The demonstrated missed readouts are finished and the one
stale display oracle is fixed; focused verification is green locally
(unit 54 + directly-affected presentation batch 309 + browser 3,
governance 9 — all 0 fail / 0 error / 0 skip). GitHub final-head
checks on the report head are PENDING (treated as pending, not
pass); strategic review and guarded merge are root-owned. This is NOT
a release/tag claim.

## Executive summary
Small, presentation-only completion of the original admin numeric
display fix in the same PR:

- The remaining read-only counters/summary totals group with the
  existing `num` filter: cohorts/owners/institutions detail
  counters, keys bulk import preview/result summary cards, pricing /
  FX / routes import preview/result counts, and the genuine
  read-only timeout / max-retries / priority readouts. IDs, dates,
  HTTP codes, versions, row provenance, raw code/JSON, and form
  transport stay literal; the bounded `rows shown` counters are left
  literal by design (page limits keep them below any grouping
  threshold and the 194-a source pin owns that exact interpolation).
- ALL remaining human-readable token quantities now use the accepted
  M display with the exact comma-grouped count in
  `title`/accessibility text: the key-detail output token margin
  (positive AND negative), the usage-detail configured token margin,
  the cached/reasoning readouts (title on each value), and the
  estimated-tokens-at-stop readout. Configured token-rate limits and
  the human policy summaries carry M `tokens/min` values with
  window/disabled/ignored/inheritance wording and the exact raw
  values preserved verbatim (no rate-enforcement or summary-meaning
  change). Per-1M monetary prices are unchanged and editable token
  inputs keep exact raw units (the key-detail token-margin form label
  now reads "(tokens)" next to the M readout).
- Service-built human policy summaries are no longer an exemption: a
  narrow pure presentation formatter (`format_policy_summary` /
  `format_rate_limit_policy`, filters `policysum` / `ratepolicy`)
  matches ONLY the exact finite producer grammars
  (`admin_key_dashboard._rate_limit_policy_summary`, `key_import`
  `rate_limit_summary`, `streaming_live_burn_surface_policy_summary`,
  the lazy-throttling wait summary, and the typed create-result rate
  policy dict) before touching any digit, then renders grouped
  counts, M token quantities, and 9-dp money with unneeded zeros
  stripped. Anything else — arbitrary text, identifiers, notes,
  provider metadata, URLs, raw JSON, code, credential-shaped strings —
  passes through byte-for-byte. There is no generic digit
  substitution, no unsafe Markup, and no change to shared service
  output used by CLI/API; the raw unrounded service string stays in
  the `title`/accessibility text of the rounded readouts.
- The exact stale 206-a oracle is fixed to `value="0"` (the
  zero-valued valid numeric default); the non-zero `-0.250000000`
  exact-digits assertion and all disabled/CSRF/action/auth checks are
  preserved unchanged.

## Stale-oracle failure and provenance (206-a report head)
- GitHub CI run 40980689318 on the 206-a report head
  `7070bd45db499ee9a7155420ac322306910fea77`: unit job
  123820143167 FAILED with 1 FAIL / 6546 PASS / 1 SKIP (106.88 s).
  The failing case was
  `tests/unit/test_admin_key_actions_templates.py::
  test_key_detail_renders_chat_streaming_live_burn_form` at line 223:
  expected `value="0.000000000"`, actual final intended value
  `value="0"`. Root retrieved the completed-job logs via REST after
  `gh --log-failed` refused while the overall run was still active.
- This is a stale display oracle (it predates the accepted zero-input
  representation change), NOT permission to revert correct zero
  normalization. The fix updates exactly that expectation and keeps
  the non-zero `-0.250000000` assertion exact.
- Qualification carried into the docs: the earlier "660 PASS" admin
  unit total PREDATES the final zero-input representation change and
  is NOT a final-tree all-admin pass; the 206-b scoped results below
  are reported separately from it.

## Changes (IMPL; all order-allowed paths)
- `app/slaif_gateway/web/formatting.py` (pure helpers, plain strings
  only, no Markup): `format_policy_summary` (known finite grammars:
  rate-limit comma-joined `N req/min` / `N tokens/min` / `N
  concurrent` / `Ns window` parts or the fixed `Default` / `none`
  labels; `Chat live-burn: on|off( (margins ignored)), cost margin
  EUR <9-dp>, token margin <int>`; lazy wait `Mode: wait; max wait:
  <n>s; max waiting per key: <n>; applies to Chat Completions and
  Responses before provider execution` — the reject variant has no
  digits and stays untouched) and `format_rate_limit_policy` (typed
  `requests_per_minute` / `tokens_per_minute` /
  `max_concurrent_requests` / `window_seconds` dict in the same
  grammar; unknown shapes fall back to the existing literal
  `str` rendering). Non-grammar input returns unchanged.
- `app/slaif_gateway/api/admin.py`: `policysum` / `ratepolicy` filter
  registration only — no handlers, auth, dependencies, services, or
  DTO changes.
- Templates (19): `num` on cohorts/owners/institutions detail
  counters; keys bulk preview/result summary cards; pricing/FX/routes
  import preview/result inline totals and cards; provider
  timeout/max-retries readouts (list + detail) and route priority
  readouts (list/detail/import preview/import result, raw
  `data-sort-value` keys untouched); `tokm` + `M` + exact-count
  `title` on the key-detail output token margin readout, the
  usage-detail configured token margin, cached/reasoning (each
  value), and estimated-tokens-at-stop; `policysum` on the key-detail
  rate/lazy/live-burn summaries (raw service string in the
  `title`), the create-result live-burn summary, the template-detail
  live-burn summary, and the bulk preview/result row policy
  summaries; `ratepolicy` on the create-result typed rate policy
  dict; `num` on the create-result lazy wait counts. The key-detail
  token-margin form label gains "(tokens)". Layout, branding,
  actions, CSRF, and controls are unchanged.
- `tests/unit/test_admin_key_actions_templates.py`: the exact stale
  expectation fixed to `value="0"` (comment records the 206-b
  correction); all other assertions preserved.
- `tests/unit/test_admin_numeric_display_206.py`: +17 cases (54
  total, 0 skip): the policy-summary / rate-policy pure matrices
  (grouping, M, negative margins, 9-dp money zero-stripping, true
  `0E-9` vs `1E-9`, empty labels, non-grammar passthrough incl. the
  legacy fixture grammar, credential-shaped text, semicolon/extra
  joins; dict fallbacks); ASGI renders of the key-detail rate /
  live-burn / lazy summaries with exact raw titles and the negative
  `-0.00025M` token-margin readout (`title="-250 tokens"`); a
  non-grammar summary string rendered byte-for-byte; usage-detail
  cached/reasoning title `937,826,734 / 1,000,000` beside
  `937.827M / 1M`, stop-estimate `title="937,826,734 tokens"` beside
  `937.827M`, configured margin `-0.00025M` (`title="-250 tokens"`);
  cohort detail with `937,826,734` / `1,234,567` grouped counters
  (no ungrouped 7+ digit counts remain); bulk-import preview with
  `1,234,567` / `1,234,560` grouped totals and the row summaries
  `Rate limits: 937,826,734 req/min, 937.827M tokens/min` and
  `Chat live-burn: on, cost margin EUR 0, token margin 0.0015M`.
- `tests/browser/test_admin_numeric_display_206.py` (extended in
  place, same owned labeled loopback tmpfs PostgreSQL fixture, real
  Chromium/uvicorn, exact container cleanup): the `num-lb` seed gains
  `rate_limit_requests_per_minute` / `rate_limit_tokens_per_minute`
  = 937,826,734 and a NEGATIVE `token_margin` -250; the usage `u0`
  seed gains `cached_tokens` / `reasoning_tokens`. The key-detail
  case now demonstrates the real page: rate summary
  `937,826,734 req/min, 937.827M tokens/min` (title keeps the exact
  `937826734 req/min, 937826734 tokens/min`), live-burn summary
  `cost margin EUR 0, token margin -0.00025M` (title keeps
  `0.000000000` / `-250`), direct readout `-0.00025M`
  (`title="-250 tokens"`), raw editable input `-250` (never
  `-0.00025M`, never `-250E+2`), plus a focused
  `key-detail-numeric-policy.png` screenshot (synthetic data only);
  the usage-detail case adds the `937.827M / 1M` cached/reasoning
  readout with title `937,826,734 / 1,000,000`. The unchanged 206-a
  sorting/legacy browser proofs are reused, not re-run.
- Docs: `docs/admin-usability.md` §6 — the unapproved
  "service-built strings outside this contract (documented
  limitation)" wording is removed; the human policy summaries are
  documented as in-scope via the known-grammar pure formatters, and
  the intentional raw machine/code/identifier/edit-field boundaries
  are explained as design, not omission.
  `docs/verification/2026-10-29-admin-numeric-display.md` — the 206-a
  record stays dated and unchanged in substance (its limitation
  bullet now points forward), and a dated 206-b completion section
  is appended to the SAME record with the stale-oracle provenance,
  the 660 qualification, the 206-b results, and residual
  limitations; no new parallel evidence file. `docs/verification/
  README.md` index entry updated in place.
- `oap/active` = `206-b` and the 206-b order committed unchanged.

## Focused verification (local; GitHub CI pending)
Layer: pure formatter + real template renders through the ASGI app
with the existing unit fake-session seams (no DB, no server, no real
provider/mail):

- `tests/unit/test_admin_numeric_display_206.py`: 54 PASS, 0 skip
  (JUnit `/tmp/slaif206/unit-206b.xml`).
- Directly affected existing presentation suites — 23 files
  including the exact previously failing test, the FX / pricing /
  routes / bulk-import template and route tests, the record detail
  template tests, the key create/keys routes and template tests, the
  194-a rows contract, the catalog FX oracles, and the usability
  inventory: 309 PASS, 0 skip (JUnit
  `/tmp/slaif206/affected-206b.xml`). All admin tests are NOT re-run
  per the order; the normal final-head CI supplies the complete
  regression gate.

Layer: actual Chromium on the owned, labeled, loopback-bound,
tmpfs-backed PostgreSQL 16 fixture (exact created container removed
on teardown; no owned containers remain after the run):

- `tests/browser/test_admin_numeric_display_206.py`: 3 PASS, 0 skip
  (10.858 s, JUnit `/tmp/slaif206/browser-206b.xml`) — including the
  new real key-detail rate/margin readouts and usage cached/
  reasoning exact titles described above.

Static/governance:

- `ruff check` on all touched Python files: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=133`.
- `tests/unit/test_oap_governance.py`: 9 PASS, 0 skip.

## Accepted 206-a evidence reused (not re-proven)
- Immutable 206-a report `oap/reports/206-a-admin-numeric-display.md`
  (sha256
  `6a9f989a080bdc25c791e5efd39360a4105b2ebbba4761542e26ca3e869e485f`,
  9390 bytes) and the accepted root source review of the pure
  formatters (grouping, exact int/Decimal, M precision, raw sort
  keys, editable raw units), the root re-run of the 37 formatter /
  template unit cases, and the root-read JUnit artifacts (unit 37 /
  earlier admin 660 (qualified above) / new Chromium 3 / existing
  browser 10 / governance 9) and both 206-a screenshots.
- The 206-a browser proof of real app/owned PG/stylesheet, exact
  sorting of three distinct token values sharing a rounded M label,
  None-last, and raw input units is reused unchanged (the extended
  browser file re-seeds the same fixture each run).

## Residual limitations
- ASGI renders are unit-fake-session (no DB); the Chromium cases are
  the actual-page proof. No real provider, email, or production
  traffic; no release/tag/deploy claim.
- The 309-case batch is the directly-affected set, not the full
  admin suite; the final-head GitHub CI run is the complete
  regression gate and is PENDING at publication (pending, not
  pass).
- `rows shown` counters intentionally stay ungrouped (bounded by
  page limits; 194-a source pin); external-tool "max calls" and
  similar small operator-level counts are grouped by `num` where
  read out (identity for small values) but were not individually
  re-baselined beyond the affected suites.

## Safe cleanup
- Owned PostgreSQL container from the browser run removed by the
  fixture's exact-ID teardown (label-verified ownership); verified
  no containers from this run remain (only pre-existing unrelated
  containers observed).
- Protected untracked files (`CODEX-SESSIONS.md`, `codex.sh`)
  untouched and uncommitted; no new worktrees, branches, or PRs;
  PR #319 (Dependabot) untouched.

## Publication state
- Same unique PR #362 amended (no new PR/objective); PR title
  unchanged, body updated around the final observable behavior and
  actual evidence.
- Report-only SELF: first parent IMPL
  `f85f6c09ccc4191f12a8c48dd7bb1744add69726`; ONLY this report
  differs between SELF and IMPL.
- Remote unique PR head = SELF before the response OK; pending
  checks remain pending.
