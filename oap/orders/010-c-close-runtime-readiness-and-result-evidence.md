# OAP Work Order — 010-c

## Objective

Amend objective-010 PR #235 to close three narrow strategic-review findings:
make positive Codex qualification prove the same baseline Responses capability
contract that runtime enforcement uses, show the safe Responses policy on every
direct pilot-key creation result as well as the existing detail page, and make
the standalone profile verifier reject misleading unused command-line
arguments. Preserve all accepted 010-a/010-b behavior and evidence otherwise.

## GitHub objective state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #235,
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/235`.
- Required existing head branch:
  `oap/010-codex-model-catalog-profile-admin-capability`.
- Base branch: `main`.
- Remote PR head at activation:
  `c29f8633b132e53ee160e256d19967562b0d4b6e`, the immutable 010-b report
  publication commit.
- Its first parent is the 010-b implementation head
  `ee1ef823220ac5e058740e7dcd152316ab87f7c7`.
- All ten report-head checks were independently observed successful. PR #235 is
  open, non-draft, unique for objective 010, and has no auto-merge request.
- Remote `main` remains
  `250ee751cffb8cc7632aaa793385eaa498ed6d08`.
- This is `AMEND_EXISTING_PR`. Reconcile current GitHub state, update the same
  branch/PR only, and never create another PR, merge, or enable auto-merge.

## Why 010-b is not yet accepted

010-b completed the intended qualification/profile/admin implementation and
all CI, but independent strategic review found three exact gaps.

### 1. Qualification can disagree with runtime baseline enforcement

`enforce_responses_route_capabilities()` always requires
`capabilities.responses.text=true` and rejects unknown or non-boolean nested
Responses flags. The new qualification service manually checks the five Codex
gates and endpoint-specific stateless/streaming/compact facts, but it can still
return `protocol_qualified` when `text` is missing/false or when the nested
Responses map contains a value runtime parsing rejects. The 010-b positive test
fixture itself omits `text`.

That is a false-positive readiness state: the profile/key could be rendered and
issued, then the first pinned Codex request would fail in normal gateway route
enforcement. Positive qualification must never be weaker than the exact runtime
operation it declares ready.

### 2. Creation result omits the policy that the pilot just stored

The existing key detail page safely summarizes stored `responses_policy`, but
the immediate `keys/create_result.html` and the direct create workflow's email-
delivery result do not receive/render the new pilot policy. 010-a explicitly
requires the key result and detail to show the existing safe Responses policy
summary. The two result templates were not in 010-a's allowlist, so this
continuation deliberately authorizes them.

### 3. The manual verifier silently ignores extra arguments

The verifier correctly creates and tests its own ephemeral numeric-loopback
URL, but `main()` accepts no parsed arguments and silently ignores any extras.
The 010-b report records an invocation with `--base-url ...`, although that
argument had no effect. The internal evidence is still valid, but a verifier
must not let an operator believe an external value was tested when it was not.

## Required remediation

### Runtime-aligned qualification

For each otherwise declared candidate route, require the complete nested
Responses map to be acceptable for the exact operation the qualification
claims:

- ordinary `/v1/responses`: text, stateless, streaming, route streaming, and
  all five Codex gates needed by the fully gated pinned request;
- `/v1/responses/compact`: text, compact, and all five Codex gates needed by
  the fully gated V1 compact request;
- unknown nested Responses flags and non-boolean values must fail closed just
  as normal runtime parsing does;
- strict `codex_limits`, reciprocal route/provider/model selection, pricing,
  FX, qualification metadata, and every other 010-b condition remain intact.

Prefer calling/reusing the existing runtime capability enforcement/parser with
the exact operation flags instead of maintaining a second divergent parser.
It is acceptable to retain the current granular fixed reason codes and add one
fixed low-cardinality `responses_runtime_capabilities_invalid` reason. Do not
expose exception text. Add `responses_text_capability_missing` only if a
separate fixed code is useful; never include raw metadata or arbitrary messages.

Update the positive qualification fixture to contain `text=true`. Add focused
negative tests proving that missing/false text, an unknown nested flag, and a
non-boolean nested value cannot qualify. Add direct drift evidence that the
same otherwise-positive ordinary and compact maps are accepted by runtime
capability enforcement for their exact operations. Do not change runtime
policy itself.

### Safe policy summary on creation results

Pass the already validated/stored `parsed_input.responses_policy` to both
direct creation result paths:

- browser plaintext result `keys/create_result.html`;
- direct-create `send-now`/`enqueue` result using
  `keys/email_delivery_result.html`.

Render only a deterministic summary when the policy exists: canonical allowed
capability names and local tool types. Do not render arbitrary metadata, raw
JSON, keys, secrets, or content. Preserve the existing plaintext-once behavior
for the browser result and the existing plaintext suppression for email
delivery. Rotation/template workflows that reuse these templates and ordinary
key creation must remain unchanged when no Responses policy is supplied.

Add focused route/template tests proving:

- a successful Codex pilot creation result shows all five canonical names and
  `function`/`custom`;
- the direct email-delivery result shows the same safe summary without adding
  plaintext to that response;
- ordinary/no-policy results omit the section;
- validation/readiness still happens before `KeyService` mutation.

The existing key detail implementation and storage format are unchanged.

### Honest verifier invocation

The manual verifier owns its ephemeral numeric-loopback URL and must have one
unambiguous interface. Use either of these, preferring the first:

1. accept no positional/options, reject every unexpected argument with a fixed
   safe usage error, and document/run exactly
   `.venv/bin/python scripts/verify_codex_profile.py`; or
2. explicitly parse a narrowly named option whose semantics are real and safe,
   without permitting non-loopback or fixed-port control.

Do not accept an operator-provided provider/gateway URL and do not weaken the
loopback-only/dead-proxy/private-home/raw-payload boundaries. Unit tests must
exercise argument parsing/helpers only and must never invoke Codex. Run the
final exact manual verifier once with the truthful supported invocation and
record its low-cardinality output in the 010-c report.

Also reject raw whitespace anywhere in the rendered gateway base URL (including
spaces in host/path), because such input is not a canonical usable URL even
though `urlsplit` may parse it. Retain all existing URL tests and add focused
host/path whitespace cases. Do not broaden supported schemes or paths.

## Documentation and support boundary

Update only the affected qualification/profile/admin contract passages so they
state that positive readiness includes baseline runtime `responses.text` and
strict nested Responses parsing, that creation results show the safe policy
summary, and that the verifier's actual invocation takes no ignored base URL.

The support claim remains exactly `protocol_qualified` for Codex 0.147.0,
bundled `gpt-5.6-sol`, profile v1, with `real_provider_e2e=false`. Do not call a
real provider/gateway, claim full compatibility/pilot completion/production
readiness, change the profile-v2 two-file layout, or expand tool authority.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/api/admin.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/web/templates/keys/create_result.html
app/slaif_gateway/web/templates/keys/email_delivery_result.html
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/security-model.md
oap/active
oap/orders/010-c-close-runtime-readiness-and-result-evidence.md
scripts/verify_codex_profile.py
tests/unit/test_admin_key_create_routes.py
tests/unit/test_admin_key_create_templates.py
tests/unit/test_codex_qualification.py
```

The final report-only commit adds only:

```text
oap/reports/010-c-close-runtime-readiness-and-result-evidence.md
```

Preserve every prior order/report byte-for-byte. If a different implementation
or test path is genuinely required, do not edit it; report `BLOCKED` with the
exact path/reason for a strategic 010-d decision.

## Focused verification and test economy

Run only:

- `tests/unit/test_codex_qualification.py`;
- the directly affected cases/files in
  `tests/unit/test_admin_key_create_routes.py` and
  `tests/unit/test_admin_key_create_templates.py`;
- focused OAP/documentation tests;
- scoped Ruff/compile, exact path/topology, fixture digest, and
  `git diff --check`;
- one final truthful no-extra-argument profile verifier run.

Do not run the full local unit suite, local PostgreSQL/integration/E2E,
Playwright/browser matrix, Docker/Compose, or HPC suites. GitHub CI owns broad
routine coverage. The user has explicitly asked that full suites not be
overused. Record all not-run suites honestly; never call a real provider,
gateway, hosted/external tool, production service, or use a real key.

## Acceptance criteria

1. No route can be `protocol_qualified` unless its exact ordinary/compact
   Responses capability map is accepted for the corresponding runtime
   operation, including `text=true`, strict known boolean flags, and all prior
   Codex/endpoint requirements.
2. Pilot creation results for plaintext and direct email-delivery modes show
   only the fixed safe Responses policy summary; ordinary/no-policy and rotation
   behavior remain unchanged, and email result plaintext suppression remains
   intact.
3. The standalone verifier rejects unused/unknown arguments and the final
   documented command exactly matches what it tests. Its internal endpoint
   remains ephemeral numeric loopback only.
4. Raw whitespace/invalid noncanonical gateway base URLs fail before rendering;
   all credential, TOML, privacy, and two-file profile boundaries remain.
5. Focused tests, manual verifier, docs, and every required report-head GitHub
   check pass. No broad local suite or real-provider call is used.
6. Only PR #235 is amended; earlier history remains immutable; the coding agent
   neither merges nor enables auto-merge; the final 010-c report has valid
   `SELF` topology.

## GitHub and report contract

Commit the unchanged 010-c order and `oap/active=010-c` with the narrow
implementation on the existing branch, push it, and update PR #235's body to
describe the current objective truth. Do not rewrite earlier commits/reports.
Inspect actual GitHub checks and repair only in-scope failures.

Publish exactly one immutable report at
`oap/reports/010-c-close-runtime-readiness-and-result-evidence.md` with literal
implementation SHA, `Report publication commit: SELF`, exact runtime-alignment,
result-summary/privacy, argument/URL, focused tests, truthful manual verifier,
GitHub checks, broad suites not run, and no-merge/no-auto-merge evidence. The
final commit changes only that report and has the implementation head as first
parent. Verify remote report head, then signal exact `OK`. Never merge.

