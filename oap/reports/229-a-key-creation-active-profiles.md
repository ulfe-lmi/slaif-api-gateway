# OAP Report — 229-a (completion): working client presets and understandable GUI key creation — execution complete

## Status

- Objective: 229-a (`oap/active` working-tree bytes `229-a`, sha256 `6870f998e5f8013d7612f64aaa5d11b7bf9cef879a9f14f3555a69d83f5552f9`, root-owned and left untouched by this commit; order `oap/orders/229-a-key-creation-active-profiles.md`, sha256 `2fa230bf370a6d6ee322738460ba74a31b35fe0d4427dca039c086614da01397`, committed with the objective).
- PR: #403 (`CREATE_NEW_PR`), branch `oap/229-key-creation-active-profiles`, base `main` at `f1feec6bca0fd55f83d78c5badef2ab0b13ee304`; PR kept as a DRAFT; no auto-merge; the coding agent never merges.
- RESULT: **PASS** — all seven required-evidence items are executed (below); the remaining delivery (CI gates, root review, guarded merge, actual-main verification) is root-owned and pending.
- No production certification, release, tag, or security/compliance claim. No provider traffic, no real email, no production `DATABASE_URL` at any point.

## Identification

Implementation head SHA: 7791f95dfb57fea4db2ac1decaaf669c317bfe1c

Report publication commit: SELF

- PR #403 head at publication: the implementation head `7791f95d` (verified via GitHub before this report commit).
- Canonical record: `docs/verification/2026-11-27-key-creation-active-profiles.md` (root cause, shared-source/data-flow design, drift-audit findings table, field-help/UX coverage, exact verification results, limitations).
- Unrelated untracked local files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) and the root-owned `oap/active` working-tree bytes were preserved and are not part of this PR.

## Implementation (one bounded root-cause fix + GUI surface)

1. Root cause: `_validated_admin_qwen_codex_policy` compared the frozen qualification profile's recorded `client_module_version` (e.g. `8`) against the installed module version, so any deployment that promoted a newer Codex compatibility preset (e.g. packaged `codex-0.167.1`, revision 16) could not create Codex keys, and the new key pin was built from the frozen constants. Fix: the runtime gate is the STABLE executable module ID; the pin is built from the ACTIVE bound snapshot through the new shared accessor `modules/clients/registry.active_client_module_facts` (responses registry first, agent-chat fallback, exact `{id, version, fixture_sha256}` pin, display provenance from the bound profile).
2. GUI "Who will use this key?" section on the guided key-create form: four client-use checkboxes (Codex / OpenCode Chat / Hermes / OpenCode Responses) with plain-language field help, endpoint preselect (server rechecks every grant), five fail-closed conflict rules with field-labeled errors, preserved values and a diagnostic reference ID, a labeled "Advanced: historical Codex key modes" disclosure, and result-page pin explanations.
3. Compatibility dashboard (admin + demo) Codex module column now reads `<module> v<active> (qualified v<frozen>)`, keeping the active runtime identity visibly distinct from the frozen qualification evidence.

No schema change, no key migration, no automatic re-pin, no digest/fixture byte change, no new framework.

## Audit and documentation impact

Whole-repo drift audit (also cross-checked against the secondary read-only audit at base `f1feec6b`, relayed by root) classified every finding with file/caller/disposition in the canonical record:

- CONFIRMED_RUNTIME_DEFECT fixed: the frozen version gate + frozen pin inputs (admin.py, inherited from `services/codex_profile_registry.py`).
- CONFIRMED misleading labels fixed: the compatibility module columns.
- INTENTIONAL_HISTORICAL_FROZEN preserved: protocol-pilot branch and frozen 0.147 profile records; key templates keep their frozen 0.147 pin (documented GUI/template gap, not a defect).
- GUI differences documented: batch/clone carry raw policy metadata without client-use presets; the doc-mode JS does not uncheck historical Codex boxes (the server-side conflict rule is the authoritative boundary).
- UNRESOLVED/UNRELATED documented only: stale "(revision 3)" docstring lines in `modules/clients/codex_0162.py` (cosmetic, no runtime effect, unchanged).

Operator docs updated: `docs/admin-usability.md` (section 21), `docs/key-templates.md`, `docs/cli-field-administration.md`, `docs/client-compatibility-presets.md`, `docs/upgrade-runbook.md`, `docs/module-architecture.md`, `docs/verification/README.md`. Historical records (228-c merged 2026-11-25T11:36:12Z, 227 accepted Chat native loops) are preserved as dated evidence and not relabeled current.

## Results (exact; mocked vs live)

Environment: owned disposable PostgreSQL (container `slaif229-tmp-pg`, port 54399, DB `slaif229_test` via `TEST_DATABASE_URL`), repo venv, Playwright Chromium against local uvicorn 127.0.0.1:18400. Providers and email MOCKED; no real inference, no real mail, no live provider call.

- Evidence 1 (rev-16 + synthetic later rev, same path): rev-16 AND synthetic rev-17 GUI creates in isolated subprocesses persist the EXACT active pin (`codex-0.162-responses-v1` v16/v17 + active digest) while the QWEN38 frozen profile records v8; no GUI version constant patched. PASS.
- Evidence 2 (Hermes + both OpenCode wires + combined/conflict): GUI creates persist `opencode-1.19.3-chat-v1 v1` / `hermes-0.22.5-chat-v1 v2` / `opencode-1.19.3-responses-v1 v1` (+ all four Responses capabilities) with the requested restrictions; combined chat+responses on one provider works; chat-family and responses-family conflicts refuse before effects; ordinary + legacy `qwen_codex` + pilot + document-mode flows regress green. PASS.
- Evidence 3 (fail-closed matrix): invalid module identity, stale digest pin, not-ready route, missing/unavailable route (exact "four OpenCode Responses gates" explanation), wrong endpoints, allow-all, unknown client module ID — all deny with precise field help and correlation ID retained; no auth expansion. PASS.
- Evidence 4 (no partial side effects): conflict and gateless-route GUI POSTs leave 0 keys, 0 email, 0 `gateway_key_created` audits with values preserved, asserted against real PostgreSQL transactions with mocked email. PASS.
- Evidence 5 (consistent active metadata; historical pins explicit): 39 unit cases (active facts incl. chat fallback and unknown-id fail-closed; all five conflict rules; gate predicate truthy-vs-True; `_safe_client_module_pins`; summary accepts active pin / rejects stale digest; monkeypatched rev-16 active facts) + focused regressions of the audited drift locations. PASS.
- Evidence 6 (browser, real styles/JS): PASSED — screenshots `229-browser-{ordinary,client-use,advanced,error,result}.png` under the owned task directory (mode 700) for root visual review; verified ordinary unchecked state, client-use endpoint preselect (summary + manual + selected list), advanced disclosure, conflict error summary with preserved values, keyboard focus/Space toggling, corrected resubmission creating the key, and a no-JS fallback create via the plain owner input.
- Evidence 7 (existing suites + checks): `tests/unit/test_key_create_client_use_presets.py` 39 passed; `tests/integration/test_admin_key_create_client_use_postgres.py` 7 passed (17.8 s); focused existing key-create/admin GUI/doc-guard suites (incl. `test_admin_usability_inventory.py` 126 passed and the 44 documentation guards) passed; `ruff check` on all changed source/test files clean; `git diff --check` clean. Not run: the broad CI full matrix (supplied by GitHub Actions — status at publication: RUNNING/pending, truthfully not claimed green), 128-worker harness, real provider/email.
- Stage-2 functional GUI smoke (TestClient, mocked): 12 cases passed, as recorded in the canonical record.

## Deployment and migration conclusions

- Promoting a Codex compatibility preset (`CODEX_COMPATIBILITY_PROFILE_FILE`) requires an application restart/recreate to bind the new active snapshot (no hot reload). From then on, NEW keys created through the GUI client-use choices (or the CLI policy fields) pin the ACTIVE identity automatically.
- There is NO existing-key migration: explicit historical pins stay explicit; a pin that no longer matches the installed DATA fails closed at request time until migrated deliberately through the audited `codex migrate-key-profile` workflow. No schema, preset-file, key-material, or quota change is introduced by this PR.
- Key templates intentionally keep their frozen 0.147 pin and have no client-use choices (documented gap); batch/clone keep raw-metadata semantics.

## Claims not made

- No CI-green claim (GitHub workflow results are root-owned and pending at publication).
- No browser/usability proof beyond the captured states and assertions above.
- No production request, deployment, or operator-database statement; the human's reference key `gw-85d9696c-bddc-4461-902f-e68bc40d09fb` was never inspected.
- No next objective activated; 229 terminal (review/merge) remains root-owned.
