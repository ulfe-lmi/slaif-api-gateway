# OAP Work Order — 181-g

## Objective and business reason

Repair the six independently reproduced transport failures remaining in181-f,
on SAME Objective181 PR318. An administrator must be able to trust acquisition
budgets, public destinations and safe provenance. Green tests/CI alone did not
prove these boundaries. Preserve accepted progress and repair the actual seams.
This round does not close181: runner-measured acquisition versus supplied/intact
replay and exact installed content identity remain REQUIRED afterward. Full182
isolated Codex,183 atomic apply/accounting and184 final workflow remain required.

## Verified current state and authority

Reconciled2026-10-12T19:01–19:02UTC:
- Canonicalrepo ulfe-lmi/slaif-api-gateway; main unchanged
  6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf.
- PR mode AMEND_EXISTING_PR; uniqueObjective181 PR318 OPEN/CLEAN/MERGEABLE,
  branch oap/181-authoritative-catalog-collection, base main, title unchanged.
- Starting immutable report/head a609e247c8ab7b5e650caa51459573fed23c23a9;
  firstparent implementation bfc59921e3f50b2d050369c8aa0a8bedb0185808;
  report-only publication; all10 literal report-head checks SUCCESS.
- Active181-f exact five bytes; orderSHA256
  3ce0853b6da9edaccfca0f5ba2984370bccf946b8352e24aa64377ac69b3e99e;
  reportSHA2567572b4936908dc6dc04498ba92d5358025d9c8ed05cdd0ea03ab74aa5f40822d.
  Sole helper80057 returned RESPONSE_OK_EXACT/exit0 and CLOSED, already consumed.
- Independent359focusedtests PASS26.01s/zero uninjectedDNS. Six negative probes
  below still fail. 181-f PARTIAL, NOT ACCEPTED. Its immutable COMPLETE claims
  do not override strategic evidence. Never rewrite181-f report/order.
- Independent181-d D1–D4 and181-e runtime sqlalchemy[asyncio] repair accepted;
  preserve hosted identity denial, mixed exact/wildcard baselines, DNS/clock
  test isolation and runtime dependencies.
- Human authorized resumed ordinary OAP supervision using the tested Qwen agent
  in codingpane%9/pid1703557; strategicpane%8/pid1700208, session7/window0.
  One coding control waiter PID2192417 under agent2075296 targeting%9 observed.
  Reverify exact FIFOs/panes/waiter; no duplicate strategic helper/reader/signal.
- Shared roots /home/janezp/codex-work/slaif-api-gateway and
  /home/janezp/codex-supervision/slaif-api-gateway. Tracked worktree clean;
  preserve untrackedCODEX-SESSIONS.md/codex.sh, ignored.codex/local catalogs,
  linked worktrees and unrelated resources. UnrelatedDependabotPR319 untouched.
- Ruleset23580289 active, deletion/non-fast-forward prohibited, no bypass.
  No change-request review, independent final-head GitHub approval or auto-merge.
  Only prereleasev0.1.0-rc.1. No release/tag/deploy/production authority.

Read applicable maintained governance/protocol, compact architecture and current
catalog-refresh contracts. Required read-only evidence under STRATEGIC_ROOT:
workorders/OBJECTIVE-181-F-FIRST-HEAD-REVIEW.md (including final reconciliation),
review-artifacts/181-f-review/negative_probe.py and negative-results.json,
workorders/181-f-bound-and-pin-catalog-source-transport.md (required contract),
workorders/OBJECTIVE-181-D-STRATEGIC-REVIEW.md,
workorders/OBJECTIVE-181-E-STRATEGIC-REVIEW.md, and
workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md.
The delayed tmux feedback reached the coding agent after final report atomic
publication; preserving it and reporting before this activation was correct.

## G1 one enforceable deadline through actual DNS and network operations

Exact-head probe:0.02s context + injected DNS sleeping0.12s lets an HTTP handler
start after expiry (~0.121s); only subsequent body charging reports deadline.
Both preflight/connect-time DNS are synchronous and unbounded; backend has no
context, and10/30s static connect/read timeouts do not bound DNS/global duration.
Existing slow-DNS test expecting twoHTTP requests after its0.6s limit is not proof.

Propagate the collection-owned absolute monotonic deadline to the actual resolver,
connection, TLS, write/header/body-read and reused-connection paths. Every blocking
operation must have a bound derived from remaining whole-invocation time, with
expiry checked before the next action. Stop before HTTP after expired DNS, before
connecting the next candidate IP after an expired attempt, before TLS/write after
expired connect and before later reads/requests on reused connections. Retry waits
and inter-phase gaps share this same context; no refreshed per-request deadline.
Timeouts safely terminate acquisition; preserve finite attempt/cache semantics.

Choose a confined, maintainable implementation using existing dependencies/stdlib.
It must work for the supported synchronous CLI production path and not silently
fall back to unbounded DNS in other execution contexts. No process-global signal
handler/timer corruption, persistent resource leak, unbounded executor shutdown,
or detached worker continuing HTTP after return. If cancellable owned DNS workers
are used, they must be bounded in number/lifetime and reaped on success/failure/
timeout; they must not acquire provider/DB/seal/configuration authority. Do not
spawn a full refresh child with unrelated application authority. Document concrete
platform/runtime limits honestly. Do not relax the deadline into an unbounded
'in-flight lookup' exception or merely loosen timing assertions.

Observable acceptance: short injected genuinely blocking DNS/connect/TLS/read
negatives return within the configured deadline plus a small stated cleanup/
scheduler tolerance, with no downstream action starting after expiry. Give actual
wall times and operation counts. Ordinary mocks may model stalls; at least the DNS
negative must use a real blocking wait so pre-check-only fixes cannot pass. A long
mock stall must not be awaited at shutdown. No private service need be contacted.
Production backend tests must intercept real connection/stream primitives rather
than testing only a guard. Preserve HTTPS Host/SNI and default certificate chain/
hostname verification, numeric vetted connections and trust_env=False.

## G2 account overflow and make exhaustion terminal

Exact-head probe: context256, consumed chunks200+100, overflow raises before
subtracting100 and leaves56credit; later50byte fetch succeeds. Actual consumed350,
remaining6. Charge ALL consumed bytes, including the crossing chunk and chunks
returned after deadline; never refund. Track actual consumed count or a negative
remaining deficit honestly. Mark the invocation exhausted so later attempts/read/
cache-phase acquisition cannot use leftover credit. A bounded crossing read can
exceed the nominal cap by its bounded read size; document that and prove no further
reads/requests. Limit requested read sizes by remaining budget when practical;
never imply exact no-overrun if a crossing chunk remains possible. Preserve per-
source caps, failed/truncated byte accounting, cache reuse and identity-only raw
reads. No decoding of compressed bodies before refusal.

Regression: SAME256context with200+100 then50 consumes at most the first300,
records all300, blocks the later fetch BEFORE its handler/connect, and retains
terminal exhaustion. Repeat across fetch phases and failed reads. Deadline failure
must not hide already consumed bytes. No reset of allowances via another phase.

## G3 globally public unicast addresses at the actual socket decision

Exact-head socket-interception probe accepts100.64.0.1: is_globalFalse but
is_privateFalse. Require positive global-unicast classification in addition to
explicit multicast/reserved/loopback/link-local/unspecified exclusions. Reject the
complete mixed set, never filter it to public members. Cover RFC6598 IPv4, IPv6
nonglobal/multicast and mapped-address cases under supported Python3.12 semantics.
Malformed/empty answers fail safely. Preserve public IPv4/IPv6 numeric ordering
and original hostname TLS; no actual private destination contact.

## G4 safe rejected URL provenance

Exact-head synthetic302 to approvedhost with credentials/query is refused, but
RetrievalResult.final_url contains synthetic-user:synthetic-password and token.
Never persist a rejected raw target in final_url, other retrieval metadata,
validation/report/error text. Only a validated safe URL or absent final field is
permitted. Preserve useful safe failure codes/last accepted provenance. Include
malformed, credentials, query, fragment and unapproved-host redirect negatives;
inspect collector JSON and sealed rendered output for synthetic markers, not just
exception type. No real secret is used. Avoid changing bundle/seal formats.

## G5 traversal and ambiguous URL encodings

Exact-head validation accepts /api/docs/models/a%2F..%2F..%2Fprivate.md because
once-decoded slash/dot fits slug regex. Reject dot segments, encoded separators
that introduce traversal, double/ambiguous percent escapes and backslash/control
variants. Preserve legitimate URL-quoted model IDs, such as valid namespaced IDs,
without widening the fixed official families. Apply equivalent safe slug admission
to generated model_page_spec and supplied/redirect URL validation. Exercise raw
and encoded dot segments and legitimate positive cases. No actual path retrieval.

## G6 safe malformed URL/port handling

NEW exact-head direct approved-host URL with port:not-a-port raises ValueError
before the fetch error boundary. This is distinct from the previously withdrawn
181-a malformed-redirect allegation; preserve that historical correction.
Handle malformed untrusted URLs/ports/brackets safely at validation and redirect
resolution; no uncaught exception or raw secret-bearing URL/exception text. Cover
nonnumeric/out-of-range ports and malformed authorities, and prove collector/CLI
fails deterministically with safe codes rather than aborting without a blocked
review where its existing blocked-run contract applies.

## Exact allowed paths and non-goals

- app/slaif_gateway/services/catalog_refresh/sources.py
- app/slaif_gateway/services/catalog_refresh/source_transport.py
- app/slaif_gateway/services/catalog_refresh/collection.py (budget/client lifecycle only)
- tests/unit/test_catalog_refresh_sources.py
- tests/unit/test_catalog_refresh_collection.py
- tests/unit/test_cli_catalog_refresh.py
- docs/catalog-refresh.md (transport guarantee, accounting and actual limits only)
- docs/cli-reference.md (transport wording only if needed)
- admin/catalog-refresh/README.md (transport wording only if needed)
- oap/orders/181-g-enforce-catalog-transport-boundaries.md (unchanged strategic bytes)
- oap/active (exact strategic five-byte181-g)
- oap/reports/181-g-enforce-catalog-transport-boundaries.md (new immutable)

No other paths. No dependencies, schema, bundle/capture/seal/rendering identity
redesign, parser/pricing/source_evidence policy, runtime gateway routing/provider/
hosted-policy/accounting/DB/import, Docker/Compose/workflow or rootgovernance
changes. No isolatedCodex researcher/wrappers yet. If another path is essential,
report the concrete need before widening scope. Preserve original181-f transcript
and all accepted behavior. Source/tool provenance follow-up remains required.

## Proportional verification and bounded public qualification

Run affected source/collection/CLI and OAP governance tests, meaningful G1–G6
regressions, Ruff, documentation checker and round diff check against starting
reporta609e247c8ab7b5e650caa51459573fed23c23a9. Reuse unaffected359-test evidence;
normal GitHubCI handles broader routine regressions. No full local DB/Redis/
Docker/browser matrix for this transport-only delta. HTTP/DNS/socket in ordinary
tests mocked or denied; prove zero uninjected defaultDNS with an external audit.
Do not repeatedly rerun a passing suite to recover counts; retain exact output.

Because actual transport changes, after pushing the literal final implementation
head, qualify through production transport with bounded unauthenticated official
GETs: both OpenAI/OpenRouter plus neededECB and one actual OpenAI model page,
selected from fetched current facts. Max24actualattempts/8MiB/120s per invocation,
plus lower per-source caps; no alternate-client or pre-commit qualification claim.
Retain safe counts/statuses/timings/body hashes and actual code identity. A source
outage remains a safe BLOCKED outcome, never bootstrap/disappearance. Verify a
sealed run offline with HTTP/DNS/socket forbidden. Use an external syntheticHMAC
key outside run, never print it. Acquisition-versus-intact-replay label and exact
installed tooling identity remain explicitly deferred/unclosed, not hidden.

## Setup, authority, privacy/accounting and immutable publication

Existing owned managedPython3.12.15 and /tmp/slaif-181c-strategic-venv available;
copied checkout.venv remains broken and must be preserved. Own ordinary isolated
scratch setup; no package/service changes needed. Small unauthenticated official
library/stdlib documentation reads to ground implementation are authorized and
separately recorded. Provider/ECB realGETs authorized only for bounded qualification
above. No production/protected files, .env/credentials, inference, provider auth,
DB mutation/import, real email, release/tag/deploy. DNS subprocesses if used do not
inherit new secret/config authority. PostgreSQL remains accounting truth; no prompt/
content/secret retention or hosted/local-tool authority expansion. All reports,
logs and evidence contain safe metadata, no raw secrets or exception text.

Amend ONLYPR318, never create anotherPR or merge/enableauto-merge. Commit/push
strategic order and active unchanged with implementation; inspect actualCI and
repair in-scope failures. Before final report atomic rename, ensure each claim
matches evidence; preserve any pending/failed/blocked limitation honestly. Report
literal implementation head and Report publication commit: SELF. Atomic final-path
publication makes the report immutable. Final report-only commit has that head as
firstparent and changes ONLYthis report. Push, verify remotePRheadSELF, then exact
responseOK(two bytes/no newline) and exactly one controlwaiter targeting verified%9.
No post-publication implementation or report mutation underG. Report G1–G6 timing/
connection/byte/privacy/encoding/URL tests, exact focused outcomes/DNSaudit/docs/CI,
setup/publicsmoke/offlineproof, scope, and deferredcapture/toolidentity/182–184.
