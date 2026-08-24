# OAP report — 152-e main reconciliation and terminal merge candidate

- Objective: `152-e`
- Active selector: `152-e`
- PR: [#287](https://github.com/ulfe-lmi/slaif-api-gateway/pull/287)
- Branch: `oap/152-real-provider-accounting-qualification`
- Implementation head: `5e580f481f96076560f912ec96b2ee58a19ab902`
- Order/selector commit: `263adc1280639c623e2774fed83bfbbdeeaa6e13`
- Merge parent 1: `263adc1280639c623e2774fed83bfbbdeeaa6e13`
- Merge parent 2 (`origin/main`): `fa5423456ec21fadae066cb12960014ad00e1d8c`
- Resolved conflict: `docs/real-provider-qualification.md` only
- Report publication commit: SELF

## Outcome

Objective 152 implementation and verifier tooling are preserved and reconciled
with current `main`. The documentation now retains PR #288's current-truth
framing and the immutable 152-a through 152-d history:

- 152-a delivered the guarded exact-eight-flow verifier and deterministic fake
  HTTP/SQL tests without a provider call.
- 152-b hardened fresh-key isolation, bounded output, protected-file handling,
  and attempted-versus-correlated accounting without live execution.
- 152-c made one explicitly authorized live attempt. Its first OpenAI
  non-streaming Chat flow reached HTTP 200 and finalized one PostgreSQL
  reservation/ledger pair, then stopped with `correlation_metadata_invalid`.
  The other seven flows were not run; this is failed partial live evidence.
- 152-d fixed the verifier's asyncpg JSON/JSONB boundary with strict codecs and
  normalization. It used no provider, credential, HTTP request, or SQL
  connection.
- 152-e merged the exact current `origin/main`, preserved all prior activated
  commits and reports, and resolved the one documentation conflict.

No replacement eight-flow live matrix ran after the 152-d fix. Therefore
**real-provider accounting qualification: not complete**. The one successful
152-c SQL row is not promoted to an eight-flow result. Synthetic tests,
transport tests, guarded dry runs, and green CI are not live provider
qualification.

## History and branch topology

The non-rewriting merge has `origin/main` as its second parent and preserves
the 152-a, 152-b, 152-c, and 152-d implementation/report history as ancestors.
The branch was not rebased, squashed, force-pushed, or amended. PR #287 is the
existing Objective 152 PR; no replacement PR was created. It remains open,
non-draft, and auto-merge disabled.

The final branch diff relative to `origin/main` is limited to these
task-authored paths:

```text
docs/real-provider-qualification.md
oap/active
oap/orders/152-a-real-provider-accounting-verifier.md
oap/orders/152-b-verifier-run-isolation-and-bounded-output.md
oap/orders/152-c-authorized-live-gateway-accounting-qualification.md
oap/orders/152-d-asyncpg-jsonb-correlation-fix.md
oap/orders/152-e-main-reconciliation-and-terminal-merge-candidate.md
oap/reports/152-a-real-provider-accounting-verifier.md
oap/reports/152-b-verifier-run-isolation-and-bounded-output.md
oap/reports/152-c-authorized-live-gateway-accounting-qualification.md
oap/reports/152-d-asyncpg-jsonb-correlation-fix.md
oap/reports/152-e-main-reconciliation-and-terminal-merge-candidate.md
scripts/verify_real_provider_qualification.py
tests/unit/test_real_provider_qualification_verifier.py
```

Files inherited unchanged from the exact current-main merge are authorized
ancestry, not additional 152-e edits.

## Verification

All verification explicitly unset `OPENAI_API_KEY`,
`OPENAI_UPSTREAM_API_KEY`, `OPENROUTER_API_KEY`, `DATABASE_URL`,
`TEST_DATABASE_URL`, and `RUN_UPSTREAM_TESTS`.

Local focused evidence:

- `git diff --check`: passed.
- `python scripts/check_documentation.py`: passed (`DOCUMENTATION_CHECK=OK
  files=78`).
- Focused pytest for the verifier, documentation inventory, documentation
  contract drift, and product-scope docs: passed in an offline ephemeral
  environment built from the cached dependency set.
- The guarded verifier dry run produced
  `attempted_requests=0`, `real_provider_called=false`, `http_requests=0`,
  `sql_queries=0`, `result=not_run`, and `reason=guarded_dry_run`.
- `git merge-base --is-ancestor
  fa5423456ec21fadae066cb12960014ad00e1d8c HEAD`: passed.
- The project-rule Ruff subset passed using cached Ruff 0.16.4 with the
  repository's configured line length and E4/E7/E9/F rules. The exact order
  command using `.venv/bin/python` could not run because this checkout has no
  `.venv`; the pinned Ruff 0.15.16 wheel was not available in the offline
  cache. No code was changed to accommodate the newer tool.
- The exact system pytest command could not import the absent system
  `structlog`; the same focused test selection passed in the cached ephemeral
  environment. No package download or network request was used.

GitHub checks on implementation head `5e580f4` all passed: Analyze
JavaScript/TypeScript, Analyze Python, CodeQL, Docker Compose smoke,
Documentation hygiene, OpenAI-compatible E2E, Playwright browser smoke,
PostgreSQL integration, and Unit/lint/migration head. They are repository
checks and do not prove live provider qualification. They must be rerun on
the final report head.

No provider credential was read. No real provider request, Gateway generation
request, SQL connection, deployment, release, tag, email, or provider-cost
spend occurred in 152-e. No release, invoice, model-quality, performance,
production, security, compliance, support, or SLA claim follows.
