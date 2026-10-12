# OAP Execution Report — 181-d: Finish catalog authority and test isolation

## Identity

- Objective: 181 — authoritative catalog collection (SAME PR 318, branch `oap/181-authoritative-catalog-collection`)
- Round: **181-d** (AMEND_EXISTING_PR), selected by `oap/active` = `181-d`
- Order: `oap/orders/181-d-finish-catalog-authority-and-test-isolation.md` (strategic-authored; committed byte-unchanged in the implementation commit; file sha256 `f138eb986987f438425012bd9979e0bd9934c52c45aa2154624b3d735ace189a`)
- `oap/active` exact bytes (verified with `od -c` before publication): `1 8 1 - d` — 5 bytes, no newline; committed byte-unchanged
- Starting PR/local head (181-c immutable report head, pre-round): `5f0684c922ff7658603de5b627887d4eac5272c5`; its first parent `502369d71265dacfcdca993e81721e60d8f3e8f3` is the 181-c implementation
- Implementation head: `1ae62c38ae30ccbb37924a451a718f58ec8fafd2` (11 files, +821/−125)
- Report publication commit: SELF (first parent = implementation head `1ae62c38ae30ccbb37924a451a718f58ec8fafd2`)
- Canonical `main`: `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`
- PR 318 at report time: OPEN, MERGEABLE, head `1ae62c38ae30ccbb37924a451a718f58ec8fafd2` (verified via `gh pr view 318 --json headRefOid` after push), `mergeStateStatus: UNSTABLE` (one required check failing — see GitHub CI section), `autoMergeRequest: null` (preserved; no merge, no auto-merge)
- Strategic review evidence (read-only, at the 181-c head; originals preserved in the strategic root `review-artifacts/181-c-review/`): `semantic_probe.py` sha256 `7cb5259a6d85b8120adca963ed524021f8ad5cb7586205cf6110934b918ba166`, `semantic-results.json` sha256 `376a0544a57e39045075ebdd3b26b820f74161b1e61ec6c1bfcc366cc79cc2b0`, `offline_guard.py` sha256 `8e1fd6e96b8489a2b52edc45482ae2803abf0afccfd70e8e7cfb960ae08569bf`, `suite-dns-audit.json` sha256 `9122d04f7b93b3cc44646095bb8158b9d2a488981eff0521ccc5f23225a142df`, `midnight_probe.py` sha256 `50247e669709ed62ad12723f5ff7ea51e895b47f05a01d134ee10a7da06f3c8f`, `midnight-results.json` sha256 `03b196c7218a3ae13083eba922250897903157a1251237a14d5aedcffa68142b`

## Status

**PARTIAL** — all in-scope 181-d work (D1–D4) is implemented, locally verified, and pushed; one required merge-gate check (`Docker Compose smoke`) FAILS at the implementation head for a cause outside this order's scope (upstream unpinned-dependency drift, dependency/Docker changes explicitly excluded from 181-d), so the PR cannot yet be merged. Strategic scope decision (concurrent with this round): the bounded dependency repair is deferred to a later same-PR continuation.

## Executive summary

181-d finishes the four defects independently reproduced during strategic review of 181-c, on the same PR 318:

- **D1**: the documented OpenRouter `:online` model variant is now excluded from standard-v1 proposals by INTRINSIC HOSTED IDENTITY — the official model-variants contract states the suffix enables real-time web search for any model (exactly equivalent to the `web` plugin, deprecated in favor of the `openrouter:web_search` server tool) — in the shared `standard_v1_billing_decision`, applied before proposal by the collector and recomputed by the supplied-bundle validator, independent of positive/zero/missing `web_search` fees. New exact reason `intrinsic_hosted_variant_unrepresentable`. Explicit selection BLOCKs; a fully grounded supplied candidate BLOCKs; flat siblings stay proposed.
- **D2**: the collector now evaluates the WHOLE local exact/wildcard baseline authority set before choosing any flat row. A mixed set (≥1 exact alias + ≥1 governing fixed-upstream prefix/glob for the same provider/upstream) is retain-only with `baseline_contract_not_flat` and an explained detail naming every alternative; no parallel route/pricing candidate is invented; the validator confirms the claim and still BLOCKs a supplied parallel bypass.
- **D3**: every focused CLI test now runs through the injected-resolver `_cli_collect` seam under a module-wide fail-on-live-I/O guard (refusing default-DNS and real socket connections, including import-time default bindings), and the FX freshness-boundary tests freeze one coherent pipeline clock, proving the three-day/ four-day calendar-age rules across a UTC midnight.
- **D4**: the maintained operational `/home/ubuntu` paths in `AGENTS.md` (line 145 only), `OAP-COMMUNICATION-coding-agent.md` (13 lines) and `oap/README.md` (3 lines) are migrated byte-for-byte to the human-confirmed `/home/janezp` roots; no other line in those files changed.

Documentation states the new exclusion, the mixed-baseline retention, and the unclosed variant-class limitation honestly. 333 focused tests pass; under the strategic-identical external guard the suite performs ZERO uninjected default-DNS calls and zero real connections. GitHub CI at the implementation head: 9/10 SUCCESS, `Docker Compose smoke` FAILURE (deterministic, out-of-scope cause — detailed below). 181 is NOT closed: transport budgets/connection/encoding, actual collection versus intact replay, and exact tooling identity remain REQUIRED in later same-PR continuations; 182/183/184 unchanged.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 318
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/318
- PR state at report time: OPEN
- Base branch: `main` (`6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`)
- Head branch: `oap/181-authoritative-catalog-collection`
- Starting remote SHA: `5f0684c922ff7658603de5b627887d4eac5272c5`
- Implementation head SHA: `1ae62c38ae30ccbb37924a451a718f58ec8fafd2`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `1ae62c38ae30ccbb37924a451a718f58ec8fafd2` (single commit; push `5f0684c..1ae62c3`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR 318)
- Merge performed: NO

## Changes made

1. **D1 — intrinsic hosted identity, fee-independent** (`source_evidence.py`): new `REASON_INTRINSIC_HOSTED_VARIANT = "intrinsic_hosted_variant_unrepresentable"` (in `BILLING_EXCLUSION_REASONS`) and `ROUTER_INTRINSIC_HOSTED_VARIANT_SUFFIX = ":online"`. `_router_billing_decision` now returns the intrinsic identity exclusion FIRST (before any price is read) whenever any authoritative row of the model ends in `:online`. This is one exact documented variant identity, not a model-name classifier: no other variant class is inferred. Because the decision lives in the shared `standard_v1_billing_decision`, the collector applies it before proposal and the validator recomputes it from the parsed official rows on supplied-bundle replay — caller-supplied inventory, warnings, or labels cannot launder the identity. OpenRouter-only; flat siblings stay proposed; explicit selection of the variant BLOCKs like any excluded model.
2. **D2 — complete authority set before any flat-row choice** (`collection.py`): `_baseline_identity_for` now computes the covering wildcard set FIRST and adds a mixed branch: `exact_rows and covering` → `(None, REASON_BASELINE_CONTRACT_NOT_FLAT, "baseline route authority for this upstream is mixed: exact <names> and governing <descriptions>; ... retained locally")`. New shared helper `se.baseline_wildcard_route_descriptions(covering)` records match type, public pattern, fixed destination (or passthrough) and priority for every governing row (first four named, remainder counted) — alternatives are explained, never reduced. The prior exact-only, non-flat, lone-wildcard, and multi-exact branches are preserved unchanged. (`validation.py`) the `baseline_contract_not_flat` inventory re-verification accepts the mixed claim: `verified = governing_wildcard or (len(exact_here) == 1 and not _baseline_route_flat_capable(exact_here[0]))`. The existing `wildcard_route_authority_bypassed` gate (unchanged) still BLOCKs a supplied parallel route for a governed upstream on a mixed baseline.
3. **D3 — offline CLI tests and one coherent clock** (`tests/unit/test_catalog_refresh_collection.py`): (a) a module-wide autouse `_no_live_io_guard` fixture refuses `socket.getaddrinfo`, `socket.socket.connect/connect_ex`, AND re-points the import-time `__kwdefaults__["resolve"]` defaults of `fetch_source`, `fetch_sources`, `guard_public_destination`, and `collect_bundle` to a refusing tripwire (Python binds function defaults at `def` time, so patching `socket` alone would not cover them); (b) `test_cli_collect_bootstrap_publishes_sealed_run` and `test_cli_collect_blocked_world_publishes_blocked_run` now run through the existing `_cli_collect` seam, which injects `resolve=_resolve_public` (pre-fix they drove the production default resolver); (c) `FROZEN_MIDNIGHT_EDGE = 2026-10-11T23:59:59Z` and `FROZEN_POST_MIDNIGHT_EDGE = 2026-10-12T00:00:01Z` with `_freeze_pipeline_clock`, which freezes the one shared instant across fixture/collection/retrieval/CLI (`sources.py`, `collection.py`, `cli/catalog_refresh.py` are the only pipeline clock readers; validation derives its clock from `bundle.generated_at`, so it stays coherent). `test_cli_collect_stale_fx_review_exit_10` (4 calendar days → exit 10 / `READY_WITH_WARNINGS` / `fx_stale_review`) and the parametrized `test_cli_collect_fx_fresh_boundary_exit_0` (3 calendar days → exit 0 / `READY`, proven at BOTH the pre-midnight and post-midnight edges) keep the real three-day fresh and four-day review assertions while proving midnight independence. Production freshness/acceptance rules are unchanged.
4. **D4 — maintained path migration** (`AGENTS.md`, `OAP-COMMUNICATION-coding-agent.md`, `oap/README.md`): absolute-path substitutions only, `/home/ubuntu/codex-work` → `/home/janezp/codex-work` and `/home/ubuntu/codex-supervision` → `/home/janezp/codex-supervision`. Exactly 17 lines changed across the three files (+17/−17, every changed line a pure root substitution): `AGENTS.md` line 145 (the strategic-protocol path — the only operational path in the root constitution); `OAP-COMMUNICATION-coding-agent.md` lines 18, 19, 142, 148, 150, 151, 152, 153, 154, 166, 440, 450, 661; `oap/README.md` lines 10, 50, 51. Post-edit `grep -c '/home/ubuntu'` = 0 in all three files. Authority, protocol behavior, and objective-neutral startup are preserved; `oap/strategic-instructions`, historical orders/reports, original evidence, and strategy-owned `message.txt`/helpers are untouched.
5. **Tests for D1/D2** (same file): `test_router_online_variant_excluded_by_intrinsic_identity_not_fee` (fees `0.01`/`0`/missing → exact intrinsic reason, sibling proposed), `test_router_online_variant_explicit_selection_blocks` (zero fee + `model_include` → BLOCKED `missing_required_selection`), `test_supplied_bundle_online_variant_proposal_blocks_regardless_of_fee` (fully grounded injected candidate, three fee states → BLOCKED `proposed_row_billing_ineligible` with the intrinsic reason in the detail), updated `test_router_online_variant_hosted_charge_excluded_and_sibling_kept` (positive-fee variant case now carries the intrinsic reason); `_mixed_baseline(match_type, pattern)` helper plus `test_refresh_mixed_exact_and_wildcard_baseline_retained_coherent` (parametrized `prefix public/`, `glob public/*`) and `test_supplied_bundle_parallel_route_on_mixed_baseline_blocks`; new `_inject_proposal_facts` grounding helper.
6. **Documentation**: `docs/catalog-refresh.md` (new `intrinsic_hosted_variant_unrepresentable` inventory row; `baseline_contract_not_flat` row and a dedicated bullet for the MIXED authority set; proposal-scope exclusion list reworded around the identity-based, fee-independent `:online` exclusion with the contract check date and the unclosed variant-class limitation); `admin/catalog-refresh/README.md` (identity exclusion + mixed-baseline clause in the eligibility/retention summary).

## Files changed

Implementation commit `1ae62c3` only (11 files, +821/−125):

- `app/slaif_gateway/services/catalog_refresh/source_evidence.py`
- `app/slaif_gateway/services/catalog_refresh/collection.py`
- `app/slaif_gateway/services/catalog_refresh/validation.py`
- `tests/unit/test_catalog_refresh_collection.py`
- `docs/catalog-refresh.md`
- `admin/catalog-refresh/README.md`
- `AGENTS.md` (line 145 only)
- `OAP-COMMUNICATION-coding-agent.md` (13 path lines only)
- `oap/README.md` (3 path lines only)
- `oap/orders/181-d-finish-catalog-authority-and-test-isolation.md` (strategic-authored, committed unchanged)
- `oap/active` (exact strategic bytes `181-d`, committed unchanged)

Allowed but UNCHANGED paths: `app/slaif_gateway/services/catalog_refresh/rendering.py` (groups the inventory generically by `reason_code`; no per-reason wording exists to update — verified by inspection), `tests/unit/test_catalog_refresh_source_evidence.py`, `tests/unit/test_cli_catalog_refresh.py`, `tests/unit/test_catalog_refresh_policy.py`, `tests/unit/test_catalog_refresh_report.py` (no 181-d defects in these surfaces; the focused suite re-verified them green), `docs/cli-reference.md` (no CLI-visible change: syntax, flags, and exit codes are identical; its catalog-refresh section delegates semantics to `docs/catalog-refresh.md` — verified by inspection).

## Acceptance-criteria evidence

### AP-D1 — online intrinsic-hosted case excluded by identity, fee-independent
- Result: PASS (local) — strategic probes `online_0`/`online_None` (READY at the 181-c head, the defect) are now excluded; `online_0.01` stays excluded.
- Evidence: `test_router_online_variant_excluded_by_intrinsic_identity_not_fee` — for `web_search` fee `0.01`, `0`, and missing, the collected inventory is `("excluded_subset", "intrinsic_hosted_variant_unrepresentable")` and the flat sibling stays proposed. `test_router_online_variant_explicit_selection_blocks` — zero fee + explicit `model_include` → no proposal, BLOCKED with `missing_required_selection`. `test_supplied_bundle_online_variant_proposal_blocks_regardless_of_fee` — a supplied bundle with fully grounded route/model/pricing facts, valid provenance, normal TSV dimensions, exact published prices, and each of the three fee states → BLOCKED with `proposed_row_billing_ineligible` and the intrinsic reason in the warning detail (the validator recomputes the shared decision from the parsed official rows). Source observations remain intact (no price invented, no fee state altered); no inferred tool authority anywhere; runtime hosted policy unchanged. Normal zero-cost text controls remain green (rest of the focused suite).

### AP-D2 — mixed exact/wildcard baselines retained as coherent non-blocked plans; supplied bypass BLOCKS
- Result: PASS (local) — strategic probes `exact_plus_prefix`/`exact_plus_glob` (BLOCKED `wildcard_route_authority_bypassed` at the 181-c head, the collector/validator disagreement) are now READY; `only_prefix`/`only_glob` remain READY.
- Evidence: `test_refresh_mixed_exact_and_wildcard_baseline_retained_coherent[prefix/public/]` and `[glob/public/*]` — baseline with a flat exact `public-alias` (denied-capability wildcard alternative preserved: disabled/hidden/non-streaming, fixed upstream `synth/alpha`) → `bundle.routes == ()`, `bundle.pricing == ()`, `bundle.models == ()`; inventory `("excluded_subset", "baseline_contract_not_flat")` with detail naming BOTH `public-alias` and the governing pattern; `validate_bundle` → READY, no `wildcard_route_authority_bypassed`, no `model_disappeared`; `synth/alpha` absent from both `routes-proposal.tsv` and `pricing-proposal.tsv` (no invented parallel route/pricing); dispositions `public-alias`/pattern/`synth/alpha` all `NOT_FETCHED` with explicit retain-local wording. `test_supplied_bundle_parallel_route_on_mixed_baseline_blocks` — the same mixed baseline, supplied bundle re-inserting the exact `synth/alpha` route (fully grounded) → BLOCKED with `wildcard_route_authority_bypassed`. Controls green: lone exact alias, multiple exact alternatives, lone passthrough and lone fixed-upstream wildcard, unrelated fixed-upstream prefix (not covering), alias preservation with denials (all pre-existing tests pass unchanged).

### AP-D3 — focused CLI tests fully offline; coherent clock proves unchanged thresholds across midnight
- Result: PASS (local) — strategic midnight probes (fixture-before/collection-after a real UTC midnight flipping exit 10 vs expected 0) can no longer occur: fixture and pipeline share one instant.
- Evidence: the pre-fix defect was first demonstrated, then repaired: before the seam rewrites, the module-wide autouse guard made BOTH un-injected CLI tests fail with `AssertionError: focused test reached a default DNS resolver (live network escape)` (exactly the five default-resolver calls strategy audited). After the rewrites, the 10-file focused suite passes 333/333, and under the strategic-identical external guard the audit file records `{"exitstatus": 0, "uninjected_dns_calls": []}` — zero default-DNS calls and zero real socket connections across the whole focused collection/CLI surface. `test_cli_collect_stale_fx_review_exit_10` freezes `2026-10-11T23:59:59Z`, quote date `2026-10-07` (exactly 4 calendar days) → exit 10, `READY_WITH_WARNINGS`, `fx_stale_review`. `test_cli_collect_fx_fresh_boundary_exit_0[pre-midnight-23-59-59]` and `[post-midnight-00-00-01]` freeze the two edges, quote date = frozen date − 3 (exactly 3 calendar days) → exit 0, `READY`: the fresh boundary holds on both sides of UTC midnight with production thresholds untouched.

### AP-D4 — maintained-path byte changes are exactly the authorized substitutions
- Result: PASS — 17 lines, all pure absolute-root substitutions; `grep -c '/home/ubuntu'` = 0 in all three files after the change; `git diff --stat` = 2/26/6 line changes (1+13+3) with +17/−17; no authority/protocol/behavior wording touched; `oap/strategic-instructions`, historical orders/reports, original evidence, and `message.txt`/helpers unmodified; governance tests (`tests/unit/test_oap_governance.py`) pass.

## Local verification

All commands run from `REPO_ROOT=/home/janezp/codex-work/slaif-api-gateway` with the working Python 3.12.15 interpreter (see Local setup):

- `/tmp/slaif-181c-strategic-venv/bin/python -m pytest tests/unit/test_catalog_refresh_source_evidence.py tests/unit/test_catalog_refresh_bundle.py tests/unit/test_catalog_refresh_policy.py tests/unit/test_catalog_refresh_report.py tests/unit/test_catalog_refresh_seal.py tests/unit/test_catalog_refresh_collection.py tests/unit/test_catalog_refresh_sources.py tests/unit/test_cli_catalog_refresh.py tests/unit/test_provider_catalog_proposal.py tests/unit/test_oap_governance.py`: **PASSED — 333 passed in 25.59s** (pre-fix focused baseline at the 181-c head: 326 passed; Δ+7 = D1 +3, D2 +3 [parametrized ×2 + 1], D3 +1 [fresh-boundary parametrized ×2])
- `PYTHONPATH=/home/janezp/codex-work/slaif-api-gateway:/tmp/slaif-181d-agent /tmp/slaif-181c-strategic-venv/bin/python -m pytest -p offline_guard <same 10 files> -q` (strategic-identical external guard, byte-identical copy at `/tmp/slaif-181d-agent/offline_guard.py`, sha256 `8e1fd6e96b8489a2b52edc45482ae2803abf0afccfd70e8e7cfb960ae08569bf`): **PASSED — exit 0; audit `{"exitstatus": 0, "uninjected_dns_calls": []}`** (agent-side audit sha256 `f1a3137bf5ffea9919504969e7dd814e8e6a739b9af95129e745322003713c6e`; strategic original audit untouched)
- `/tmp/slaif-181c-strategic-venv/bin/python -m ruff check app tests`: **PASSED — "All checks passed!"**
- `/tmp/slaif-181c-strategic-venv/bin/python scripts/check_documentation.py`: **PASSED — `DOCUMENTATION_CHECK=OK files=91`**
- `git diff --check 5f0684c922ff7658603de5b627887d4eac5272c5`: **CLEAN** (no whitespace errors in the whole round diff)
- Full local DB/Redis/Docker/HPC/browser matrix: **NOT RUN** — explicitly not required for this round (GitHub CI ran the equivalents: PostgreSQL integration, E2E, Playwright, Docker Compose smoke)

## Baseline isolation disclosure (required; kept separate from the allowed documentation GET)

- **Pre-fix local baseline (181-c head, UNguarded, previous session)**: 326 passed over the same 10 focused files, run WITHOUT the external network guard. The two CLI tests at that head drove the production collect path without resolver injection, so the run performed **up to five public DNS lookups through the default resolver** — `openrouter.ai` ×4 (one bootstrap fetch + the 503-blocked world's three attempts) and `www.ecb.europa.eu` ×1 — matching the strategic `suite-dns-audit.json` (sha256 `9122d04f7b93b3cc44646095bb8158b9d2a488981eff0521ccc5f23225a142df`) recorded at the same head. All HTTP in that run was served by `httpx.MockTransport`: **zero real HTTP connections**. That baseline is therefore honestly reported as *potentially having performed public DNS*; no all-offline claim is made for it.
- **Strategic guard-based baseline (same head)**: per the strategic review record — 318 passed, 5 audited default-resolver calls, socket connects refused.
- **Post-fix (implementation head `1ae62c3`)**: the same 10-file focused suite under the external guard records `uninjected_dns_calls: []` (zero default-DNS calls, zero real connections) — see Local verification. The module-level autouse guard additionally makes any future default-DNS or real-socket escape fail the suite loudly.
- **Strategic independent re-verification at `1ae62c3`** (per strategic message this round): 333 tests, zero default-DNS audit, and the original semantic probes passed.
- **Allowed official documentation GET (separate from test isolation)**: one read-only, unauthenticated GET of the OpenRouter official model-variants contract (https://openrouter.ai/docs/guides/routing/model-variants/online, checked 2026-10-12) grounded the D1 intrinsic-hosted semantics. It is the explicitly allowed official-documentation GET, performed outside any test run; no test in this round performs any network GET.

## GitHub CI / required checks

Check state observed for implementation head `1ae62c38ae30ccbb37924a451a718f58ec8fafd2`:

- Check name: SUCCESS/FAILURE/PENDING/CANCELLED/MISSING — details
- `Unit, lint, and migration head`: **SUCCESS** (2m10s)
- `PostgreSQL integration tests`: **SUCCESS** (2m34s)
- `OpenAI-compatible E2E tests`: **SUCCESS** (1m37s)
- `Playwright browser smoke`: **SUCCESS** (2m47s)
- `Documentation hygiene`: **SUCCESS** (6s)
- `Analyze Python`: **SUCCESS** (1m15s); `CodeQL`: **SUCCESS** — `Analyze (python)` SUCCESS (2m19s), `Analyze (javascript-typescript)` SUCCESS (39s)
- `Docker Compose smoke`: **FAILURE** — step "Run migrations explicitly": `from greenlet import getcurrent` → `ModuleNotFoundError: No module named 'greenlet'` → `ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed. ... use the 'sqlalchemy[asyncio]' install target`. The image build log for the same run shows pip resolved `sqlalchemy-2.1.4` and its "Successfully installed" list contains NO `greenlet`. The failure repeated deterministically on the coding-agent-requested re-run (identical error, 48s). Strategic independently confirmed that SQLAlchemy 2.1.4's installed metadata requires `greenlet` only under the asyncio extra, while `pyproject.toml` declares plain `sqlalchemy` and the Dockerfile installs `pip install .`.
- All required checks green for the implementation head at report drafting: **no — 9/10**
- Out-of-scope cause: `git diff --name-only 5f0684c..1ae62c3` touches none of `pyproject.toml`, `requirements*.txt`, `Dockerfile`, `docker-compose*`, or migrations; the 181-c head `5f0684c` passed this same job with identical dependency files. The failure is upstream unpinned-dependency drift (a SQLAlchemy 2.1.x release moving `greenlet` behind the asyncio extra), not a 181-d regression.
- Strategic scope decision (concurrent with this round): the dependency repair is OUTSIDE 181-d (the order excludes dependencies/workflow/deploy/container changes); a bounded same-PR dependency continuation will follow report reconciliation.
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: NONE this round. The copied repo `.venv` is broken (symlink → missing `/usr/bin/python3.12`); it was left untouched. Execution reused the working `/tmp/slaif-181c-strategic-venv` (Python 3.12.15; pytest, httpx, ruff 0.16.7) with NO package changes, run from the repo root.
- Agent-owned guard copy at `/tmp/slaif-181d-agent/offline_guard.py` (byte-identical to the strategic original; writes its own `suite-dns-audit.json` next to itself, so the strategic original stays pristine) — outside both repositories, as required.
- `sudo`-level setup performed: none. No apt packages, no services, no local PostgreSQL/Redis/Docker.
- Durable setup changes committed/documented: none.

## Documentation

Documentation impact: `docs/catalog-refresh.md` now states (1) the new inventory reason `intrinsic_hosted_variant_unrepresentable` and its fee-independence (contract checked 2026-10-12; one documented variant identity, not a classifier), (2) the `baseline_contract_not_flat` row and a dedicated bullet for the MIXED exact + governing-wildcard authority set (whole set evaluated before any flat-row choice; every alternative recorded; no invented candidate; supplied bypass BLOCKed), and (3) the unclosed limitation that other OpenRouter variant classes have NO reviewed executable ordinary-Chat contract — unknown classes remain honestly unsupported/ambiguous and stay subject to the price-based gates. `admin/catalog-refresh/README.md` carries the matching one-line identity exclusion and mixed-baseline clause. `docs/cli-reference.md` required NO change (no CLI-visible semantics changed; the section delegates to `docs/catalog-refresh.md`). `AGENTS.md` changed only at its one strategic-protocol path (line 145); `OAP-COMMUNICATION-coding-agent.md` and `oap/README.md` changed only by absolute-path substitutions (13 + 3 lines). `scripts/check_documentation.py`: OK, 91 files.

## Safety and scope confirmations

- Unrelated files changed: no — untracked `CODEX-SESSIONS.md`, `codex.sh` preserved (not committed); ignored `.codex/`, `.local-provider-catalog/`, and unrelated worktrees untouched; no stash/reset/clean.
- Production secrets accessed: no.
- Production systems accessed: no.
- Required tests skipped/not run: yes — full local DB/Redis/Docker/HPC/browser matrix not run locally (explicitly not required this round); GitHub CI covered the equivalents (9/10 green; the one failure is documented as out-of-scope dependency drift).
- Scope deviation: no — implementation limited to the order's exact allowed paths; no runtime pricing/accounting/provider-policy/route-resolution, DB/schema/migration, sources.py transport, bundle/schema/seal, dependency, or deploy changes; no Codex-researcher or archival-transcript work.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO (`autoMergeRequest: null` preserved; no merge action of any kind)
- Activated order and `oap/active` edited by coding agent: NO (order sha256 `f138eb98...` and exact 5-byte active `181-d` verified before publication and committed byte-unchanged)
- Report-publication commit changes only this report file: yes (verified by staged diff before the commit)
- Real upstream/provider calls: none (mocks/synthetic source facts only; the single allowed official-documentation GET is documented above)
- Report layout redesign: none — follows the established 181-x report structure

## Known limitations / blockers

- **`Docker Compose smoke` FAILURE at the implementation head** (deterministic; SQLAlchemy 2.1.4 resolved without `greenlet`; production install declares plain `sqlalchemy`; 181-d does not and may not touch dependencies/Docker per the order). The PR merge gate is not green until a bounded same-PR dependency continuation lands (e.g., pin the SQLAlchemy line or add the `greenlet`/`sqlalchemy[asyncio]` install target) — deferred to that round per the strategic scope decision.
- Objective 181 is NOT closed by this round: transport budgets/connection/encoding closure, actual collection versus intact replay, and exact tooling identity remain REQUIRED in later same-PR continuations. Objectives 182 (isolated Codex), 183 (atomic audited apply/accounting), 184 (final administrator workflow) remain pending.
- The pre-fix unguarded baseline is disclosed as potentially having performed public DNS (5 lookups, zero real HTTP connections); it is not an offline proof.

## Recommended strategic follow-up

Factual recommendation only: a bounded same-PR dependency continuation for the `Docker Compose smoke` gate (pin SQLAlchemy below the greenlet-metadata change or add the asyncio/greenlet install target to the production install), then re-verify the full required-check set on the new head before acceptance/merge. The strategic model decides whether to activate that continuation, amend again, or otherwise proceed.
