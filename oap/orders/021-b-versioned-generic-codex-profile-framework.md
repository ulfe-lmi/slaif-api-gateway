# OAP Work Order — 021-b

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Finish Objective 021 on existing PR #247. The 021-a framework preserves the
legacy profile and is green, but strategic review found that future profiles
would still be ranked and reported through module-global GPT/OpenAI constants,
provider kind is not verified, optional model-catalog rendering has no required
synthetic proof, the admin ready copy is pinned to the legacy model, and two
review threads remain unresolved. Correct these framework defects before any
Qwen profile is introduced.

Do not repeat broad reconnaissance. Read this order, the current 021-a diff,
the two live review threads, and only concrete symbols/tests needed for the
fixes. Implement in focused slices.

## Verified continuation state

- `main` remains `5c7bf45e3f1b7f5bd9fa45e4b07820bf801d945c`.
- Existing ready PR #247 is `[OAP 021] Add versioned Codex qualification
  profiles`, base `main`, branch
  `oap/021-versioned-generic-codex-profile-framework`.
- Remote/report head is
  `179ef4d5f8ca8a4b61ace2186dde1c58213621db`; its first parent is implementation
  head `d1954057a0487e06026d1c91508462ecb18d1945` and the report commit changes only
  `oap/reports/021-a-versioned-generic-codex-profile-framework.md`.
- All ten checks are green, but green CI does not cover the findings below.
- Unresolved review threads identify unused `_REQUIRED_FIELDS` and a redundant
  `compatible_ids` assignment. Resolve both by code/tests, not dismissal.
- `oap/active` is now `021-b`. Do not create another PR, merge, or enable
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
oap/orders/021-b-versioned-generic-codex-profile-framework.md
oap/reports/021-b-versioned-generic-codex-profile-framework.md
```

One exact adjacent focused test path is allowed only if a changed concrete
symbol requires it and must be reported. No schema migration or request-runtime
widening is authorized.

## Required corrections

### 1. Remove legacy constants from generic qualification paths

- Runtime route selection must match/rank against the resolved profile's
  `public_model`, not `CODEX_MODEL`. Pass the resolved profile/model explicitly
  through selection helpers, including paired-route selection.
- Qualification results for version 2 must populate CLI version, evidence
  profile/catalog source, wire API, provider display/identity, live-provider
  evidence, profile ID, metadata version, and badge inputs from the resolved
  registry profile. Preserve every legacy version-1 result and default renderer
  byte exactly.
- Provider readiness must validate the enabled provider row's exact `kind`
  against `profile.provider_kind`; when `provider_slug` is set it must also
  match exactly. A same-name row with the wrong kind fails with a fixed bounded
  reason code.
- Add a synthetic non-OpenAI, non-`gpt-5.6-sol`, single-Responses-endpoint
  profile test that proves correct model ranking, provider-kind validation,
  no compact-pair requirement for client-local compaction, and profile-derived
  safe result fields. Do not register or qualify Qwen in production.

### 2. Make registry definitions actually fail closed

- Remove the unused `_REQUIRED_FIELDS` artifact or use a real complete
  validation path; do not retain dead validation theatre.
- At construction/registry validation, reject malformed or unsafe values for
  every profile field that later affects qualification or artifact rendering:
  safe bounded IDs/names/versions, supported wire API/compaction mode/provider
  kind, unique canonical endpoints/gates/local-tool types, strict booleans,
  positive coherent numeric limits, exact SHA-256/date, safe provider fields,
  and coherent optional catalog artifact/target pairs.
- Deep immutability or primitive-only validation must prevent mutable nested
  values from surviving inside frozen definitions.
- A caller-supplied `CodexQualificationProfile` object must not become a
  selectable ready CLI/admin profile unless it is the exact registered
  definition. Synthetic artifact tests may use a separate pure renderer/helper,
  but runtime/CLI selection remains registry-owned.

### 3. Prove deterministic, credential-free optional catalog artifacts

- Add the acceptance test omitted by 021-a: render a safe unregistered
  synthetic profile through a pure artifact-rendering path with deterministic
  canonical model-catalog JSON and an explicit safe relative target filename.
  This is test evidence only and must not make the synthetic profile selectable
  or qualified.
- Reject mismatched artifact/target pairs, absolute/traversal targets,
  non-canonical JSON, secret-looking values, URLs/backend addresses, arbitrary
  prompt/output/tool/reasoning content, and mutable catalog content. The public
  CLI/admin path must emit only registry-owned ready artifacts and must keep the
  upstream/LAN URL and provider secret env-var absent.
- Preserve `render_codex_profile(base_url)` and its legacy text/JSON output
  byte-for-byte.

### 4. Strengthen sanitized fixture structure

- Replace distinct encountered opaque IDs with stable first-seen placeholders
  (`ID_1`, `ID_2`, ...) so relationships/order are retained without raw IDs.
- Bound total nodes/IDs as well as depth and list cardinality. Accept only the
  finite structural key/value vocabulary; an input `digest` must not grant or
  override the computed digest.
- Reject secret-looking or content-like string values even when they contain no
  spaces (for example key/token canaries). Add privacy negatives proving raw
  prompt/output/tool schema/arguments/results/reasoning, URLs, headers,
  credentials, environment/workspace paths, and arbitrary metadata cannot
  survive.

### 5. Finish safe admin presentation

- Populate admin DTO profile ID/version and all displayed ready facts from the
  already resolved `CodexQualificationResult`, not by independently blessing a
  merely well-formed route declaration.
- Remove the hard-coded `Codex 0.147.0 / gpt-5.6-sol` ready paragraph for v2;
  display only escaped profile-derived safe facts. Preserve the exact legacy-v1
  wording when applicable.
- Complete the activated 021 requirement for admin artifact display/download:
  expose deterministic credential-free artifacts only when the route is
  actually ready and the profile is the exact registered definition. Require
  an explicit validated gateway `/v1` base URL if public origin cannot be
  safely inferred; never use/display the upstream provider base URL as a Codex
  gateway URL. Non-ready/unknown/drifted routes expose no artifacts. Keep CSRF,
  escaping, and no-write behavior intact.

### 6. Review cleanup

- Correct both current review findings, push the implementation, then resolve
  the threads only after their code is obsolete/fixed. Check for any new
  threads on the final head.

## Non-goals

No Qwen/vLLM profile, Codex 0.148 capture/live run, real network/provider/LAN,
pilot-key generalization, schema migration, new request/event/tool acceptance,
hosted tools, remote images, production/release claim, or broad local suite.

## Acceptance and focused verification

1. A synthetic generic profile proves non-GPT route selection, exact provider
   kind, single Responses endpoint, client-local compaction, and profile-derived
   result/artifact fields while remaining unregistered and unselectable.
2. Legacy v1 qualification, pilot behavior, default profile bytes, CLI output,
   verifier digest, and admin wording remain unchanged.
3. Malformed registry definitions, unknown/drifted declarations, wrong provider
   kind, mutable/unsafe catalog data, unsafe fixture strings, and non-ready
   admin artifact access all fail closed with bounded safe output.
4. Safe catalog and fixture outputs are deterministic and contain no secret,
   URL, backend, prompt/output/tool/reasoning, or arbitrary metadata canary.
5. Run the focused registry/qualification/CLI/admin/template tests, scoped
   Ruff, compileall, Jinja parse if changed, `git diff --check`, and routine
   GitHub CI. Do not run the full local suite.
6. Every required final-report-head check passes and all review threads are
   resolved before strategic merge consideration.

## Publication

Amend PR #247 only. Commit implementation, then publish exactly one immutable
`oap/reports/021-b-versioned-generic-codex-profile-framework.md` report-only
final commit with the literal implementation head and
`Report publication commit: SELF`. Report the exact focused commands/results,
legacy byte-compatibility evidence, synthetic generic profile evidence, admin
artifact negative/positive evidence, privacy negatives, review-thread state,
and GitHub checks. Verify remote head, send exact response-FIFO `OK`, and return
to one control wait. Never merge.
