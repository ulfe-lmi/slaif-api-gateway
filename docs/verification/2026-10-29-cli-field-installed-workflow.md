# 205-a verification record — installed CLI field administration workflows

**Status: PARTIAL (205-a scope-boundary handoff).** This record documents what
was actually executed through the installed `slaif-gateway` console for work
order `oap/orders/205-a-cli-field-workflow-qualification.md` (unique PR for
objective 205; same-PR 205-b continuation reserved by root). Outcomes 5,
7, 8, 9, 10, 11 and the runtime-configuration evidence are NOT yet executed
and remain mandatory for the final 205 PR. Nothing below claims them.

## Installation and identity (executed)

- Source: accepted objective-204 merge commit
  `5e59a023154bfebc998ef4e0a7089a3151fda0e2` (remote `main` at qualification
  time), pinned shallow-safely in an owned pristine archive.
- Wheel: `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual selected
  SHA256 `5c5bbdb405c7b84f4434a3cfc28f6c15cae2c4947f61d32540149e61b3f6ec55`
  (built from that exact source in the setup slice; the fixture records the
  ACTUAL selected wheel SHA, not a manual ZIP hash, and re-verifies the
  payload for any reuse or fresh build).
- Owned venv: `/tmp/slaif205/venv2` (Python 3.12.15); console
  `/tmp/slaif205/venv2/bin/slaif-gateway`; package resolves to
  `/tmp/slaif205/venv2/lib/python3.12/site-packages/slaif_gateway/__init__.py`.
  Installed payload file set verified exactly against the selected wheel
  payload. Root independently verified the installed package bytes against
  the accepted source (root evidence, not an agent run).
- Migrations: run from the pristine pinned source (the wheel does not ship
  migrations) to the `0026` head; the fixture asserts 33 public tables and
  the presence of `request_diagnostics` before seeding.
- Every operator action under test is a subprocess of the venv console from an
  owned operator directory OUTSIDE the checkout, with `PYTHONPATH` unset and
  inherited credentials scrubbed. DoD0 asserts the installed identity facts
  (console path, package path, Python version, wheel SHA, payload verification
  booleans) for every run.
- Owned PostgreSQL 16 container, unique per run: name `slaif205a-<RUN_TOKEN>`,
  labels `slaif205a.run=<RUN_TOKEN>` / `slaif205a.owner=uid<uid>` /
  `slaif205a.purpose=field-workflow-qualification` / `slaif205a.order=205-a`,
  loopback-only published port, 512 MiB tmpfs data directory. Ownership,
  labels, loopback binding, and tmpfs are inspected BEFORE migrations; only
  the exact owned container ID is removed in teardown after re-checking its
  label. Verified after the final run: no container with label
  `slaif205a.order=205-a` remains.
- Generated credentials (PG password, HMAC secret, one-time-secret encryption
  key, key secrets) are random, kept in memory or 0600 files, and
  substituted/masked in every retained projection; retained artifacts carry
  booleans/hashes only. No real OpenAI/OpenRouter backend, no real client,
  no real SMTP, no Redis anywhere in this record.

## IO substitutions (executed layer)

- SMTP: loopback synthetic sink (`127.0.0.1`, owned port) is armed in the
  fixture. The one-time key-delivery lifecycle (outcome 9) is NOT yet
  exercised against it by the module.
- Provider upstream: the test module contains DRAFT, not-yet-wired
  `ProviderMock` / `GatewayServer` helpers for outcomes 5–11; the current
  seed uses a fictional provider `base_url`
  (`https://openai-fixture.example.invalid/v1`) and NO gateway process is
  started. Outcomes 5, 7, 8, 10 therefore have no executed evidence here.

## Per-outcome evidence (order section 12, eleven outcomes)

Final module run (`205a-final2`, JUnit authoritative, 2026-10-29T13:55Z,
6 tests, 0 failures, 0 errors, 0 skipped, exit 0, 216.98 s) — the only run
whose test bytes equal the committed test file:

| # | Outcome (order title) | Status | Evidence |
|---|-----------------------|--------|----------|
| 1 | Identities: list/show by UUID/public-ID/exact owner email, complete bounded paging, full-bearer lookup refusal without echo | EXECUTED PASSED | `test_dod1_lookup_and_bounded_paging` |
| 2 | Effective policy + route explanation: configured vs inherited rate members/sources, unlimited quotas vs inherited operational limits, allow-list/enabled-route intersection | EXECUTED PASSED | `test_dod2_effective_policy_and_route_explanation` |
| 3 | Record operations: institution/owner/cohort create/list/show exactly once, normalized duplicate refusal, owner move preserving omitted fields/member key state, cohort edit omission/clear rules, bad UUID/no-reason/conflict negatives | EXECUTED PASSED | `test_dod3_record_operations` |
| 4 | Exact standard student/beta + TWO chat clones: dry-run plans, one secure channel per execute, canonical configuration parity (incl. nontrivial Codex/Responses pin), inherited members as inheritance, zero copied usage/ownership, source unchanged, exact-repeat dedup, stale/unknown-field refusals, deny-all providers distinct | EXECUTED PASSED | `test_dod4_exact_student_beta_and_chat_clones` |
| 5 | Discovery grant: `keys policy update` + real filtered `GET /v1/models` through the installed gateway | NOT EXECUTED | gateway not started; draft helper not wired (205-b) |
| 6 | Rates, bounded lazy configuration (within actual ceilings, overbound refusal, reject/clear), exact-37 cohort batch with stale refusal after new-member create, UUID re-review, exact 37 audits | EXECUTED PASSED | `test_dod6_rates_lazy_and_exact37_batch` |
| 7 | Two configured completion services via `providers add` (disabled, distinct origins/profiles/timeouts/zero retries) | NOT EXECUTED | 205-b |
| 8 | Explicit activation + stable route edit (`routes update` dry-run/execute, ceiling/media changes, stale-plan refusal) | NOT EXECUTED | 205-b |
| 9 | One-time delivery lifecycle: real send to loopback SMTP, consumption, repeat refusal, sent/failed/pending/expired/ambiguous inspection and safe retry semantics | NOT EXECUTED | SMTP sink armed, flow not yet in module (205-b) |
| 10 | Gateway-recorded failure investigations via installed `diagnostics request show` | NOT EXECUTED | no gateway process/diagnostics arming yet (205-b) |
| 11 | Reviewed replay maintenance via installed `codex replay inspect/extend` | NOT EXECUTED | 205-b |

Additional order requirement: `config show --json`/text with a valid
override/default/source/restart snapshot plus an invalid-Settings no-echo
probe — NOT EXECUTED in this module (205-b).

Qualification: these are installed-CLI workflow proofs on a fictional owned
fixture. They are not real-provider/client/backend qualification, not a
measured performance claim, and not evidence for the unexecuted outcomes.

## JUnit chronology (overlapping slice runs; never summed)

All runs: same module path, JUnit XML authoritative (repository addopts
suppress the console summary), zero skips in every run.

| Artifact (UTC 2026-10-29) | tests | failures | failing cases |
|---|---|---|---|
| `205a-slice1` 12:45 | 4 (DoD0–3) | 0 | — (first green slice) |
| `205a-slice2` 12:53 | 6 | 2 | DoD4, DoD6 |
| `205a-slice3` 13:04 | 6 | 2 | DoD4, DoD6 |
| `205a-slice4` 13:16 | 6 | 2 | DoD4, DoD6 |
| `205a-slice5` 13:21 | 6 | 2 | DoD4, DoD6 |
| `205a-slice6` 13:25 | 6 | 2 | DoD4, DoD6 |
| `205a-slice7` 13:32 | 6 | 2 | DoD4, DoD6 |
| `205a-slice8` 13:37 | 6 | 1 | DoD6 |
| `205a-slice9` 13:45 | 6 | 1 | DoD6 (stale-batch error-code oracle: installed boundary reports `key_batch_stale`, not generic `command_failed`) |
| `205a-final` 13:50 | 6 | 0 | — (post oracle fix) |
| `205a-final2` 13:55 | 6 | 0 | — (final byte-matched run; the only delta after `205a-final` was removal of one unused local assignment, non-behavioral hygiene) |

The intermediate failures are draft-iteration harness/oracle corrections in
the NEW test file (seed field fidelity, clone source fixtures, metadata
column names, error-code mapping, lazy stored-state assertions); each was
corrected in the test file and re-run. They are not product failures and are
not summed as unique cases.

## ROOT independent evidence (root runs, not agent runs)

Credited separately from the pytest evidence above:

- `205-qualification-baseline.json` — product/preserved-path baseline
  (466 product paths, 1724 existing non-allowed paths) deriving the accepted
  tree; cited by the order.
- `205-installed-lazy-numeric-canary-probe.json` — actual installed CLI
  probe: both `set-lazy-throttling` numeric flags echo a complete generated
  credential-shaped canary in usage stderr, exit 2 (boolean-only receipt).
- `205-installed-new-numeric-surface-canary-probe.json` — actual installed
  CLI probe: 17 argument positions across the SELECTED new/extended
  lookup/clone/lazy/provider/route/replay command families echo complete
  generated credential-shaped values, all exit 2 (boolean metadata only, no
  raw outputs). This is a bounded probe of the selected families, NOT a
  blanket legacy-CLI audit claim.
- `205-numeric-privacy-scope-decision.json` — root scope decision reserving a
  narrow 205-b numeric-parsing fix (preserving retry-0/offset-0/signed
  priority/None handling, existing validators, and all eleven outcomes) on
  the same 205 PR.
- Root-verified wheel/venv installation: 432 application files byte-identical
  to accepted source `5e59a02` (only 4 empty `.gitkeep` placeholders omitted),
  installed console at the owned venv path; root also enforced private
  creation for generated fixture credentials (final fixture asserts 0600).
- Root review aids: `/tmp/slaif205-root/early-installed-workflow-review.md`
  (fixture items 1–9) and `/tmp/slaif205-root/clone-batch-slice-review.md`
  (clone/batch slice corrections), plus the source command map
  `205-cli-command-planning-checkpoint-20261029.json`.

## Product scope boundary (deferred to same-PR 205-b)

The confirmed NEW CLI privacy gap — credential-shaped numeric input echoed
completely in `set-lazy-throttling` usage stderr before the command body
runs — requires product edits, which active 205-a explicitly does not
permit. It is reported, not fixed, in this handoff. The ordinary usage-error
law itself (native Typer `BadParameter` → exit 2, stderr, no JSON payload,
even with `--json`) is documented 197 behavior: the module asserts the fixed
refusal and unchanged state, and does NOT treat non-JSON usage output alone
as a defect or weaken actual bounds. No product, runtime, schema, migration,
settings/CI byte was changed under 205-a.

## Limitations

- No gateway process is started by the current fixture; outcomes 5, 7, 8,
  10, 11 and the config-show evidence have NO executed proof yet.
- The provider mock and gateway server helpers are drafted in the module but
  not wired into the fixture; the seed's provider `base_url` is fictional and
  never contacted.
- SMTP sink is armed but the one-time delivery lifecycle (outcome 9) is not
  yet exercised.
- The numeric-echo defect above is unresolved by design of this handoff.
- No merge, no tag/release, no real provider/client/mail, no Redis.
