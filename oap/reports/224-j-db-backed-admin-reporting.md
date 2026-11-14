# OAP 224-j — immutable final report (report-only SELF)

* Objective: 224, database-backed demo-admin read pages; AMEND_EXISTING_PR #383, `oap/224-demo-web`.
* Strategic order: `oap/orders/224-j-db-backed-admin-reporting.md`, unchanged SHA256 `cc5b0f36f4424c29b2b10633290018d917c61d4984559ee59cc6bdc1a15b6e4a`.
* Activation commit: `d7dc1a2536d4cb60ed1970aec9623636990be6e9` (sole order and `oap/active=224-j` bytes), parent `cc7b02889162aac34c86c64f3f8c692ed913ab26`.
* Implementation commit, intended sole parent of report-only SELF: `5127c0cfcfdd44a40fc3d69ad1bf321d86965a73`; tree `a9f9644e565741ecb5bcc20aa887805352cba400`.
* Remote main at publication: `d3762e51c9a323dee6b728c4a45fa21b0bffae86`; PR #383 remains OPEN. The coding agent did not merge or enable auto-merge.

## Implemented scope

The central demo gate admits exactly fourteen additional fixed GET paths: five report pages (`/admin/reports/`, `/live-burn`, `/export`, `/pricing-disable`, `/fx-lookup`); five accounting index/candidate pages (`/admin/accounting-operations/`, `/expired-reservations`, `/external-tool-fences`, `/external-tool-holds`, `/provider-completed-recovery`); three administrator-account list/create/reset pages; and `/admin/key-batch`. The shared gate still denies missing-slash, extra-suffix, unknown, file-backed, action and download GETs. All unsafe `/admin` methods, including report export, accounting review, account create/reset and batch plan, still return the quiet 204 before body parsing or handler dispatch; demo logout is the existing explicit exception.

The isolated, never-persisted demo display identity has `superadmin` role so the existing account GETs render. It does not alter real admin roles or create authority outside the demo process. Account rows come from the verified per-session copy and remain fictionalized. The expired-reservation and effective-FX pages explain that their rows are frozen at copy time while their derived time-sensitive result is calculated at view time. Links were restored only to newly admitted read pages, and Accounts was added to the demo navigation. The accounting index hides its still-gated Operations link in demo mode. The ordinary admin GUI is unchanged in its authorization and behavior.

Implementation diff is confined to `app/slaif_gateway/api/admin.py`, `api/demo_admin_gate.py`, eight directly affected templates, `docs/demo-admin.md`, `tests/unit/test_demo_web.py` and `tests/integration/test_demo_web_admin_gate_postgres.py` (13 paths). No schema, worker, sanitizer, adapter, provider, production configuration or public endpoint changed. The documentation names the still-gated families and does not claim full demo completion.

## Verification and boundaries

* Focused local unit/documentation run: 122 passed, specifically 106 `test_demo_web.py` tests and 16 `test_documentation_inventory.py` tests (verified by independent collection). The earlier focused admin usability inventory also passed. Scoped Ruff E4/E7/E9/F and `git diff --check` passed.
* Owned PostgreSQL 16 module: two tests passed after the amount assertion. The real worker created two independently verified and sanitized per-session copies behind the SELECT-only reader role. All fourteen newly admitted GETs rendered 200 with `private, no-store` and demo banner; near misses stayed 404; sampled unsafe methods returned 204 with unparsed garbage bodies. Copied fictional administrator emails appeared, while source emails, dummy password hashes, copy names, DSN fragments and reader-role identifiers did not. The source and both copies retained their tested accounting/data counts through the read/no-op phase.
* The report group count matched the selected copy's distinct provider:model groups. In the fixture's sole group, the report token sort/title value matched the selected copy's 200-token ledger sum, and the actual-cost sort value matched its 0.0023 EUR sum. Expired-reservation rows matched the copied pending-and-expired quota rows within the existing limit. The explicit view-time hints appeared.
* Real Chromium at desktop width followed the demo nav to Accounts and rendered the report, expired-reservation and key-batch pages with the banner and no-store. The report screenshot `/tmp/slaif-224j-browser-reports-731713-644988886f.png` was inspected; the fourteen-item navigation fits and the report layout is coherent. This is owned synthetic browser evidence, not a live company deployment.
* Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` remained unstaged and unchanged at SHA256 `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`, `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`, `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6` respectively. Explicit Git path staging only.

The first PostgreSQL run found a still-gated Operations header link on the newly admitted accounting index; it was hidden only in demo mode, and the focused module then passed. After the amount assertion, the owned PostgreSQL module passed again. A system-Python pytest attempt did not collect because that interpreter lacks pytest; the `.venv` run is the valid evidence. A whole-file Ruff format check reported pre-existing formatting drift in legacy modules; no broad reformat was applied and scoped lint/diff checks passed. An unnecessary duplicate PostgreSQL invocation was stopped; the completed two-pass result above is the evidence.

## Hosted CI, review and continuation

At report publication, exact-head hosted checks for implementation `5127c0cf` are running. Pending checks are not passes. Root must independently verify final-head CI, review threads, report-only SELF topology, PR identity, diff scope, security/privacy/accounting and mergeability. Objective 224 is not complete: replay/diagnostics, compatibility, file-backed catalog and process settings, remaining read/download families and full GUI audit need later same-PR suffixes; objective 225 is the installed acceptance gate. Do not merge PR #383 in this round.

This report is the sole file intended to differ in its SELF publication commit. The report will be immutable after that commit.
