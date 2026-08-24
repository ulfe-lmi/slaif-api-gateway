# OAP Work Order — 153-b

PR mode: `AMEND_EXISTING_PR`
PR: `#289`
Branch: `oap/153-client-server-module-architecture`
Base: `main @ 05f7b6deddea3f742acba686fbeedc9088c4b057`
Current remote head: `610e5e2ac6658aa72c255481b2bb41650c27c309`
Title remains: `obj153: adopt static client and server modules`

## Objective and reason

Close the architecture-enforcement gap found in independent review of 153-a.
The implementation and final-head CI are green, but the activated order
required executable guardrails for both trust directions and for production
registry ownership. The current `tests/unit/test_module_architecture.py`
checks client-module imports and proves the two create handlers call a default
helper, but it does not:

- prevent server modules from importing public authentication or directly
  invoking Gateway DB/quota/accounting/pricing/audit mutation paths;
- prove the default helper resolves through the client registry rather than a
  module singleton bypass; or
- guard the provider factory's production server-registry/pair-resolution
  callsites against future bypass.

Add the narrow missing enforcement without changing module behavior or widening
Objective 153. Previous reports are immutable; publish a new 153-b report.

## Verified starting state

- PR #289 is open, non-draft, mergeable, and has no auto-merge.
- Report head `610e5e2ac6658aa72c255481b2bb41650c27c309` has implementation head
  `ea198ac8fd405d604174782fbbb638c86a082e58` as first parent and changes only
  `oap/reports/153-a-static-client-server-module-architecture.md`.
- All ten checks on that report head passed after the built-in OpenRouter
  dispatch regression was fixed at `ea198ac`.
- Facial adapter code is behavior-equivalent apart from its server-module base
  and import path. Current client/server registries are immutable finite maps.
- No Codex 0.149, Local Coding, OpenCode, hosted-tool, identity, migration, or
  live work is authorized.

## Required implementation

### 1. Client registry ownership

- Make `normalize_default_client_request(...)` obtain the default client module
  through the same finite `get_client_module(DEFAULT_CLIENT_MODULE_ID)` lookup
  used for future explicit module selection, then invoke `normalize`.
- Do not expose a client-supplied module ID or add key/route selection in this
  continuation.
- Add a test that substitutes/observes the registry resolver and proves the
  production helper cannot silently call a parallel singleton path.

### 2. Server trust-boundary guardrail

Extend the focused architecture test to parse every Python source file under
`app/slaif_gateway/modules/servers/` and fail if a server implementation or
registry imports:

- public Gateway authentication/session/key validation services;
- database sessions or repositories;
- quota, reservation, accounting, pricing, FX, audit mutation, reconciliation,
  external-tool fence/hold, or key-management services; or
- dynamic-loading mechanisms (`importlib`, entry points, arbitrary import/
  reflection helpers).

The guard must be path/module aware rather than a loose substring rule that
rejects safe provider error/transport/schema imports. Existing provider
adapter, diagnostics, header, streaming, schema, settings, and pure module
contract imports remain allowed.

### 3. Production server-registry ownership guardrail

- Add focused AST/callsite tests proving `providers/factory.py` resolves a
  server descriptor, checks the finite client/server pair, and builds through
  the server registry.
- Prove the factory does not directly instantiate OpenAI, OpenRouter, generic,
  or facial adapter classes and does not call the legacy native
  `get_module_adapter` production path.
- Preserve the legacy function only as a compatibility API outside production
  dispatch; do not remove it or create another implementation.
- Keep exact built-in provider-slug precedence and strict generic/native URL/
  identifier validation from `ea198ac`.

### 4. Focused truth checks

- Add/retain tests proving registry maps are immutable, IDs/pairs are finite,
  duplicate/dynamic selection fails, the legacy facial path is re-export-only,
  and ignored `__pycache__` files are absent from the Git diff.
- Do not rewrite architecture docs unless a wording correction is required by
  the exact implementation. No broad documentation restyling.

## Exact allowed paths

```text
app/slaif_gateway/modules/clients/registry.py
app/slaif_gateway/modules/servers/registry.py
app/slaif_gateway/providers/factory.py
tests/unit/test_module_architecture.py
tests/unit/test_module_provider.py
docs/module-architecture.md
oap/orders/153-b-module-boundary-enforcement-closure.md
oap/reports/153-b-module-boundary-enforcement-closure.md
oap/active
```

Use the narrowest subset. Changes to server registry/provider factory are
authorized only if a focused guardrail exposes a real implementation issue;
test-only closure is expected otherwise.

## Required verification

```text
git diff --check
python scripts/check_documentation.py
.venv/bin/python -m ruff check <changed Python paths>
.venv/bin/python -m pytest -q tests/unit/test_module_architecture.py tests/unit/test_module_provider.py tests/unit/test_provider_factory.py tests/unit/test_facial_scoring_adapter.py
<focused Chat/Responses handler and OpenRouter built-in/generic dispatch regression tests>
git diff --name-only origin/main...HEAD
```

No PostgreSQL rerun is required if no behavior file other than the pure client
registry changes; final GitHub PostgreSQL/E2E checks remain mandatory. If
server registry or provider factory behavior changes, rerun the exact focused
PostgreSQL/provider tests affected by that change. Do not run broad local
suites.

## Anti-false-positive acceptance

- A prose assertion that server modules “cannot” import core authority without
  an executable guard fails.
- A client helper that still bypasses `get_client_module` fails.
- A test that merely searches for one current call string without detecting
  direct adapter construction/legacy dispatch fails.
- Overbroad substring rules that pass only because safe imports were removed or
  that cannot distinguish `providers.errors` from accounting services fail.
- Any change to request acceptance, provider selection, URL validation,
  authentication, quota/accounting, facial behavior, or error shape fails.
- Final report-head CI must be green; prior green checks are not sufficient.

## Boundaries and non-goals

- No Codex, Local Coding, OpenCode, signed identity, hosted tools, new module,
  dynamic plugin API, migration, live provider, production, deployment,
  release, certification, compliance, invoice, support, or SLA work.
- Do not modify or merge Local Coding PR #7 or Dependabot PRs #224/#250.

## Publication and response duties

- Amend only PR #289; never merge or enable auto-merge.
- Commit this order and `oap/active` unchanged.
- Publish exactly one immutable
  `oap/reports/153-b-module-boundary-enforcement-closure.md` as the sole path in
  the final report-only commit, recording implementation head, exact guardrails,
  focused tests, final diff/checks, docs impact, and boundaries.
- Verify report topology and remote head, then send exact `OK` to the response
  FIFO and resume the control FIFO.
