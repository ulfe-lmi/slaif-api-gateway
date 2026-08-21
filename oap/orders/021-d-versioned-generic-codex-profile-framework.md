# OAP Work Order — 021-d

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Correct four exact framework defects on PR #247 before merge. Do not redesign
or broaden Objective 021. Strategic final review found that 021-c encoded an
invented image gate, an invented catalog top-level schema, an invalid TOML
table for Codex's root `model_catalog_json` key, and a legacy-hard-coded human
target line for generic profiles.

Start implementation immediately after reading this order and the named
symbols/tests. Do not repeat reconnaissance, run Codex, access a network, or run
a broad local suite.

## Verified continuation state

- `main` remains `5c7bf45e3f1b7f5bd9fa45e4b07820bf801d945c`.
- PR #247 is the unique ready Objective 021 PR on
  `oap/021-versioned-generic-codex-profile-framework`.
- Remote/report head is
  `7c853e4b02443861d0a3e22b2627ced0c7286477`; first parent implementation is
  `60534765e4bd20419833b025bd0b3f6c2e730e25`; the report commit changes only
  `oap/reports/021-c-versioned-generic-codex-profile-framework.md`.
- All ten checks pass; both historical review threads are resolved/outdated.
- Read-only strategic inspection of installed `codex-cli 0.148.0` already
  established that bundled catalog JSON has exact root shape `{"models":[...]}`
  and the config override is the root key `model_catalog_json`. Do not rerun
  Codex in this objective.
- The gateway's authoritative Responses capability constant is
  `RESPONSES_CAPABILITY_IMAGE_INPUT = "image_input"` in
  `responses_route_capabilities.py`; `responses_image_input` is not a route key.
- `oap/active` is `021-d`. Amend only PR #247; never merge or auto-merge.

## Allowed paths

```text
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/codex_qualification.py
tests/unit/test_codex_profile_registry.py
tests/unit/test_codex_qualification.py
tests/unit/test_cli_codex.py
docs/codex-compatibility.md
oap/active
oap/orders/021-d-versioned-generic-codex-profile-framework.md
oap/reports/021-d-versioned-generic-codex-profile-framework.md
```

Import the existing image capability constant rather than duplicating another
string if that does not create a cycle. No admin/schema/template change is
needed unless a focused test proves otherwise.

## Required corrections

1. Use the exact route capability key `image_input` for profile coherence and
   qualification. A vision profile requires it true; a text-only profile
   requires it absent/false. Pass the image request fact through the existing
   runtime capability enforcer so the same authoritative parser approves the
   claimed vision operation. Remove every production/test use of the invented
   `responses_image_input` key.
2. Validate replacement catalogs with exact Codex root shape
   `{"models":[one exact model entry]}`. Remove invented root
   `schema_version`, `context_window`, `auto_compact_token_limit`, and
   `input_modalities`. Require the one model entry itself to contain exact
   `slug`, `context_window`, `auto_compact_token_limit`, and
   `input_modalities` matching the profile; retain the finite safe optional
   field schema and all privacy/size/canonical-JSON checks.
3. Render `model_catalog_json` as a root key in the complete named TOML, before
   any `[features]` table. Do not emit a `[model_catalog]` table. Parse the
   generated TOML in a test and assert the root value and features table are
   exactly where intended. Legacy default TOML still omits the key and remains
   byte-for-byte unchanged.
4. `render_codex_profile_text()` must use
   `artifacts.profile_config_target` for the “Place this complete content” line.
   Because the legacy artifact target is still
   `$CODEX_HOME/slaif.config.toml`, legacy output remains byte-identical; two
   generic profiles must show their distinct targets rather than the legacy
   target. Continue printing the explicit catalog target consistently.

## Non-goals

No registry entry, Qwen/vLLM/Codex run, capture, live/network call, path
resolution redesign, admin change, request-policy widening, migration, or full
local suite.

## Acceptance and focused verification

- Synthetic text and vision profiles qualify/fail on the real `image_input`
  field and the authoritative runtime parser; no invented field remains.
- Synthetic 150000/125000 catalog has only `models` at root and exact matching
  model-entry facts; invented/unknown root fields fail.
- `tomllib.loads()` proves replacement `model_catalog_json` is at root and
  `features.remote_compaction_v2` is false; legacy output remains exact.
- Generic human text shows its profile-specific target; legacy text remains
  unchanged.
- Run only focused registry/qualification/CLI tests, scoped Ruff, compileall,
  `git diff --check`, and routine GitHub CI. Do not run the full local suite.

## Publication

Amend PR #247. Commit implementation, then publish exactly one immutable
`oap/reports/021-d-versioned-generic-codex-profile-framework.md` report-only
final commit with literal implementation head and
`Report publication commit: SELF`. Report exact focused results, legacy byte
evidence, image capability/parser evidence, parsed TOML/catalog shape, review
threads, and final-head checks. Verify remote head, signal exact response-FIFO
`OK`, and return to one control wait. Never merge.
