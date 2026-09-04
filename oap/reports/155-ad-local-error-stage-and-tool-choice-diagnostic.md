# Objective 155-ad — Local error stage and tool-choice diagnostic

Date: 2026-09-02

RESULT=FAILED

This report records one bounded diagnostic execution. It is not an integration
acceptance or a product-release claim.

## Topology

- Repository: `ulfe-lmi/slaif-api-gateway`, PR #291, branch
  `oap/155-local-coding-signed-server-module`.
- Starting report head: `1708eea898d6f1403518dd78897a119366a62652`.
- Activation commit: `b0441d943ca858681615244408a1178ebdb67a3d`.
- Diagnostic implementation head: `407f75fe38643c0cfe8cf30a615449b91cf614ec`.
- This report is a report-only `SELF` commit whose first parent is the
  diagnostic implementation head above.
- The active selector and exact 155-ad order were used. No merge, cutover, or
  product correction was performed.

## Scope and source authority

The implementation changes are verifier-only and are limited to the ordered
verifier/test/governance paths. No `app/` product file, Local Coding checkout,
Qwen service, Codex package, fixture, schema, dependency, or lockfile was
changed. Local error-code vocabulary and stage mapping were bound against the
unchanged Local 005-m source checkout at its ordered report head.

## Checks and fake evidence

- Focused verifier and governance tests passed.
- Ruff and diff checks passed.
- All ten required PR checks passed on implementation head
  `407f75fe38643c0cfe8cf30a615449b91cf614ec`.
- The normal composed fake qualification passed: two turns, one function
  lifecycle, one message lifecycle, two accounting rows.
- The fake provider-failure matrix failed closed with one inference-side
  upstream error, one released reservation, one failed ledger, and zero
  pending state.
- The deliberate fake validator-rejection matrix failed closed with retained
  bounded rejection evidence, one released reservation, one failed ledger,
  and zero pending state.

## Protected diagnostic

Exactly one protected task-local Codex 0.149.0 process was run. There was no
retry and no second protected process. The task-local package, invoked binary,
and catalog were the same bounded 0.149.0 installation; the host-default
version class was 0.149.1 and was not invoked.

The first request reached Gateway, Local, and protected Qwen successfully:

- Gateway: two requests and two responses overall; the first was 2xx SSE and
  the second was 4xx JSON.
- Local: one request and one 2xx SSE response.
- Qwen: one inference request, 2xx SSE, normal close; compiler calls: zero.
- The first request had the bounded observed top-level taxonomy classes
  `custom=1`, `function=5`, `tool_search=1`, `web_search=1`, and tool choice
  class `automatic_none`.
- The second request was classified as
  `top_level_function_pair_without_additional_tools`; its bounded input item
  classes included the adjacent function call/output continuation.
- The second Gateway response exposed only the safe error classes
  `code=other`, `param_root=input`, `param_leaf=other`. No raw body, IDs,
  names, arguments, or error text were retained.

The Local-bound signed evidence was positive without retaining values:
service Bearer equality, exact required-header cardinality, canonical-byte
reconstruction, raw-body canonical-signing participation, independent HMAC
verification, route/method/path/query validity, timestamp and nonce shape, and
no extra internal headers all passed. Local tool-policy state was
`transformed`; Local and Qwen both returned normal 2xx SSE for the one turn
that reached them. Hosted search was not admitted as a provider capability.

The bounded second-request reasoning projection reported a reasoning item with
nonempty content-array class, null encrypted-content class, empty summary-array
class, exact allowed-key-set match, no unexpected semantic fields, and absent
ID class. These are structure classes only.

## Failure and accounting

The run returned the fixed failure code `qualification_accounting_incomplete`.
Accounting had one finalized reservation, one finalized ledger row, zero
pending rows, and zero released/failed rows. The required two-turn accounting
predicate therefore was not met: the second Gateway rejection occurred before
a second Local/Qwen turn and no second terminal accounting row/class was
retained. The evidence is consequently insufficient for a passed diagnostic
answer, and no Local/Qwen ownership conclusion is claimed for that second-turn
failure.

## Cleanup and privacy

The owner-only runtime reference was removed after the run. The exact
155-ad temporary root, installed task-local Codex files, summaries, processes,
listeners, containers, and named task database were absent after cleanup. The
Local checkout remained Git-clean with no task `.venv` or bytecode state.

No credential, endpoint, prompt, request/response body, raw header, canonical
bytes, timestamp, nonce, signature, ID, tool value, exception text, or private
artifact was persisted or included in this report. No product correction,
acceptance, merge, or next objective was inferred.
