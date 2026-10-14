# OAP Execution Report — Objective 183-a: Isolated Source Research

Report status: IMMUTABLE (finalized at the exact final implementation head
`4b410505cc6dcb990bb3443c887357d6415849b5`; published atomically as the
immutable report; the report-only SELF commit is its publication commit).

## 1. PR identity and merge state

- PR: #321 `feat: research unresolved catalog facts with isolated Codex`
  (the unique 183 PR; CREATE_NEW_PR).
- Branch: `oap/183-isolated-source-research`.
- Base: `main` at `50acd24459b9feb4277044f724a06f04720f2491` (PR #320
  merged; verified `origin/main` unchanged at publication time).
- Commit chain on the branch:
  - `635a063` — activation: order + `oap/active` (order bytes unchanged
    since).
  - `00992b4` — OAP 183-a implementation.
  - `e59e11b` — docs: correct stale research/apply status in
    `admin/catalog-refresh/README.md`.
  - `4b410505cc6dcb990bb3443c887357d6415849b5` — implementation head:
    compact blocked-state first screen (renderer only; first parent of
    SELF).
- Report-only SELF commit: the publication commit of this report; first
  parent = implementation head `4b41050…`; only this report path differs.
- Merge performed: NO. Auto-merge: not requested/enabled. Coding agent
  never merges.
- Order: `oap/orders/183-a-isolated-source-research.md` (activated bytes
  immutable; unchanged by any implementation commit); `oap/active` =
  `183-a` (5 bytes, no LF). All prior 181/182 orders/reports remain
  IMMUTABLE and untouched.

## 2. Environment

- Coding checkout `/home/janezp/codex-work/slaif-api-gateway`; strategic
  root `/home/janezp/codex-supervision/slaif-api-gateway`.
- Python 3.12.15 (`/tmp/slaif-181c-strategic-venv`), pytest, Ruff (venv).
- Real isolated research worker: Docker with pinned digest image
  `python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f`
  (`--pull=never`), standard isolated gateway mode
  (`--internal` + `gateway_mode_ipv4=isolated`, IPv6 disabled), read-only
  mounts, no-new-privileges, cap-drop ALL, env allowlist, 0400-file
  synthetic credential, relay-only egress with pre-forward authority
  refusals, owned-label owned-resource cleanup. No host firewall changes.
- Real Codex CLI under test: `codex-cli 0.162.1`, binary
  `/home/janezp/.codex/packages/standalone/releases/0.162.1-x86_64-unknown-linux-musl/bin/codex`,
  sha256 `628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`
  (pinned release; identity bound to the exact copied template/schema and
  executed binary).
- Browser: Playwright Chromium, JS disabled, scoped
  `LD_LIBRARY_PATH=/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu`
  on targeted commands only (owned temporary runtime; no system install).
- No system package installs, no `DATABASE_URL` contact, no real source
  GET, no provider key, no real email, no production import.

## 3. What 183-a implements

Opt-in isolated Codex research for catalog facts that deterministic
extraction cannot resolve (R1 planning/orchestration, R2 enforced
isolation, R3 measured research identity + canonical artifacts, R4
reporting). Deterministic extraction stays first: Codex runs only for
genuinely unresolved fields; a deterministic official observation always
wins, and research facts are re-grounded against the captured source
bytes at review time (semantic fallback, parent-verified). The research
worker has no gateway, no default network path (relay-only egress,
forbidden authorities refused before forwarding), no write access to the
host repo/config, and only the pinned release runtime is exposed.

Measured-vs-declared identity is a core contract: the producing run's
DECLARED research identity (historical for supplied reviews) is
distinguished from THIS review's measured re-grounding; a sealed fact set
can only exist when the declaration is SUCCEEDED; supplied/fixture
results are never labelled a measured live execution; missing measured
fields are refused (UNAVAILABLE with a safe refusal code), never invented.

## 4. CI at the final implementation head (authoritative)

Run `38489916288` on `4b410505cc6dcb990bb3443c887357d6415849b5` (PR #321):

| Check | Result |
|---|---|
| Playwright browser smoke | PASS (3m04s) |
| PostgreSQL integration tests | PASS (2m57s) |
| OpenAI-compatible E2E tests | PASS (1m43s) |
| Docker Compose smoke | PASS (1m03s) |
| Documentation hygiene | PASS |
| CodeQL: Analyze (python) / Analyze (javascript-typescript) / CodeQL aggregate | PASS |
| Unit, lint, and migration head | **FAIL — 1 failed / 4641 passed / 1 skipped** |

The single failing unit test is
`tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`,
which asserts the activated `-a` order header carries
`` PR mode: `CREATE_NEW_PR` `` (inline-code Markdown). The activated 183-a
order byte is immutable and its header reads `PR mode: CREATE_NEW_PR`
(plain). This order therefore cannot repair its own activation header,
and the governance test is the durable invariant and was not weakened.
**This is the sole unresolved check at the exact head.** Strategy will
activate an ordinary 183-b on the SAME PR #321 with a correct governing
header and current state; no new PR or permission is required. All other
final-head checks are green.

Honest prior-run history on this PR (not superseded):
- `38487184042` @ `00992b4`: browser FAIL — blocked case
  `#changes > :nth-child(2)` bottom 917.9375 > 900 at 1440x900.
- `38487495027` @ `e59e11b`: browser FAIL (same) + unit FAIL (governance
  literal above).

## 5. Blocked-state first-screen repair (the authoritative CI browser fix)

The blocked fixture case is the tallest first screen: its `.state` banner
repeated the three leading blocker codes plus their human labels —
duplicating the findings line directly below — and wrapped to 3 lines at
1440x900 locally (4 under CI font metrics), pushing the What-changed
heading past the first screen in CI.

Change (renderer only, `rendering.py`; no font, viewport, or assertion
changes):
- BLOCKED banner: now `N blocking issue(s): <human label of the first
  blocking code> (+N more)`. The full count is preserved, the primary
  reason stays human-readable, and the remaining codes AND their labels
  remain visible on the first screen in the findings line (up to 3 groups
  + "all N findings" link) with per-item detail in the expanded
  `#all-findings` section.
- First-screen research chip: `research NOT_RUN (deterministic only)` →
  `research NOT_RUN`; the full NOT_RUN explanation ("no Codex invocation
  occurred in the producing run; the deterministic official-source
  collection/parsing alone produced every fact") remains in the expanded
  run-identity research note.

Measured geometry (JS-disabled Chromium, exact first-screen selectors):
- blocked case worst first-screen bottom: 892.42 → **843.83** at 1440x900
  (margin 56.2px); the banner is a single line locally and under a
  wider-metric font simulation (523/564px text vs 703px content width).
- CI browser smoke PASS at `4b41050` (run `38489916288`).
- Focused suite after the change, local at the implementation head:
  `tests/unit/test_catalog_refresh_report.py` 11 passed;
  `tests/browser/test_catalog_refresh_report.py` 1 passed (all 12 cases,
  1440/1280/375 initial + fully expanded, zero external requests, font
  floors retained); Ruff clean on the changed path.

## 6. Local focused verification at the implementation head

- Focused unit scope
  (`tests/unit/test_catalog_refresh_*.py` + `tests/unit/test_cli_catalog_refresh.py`):
  all passed (exit 0) at `4b41050`; the same scope recorded 572 passed at
  `e59e11b` before this session's renderer change.
- Browser suite: 1 passed (12 cases) as above.
- Integration (real Docker + real Codex CLI 0.162.1, qualification mock
  model transport): `tests/integration/test_catalog_refresh_research_codex.py`
  **5 passed** at `4b41050`:
  1. RP1 real CLI tool loop: call_id-matched `function_call_output`
     public-read control (exact mounted evidence content, exit 0), owned
     invocation-created resource IDs verified removed, cleanup_errors
     empty.
  2. RP2 malicious local-tool attempts: host-file/env/private-service
     canaries denied with MEASURED denial (owner-uid → EROFS
     `Read-only file system`; non-owner → EACCES `Permission denied`),
     zero host-bridge contacts, target sha256 unchanged; hosted
     web/background/MCP/unknown authorities refused before forwarding.
  3. Child timeout measured (watchdog SIGKILL, exit 137) — no partial
     output accepted.
  4. Malformed final CLI output refused by the PARENT parser (measured
     behavior: the CLI exits 0 on a malformed completion; the parent
     parser is the enforcement boundary and fails the phase — documented,
     not claimed as CLI-side enforcement).
  5. RP1 full pipeline: real CLI → collect_bundle (grounding) →
     validate/plan → render → atomic sealed publish → verify_run
     (READY/READY_WITH_WARNINGS, receipt + proposal artifacts present).

## 7. Fresh actual-CLI sealed report measured at the final head

After the final renderer edits, the RP1 full-pipeline test produced a new
actual-CLI sealed run on the implementation head:
`collect-20261014-002935-74081a05d5cd` (state READY_WITH_WARNINGS,
live-collection scope, declared research SUCCEEDED with 5/5 facts
re-grounded by this review; mock transport).

- `REVIEW.html` sha256
  `5fe700b64b994ae2e0330b0ab63eea60c6db6baf03d993c89ff7567b2e6ce7be`;
  `manifest.json` `da989a20de790ff4a112fa974033e34cc31c2622a496fd03e43575cc006b2144`;
  `receipt.json` `0562684f3e1f34343c2a32daa1e33d83555a41df4d1afecb6b1d50afba45f764`.
- JS-disabled Chromium measurements of that exact artifact:
  - 1440x900 first screen: worst bottom `#changes > :nth-child(2)`
    **863.33** (≤ 900, margin 36.67).
  - 1280x800: collapsed 1280 / fully expanded 1280 (no overflow).
  - 375x812: collapsed 375 / fully expanded 375 (zero offenders).
  - Requests: the document only (zero external/physical requests).
  - Expanded: 10 full 64-hex digests visible; re-grounding and mock
    declaration text present.
- A copy of the run directory plus the measurement JSON is retained in
  the scratch evidence area (removed with the scratch root after
  publication, per the end-of-order sequence).

This is the literal final-head qualification; pre-commit or earlier-head
smoke is not described as qualifying this head.

## 8. Product defects found and fixed during 183-a

1. `research.py`: a post-execution workspace-cleanup failure replaced a
   completed measured outcome with blank UNAVAILABLE and discarded
   executed-task history → ordinary execution exceptions and
   workspace/adapter failures now return a measured FAILED preserving
   executed history (outputs still discarded); pre-invocation failures
   stay UNAVAILABLE.
2. `source_evidence.py` (research backing): a fact conflicting with a
   deterministic observation, an undeclared field source, a non-official
   source key, or a value mismatch was accepted → deterministic
   precedence enforced; per-field declared-source AND official-source-key
   reference check; BLOCKER `source_evidence_reference_mismatch` on
   violation.
3. `validation.py` (re-grounding loop): duplicate grounded research facts
   silently last-wins; conflicting values for the same
   (provider, model, field) accepted → identical duplicates deduped;
   conflict blocks (`research_facts_conflict`).
4. RP2 denial assertion assumed EACCES only; measured errno depends on
   researcher-uid vs file-owner (EROFS vs EACCES) → assertion accepts the
   measured variants plus a sha256-unchanged proof.
5. Browser fixture `_pipeline_bundle` was FX-incomplete (a USD row
   honestly BLOCKS) → deterministic ECB fixture bytes added;
   research-live/supplied cases reach the READY_WITH_WARNINGS success
   path.
6. Renderer: research chip overflowed 375 (chip-wrap on the long chip
   only); source-evidence live suffix duplicated the collection row
   (deduped, mechanism stays expanded); BLOCKED first screen exceeded the
   900px first screen in CI (section 5).
7. `admin/catalog-refresh/README.md` stale NOT_RUN / "No
   Codex-assisted research" / future-apply wording → corrected to the
   implemented opt-in isolated research fallback and accepted audited
   apply, with the pending 184 wrapper/installed qualification stated.
8. 183-a activated order header lacks the inline-code `PR mode` literal
   → NOT fixed (activated bytes immutable; governance test retained);
   addressed by the 183-b activation on the same PR.

## 9. Mock versus live; credentials

- Every model interaction in this objective is the qualification MOCK
  transport (canned SSE) inside the enforced isolated worker, or the
  owned loopback-only synthetic relay probe. **Zero live model calls.**
- Source bytes are captured fixture snapshots served through
  `httpx.MockTransport`; the "HTTPX GET 200" log lines visible in CI for
  the collection browser fixtures are mock responses, not physical
  network fetches. **Zero physical source GETs** in the test suites.
- No protected credential value was ever printed. Scans of every 183-a
  diff, new file, and scratch artifact found no `auth.json` value
  (scanned without printing). The host `auth.json` mtime
  (2026-10-13T13:31Z) predates the work window, and no
  `~/.codex/sessions/2026-10-13` host session directory was created.

## 10. Disclosure: initial host-side CLI inheritance deviation

Before the strategic boundary correction, initial host-side codex CLI
exploration ran under the inherited `HOME`/`CODEX_HOME` environment.
Facts, honestly scoped:
- The host-side calls were help/version/availability-level probes; no
  live model invocation was made (and none was made anywhere in this
  objective — section 9).
- No credential-bearing file or log was created by the coding agent; no
  protected auth file was re-read.
- Unresolved, reported without overclaim: exactly ONE `Authorization`
  field exists in the owned mock relay log; safe inventory could not
  classify its prefix as the explicitly configured synthetic token
  (`authorization_fields_found: 1`,
  `all_auth_fields_use_explicit_synthetic_prefix: false`, values never
  printed). Resolving it conclusively would require inspecting the
  protected auth file, which this order does not authorize. All later
  executions used the isolated worker with an explicitly configured
  synthetic task config; no protected credentials were used by them.

## 11. Residuals and deferrals (no overclaim)

1. `Unit, lint, and migration head` remains FAIL at this head solely for
   the immutable 183-a governance-header literal (section 4); 183-b on
   PR #321 carries the corrected governing header.
2. Installed-package (wheel) template/schema path resolution: the
   checked-in repo path is qualified; the installed layout needs a later
   demonstrated path decision — deferred to the 184 slice. A missing
   template/schema file refuses UNAVAILABLE; identity is never invented.
3. Worker-only sandbox override: explicitly permitted by the order after
   validating the complete outer nonroot/FS/env/isolated-network/broker
   boundary (validated in RP2); host `--yolo`/exec, AppArmor/sysctl/
   seccomp relaxation, and extra privileges were never used.
4. Objective 184 remains required (one-command wrapper, installed-package
   qualification). Nothing here claims the complete human workflow is
   done, and no live semantic-accuracy claim is made for the mock
   transport.

## 12. Files changed (24; all within the order's path list)

- `admin/catalog-refresh/README.md` (stale status corrected)
- `admin/catalog-refresh/research-instructions.md` (new)
- `admin/catalog-refresh/research-output.schema.json` (new)
- `app/slaif_gateway/cli/catalog_refresh.py`
- `app/slaif_gateway/schemas/catalog_refresh.py`
- `app/slaif_gateway/services/catalog_refresh/collection.py`
- `app/slaif_gateway/services/catalog_refresh/execution_identity.py`
- `app/slaif_gateway/services/catalog_refresh/rendering.py`
- `app/slaif_gateway/services/catalog_refresh/research.py` (new)
- `app/slaif_gateway/services/catalog_refresh/research_grounding.py` (new)
- `app/slaif_gateway/services/catalog_refresh/research_isolation.py` (new)
- `app/slaif_gateway/services/catalog_refresh/source_evidence.py`
- `app/slaif_gateway/services/catalog_refresh/validation.py`
- `docs/catalog-refresh.md`
- `docs/cli-reference.md`
- `docs/security-model.md`
- `oap/active` (exact `183-a`, 5 bytes, no LF)
- `oap/orders/183-a-isolated-source-research.md` (activated bytes,
  unchanged since activation)
- `tests/browser/test_catalog_refresh_report.py`
- `tests/integration/test_catalog_refresh_research_codex.py` (new)
- `tests/unit/test_catalog_refresh_report.py`
- `tests/unit/test_catalog_refresh_research.py` (new)
- `tests/unit/test_catalog_refresh_research_isolation.py` (new)
- `tests/unit/test_catalog_refresh_source_evidence.py`

No other paths, dependencies, or runtime fallbacks were added. No
skipped test is reported as pass anywhere above.

## 13. Final statement

- Implementation head: `4b410505cc6dcb990bb3443c887357d6415849b5`;
  base: `50acd24459b9feb4277044f724a06f04720f2491`; PR #321.
- All final-head checks pass except the single immutable-header
  governance literal (1 failed / 4641 passed / 1 skipped).
- The coding agent never merges and does not enable auto-merge; merge
  authority for OAP-managed PRs belongs to the strategic model as the
  human maintainer's delegate, after independent review and satisfactory
  final-head checks.
