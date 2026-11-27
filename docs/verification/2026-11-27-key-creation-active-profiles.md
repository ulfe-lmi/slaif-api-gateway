# 2026-11-27 — Key creation uses active client profiles and explains its choices

OAP objective 229-a. Scope: the admin GUI key-creation form now issues key
pins from the ACTIVE installed client-module DATA snapshot (not from frozen
qualification constants), the four "Who will use this key?" choices carry
field-level help, conflict rules fail closed with preserved values, and the
result page explains which client module each created key is pinned to.

## Root cause

A deployment that bound a newer Codex compatibility profile through
`CODEX_COMPATIBILITY_PROFILE_FILE` (for example the packaged
`codex-0.167.1`, module `codex-0.162-responses-v1`, DATA revision 16) could
NOT create a Codex key at all:

- `_validated_admin_qwen_codex_policy` compared the frozen qualification
  profile's recorded `client_module_version` (e.g. `"8"` in
  `QWEN38_CODEX_PROFILE`) against the installed module's
  `module.module_version` and failed the request whenever the deployment had
  promoted a newer revision, even though the stable executable module ID
  had not changed.
- The new key's `responses_policy` pin was built from the same frozen
  constants, so even when the equality gate was satisfied the pin described
  the qualification snapshot, not the DATA the gateway actually runs.

The frozen qualification revision is EVIDENCE (the DATA snapshot a route was
qualified against), not a runtime equality gate. The runtime gate is the
stable executable module ID; the pin must come from the active snapshot.

## Four concepts kept distinct

1. **Stable executable module ID** — e.g. `codex-0.162-responses-v1`.
   Never renamed or substituted; it does not encode the CLI version.
2. **Active installed DATA** — revision + canonical digest + CLI provenance
   of the profile bound once at bootstrap
   (`bind_codex_0162_client_module`), exposed through
   `slaif_gateway.modules.clients.registry.active_client_module_facts`.
3. **Frozen qualification profiles/evidence** — the per-route qualification
   records in `services/codex_profile_registry.py` /
   `services/codex_qualification.py` (including their recorded
   `client_module_version`).
4. **Route/key capabilities** — the independent `codex_*` route gates and
   key `responses_policy` capabilities that authorize behavior.

## Current shared-source / data-flow design

- `modules/clients/registry.py`
  - `ActiveClientModuleFacts` + `active_client_module_facts(module_id)`:
    one accessor for the active identity. Responses registry is consulted
    first, then the agent-chat registry; `.pin` is the exact
    `{id, version, fixture_sha256}` triple; provenance comes from the bound
    `.profile` (or `policy_spec.provenance`) and is used for DISPLAY, never
    for qualification.
- `api/admin.py` (key-creation POST)
  - Four client-use checkboxes (`client_use_codex`,
    `client_use_opencode_chat`, `client_use_opencode_responses`,
    `client_use_hermes`), each with a "What is this for?" help panel.
  - `_validate_admin_client_use_selection`: fail-closed conflict rules —
    client-use + advanced configuration document, client-use +
    trusted calibration, a second Chat-family binding, a second
    Responses-family binding, advanced historical Codex sections +
    client-use. Each error names the fields and the form re-renders with
    every entered value preserved plus a diagnostic reference ID.
  - Codex choice: the checkbox is the confirmation on the existing
    `_validated_admin_qwen_codex_policy` path. The gate is now a stable
    module-ID match between the selected frozen profiles and
    `active_client_module_facts(CODEX_0162_CLIENT_MODULE_ID)`; the returned
    policy builds the pin from the ACTIVE snapshot (revision/digest of the
    bound DATA), while route readiness still comes from
    `CodexQualificationService.inspect()` and the frozen profiles' gates.
  - OpenCode (Chat) / Hermes: chat preset from the agent-chat registry's
    active facts; requires the `/v1/chat/completions` endpoint on the key.
  - OpenCode (Responses): `_validated_admin_opencode_responses_policy` —
    explicit models + providers (no allow-all), the `/v1/responses`
    endpoint, and an enabled exact `/v1/responses` route with ALL four
    OpenCode Responses gates True for every selected model × provider pair
    (fail closed otherwise, no dead-end grants).
  - `_safe_client_module_pins` renders the created key's pins on the result
    page ("Responses client module" / "Chat client module" lines);
    `_safe_codex_responses_policy_summary` keeps an acceptable-pin list
    (a list, not a set) for the Codex summary.
- `api/admin_compatibility.py` / `api/demo_admin_compatibility.py`
  - The compatibility dashboard's Codex module column now reads
    `<module> v<active> (qualified v<frozen>)`, keeping the active runtime
    identity and the frozen qualification evidence visibly distinct.
- `web/templates/keys/create.html`, `create_result.html`,
  `web/static/css/admin.css`
  - Client-use section with per-choice help, an endpoint preselect
    convenience (the server rechecks every grant), a clearly labeled
    "Advanced: historical Codex key modes" disclosure, and result-page pin
    lines.

## Drift audit findings

| # | Location / caller | Classification | Disposition |
|---|-------------------|----------------|-------------|
| 1 | `api/admin.py` `_validated_admin_qwen_codex_policy` (frozen `client_module_version != module.module_version` gate; frozen pin inputs inherited from `services/codex_profile_registry.py` `QWEN38_CODEX_PROFILE` via `_qwen_capacity_profile`) | CONFIRMED_RUNTIME_DEFECT | FIXED: stable-ID check only; pin from active snapshot |
| 2 | `api/admin_compatibility.py`, `api/demo_admin_compatibility.py` module column (frozen revision displayed as the current module) | CONFIRMED (misleading current label) | FIXED: "active vN (qualified vM)" |
| 3 | `api/admin.py` codex-protocol-pilot branch; `services/codex_profile_registry.py` frozen 0.147 `OPENAI_CODEX_PROFILE` | INTENTIONAL_HISTORICAL_FROZEN | PRESERVED: the pilot and 0.147 records remain frozen qualification evidence; the historical section is labeled as such in the GUI |
| 4 | `services/key_template_service.py` (hardcoded frozen `CODEX_0147_CLIENT_MODULE` pin check) | INTENTIONAL_HISTORICAL_FROZEN | PRESERVED + DOCUMENTED: key templates intentionally pin the 0.147 qualification; templates do not offer the client-use choices, so this is a known GUI/template gap, not a defect |
| 5 | `api/admin_key_batch.py`, `api/admin_key_clone.py` (carry `responses_policy` / `chat_client_module` metadata without Codex client-use checkboxes) | GUI difference | DOCUMENTED: batch/clone manage the raw policy metadata and have no client-use presets; no behavior change |
| 6 | `keys/create.html` `guidedPolicyControls` script (does not uncheck historical Codex checkboxes when switching to document mode) | Pre-existing client-side gap | DOCUMENTED: the server-side conflict rule (client-use + configuration document) is the authoritative boundary; the JS only hides guided policy controls |
| 7 | `modules/clients/codex_0162.py` stale "(revision 3)" docstring lines | UNRESOLVED / UNRELATED | DOCUMENTED only: cosmetic comment staleness in module docstrings; no runtime effect; left unchanged in this order |

Frozen fixture/digest evidence was NOT altered to make any check pass.

## Field-help / UX coverage

- Every client-use checkbox has an inline "What is this for?" disclosure
  explaining what the preset grants and what it does not.
- Checking a client preselects its unambiguous endpoint(s) and shows a
  summary line; the UI states that the server rechecks every grant.
- The historical Codex sections sit in one disclosure titled
  "Advanced: historical Codex key modes" and cannot be combined with
  client-use (server-enforced).
- Errors render a `role="alert"` flash with a diagnostic reference ID; all
  entered values (owner, validity, policy lists, checkboxes) are preserved
  for correction.
- No-JS fallback: the owner/cohort record choices degrade to plain inputs
  and the manual policy strings panel is the primary policy editor; the form
  still creates keys server-side (verified in the browser smoke).
- All new controls are keyboard reachable (checkboxes toggle with Space;
  the record-choice and manual panels are native form controls).

## Verification results (exact)

Environment: owned disposable PostgreSQL
(`slaif229-tmp-pg`, port 54399, DB `slaif229_test`,
`TEST_DATABASE_URL=postgresql+asyncpg://postgres:229tmp@127.0.0.1:54399/slaif229_test`),
repo venv, Playwright Chromium against a local uvicorn on
127.0.0.1:18400. Providers and email are MOCKED; no real inference, no real
mail, no production `DATABASE_URL`.

- `tests/unit/test_key_create_client_use_presets.py` — **39 passed** in
  2.24s (active facts incl. chat fallback and unknown-id fail-closed; all
  five conflict rules and allowed combinations; chat preset endpoint/pin;
  gate predicate truthy-vs-True; `_safe_client_module_pins`; summary
  accepts an active pin and rejects a stale digest; Qwen policy with
  monkeypatched rev-16 active facts → pin == active identity, module-ID
  mismatch rejected, not-ready route rejected, exact-endpoint rule,
  allow-all rejected).
- `tests/integration/test_admin_key_create_client_use_postgres.py` —
  **7 passed** in 17.84s (GUI POSTs persist the EXACT active pin in
  `metadata_json` for chat/Hermes/OpenCode-Responses; result page shows the
  pin labels; conflict 400 leaves 0 keys / 0 email / 0
  `gateway_key_created` audits with values preserved; gateless route 400;
  rev-16 and synthetic rev-17 GUI creates in isolated subprocesses pin the
  active identity while the QWEN38 frozen profile records v8).
- Browser smoke (Playwright, real styles + JS, disposable PG seed):
  **PASSED**. States captured under the owned task directory as
  `229-browser-ordinary.png`, `229-browser-client-use.png`,
  `229-browser-advanced.png`, `229-browser-error.png`,
  `229-browser-result.png` (mode 700). Verified: ordinary unchecked state;
  client-use endpoint preselect (summary + manual + selected list);
  advanced disclosure; conflict error flash with preserved values and
  diagnostic reference ID; keyboard focus/Space toggling; a corrected
  resubmission that creates the key; no-JS fallback create with the plain
  owner input.
- Stage-2 functional GUI smoke (TestClient, mocked provider/email):
  **12 cases passed** (ordinary-key regression; OpenCode-Chat pin
  `opencode-1.19.3-chat-v1 v1`; Hermes pin `hermes-0.22.5-chat-v1 v2`;
  chat-family conflict 400 pre-effects; Codex preset pin
  `codex-0.162-responses-v1 v8` under the packaged default;
  responses-family conflict; missing-route fail-closed; OpenCode-Responses
  pin `opencode-1.19.3-responses-v1 v1` with all four capabilities;
  advanced + client-use conflict; legacy `qwen_codex` regression; combined
  chat + responses on one provider).
- `ruff check` on all changed source and test files: **All checks passed**.
  (`ruff format --check` drift in `api/admin.py` is pre-existing at the
  base HEAD; CI runs `ruff check`.)
- `git diff --check`: clean.
- Not run: no real provider traffic, no real email, no production DB, no
  full 128-worker harness; CI workflow results are reported by the OAP
  publication record, not claimed here.

## Limitations

- The browser smoke exercises ONE synthetic scenario (one owner, one
  provider, one route) per state; it is form-level proof, not a full admin
  UX audit.
- Key templates, batch import, and clone intentionally keep their frozen /
  raw-metadata behavior (findings 4–5); the client-use presets exist only
  on the interactive create form.
- No existing-key migration: keys created with explicit pins keep those
  pins; a pin that no longer matches the installed DATA fails closed at
  request time instead of being silently rewritten. Operators migrate
  deliberately through the audited CLI workflow, as before.
- Document (configuration-JSON) mode and client-use are mutually exclusive
  by server rule; the client-side script does not uncheck the historical
  Codex boxes in document mode (finding 6) — the server boundary is the
  guarantee.
- Historical records (including 228-c OpenCode Responses qualification and
  the accepted 227 Hermes/OpenCode Chat native loops) are preserved as
  dated evidence and are not relabeled current by this change.
