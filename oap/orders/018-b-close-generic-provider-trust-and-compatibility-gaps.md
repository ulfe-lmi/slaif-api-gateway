# OAP 018-b — Close generic-provider trust and compatibility gaps

## Objective and reason

Amend the sole Objective 018 PR #244. Objective 018-a established the generic
runtime foundation and passed CI, but independent strategic review found two
real defects plus missing direct evidence/documentation. Repair only these
findings; do not broaden into discovery, endpoint conformance, or Codex work.

Start implementation now after reading the named changed symbols and focused
tests once. Do not repeat broad reconnaissance or run broad local suites.

## Verified continuation state

- PR: #244, <https://github.com/ulfe-lmi/slaif-api-gateway/pull/244>
- Base: `main`; head branch:
  `oap/018-generic-openai-compatible-backend-runtime`.
- Current report head: `532f3e653bbdff27a63a08395b56f1fe3bbe6065`.
- 018-a implementation head:
  `4616033e873824c5230428499028208047be7256`.
- 018-a report topology is valid and all ten current checks are green.
- PR is open, non-draft, mergeable, and has no review threads.
- Reuse this PR and branch. Do not create another PR, merge, or enable
  auto-merge. Do not edit the immutable 018-a order or report.

## Exact findings to close

1. **Built-in OpenRouter admin regression**
   - `_validate_admin_base_url()` now requires path `/v1` for every provider,
     so the valid built-in OpenRouter base URL `/api/v1` is rejected before the
     provider service's correct built-in exception can run.
   - Restore existing OpenAI/OpenRouter create/edit behavior while retaining
     exact canonical `/v1` enforcement for operator-defined generic providers.
   - Use one shared validator/service contract or provider-aware admin
     validation; do not leave divergent URL rules.

2. **Generic adapter secret fallback**
   - `OpenAICompatibleProviderAdapter` inherits
     `OpenAIProviderAdapter._configured_api_key()`, which falls back to
     `Settings.OPENAI_UPSTREAM_API_KEY` when `_api_key` is absent.
   - A generic adapter must never use the built-in OpenAI secret. Override or
     refactor the key lookup so generic instances require their exact configured
     key and fail with their own provider slug when absent.
   - Add a direct negative test with a populated OpenAI upstream secret proving
     it is not used or disclosed.

3. **Canonical provider identity**
   - Factory provider names are lowercased while provider-config creation stores
     arbitrary case. That can make adapter identity diverge from routing,
     pricing, accounting, and audit identity.
   - Define and enforce one safe canonical provider slug contract at provider
     config create/update (lowercase ASCII slug, bounded length, no whitespace
     or secret-like value). Preserve built-in names and use that identical
     stored slug everywhere.
   - Add create/update and route/factory proof; do not silently change unrelated
     existing rows or add a migration.

4. **Redirect and propagation evidence**
   - Add a focused generic-adapter test proving a 3xx response is surfaced as a
     safe provider failure and no second-origin request occurs. Runtime-created
     HTTPX clients must remain no-follow; test doubles may not invalidate that
     promise.
   - Add direct route-resolution proof that `provider_kind`, slug, base URL,
     env-var name, timeout, and retry facts survive selection together.

5. **Operator-flow evidence and documentation**
   - Add direct CLI and admin create/edit tests for unconfirmed HTTP denial,
     confirmed-with-reason success, HTTPS success without HTTP acknowledgement,
     safe env-var-only rendering, and built-in OpenRouter `/api/v1` regression.
   - Ensure the audit record for confirmed generic HTTP contains safe explicit
     acknowledgement evidence (boolean/base URL/reason), never a key value.
   - Update the current-facing contracts required by 018-a: `README.md`,
     `AGENTS.md`, `docs/configuration.md`, `docs/database-schema.md`,
     `docs/deployment.md`, `docs/compatibility-matrix.md`, and
     `docs/security-model.md`, in addition to the two already changed docs.
     State runtime foundation versus qualification, bearer env-var isolation,
     generic HTTP risk, no redirect, and no hosted-tool/OpenRouter-cost
     inheritance. Preserve historical evidence and the README brand block.

## Allowed paths

Use only the existing 018-a changed paths plus the exact adjacent tests/docs
named above, `oap/active`, this order, and the new 018-b report. No migration,
discovery/wizard, Qwen/Codex, real network, provider, production, or unrelated
refactor is authorized.

## Acceptance criteria

1. Built-in OpenRouter `/api/v1` create/edit works again; generic `/v1` remains
   exact.
2. A generic adapter can never fall back to or expose the OpenAI built-in
   secret.
3. Canonical provider slug identity is consistent through config, route,
   adapter, safe failure, pricing/accounting facts, and audit without migration.
4. Redirect, missing-secret, malformed URL/env/slug, and HTTP confirmation
   negatives have direct focused proof.
5. CLI/admin positive and negative behavior is directly tested; HTTP
   acknowledgement is safely audited.
6. All current-facing docs name the runtime foundation and its non-claims.
7. Existing OpenAI/OpenRouter focused regressions, Ruff, compileall, Alembic
   head, and diff check pass. Do not run a full local suite.

## Verification

Run the smallest focused union of:

```bash
python -m pytest -q \
  tests/unit/test_provider_factory.py \
  tests/unit/test_openai_provider_adapter.py \
  tests/unit/test_provider_config_service.py \
  tests/unit/test_route_resolution_service.py \
  tests/unit/test_cli_providers.py \
  tests/unit/test_admin_provider_config_actions_routes.py \
  tests/unit/test_admin_catalog_templates_safety.py \
  tests/unit/test_documentation_contract_drift.py
python -m ruff check <changed Python files/tests>
python -m compileall -q <changed Python modules>
python -m alembic heads
git diff --check
```

If an exact test name differs, select its focused equivalent and report it.
No full local unit/integration/E2E/browser/matrix suite and no real endpoint.

## Publication duties

- Commit this order and exact `oap/active=018-b` unchanged on the existing
  branch/PR.
- Push implementation commits; keep PR #244 ready and auto-merge disabled.
- Publish exactly one immutable
  `oap/reports/018-b-close-generic-provider-trust-and-compatibility-gaps.md`
  report in a final report-only commit with literal implementation head and
  `Report publication commit: SELF`.
- Report exact evidence, diff, docs, safe negatives, PR/check state, and any
  remaining limitation.
- Verify the report commit is remote PR head, then send exact `OK` to the
  response FIFO and return to one blocking control-FIFO wait.
