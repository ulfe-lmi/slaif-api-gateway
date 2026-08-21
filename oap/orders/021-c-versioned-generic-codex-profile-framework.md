# OAP Work Order — 021-c

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Complete the Objective 021 framework on PR #247 so Objective 022 can add the
approved Codex 0.148/Qwen text profile without redesigning or silently emitting
the wrong configuration. Strategic review of 021-b found four concrete blockers:
client-local compaction renders `remote_compaction_v2=true`; the model-catalog
validator rejects legitimate safe Codex tool metadata while allowing arbitrary
unknown fields; generic artifacts remain targeted at `slaif.config.toml` and do
not reference their replacement catalog; and admin wording discards the
profile's live-E2E fact. The fixture helper also still accepts arbitrary
single-token strings rather than a finite caller-supplied structural vocabulary.

Do not repeat broad discovery. Read this order, the current 021 diff, the
existing safe catalog vocabulary in `scripts/capture_codex_protocol.py`, and
only concrete renderer/config tests required. Do not run Codex, capture traffic,
or call a network/backend in this objective.

## Verified continuation state

- `main` is `5c7bf45e3f1b7f5bd9fa45e4b07820bf801d945c`.
- PR #247 remains the unique ready Objective 021 PR, base `main`, branch
  `oap/021-versioned-generic-codex-profile-framework`.
- Remote/report head is
  `6b471beebb6f0f816a8550493d71bb3c7f2768bb`; its first parent is implementation
  head `444361422f38b7660e24425a16ddb4af57b7016f`, and its report commit changes only
  `oap/reports/021-b-versioned-generic-codex-profile-framework.md`.
- All ten final-head checks pass. The two prior review threads are resolved and
  outdated; there are no other review threads.
- `oap/active` is now `021-c`. Amend PR #247 only; never merge or enable
  auto-merge.

## Allowed paths

Use the smallest necessary subset of:

```text
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/services/admin_catalog_dashboard.py
app/slaif_gateway/schemas/admin_catalog.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/web/templates/routes/detail.html
tests/unit/test_codex_profile_registry.py
tests/unit/test_codex_qualification.py
tests/unit/test_cli_codex.py
tests/unit/test_admin_catalog_routes.py
tests/unit/test_admin_catalog_templates_safety.py
docs/codex-compatibility.md
docs/compatibility-matrix.md
oap/active
oap/orders/021-c-versioned-generic-codex-profile-framework.md
oap/reports/021-c-versioned-generic-codex-profile-framework.md
```

`scripts/capture_codex_protocol.py` is a read-only vocabulary reference in this
round; do not change it. One exact adjacent focused test path is allowed only if
a changed symbol requires it and must be reported. No migration or runtime
request-policy widening.

## Required corrections

### 1. Represent the approved future profiles exactly

- Extend the frozen profile definition with exact input modalities and an
  optional client-local auto-compaction token threshold. Preserve the built-in
  OpenAI profile's existing facts/output exactly.
- Supported modalities are the finite set `text` and optional `image`, unique
  and non-empty. For a future single-endpoint `client_local` profile, require a
  positive auto-compaction threshold strictly below its context window and no
  remote compact endpoint/gate. For `none`, require no threshold and no remote
  compact endpoint/gate. For `remote_v1`, require the exact Responses/compact
  pair and `codex_compaction`; it must not imply remote V2.
- Restrict route gates to the finite runtime-supported Responses/Codex gate
  vocabulary, including exact image input when claimed. Reject incoherent
  reasoning/streaming/local-tool/modalities/compaction claims at profile
  construction. Do not accept a nominal `chat` Codex profile: this roadmap has
  no Chat-to-Responses translation.
- Qualification must require `responses.image_input=true` for an image profile
  and must not qualify a text-only profile whose declared route enables generic
  image input. Keep the legacy v1 path byte/behavior compatible.

### 2. Make replacement catalog validation finite and usable

- Replace substring-based catalog validation with an explicit, bounded schema
  derived from the already committed safe catalog vocabulary in
  `scripts/capture_codex_protocol.py`. The safe schema may admit structural
  tool-related fields such as shell/apply-patch/tool-mode booleans/enums; it
  must reject unknown keys and all free-text instruction/description/message/
  migration fields.
- Require exact top-level catalog structure, bounded total nodes/list sizes/
  string lengths, one exact model entry for `profile.public_model`, canonical
  JSON, finite numbers, strict booleans, allowlisted enum values, and catalog
  context/auto-compaction/modalities facts equal to the profile definition.
- Make `catalog_source` coherent: bundled means no replacement artifact/target;
  replacement means both are present, safe, and validated. The synthetic proof
  must use `catalog_source=replacement` and a realistic safe Codex catalog
  shape, not the current placeholder `{models:[{id:...}]}`.
- Continue excluding credentials, API/backend/gateway URLs, env vars, headers,
  prompts, outputs, arbitrary instructions, tool schemas/arguments/results,
  reasoning/encrypted content, and mutable nested data.

### 3. Render a usable, profile-specific artifact bundle

- Preserve `render_codex_profile(base_url)` and the complete legacy text/JSON
  output byte-for-byte, including legacy targets and omission of
  `model_catalog_json`.
- For a non-legacy registered replacement profile, use a safe profile-specific
  provider alias and profile filename; do not overwrite
  `$CODEX_HOME/slaif.config.toml` when text and vision profiles coexist.
- The complete named profile must reference the exact replacement
  `model_catalog_json` target, and the bundle/text/JSON/admin output must expose
  a matching explicit target for the catalog file. Keep ordering/newlines/TOML
  quoting deterministic and injection-safe. If an operator path substitution
  is unavoidable until live Objective 022 proves Codex path resolution, label
  it explicitly and consistently rather than emitting a silently unusable
  path.
- `client_local`, `none`, and `remote_v1` must all render
  `remote_compaction_v2=false`; no profile may render true until a separately
  represented and qualified remote-V2 mode exists.
- Add exact tests for the future shape: two different synthetic replacement
  profile names produce distinct targets, the profile references its catalog,
  150000 context/125000 threshold survive the safe catalog, upstream/LAN URL
  and provider env-var do not, and public selection still rejects unregistered
  objects.

### 4. Make fixture strings truly structural

- Require an explicit immutable finite allowed-type vocabulary (argument or
  equivalent server-owned contract) for retained `event_type`, `field_type`,
  and `tool_type` strings. Unknown single tokens such as a prompt/output canary
  must fail even when they contain no spaces or obvious secret marker.
- Enforce key-specific types: counts/indexes are bounded non-negative integers,
  enabled is a strict boolean, IDs are placeholder-mapped, and type values come
  only from the supplied vocabulary. Preserve deterministic ordering,
  placeholders, total-node/ID bounds, and computed digest.
- Add positives for a small finite structural vocabulary and negatives for
  arbitrary one-word content, wrong scalar types, and prior privacy classes.

### 5. Preserve live qualification truth in admin

- Carry the resolved result's `real_provider_e2e`/live qualification fact into
  the admin DTO. For v2, render an escaped explicit `qualified` versus
  `not claimed` live-E2E label from that fact; do not always state that live E2E
  is absent. Preserve the exact legacy-v1 paragraph.
- Artifact display/download remains ready+registered-only and continues using
  validated `PUBLIC_BASE_URL`, never the provider base URL.

## Non-goals

No production Qwen/vLLM registry entry, Codex process/capture, live/network/LAN
run, request/event/tool runtime widening, pilot-key generalization, schema
migration, hosted tools, remote images, release/production claim, or full local
suite.

## Acceptance and focused verification

1. The built-in legacy profile, v1 qualification, default renderer bytes, CLI
   text/JSON, pilot behavior, and verifier digest remain exact.
2. A synthetic 150000/125000 client-local replacement profile yields a
   profile-specific, catalog-referencing, credential-free bundle with remote V2
   false, while malformed/incoherent catalogs/profiles fail at construction.
3. Text-only versus image route capability mismatches fail closed; the safe
   generic single-endpoint test remains protocol-qualified only with matching
   provider/model/kind/limits/modalities.
4. Arbitrary fixture strings and wrong types fail; allowed structural types and
   ID relationships produce a deterministic digest without raw content.
5. Admin v2 distinguishes live-qualified true/false and serves artifacts only
   for the exact ready registered profile; legacy wording is unchanged.
6. Run focused registry/qualification/CLI/admin/template/verifier/docs tests,
   scoped Ruff, compileall, Jinja parse if changed, `git diff --check`, and
   routine GitHub CI. Do not run the full local suite.

## Publication

Amend PR #247 only. Commit implementation, then publish exactly one immutable
`oap/reports/021-c-versioned-generic-codex-profile-framework.md` report-only
final commit with literal implementation head and
`Report publication commit: SELF`. Report exact focused commands/results,
legacy byte evidence, realistic synthetic catalog/artifact evidence,
compaction/modalities/fixture/admin negatives, review-thread state, and GitHub
checks. Verify remote head, send exact response-FIFO `OK`, and return to one
control wait. Never merge.
