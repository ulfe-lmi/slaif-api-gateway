# OAP Work Order — 181-f

## Objective and business reason

Close the independently reproduced catalog-collection transport gaps on SAME
Objective181 PR318. Official-source acquisition must have one real finite budget
and connect only to the vetted public destinations it records. Preserve every
accepted pricing/authority/baseline/sealing behavior. This is transport only:
runner-measured acquisition versus supplied/replayed data and exact installed
tooling identity remain REQUIRED in a later same-PR continuation. Full182 isolated
Codex,183 atomic audited apply/accounting and184 final workflow remain required.

## Verified state and authority

Reconciled2026-10-12 after181-e response:
- Canonicalrepo ulfe-lmi/slaif-api-gateway, main
  6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf, unchanged.
- PR mode: `AMEND_EXISTING_PR`; uniqueObjective181 PR318 OPEN/MERGEABLE,
  branch oap/181-authoritative-catalog-collection, base main; title unchanged.
- Starting report/headb0cdb0019c31a744d464c2502b7f98ffb5d7b839, firstparent
  implementation2913321669d4c51251aaa5079fe6a3d5e1515462; publication reportonly.
  All10literalreport-headchecksSUCCESS; no change-request review/auto-merge.
- 181-e orderSHA25630376e96a379ca12236c46fd0e58123b3f7665eeceb5e39277f77c89ee185606,
  active181-e exact; helper2512 exactRESPONSE_OK_EXACT/exit0 and CLOSED.
- 181-d D1–D4 independently accepted:333focusedtests, zero uninjectedDNS,
  actual midnight challenge, identity/supplied-bypass/mixed-baseline proofs.
  181-e runtime-only asyncio dependency repair independently accepted; do not
  change those dependencies again or conflate previous Docker failure with
  this transport task. Neither round completes181.
- Codingpane%9/pid1703557, strategicpane%8/pid1700208; migrated shared roots
  /home/janezp/codex-work/slaif-api-gateway and
  /home/janezp/codex-supervision/slaif-api-gateway. Reverify current waiter/panes.
- Tracked coding worktree clean; preserve CODEX-SESSIONS.md/codex.sh, ignored
  .codex/.local-provider-catalog and unrelated worktrees/resources. Unrelated
  DependabotPR319 remains open/untouched. Main ruleset23580289 active, forbids
  deletion/non-fast-forward; no release/tag/production authority.

Human authorized normal OAP supervision with the tested Qwen coding agent in%9.
Read this complete order, applicable maintained constitution/protocol, current
catalog-refresh contracts and compact architecture. Required strategic evidence
(read-only) under STRATEGIC_ROOT:
- workorders/OBJECTIVE-181-TRANSPORT-CAPTURE-ASSESSMENT.md
- review-artifacts/181-c-review/transport_probe.py and transport-results.json
- review-artifacts/181-transport-supplement/probe.py and results.json
- workorders/OBJECTIVE-181-D-STRATEGIC-REVIEW.md and
  OBJECTIVE-181-E-STRATEGIC-REVIEW.md (accepted behavior to preserve).
Full mandate remains workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md.

## Confirmed transport failures, not historical speculation

sources.py SHA25655015631a6a85f0da0ad3e29382e28a66d687cf9adf9aca829980672bc380482
is unchanged through181-e. Literal committed-source synthetic probes show:
- Aggregate request budget2 permits6actual HTTP attempts (retries count as one).
- Two phases with1request/256bytes each permit2requests/400bytes in aggregate.
- Failed body reads consume200bytes on each of3retries, then another successful
  request consumes200:800actual mock bytes under256aggregate limit, only200counted.
- gzip8175wirebytes expands to8MiB and25,218,022bytes traced allocation BEFORE
  a256byte cap reports body_too_large (iter_bytes chunks AFTER decoding).
- Synthetic HTTPS_PROXY enables an implicit proxy pool; no traffic was sent.
- Mixed public+loopback DNS and arbitrary non-document path/query on an approved
  host pass current guards. DNS guard and actual HTTPX resolution are separate.
No private service was contacted. Malformed-port redirect returned safe
transport_error; do not revive the withdrawn uncaught-exception claim.

## F1 one acquisition-owned budget and cache across all phases

Create one collection-owned finite attempt/byte/deadline/cache context BEFORE
acquisition starts; pass it through catalog, model docs, ECB, every redirect and
retry. No second fetch_sources call resets any allowance. Count every real HTTP
attempt/hop/retry, and all consumed successful/failed/interrupted/overflow body
bytes. Reserve/check remaining allowance BEFORE starting another attempt/read;
failure cannot refund consumed traffic. Use bounded streaming buffers and honest
documented accounting; do not claim decoded chunks bound decompressor allocation.

Keep existing128attempt/32MiB and per-source caps unless a justified bounded
adjustment is documented; introduce a finite explicit global monotonic acquisition
deadline (choose/document a practical value). DNS, connect, TLS, read, retry sleep,
and gaps between fetch phases consume that same deadline. Per-read timeout alone
does not bound slow-drip or DNS. Stop on expiry before later network activity;
safe finite failures identify exhaustion. Do not leave unbounded blocking DNS/
worker shutdown or background HTTP continuing beyond the deadline. Keep retry/
redirect/concurrency bounds finite and declare exactly what attempts count.

One URL's success OR failure is cached across phases within this invocation;
reuse captured bytes/outcome without new retrieval/time claims or duplicate
network/budget expenditure. Revalidate each planned spec's registry identity
before accepting a cached result. No caller-supplied JSON may own this context.
Keep provenance, safe outcomes and deterministic failure-to-BLOCKED behavior.

## F2 connection binding, exact URL families, no implicit proxies

Fixed registry source-kind/provider URL/path families only: known OpenRouter
catalog, OpenAI pricing/index/model-doc paths, ECB daily reference XML. No arbitrary
same-host path/query/fragment/credential/port expansion; reject traversal/encoded
ambiguity and malformed inputs safely. Validate BEFORE first request and on each
redirect/cache reuse. No new host/path family without concrete source evidence
and bounded justification; fail closed on unsupported source redirects/drift.
Record only validated safe URLs; a rejected redirect target must not leak its
credentials/query or raw exception text into retrieval outcomes or reports.

Reject mixed/non-global DNS answers, not just all-private sets. Bind the ACTUAL
connection to the vetted PUBLIC NUMERIC destination(s); original approved HTTPS
hostname, Host, SNI and certificate chain/hostname verification MUST remain.
Preflight getaddrinfo followed by an independent client resolution is not a fix.
Connection reuse, retries and redirects cannot bypass the vetted destination/
deadline decision. Disable environment proxies and implicit network configuration.
Use existing supported library/stdlib boundaries, no new dependency, vendored
client, TLS bypass or credentials. A small source_transport.py helper is allowed
below if needed; keep it readable and confined to this acquisition subsystem.

## F3 bound encoding before expansion

Prefer Accept-Encoding:identity and reject unexpected Content-Encoding BEFORE
any decoding/expansion. This is authorized if final current official sources
support it (the September feasibility probe is historical, not qualification).
Otherwise an incremental decoder must cap both wire/plaintext/allocations before
expansion. Test real streaming compressed bytes, not already-decoded fixture
content. Bound oversized/unknown encodings and premature/failed bodies honestly.
Preserve digest/body/captured-byte correspondence and existing180descriptor/HMAC
protections. No arbitrary Content-Length trust or full unbounded response.read.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/sources.py
- app/slaif_gateway/services/catalog_refresh/source_transport.py (new if needed)
- app/slaif_gateway/services/catalog_refresh/collection.py (budget/client lifecycle only)
- tests/unit/test_catalog_refresh_sources.py
- tests/unit/test_catalog_refresh_collection.py
- tests/unit/test_cli_catalog_refresh.py
- docs/catalog-refresh.md (transport/budget guarantees and honest limits only)
- docs/cli-reference.md (catalog-refresh transport wording only if needed)
- admin/catalog-refresh/README.md (transport/budget wording only)
- oap/orders/181-f-bound-and-pin-catalog-source-transport.md (unchanged)
- oap/active (exact strategic five-byte181-f)
- oap/reports/181-f-bound-and-pin-catalog-source-transport.md (new immutable)

No other paths. No schema/bundle/capture/seal/rendering identity redesign,
source_evidence pricing/parser policy, runtime gateway pricing/accounting/provider/
hosted-policy/routing/DB/import changes, dependencies/Docker/Compose/workflows,
Codex researcher/wrappers/rootgovernance/archive/localcatalog changes. Budget
metadata may remain internal; if a required design truly needs another path,
report the exact need rather than silently expanding scope. Preserve D/E fixes.

## Acceptance and proportional verification

AP-F1: actual attempts and consumed bytes obey one whole-invocation budget,
including all phases/retries/redirects/failed/truncated bodies; cache reuse cannot
reset or double-fetch. Real slow-DNS/slow-drip/deadline and finite retry-sleep
negatives prove bounded wall time and no later HTTP after exhaustion.
AP-F2: tests intercept the ACTUAL connection primitive/backend, proving vetted
numeric destinations and original HTTPS hostname/SNI/verified certificate policy;
mixed/private/rebinding/proxy/redirect/reuse/spec-cache bypasses fail closed.
A guard-only test is insufficient. Use mocks or owned test transport without
relaxing production URL/host/TLS rules or contacting an actual private service.
AP-F3: streaming gzip allocation reproducer no longer expands before refusal,
or proves strictly bounded incremental expansion; unknown encodings, misleading
Content-Length, oversized/partial streams and failed-byte budgets are covered.
AP-F4: whole collector/CLI -> validation -> sealed report regressions retain
accepted pricing/authority/baseline/HMAC semantics; failure is BLOCKED with safe
codes, no false disappearance/bootstrap. All unit HTTP/DNS remains mocked.

Run focused catalog source/collection/bundle/policy/report/seal/CLI/proposal and
OAP governance tests, Ruff, documentation checker, round diff check against
b0cdb0019c31a744d464c2502b7f98ffb5d7b839, and normal GitHubCI. No full local DB/
Redis/Docker/HPC/browser matrix for this transport-only delta. Execute meaningful
connection-level negatives and explicit bounded timing/allocation evidence.

AP-F5: on the literal final implementation, run a bounded official unauthenticated
GET smoke THROUGH THE PRODUCTION transport (no ad-hoc alternate HTTP client):
one eligible model/provider, then both OpenAI and OpenRouter plus required ECB,
including an actual OpenAI model page. Select scope from fetched current facts,
not stale prices. Max24real HTTP attempts/8MiB/120s per smoke invocation; each
source still respects its lower per-body cap. No retries outside those limits.
Identity-only support must be measured for the actual endpoints. Retain safe
status/count/hash/timestamp evidence and review outcomes; no inference/auth or
actual DB. Verify the sealed result offline with HTTP/DNS/socket forbidden.
Intact replay's misleading live label/tooling identity is explicitly UNCLOSED
and must be reported as deferred, not hidden by this transport smoke.

## Setup, security/privacy and immutable publication

Own ordinary scratch/test setup; existing managedPython3.12.15/strategic devvenv
is available. No package/dependency/service changes needed. No .env/protected
credentials/private files, production database/import, inference, real email,
deploy/tag/release. Provider/ECB source GETs are authorized ONLY within AP-F5's
exact bounded smoke; small unauthenticated official library/stdlib documentation
reads to ground the transport design are also allowed, separately recorded.
Normal tests use mocks. Use owned run roots and an
external synthetic HMAC key, preserving Linux namespace and descriptor controls;
never publish secrets/DBURLs/raw exception text. PostgreSQL remains accounting
truth and hosted tools remain denied by default; no runtime authority is widened.

Amend ONLY PR318; no new PR, merge or auto-merge. Commit/push exact strategic
order/active bytes unchanged with implementation, inspect actual CI and repair
in-scope failures. After implementation is pushed, record literal implementation
head and Report publication commit: SELF; atomically publish one named report,
final report-only commit with matching first parent, push and verify remote PR
head BEFORE exact two-byte responseOK/no newline. No later mutation or old report
rewrite. Return to exactly one control helper with verified TMUX_PANE=%9. Report
exact attempts/bytes/timing/connection/allocation/smoke/negative evidence, setup,
docs, safety, scope and all remaining capture/tooling/full-workflow limitations.
