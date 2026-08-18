# OAP Coding-Agent Report — 010-a

## Work order

- Identifier: `010-a`
- Work-order file:
  `oap/orders/010-a-codex-model-catalog-profile-admin-capability.md`
- Numeric objective: `010`
- PR mode: `CREATED_NEW_PR`

## Status

BLOCKED

## Executive summary

Objective 010-a stopped at its explicit fail-fast boundary before product
implementation. The mandatory rendered configuration contains an inline legacy
`[profiles.slaif]` table and instructs users to run `codex --profile slaif`.
Pinned Codex CLI 0.147.0 rejects that exact combination before model/provider
loading and requires profile-v2 settings in the separate user-level file
`$CODEX_HOME/slaif.config.toml`.

This is not a catalog-decoding failure, qualification-policy failure, or test
failure. It is an internal work-order contract conflict confirmed by current
official OpenAI documentation, the pinned source, the pinned binary help, and a
credential-free private temporary-`CODEX_HOME` diagnostic. Implementing the
specified renderer would knowingly publish a profile that cannot load; changing
it to the separate-file layout would violate the order's fixed rendered snippet
and output contract. No replacement catalog, credential, product code,
documentation, admin flow, key behavior, database state, or user/repository
Codex configuration was created or changed.

The activated pointer and unchanged order were published on the required new
PR. All 17 bounded local governance/documentation tests and all ten
implementation-head GitHub checks passed. The strategic model must issue a
narrow 010 continuation that deliberately replaces or clarifies the obsolete
profile-layout contract before implementation can proceed.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Starting remote `main`: `250ee751cffb8cc7632aaa793385eaa498ed6d08`
- Implementation head SHA: `2dada60375bc341fd113e64cb2f5b7801aadcacd`
- Implementation commit first parent:
  `250ee751cffb8cc7632aaa793385eaa498ed6d08`
- Implementation commit message:
  `OAP 010-a: publish blocked profile contract`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `235`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/235`
- PR title: `[OAP 010] Manage Codex qualification and user profiles`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE` / `CLEAN`
- Base branch: `main`
- Head branch: `oap/010-codex-model-catalog-profile-admin-capability`
- Objective-010 PR count: exactly one, PR #235
- Created a new PR this turn: YES
- Amended an existing PR this turn: NO
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Reconciliation and blocker evidence

### Official configuration contract

The OpenAI Codex configuration reference and advanced-configuration guide were
checked before implementation:

- `https://developers.openai.com/codex/config-reference`
- `https://developers.openai.com/codex/config-advanced`

They document profile v2: `--profile name` loads
`$CODEX_HOME/name.config.toml`; since Codex 0.134, legacy
`[profiles.<name>]` tables in `config.toml` are no longer read as named
profiles. They also confirm that provider/auth selection remains user-level
configuration. The OpenAI documentation skill materially prevented publishing
the obsolete fixed snippet as a purportedly working profile.

### Pinned source and binary

- `/usr/bin/codex --version`: PASSED — `codex-cli 0.147.0`.
- `/usr/bin/codex` SHA-256:
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`.
- Pinned source checkout:
  `/tmp/slaif-oap005-codex-source-YSOVKH`.
- Pinned source HEAD/tag: `be6e8eac029b183056b7e4402879f15d2c85f61b` /
  `rust-v0.147.0`; checkout status was clean.
- `/usr/bin/codex --help` identifies `--profile` as
  `CONFIG_PROFILE_V2` and says it layers
  `$CODEX_HOME/<name>.config.toml` over the base user configuration.
- `codex-rs/config/src/loader/mod.rs` explicitly rejects a selected profile
  when base `config.toml` contains matching legacy `profile = "name"` or
  `[profiles.name]` configuration and directs the settings to
  `name.config.toml`.
- `codex-rs/protocol/src/config_types.rs`,
  `codex-rs/utils/cli/src/shared_options.rs`, and
  `codex-rs/core/src/config/mod.rs` independently encode the same profile-v2
  path semantics.

### Credential-free diagnostic

A private temporary directory
`/tmp/slaif-oap010-profile-check-Ze39T1hr` was used only as an isolated
diagnostic `CODEX_HOME`. Its base `config.toml` contained the order's exact
mandatory provider/profile structure, with numeric loopback base URL
`http://127.0.0.1:1/v1`; the child environment supplied only a fixed dummy
`OPENAI_API_KEY`. No real key, provider, gateway, or non-loopback endpoint was
used.

The decisive command was:

```text
CODEX_HOME=/tmp/slaif-oap010-profile-check-Ze39T1hr \
OPENAI_API_KEY=<fixed-dummy> \
/usr/bin/codex -p slaif sandbox linux -- /bin/true
```

It exited 1 before network or model/provider loading with the safe error:

```text
Error: --profile `slaif` cannot be used while /tmp/slaif-oap010-profile-check-Ze39T1hr/config.toml contains legacy `profile = "slaif"` or `[profiles.slaif]` config; move those settings into /tmp/slaif-oap010-profile-check-Ze39T1hr/slaif.config.toml and remove the legacy profile selector/table. See https://developers.openai.com/codex/config-advanced#profiles for more information.
```

It also emitted a safe warning refusing PATH aliases under the temporary
directory. It printed/persisted no request/response payload, prompt,
completion, tool content, real key, or provider secret and made no network
request.

One earlier diagnostic attempt used
`codex -p slaif debug models --bundled`; it exited 1 because that debug
subcommand does not accept/apply the runtime profile option in that position.
It printed no catalog contents or raw payload, made no network request, and
changed no repository state. The runtime `sandbox` diagnostic above then
confirmed the actual profile-load rejection.

## Acceptance-criteria disposition

1. Strict route-pair/provider/pricing qualification: NOT IMPLEMENTED — blocked
   before product edits by the mandatory profile-load contract.
2. Deterministic credential-free CLI inspect/profile: NOT IMPLEMENTED — the
   required profile output is rejected by the pinned client.
3. Exact Codex 0.147.0 profile load: BLOCKED — the required inline legacy
   `[profiles.slaif]` table is rejected before provider/model loading. No
   replacement catalog was created and no credential was required.
4. Admin qualification views: NOT IMPLEMENTED — downstream of the blocked
   qualification/profile contract.
5. Admin protocol-pilot key preset: NOT IMPLEMENTED — readiness could not be
   proved under the required profile contract, so no key mutation path was
   added or exercised.
6. Ordinary key creation and `/v1/models`: UNCHANGED — no product code changed;
   no Codex metadata or secret can newly leak.
7. Focused verification: PASSED for the applicable governance, topology,
   fixture, privacy, and GitHub checks. Product-focused tests, renderer checks,
   and the final manual verifier were NOT RUN because no compliant
   implementation exists.
8. GitHub/report safety: PASSED for coding-agent-controlled behavior — exactly
   one new non-draft objective PR, no merge/auto-merge, and SELF topology.

## Changes and exact paths

The implementation commit changes exactly the two unchanged strategic inputs:

- `oap/active`
- `oap/orders/010-a-codex-model-catalog-profile-admin-capability.md`

The active pointer is exactly `010-a`; exactly one matching order exists; no
report existed before this publication. No product, test, documentation,
fixture, capture, verifier, CI, deployment, dependency, schema, migration,
provider, policy, accounting, HMAC, admin, CLI, or template path changed.

The final report-publication commit adds only:

- `oap/reports/010-a-codex-model-catalog-profile-admin-capability.md`

## Local verification

- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`:
  PASSED — 17 tests, zero failures/errors/skips.
- `git diff --check`: PASSED.
- Exact branch, starting HEAD, active pointer, one matching order, no
  preexisting report, and exact two-path implementation status/staging/commit:
  PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`:
  PASSED —
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
- Exact pinned binary/source checks and credential-free diagnostic: completed
  as recorded above.
- New qualification, CLI, admin/catalog/models, template, and public-model
  unit tests: NOT RUN — no compliant implementation was created.
- Scoped Ruff and compile checks: NOT RUN — no Python code changed.
- Manual `scripts/verify_codex_profile.py`: NOT CREATED / NOT RUN — the pinned
  client rejects the mandatory profile structure before a conforming verifier
  can exist.
- Local Playwright browser smoke: NOT RUN — blocked before UI implementation;
  GitHub's unchanged broad browser check passed.
- Full local unit suite: NOT RUN — prohibited by the active order.
- Integration and PostgreSQL suites: NOT RUN — prohibited by the active order.
- Local E2E, browser matrix, Docker/Compose, and HPC suites: NOT RUN —
  prohibited by the active order.
- Real upstream provider/tool/gateway smoke: NOT RUN — prohibited; no real key
  or non-loopback request was used.

## GitHub CI / checks

All ten checks completed successfully for implementation head
`2dada60375bc341fd113e64cb2f5b7801aadcacd`, observed after exact 30-second
wait blocks:

- `Analyze (javascript-typescript)`: SUCCESS — 47s.
- `Analyze (python)`: SUCCESS — 1m51s.
- `Analyze Python`: SUCCESS — 1m11s.
- `CodeQL`: SUCCESS — 3s.
- `Docker Compose smoke`: SUCCESS — 59s.
- `Documentation hygiene`: SUCCESS — 7s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m24s.
- `Playwright browser smoke`: SUCCESS — 1m21s.
- `PostgreSQL integration tests`: SUCCESS — 1m58s.
- `Unit, lint, and migration head`: SUCCESS — 2m05s.
- All implementation-head checks green at report drafting: YES.
- Fresh report-head checks may run after SELF publication and are not
  represented as implementation-head evidence.

## Documentation impact

Documentation checked, no update needed because the pinned profile contract
blocked implementation before repository behavior changed. No product or
support claim changed.

## Local setup / dependencies

- Packages/tools/services installed or configured: NONE.
- `sudo`-level setup performed: NONE.
- Durable setup changes committed/documented: NONE.
- Private temporary diagnostic state was credential-free, outside the
  repository, and did not modify user or project Codex configuration.

## Safety, privacy, and scope confirmations

- Unrelated files changed: NO.
- Product files changed: NO.
- Production secrets accessed: NO.
- Production systems accessed: NO.
- Real provider/gateway or side-effecting external tool called: NO.
- Gateway/admin key created or mutated: NO.
- User `~/.codex` or repository `.codex` accessed or modified: NO.
- Replacement/partial model catalog created: NO.
- Raw model catalog, instructions, request, response, prompt, completion, body,
  tool payload, API key, provider key, gateway key, or arbitrary pricing data
  printed, persisted, or committed: NO.
- Required product tests skipped: BLOCKED before applicability; all omissions
  are listed explicitly above.
- Scope deviation or contract weakening: NO.
- Extra objective-010 PR created: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO; exact strategic
  bytes were committed unchanged.
- `.local-provider-catalog/` accessed, modified, staged, or committed: NO.
- Report-publication commit changes only this report: YES, verified before the
  FIFO response.

## Blocker and recommended strategic continuation

The blocker is exact: the active order requires the renderer to include legacy
`[profiles.slaif]` and `[profiles.slaif.features]` tables in the printed base
snippet while requiring users and the verifier to select `--profile slaif`.
Pinned Codex 0.147.0 rejects that base configuration and requires
`$CODEX_HOME/slaif.config.toml`. The order simultaneously fixes the rendered
snippet/output behavior, so the coding agent cannot independently substitute a
two-file profile-v2 contract.

The strategic model should activate a narrow 010 continuation that explicitly
defines the current two-file user-level layout: base `config.toml` for
`[model_providers.slaif]`, plus `slaif.config.toml` with top-level `model`,
`model_provider`, and feature settings. The continuation must deliberately
re-scope CLI output/JSON, file-free rendering, installation instructions, and
the manual verifier around that profile-v2 contract before route readiness or
the admin pilot-key preset is implemented. The coding agent makes no
continuation, acceptance, or merge decision.

## Final safety statement

This turn created only PR #235, truthfully published the fail-fast BLOCKED
result, preserved immutable report topology, and performed no merge or
auto-merge action. Coding-agent `OK` after remote SELF verification means only
that this execution turn, immutable report, and claimed GitHub state are
published; it does not mean the work is accepted.
