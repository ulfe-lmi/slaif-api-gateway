# OAP Execution Report — 181-g: Enforce catalog transport boundaries

## Identity

- Objective: 181 — authoritative catalog collection (SAME PR 318, branch `oap/181-authoritative-catalog-collection`)
- Round: **181-g** (AMEND_EXISTING_PR), selected by `oap/active` = `181-g`
- Order: `oap/orders/181-g-enforce-catalog-transport-boundaries.md` (strategic-authored; committed byte-unchanged in the implementation commit; file sha256 `0eaf1a0b92b8a51a621a1b076bec7563530b81a3f22a3fdef509c742973a23a4`)
- `oap/active` exact bytes (verified with `od -c` before publication): `1 8 1 - g` — 5 bytes, no newline; sha256 `c5ac6af9b8e0d9aec51825980f0be4a1a33f42d2f2835add08c24d63765068ab`; committed byte-unchanged
- Starting PR/local head (181-f immutable report head, pre-round): `a609e247c8ab7b5e650caa51459573fed23c23a9`; its first parent `bfc59921e3f50b2d050369c8aa0a8bedb0185808` is the 181-f implementation
- Implementation head: `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47` (8 files, +1788/−115)
- Report publication commit: SELF (first parent = implementation head `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47`)
- Canonical `main`: `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf` (unchanged)
- PR 318 at report time: OPEN, MERGEABLE, head `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47` (verified via `gh pr view 318 --json` after push), `autoMergeRequest: null` (preserved; no merge, no auto-merge)
- Strategic inputs (read-only): `workorders/OBJECTIVE-181-F-FIRST-HEAD-REVIEW.md` (including final reconciliation), `review-artifacts/181-f-review/negative_probe.py` + `negative-results.json` (the six probe mechanisms, mirrored one-for-one in the new regressions), `workorders/181-f-bound-and-pin-catalog-source-transport.md` (required contract), `workorders/OBJECTIVE-181-D-STRATEGIC-REVIEW.md`, `workorders/OBJECTIVE-181-E-STRATEGIC-REVIEW.md`, `workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md`; plus two in-round strategic reminders: (1) a timed join on a daemon resolver thread was REJECTED as non-compliant — the repair must prove bounded owned DNS cancellation and cleanup (kill + reap), no detached HTTP, no process-global signal corruption, deadline context at the actual backend/stream operations; (2) installed httpcore `SyncStream.write` resets the same timeout on every partial send, so deadline checks/clamped timeouts are required inside partial-send loops and at post-connect/TLS/read transitions, including reused streams.

## Status

**COMPLETE (repair round)** — all six independently reproduced 181-f findings (G1–G6) are repaired at the actual seams, with focused regressions at those seams (56 new tests), the zero-uninjected-default-DNS audit is clean, and GitHub CI at the implementation head is 10/10 SUCCESS. 181-f remains **PARTIAL / NOT ACCEPTED**: its immutable `COMPLETE` claims do not override the strategic evidence, and this report frames 181-g as the repair of those six findings, not an acceptance of 181-f. Objective 181 remains NOT closed: runner-measured acquisition versus supplied/intact replay and exact installed tooling identity remain REQUIRED in a later same-PR continuation.

## Executive summary

The six negative probes reproduced against the 181-f implementation head `bfc59921e3f50b2d050369c8aa0a8bedb0185808` are closed by one bounded transport delta confined to the acquisition subsystem:

1. **G1 — one enforceable deadline through the ACTUAL operations.** The collection-owned absolute monotonic deadline now reaches the real resolver, connection, TLS, and stream seams. The default (production) resolver — a blocking C call that cannot be cancelled in-process — runs in a short-lived OWNED child process (`sys.executable -I` with an EMPTY environment: it inherits no secrets, site configuration, or provider/DB/seal authority and executes only stdlib `json`/`socket`/`sys`/`time`); the parent waits with the REMAINING deadline seconds and on expiry SIGKILLs (uncatchable) and REAPS the child — bounded lifetime, reaped on success/failure/timeout, no detached lookup, no daemon thread, no process-global timer. `collect_bundle` binds the context to the client's vetted transport backend (`bind_acquisition_to_client`), so every candidate-IP connect, the post-connect transition, the TLS handshake (before AND after), every stream read, and — per the second strategic reminder — EVERY iteration of the partial-send loop re-check the deadline and clamp the socket timeout to the remaining whole-invocation time. Expired connects and expired handshakes close their sockets BEFORE the failure propagates (no resource leak). Real DNS is capped at 120 s even without a context, so no execution path silently falls back to unbounded DNS.
2. **G2 — overflow debited in full, exhaustion terminal.** A consumed chunk that crosses the remaining byte budget is debited in full (the honest deficit is kept — `bytes_remaining` goes negative, never refunded) and the invocation is marked TERMINALLY exhausted: later attempts, reads, and fetch phases cannot use leftover credit (refused before their handler/connect). A deadline failure does not hide already-consumed bytes. Requested read sizes are clamped to the remaining budget where practical, so a crossing read can overrun only by that bounded read size (documented, not claimed as exact no-overrun).
3. **G3 — global-unicast classification at the actual socket decision.** Positive `is_global` classification in ADDITION to the explicit loopback/private/link-local/reserved/multicast/unspecified exclusions: RFC 6598 shared address space, documentation ranges, benchmarking, reserved 240/4, multicast, link-local, and IPv4-mapped variants of all of them are refused at `connect_tcp`; mixed answer sets are refused as a whole, never filtered to their public members.
4. **G4 — safe rejected URL provenance.** A rejected redirect target (credentials, query, fragment, unapproved host, malformed port) never leaves the resolution loop variable: `final_url` records only the LAST VALIDATED SAFE URL (or is absent), and the sealed-run marker scan proves no synthetic secret marker survives in any run artifact.
5. **G5 — traversal and ambiguous encodings refused.** Safe slug admission for the model-page segment (supplied URLs, redirect targets, AND generated `model_page_spec`s): dot segments, encoded separators that introduce traversal, double/ambiguous percent escapes, backslash/control variants, and empty parts are refused; legitimate URL-quoted model IDs (plain and namespaced, e.g. `vendor%2Fmodel`, `meta%2Fllama-3.1%3Afree`) are preserved without widening the fixed official path families.
6. **G6 — safe malformed URL/port handling.** Malformed untrusted authorities and ports (nonnumeric, out-of-range, broken IPv6 brackets) fail with safe codes at validation (`url_nondefault_port` / `url_host_not_approved`) — never an uncaught `ValueError` or raw text — and at redirect resolution: parseable out-of-range ports reach our re-validation with the exact safe code, while a nonnumeric port is refused even earlier by httpx's own redirect bookkeeping and still surfaces as the safe `transport_error` with no raw target text (both variants covered by tests at their actual seams).

The 415-test focused 10-file suite passes with a zero-uninjected-default-DNS audit; the bounded production-transport smoke was executed on the LITERAL implementation head `e8da2b6` (15 real unauthenticated official GETs, all 200, identity honored) and produced a sealed READY run that verifies `valid: true` offline with HTTP/DNS/socket forbidden.

Objective 181 remains NOT closed by this round: actual collection versus intact replay (runner-measured acquisition versus supplied/replayed data) and exact installed tooling identity remain REQUIRED in a later same-PR continuation; 182/183/184 unchanged.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 318
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/318
- PR state at report time: OPEN
- Base branch: `main` (`6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`)
- Head branch: `oap/181-authoritative-catalog-collection`
- Starting remote SHA: `a609e247c8ab7b5e650caa51459573fed23c23a9` (181-f report-only publication)
- Implementation head SHA: `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47` (single commit; push `a609e24..e8da2b6`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR 318)
- Merge performed: NO

## Confirmed pre-round failures (from the order; reproduced by strategic probes at bfc5992)

1. **G1**: 0.02 s context + injected DNS sleeping 0.12 s let an HTTP handler START after expiry (~0.121 s); both preflight and connect-time DNS were synchronous and unbounded; the backend had no context, and the static 10/30 s timeouts did not bound DNS or global duration. The existing slow-DNS test expecting two HTTP requests after its 0.6 s limit was not proof.
2. **G2**: context 256 with consumed chunks 200+100 raised the overflow BEFORE subtracting the 100 and left 56 credit; a later 50-byte fetch then succeeded (350 actual consumed, 6 remaining).
3. **G3**: the actual mocked connection primitive accepted `100.64.0.1` (RFC 6598: `is_global=False` but `is_private=False`).
4. **G4**: a rejected credential/query 302 target leaked the ENTIRE unsafe target (synthetic user/password and token) into `RetrievalResult.final_url`.
5. **G5**: the encoded traversal `…/api/docs/models/a%2F..%2F..%2Fprivate.md` was ACCEPTED (the old slug pattern allowed `/` and `:` in decoded slugs for namespaced IDs).
6. **G6**: `https://developers.openai.com:not-a-port/api/docs/models/a.md` raised `ValueError` out of `validate_source_url` before the safe-code boundary (new exact-head reproduction; the previously withdrawn 181-a malformed-redirect allegation remains withdrawn and was not revived).

## Changes made

1. `app/slaif_gateway/services/catalog_refresh/source_transport.py` (476 ± lines): the bounded owned-DNS worker (`_spawn_resolver` Popen seam, `_resolve_default_bounded`, `_RESOLVER_SCRIPT` child: optional genuine block seam, `getaddrinfo`, JSON answer list or `ERROR`; empty environment, isolated mode); `resolve_vetted_public_destination` (remaining-seconds bounded; default-resolver identity at call time selects the worker; deadline re-check after the resolver); `_is_global_unicast_ip` (positive `is_global` + explicit exclusions; IPv4-mapped IPv6 classified by the embedded v4); `DeadlineStream` (SyncStream-compatible: deadline check + budget-clamped requested size + clamped timeout on `read`; deadline check + clamped timeout INSIDE the partial-send loop on `write`; deadline checks before AND after the TLS handshake on `start_tls`, returning a new `DeadlineStream` over the upgraded socket so the enforcement survives the TLS transition and pool reuse; expired connect/handshake sockets closed before failure); `VettedNetworkBackend` (connect-time re-resolution + whole-set vetting on every new connection; deadline check before EVERY candidate-IP connect, post-connect check with socket close on expiry, clamped connect timeout; `bind_deadline` for the collection-owned context; UDS forbidden); `VettedHTTPTransport` (deadline handed to the backend; `trust_env=False`; standard SSL context/pool limits inherited).
2. `app/slaif_gateway/services/catalog_refresh/sources.py` (291 ± lines): `AcquisitionContext.exhausted` (terminal exhaustion flag) with overflow debit-in-full in `charge_body_bytes`, refusal in `reserve_attempt`/`fetch_sources` pre-reservation, and `_read_bounded` buffered-slice clamping to the remaining budget; `fetch_source` — post-DNS `check_deadline()` BEFORE any HTTP request, per-request timeouts clamped to remaining time, `last_safe_url` tracked (updated only after validation passes) and used at every `_failed` site and on success so a rejected target never reaches provenance, collection-level codes re-raised; `guard_public_destination` (`remaining` kwarg → deadline-bounded vetting); `validate_source_url` — malformed-authority/bracket `ValueError` → `url_host_not_approved`, malformed/out-of-range `.port` `ValueError` → `url_nondefault_port` (G6); `_validate_slug_text` + tightened `_SLUG_PART_PATTERN` (colon kept for legitimate namespaced IDs; first char alphanumeric) with ≤32 parts, ≤200 decoded total, no empty/`.`/`..` parts, no double/ambiguous escapes, no backslash/control (G5), applied in `_validate_path_family` AND `model_page_spec` (generated specs get equivalent admission); `bind_acquisition_to_client` (binds the context to a client's vetted backend; documented no-op for mock clients).
3. `app/slaif_gateway/services/catalog_refresh/collection.py` (5 + lines, budget/client lifecycle only): `collect_bundle` calls `sources.bind_acquisition_to_client(client, context)` immediately after the one context exists, so the deadline reaches the actual backend even when the client was constructed before the context (the CLI path).
4. `tests/unit/test_catalog_refresh_sources.py` (655 ± lines; 45 → 98 tests): the 53 new G1–G6 regressions at the actual seams (below), plus the slow-DNS seam test corrected to the honest in-process-seam semantics (1 HTTP, 2 DNS, collection-level raise — the real interruptible default-resolver path is proven by the new subprocess test).
5. `tests/unit/test_catalog_refresh_collection.py` (173 + lines; 72 → 75 tests): C1 — `collect_bundle` binds the collection-owned context to the actual `VettedNetworkBackend` (sentinel fetch proves the bind precedes phase-1; mock-transport clients are a documented no-op with the full collection still succeeding); C2 — sealed-level G4: a 302 carrying synthetic credentials+query on the approved host → BLOCKED exit 20, `url_credentials` in the retrieval record and rendered review, and NO synthetic marker in ANY file of the sealed run directory; C3 — CLI-level G6: a 302 to an out-of-range port → deterministic BLOCKED (exit 20) with the exact safe code in the retrieval record/validation, no `ValueError`/traceback/raw target in the output.
6. `docs/catalog-refresh.md` (80 ± lines): global-unicast guard wording (RFC 6598/documentation/NAT64 refused, deadline-bounded, connect-time re-vetting); overflow debit + terminal exhaustion and the bounded crossing-read limit; the deadline-at-actual-operations paragraph with the honest platform limits (resolver-child spawn overhead, 5 s reap safety net, 120 s no-context cap, injected-seam limit); safe `final_url` provenance in the collection-identity paragraph.
7. Committed the strategic-authored 181-g order and the exact 5-byte `oap/active` (`181-g`) unchanged with the implementation.

Two in-round refinements found while writing the seam regressions (both fixed and tested before commit, both in the allowed transport file): (a) the post-connect and post-TLS expired-deadline branches raised before closing the just-connected/upgraded socket — an expired operation would have leaked its socket; both now close the socket BEFORE the failure propagates (regressions assert the close). (b) the fetch-level behavior for a NON-NUMERIC malformed `Location` was pinned explicitly: httpx 0.28 refuses it in its own redirect bookkeeping (`RemoteProtocolError`, caught by the existing safe-code boundary → `transport_error`, retries bounded, no raw text); a NUMERIC out-of-range port parses through and is refused by OUR re-validation with the exact `url_nondefault_port` — both documented in the tests and in Known limitations.

`app/slaif_gateway/cli/catalog_refresh.py` was NOT modified; `docs/cli-reference.md` and `admin/catalog-refresh/README.md` needed no transport wording (verified by inspection); `tests/unit/test_cli_catalog_refresh.py` unchanged (28 tests re-verified green).

## Files changed

Implementation commit `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47` only (8 files, +1788/−115):

- `app/slaif_gateway/services/catalog_refresh/source_transport.py` (476 ±)
- `app/slaif_gateway/services/catalog_refresh/sources.py` (291 ±)
- `app/slaif_gateway/services/catalog_refresh/collection.py` (5 +)
- `tests/unit/test_catalog_refresh_sources.py` (655 ±)
- `tests/unit/test_catalog_refresh_collection.py` (173 +)
- `docs/catalog-refresh.md` (80 ±)
- `oap/orders/181-g-enforce-catalog-transport-boundaries.md` (221 +, strategic-authored, committed unchanged)
- `oap/active` (exact strategic bytes `181-g`, committed unchanged)

No other tracked path changed (verified by `git diff --stat` between the starting head and the implementation head). The safe failure-code list is UNCHANGED by this round (no new codes); the nonnumeric malformed-`Location` case maps to the existing `transport_error`.

## Acceptance-criteria evidence

### G1 — one enforceable deadline through the actual DNS and network operations
- Result: PASS (the DNS negative uses a GENUINELY blocking wait, so a pre-check-only fix cannot pass).
- Real interruptible default resolver (the required real-blocking negative): `test_real_blocking_dns_is_killed_and_reaped_at_the_deadline` — the child (real `sys.executable -I` process) genuinely blocks 0.12 s before `getaddrinfo`; the collection deadline is 0.02 s. Measured: the entire `fetch_source` call returned in **0.02 s** of test time; the spy on `_spawn_resolver` saw exactly 1 spawn; the child was SIGKILLed (reaped `returncode == -9`) and REAPED (`poll() is not None` — no zombie/detached lookup); **0** HTTP handler hits; **0** `socket.create_connection` calls; raised `acquisition_deadline_exceeded`.
- Seam negatives (operation counts; measured wall ≤ 10 ms per subtest, except the 50 ms injected-DNS seam and the 300 ms stalling-body test): expired preflight DNS (injected 0.05 s seam vs 0.02 s deadline) → raise with **0** HTTP requests (wall 0.05 s, bounded by the documented in-process-seam limit); expired connect (first candidate consumes 6 ms of a 5 ms deadline) → expired socket CLOSED, second candidate never connected; failed-connect retry on expiry → loop stops before the next candidate (connect calls == 1, exactly the first IP); partial-send loop (each send 3 ms, 2 ms deadline) → exactly **1** send before the loop's own deadline check raises (httpcore's own loop would keep resetting the timeout); `start_tls` on an expired deadline → `wrap_socket` **0** calls; handshake that consumes the deadline → upgraded socket CLOSED before the raise; stream read with 10-byte remaining budget → requested size clamped to 10, and an exhausted context refuses further reads at the stream seam.
- Binding: `test_collect_bundle_binds_context_to_client_transport` proves `collect_bundle` binds the context to the actual backend (`client._transport._pool._network_backend._deadline is context`) and that mock clients are a documented no-op.
- Library facts (installed httpcore 1.0.9, read from venv sources): `SyncStream.write` resets the same timeout on every partial send (hence the in-loop check/clamp); `start_tls` returns a new `SyncStream` over the upgraded socket (hence the re-wrap so enforcement survives TLS and pool reuse).
- Honest platform limits (documented in `docs/catalog-refresh.md`): resolver-child spawn adds small bounded overhead per resolution; the post-SIGKILL reap wait has a 5 s extreme safety net; real DNS is capped at 120 s even without a context; an injected resolver (test seam only) is in-process and enforced around the call, not mid-call.

### G2 — overflow debited in full, exhaustion terminal
- Result: PASS (exact probe case: 256 context, 200+100).
- `test_overflow_chunk_is_debited_and_exhaustion_is_terminal`: after 200+100 under a 256 budget, `bytes_remaining == -44` (all 300 consumed bytes debited, honest deficit, no refund), `exhausted is True`, and the later 50-byte fetch is refused with `collection_budget_exhausted` BEFORE its handler runs (handler hits == 0).
- `test_failed_read_bytes_are_never_refunded`: 200 consumed, mid-stream failure, finite retry re-reads 200 → `bytes_remaining == -144`, terminal exhaustion, later 100-byte fetch refused pre-handler (hits == 0); `test_charge_and_reserve_refuse_after_terminal_exhaustion` pins the accounting seam directly (crossing debit in full, then charge AND reserve refuse); `test_deadline_failure_does_not_hide_consumed_bytes` (0.3 s measured: 200 consumed, stall past the 0.1 s deadline → `acquisition_deadline_exceeded` with `bytes_remaining == 56` — consumed bytes not hidden).

### G3 — globally public unicast addresses at the actual socket decision
- Result: PASS at `connect_tcp` with the real connect primitive intercepted (14 parameterized cases).
- Refused with `destination_not_public` and **0** connects: `100.64.0.1` (the probe case), `100.127.255.255` (RFC 6598 edge), `192.0.2.1`, `198.18.0.1`, `224.0.0.1`, `240.0.0.1`, `2001:db8::1`, `fe80::1`, `ff02::1`, `::ffff:100.64.0.1` (mapped CGNAT).
- Mixed `[global, 100.64.0.1]` → `destination_mixed_or_not_public`, 0 connects (refused as a whole, never filtered).
- Accepted (connected to the vetted NUMERIC destination, 1 connect each): `93.184.216.34`, `8.8.8.8`, `2606:4700:4700::1111`, `::ffff:93.184.216.34`. No actual private destination was contacted.

### G4 — safe rejected URL provenance
- Result: PASS (exact probe case plus query/fragment/unapproved-host variants, plus the sealed-artifact scan).
- Fetch level: a 302 to `https://synthetic-user:synthetic-password@developers.openai.com/api/docs/models/a.md?token=synthetic-token` → `url_credentials`, `final_url is None` (last-safe == requested URL); query-only → `url_query_forbidden`; fragment-only → `url_fragment_forbidden`; unapproved host → `url_host_not_approved`; out-of-range numeric port → `url_nondefault_port`; nonnumeric port → safe `transport_error` (httpx pre-refusal, no escaping exception). In every case `dataclasses.asdict(result)` contains none of the synthetic markers.
- Sealed level (`test_cli_collect_rejected_redirect_secrets_absent_from_sealed_output`): CLI bootstrap with the synthetic-credentials 302 → BLOCKED, exit 20; EVERY file of the sealed run directory (`catalog-refresh.json`, `REVIEW.html`, `validation.json`, `receipt.json`, manifest, and all others) was scanned byte-for-byte: `synthetic-user`, `synthetic-password`, `synthetic-token`, and the full unsafe target are absent from all of them, while the safe code `url_credentials` is present in the retrieval record and the rendered review.

### G5 — traversal and ambiguous URL encodings
- Result: PASS (9 negative slug cases at URL validation + generated-spec admission + redirect level + 5 positive cases).
- Refused with `model_page_slug_invalid`: `a%2F..%2F..%2Fprivate` (the probe case), `%2e%2e%2fsecret`, `..%2Fsecret`, `a%2F..%2Fb`, `a%5Cb` (backslash), `%252Fetc` (double/ambiguous escape), `a%00b` (control), `a%2F%2Fb` (empty part), `..%2F..%2Fetc%2Fpasswd`; generated specs: `model_page_spec("openai", "a/../../private")`, `"%2Fetc"`, `"a%2F..%2Fb"` all refused with the same code; redirect to the encoded-traversal target → refused with `final_url` clean.
- Preserved (must not raise): `gpt-4o`, `gpt-5.2`, `vendor%2Fmodel`, `meta%2Fllama-3.1%3Afree` (namespaced ID with tag — the colon kept deliberately), `chat%2D4o`; `model_page_spec("openai", "openai/gpt-4o")` → `…/models/openai%2Fgpt-4o.md`. No actual path retrieval; the fixed official families are not widened.

### G6 — safe malformed URL/port handling
- Result: PASS (validation, fetch, and CLI levels; the withdrawn 181-a allegation was not revived).
- Validation: `https://developers.openai.com:not-a-port/api/docs/models/a.md` (the probe case) → `url_nondefault_port` (no `ValueError`); `:99999` (out-of-range) → `url_nondefault_port`; `https://[::1/api/docs/pricing.md` (broken brackets) → `url_host_not_approved`; explicit `:443` still accepted.
- Fetch: 302 → out-of-range port → exact `url_nondefault_port` with clean provenance; 302 → nonnumeric port → safe `transport_error` with no raw target text.
- CLI (`test_cli_collect_malformed_port_redirect_blocks_safely`): deterministic BLOCKED run, exit 20, exact safe code in the retrieval record and `validation.json`, no `Traceback`/`ValueError`/raw target in the output.

## Local verification

- Focused 10-file suite (executed once; output retained in-session; count confirmed by collect-only, not by re-execution): **415 passed, 0 failed, 0 skipped** (wall ≈ 26.6 s including interpreter startup). Per file (collect-only): `test_catalog_refresh_source_evidence.py` 79, `test_catalog_refresh_bundle.py` 30, `test_catalog_refresh_policy.py` 41, `test_catalog_refresh_report.py` 11, `test_catalog_refresh_seal.py` 28, `test_catalog_refresh_collection.py` 75, `test_catalog_refresh_sources.py` 98, `test_cli_catalog_refresh.py` 28, `test_provider_catalog_proposal.py` 17, `test_oap_governance.py` 8. (The 181-f count was 359; the +56 delta is exactly this round's 53 new sources regressions and 3 new collection regressions.)
- Zero-default-DNS audit (strategic external guard `-p offline_guard`, the 3 transport/CLI files, 201 tests): exit 0, `{"exitstatus": 0, "uninjected_dns_calls": []}` — zero uninjected default-DNS calls and zero real connections in the unit surface. (The one real subprocess DNS test kills its genuinely-blocked child before the lookup, so it performs no DNS and is invisible to — and clean under — the guard.)
- `ruff check app tests`: **All checks passed**.
- `scripts/check_documentation.py`: **DOCUMENTATION_CHECK=OK files=91**.
- `git diff --check a609e247c8ab7b5e650caa51459573fed23c23a9`: **CLEAN**.
- Full local DB/Redis/Docker/HPC/browser matrix: **NOT RUN** — explicitly out of scope for this transport-only delta per the order; GitHub CI ran the full matrix at the implementation head (10/10 SUCCESS).

## GitHub CI / required checks

Check state observed for implementation head `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47` (all resolved before report drafting):

- `Docker Compose smoke`: **SUCCESS** (1m1s) — run 38300456867, job 114981842274
- `Unit, lint, and migration head`: **SUCCESS** (2m40s) — run 38300456867, job 114981842563
- `PostgreSQL integration tests`: **SUCCESS** (2m24s) — run 38300456867, job 114981842538
- `OpenAI-compatible E2E tests`: **SUCCESS** (1m28s) — run 38300456867, job 114981842442
- `Playwright browser smoke`: **SUCCESS** (2m56s) — run 38300456867, job 114981842486
- `Documentation hygiene`: **SUCCESS** (4s) — run 38300456867, job 114981842501
- `Analyze Python`: **SUCCESS** (1m16s) — run 38300456864, job 114981842684
- `CodeQL`: **SUCCESS** — `Analyze (python)` SUCCESS (2m17s, run 38300452921, job 114981831208), `Analyze (javascript-typescript)` SUCCESS (47s, run 38300452921, job 114981831646)
- All required checks green for the implementation head at report drafting: **yes — 10/10**
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Bounded production-transport qualification smoke (literal implementation head)

- Result: PASS — qualified on the LITERAL implementation head (the report commit is documentation-only and postdates the run; the working tree was verified equal to HEAD `e8da2b6afa26679e78e838a7fbd3ceb9391d3f47` — tracked files clean — before the run; the SHA is recorded in the retained artifacts: `smoke-run-head-e8da2b6.out` header line and `smoke-evidence-HEAD-e8da2b6.json`). No pre-commit or alternate-client claim is made.
- Production path: the smoke used the production `new_client()` (evidence fingerprint: transport `VettedHTTPTransport`, backend `VettedNetworkBackend`, `trust_env: false`, `Accept-Encoding: identity` sent) and `collect_bundle(...)` with the production CLI review tail (`validate_bundle` → `_finalize_review_pipeline`, stage "live collection").
- Scope selection from FETCHED current facts (2026-10-12): scope prefetch fetched `pricing.md` (23,231 B, sha256 `e0767b50…c929`) and `models.md` (12,144 B, `150ad20e…44cc`) in 2 attempts / 0.386 s; 120 pricing rows, 102 index IDs, 40 standard candidates, 29 eligible (23 index-eligible); candidate order `[babbage-002, davinci-002, gpt-3.5-turbo, gpt-4.1, gpt-4.1-mini]`.
- Candidate attempts (each a fresh bounded invocation with its own ≤24-attempt / ≤8 MiB / ≤120 s context):
  - Attempt 1 `babbage-002`: 4 attempts / 807,933 B / 0.765 s; sources 200: `models.md`, `models/babbage-002.md` (3,077 B, `2bf7fd23…`), `pricing.md`, OpenRouter catalog (769,481 B, `30a8d7b8…`); BLOCKED (`page_no_chat` → `collection_empty_bootstrap`, `gate:completeness`, `missing_required_selection`), exit 20; sealed run `collect-20261012-195340-c96e23776cf7`.
  - Attempt 2 `davinci-002`: 4 attempts / 807,927 B / 0.778 s; same set with `models/davinci-002.md` (3,071 B, `b7334cd0…`); BLOCKED with the same safe codes, exit 20; sealed run `collect-20261012-195341-9738e0ae145f`.
  - Attempt 3 `gpt-3.5-turbo`: 5 attempts / 809,661 B / 0.893 s; adds `www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` (1,547 B, `569019b3…`) plus `models/gpt-3.5-turbo.md` (3,258 B, `b4c0d862…`); **READY** — "all recomputed gates verified; no review findings", 0 blockers, 0 review findings, exit 0; proposed `openai/gpt-3.5-turbo`; sealed run `collect-20261012-195342-89b30799e894`.
- All real requests: HTTP 200, exactly 1 attempt each, 0 redirects, 0 retries. Totals for the head run: 15 real HTTP attempts (scope 2 + 4 + 4 + 5), 2,460,896 charged body bytes, 2.822 s network wall; every invocation stayed far inside the 24-attempt / 8 MiB / 120 s smoke caps (max per invocation: 5 attempts, 809,661 B, 0.893 s).
- Offline verification (HTTP/DNS/socket forbidden — `socket.getaddrinfo`/`connect`/`connect_ex` replaced by refusal counters): `verify_run` on all three sealed runs returned `valid: true` with checks `digests: ok`, `hmac: ok`, `sql_evidence: replayed from sealed bytes (no SQL executed during verification)`, `artifacts: ok`, `validation: ok`, `report: ok`, `correspondence: ok`; the selected run reports `state: READY`. 0 refusal events (no network primitive was invoked offline). The seal key is the same synthetic external 32-byte HMAC key loaded through the sanctioned `load_seal_key_bytes` (anchored, 0600, 64-hex), never printed. No inference, no auth, no DB writes.
- Deferred (explicitly UNCLOSED, reported not hidden): the acquisition-versus-intact-replay label (runner-measured acquisition versus supplied/replayed data) and exact installed tooling identity are NOT closed by this smoke; they remain REQUIRED in a later same-PR continuation.

## Local setup / dependencies

- Packages/tools/services installed or configured: none. The strategic dev venv (`/tmp/slaif-181c-strategic-venv`, Python 3.12.15, httpx 0.28.1 / httpcore 1.0.9, pytest, ruff) was used for tests/lint/docs only; no package was installed, upgraded, downgraded, or removed anywhere; the copied checkout `.venv` remains broken and was preserved.
- Owned scratch: `/tmp/slaif-181f-agent` (reused; mode 700) holding the smoke script (v3), the synthetic external seal key (0600), the sealed run directories, and the retained evidence artifacts, now including `smoke-evidence-HEAD-e8da2b6.json` and `smoke-run-head-e8da2b6.out`. Scratch only; nothing outside the allowed repo paths was changed.
- Network usage: ONLY the bounded qualification smoke — 15 unauthenticated official GETs (scope 2 + 4 + 4 + 5), all HTTP 200, no auth headers, no inference, no DB. Library design facts were taken from the installed venv sources (httpx 0.28.1, httpcore 1.0.9); the one small unauthenticated official documentation read authorized by the order was NOT needed this round.
- No `.env`, no protected credentials, no private files, no production database/import, no real email, no deploy/tag/release. No `sudo`-level setup.

## Documentation

`docs/catalog-refresh.md` now states the 181-g transport and accounting guarantees: the global-unicast guard (positive `is_global` plus explicit exclusions; RFC 6598/documentation/NAT64 refused; deadline-bounded; connect-time re-vetting on the bound answer set); overflow debited in full with terminal exhaustion and the bounded crossing-read limit; the 120 s deadline enforced at the actual operations (owned killed/reaped resolver child, deadline checks and clamped timeouts at every candidate-IP connect, post-connect and post-TLS transitions — expired sockets closed before failure — and inside the partial-send loop; the 120 s no-context DNS cap; the honest platform limits: spawn overhead, 5 s reap safety net, injected-seam limit); and safe `final_url` provenance (only the last validated safe URL, or absent). `docs/cli-reference.md` and `admin/catalog-refresh/README.md` required no transport wording (verified by inspection; both unchanged). `scripts/check_documentation.py` OK (91 files).

## Safety and scope confirmations

- Unrelated files changed: no — the implementation commit touches exactly the eight allowed paths; untracked `CODEX-SESSIONS.md`, `codex.sh` preserved (not committed); ignored `.codex/`, `.local-provider-catalog/`, linked worktrees, and all historical reports (181-a…181-f) untouched.
- Allowed-path discipline: the CLI file `app/slaif_gateway/cli/catalog_refresh.py`, dependencies, Dockerfile/Compose, workflows, schema/bundle/capture/seal/rendering, `source_evidence` pricing/parser policy, and all runtime gateway surfaces are unchanged; the delta is confined to the acquisition subsystem plus its tests/docs/order/active.
- Production secrets accessed: no. Production systems accessed: no. No secrets, DB URLs, or raw exception text appear in this report (safe status/counts/hashes/timestamps/codes only; synthetic probe markers are identified, never reproduced in full).
- Required tests skipped/not run: yes — full local DB/Redis/Docker/HPC/browser matrix not run locally (out of scope per the order); GitHub CI ran the full matrix at the implementation head (10/10 SUCCESS).
- Scope deviation: no — no merge or auto-merge of any kind; no new PR; PR 318 amended only; no release/tag/production authority exercised.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO (`autoMergeRequest: null` preserved)
- Activated order and `oap/active` edited by coding agent: NO (order sha256 `0eaf1a0b92b8a51a621a1b076bec7563530b81a3f22a3fdef509c742973a23a4` and exact 5-byte active `181-g` verified at commit and at publication; committed byte-unchanged)
- Report-publication commit changes only this report file: yes (verified by staged diff before the commit)
- Real upstream/provider calls: only the bounded qualification smoke described above. No real email. No inference. No production DB. No tags/releases.
- Report layout redesign: none — follows the established 181-x report structure

## Known limitations / blockers

- No CI blockers remain: all ten required checks are SUCCESS at the implementation head.
- Objective 181 is NOT closed by this round: runner-measured acquisition versus supplied/replayed data (intact replay's misleading live label) and exact installed tooling identity remain REQUIRED in a later same-PR continuation and are reported here as deferred, not hidden. Objectives 182 (isolated Codex), 183 (atomic audited apply/accounting), 184 (final administrator workflow) remain pending; no 182 while 181 is unresolved.
- The 181-f round is NOT accepted: its immutable `COMPLETE` claims are overridden by the six independently reproduced findings this round repairs; this report does not retroactively claim 181-f acceptance.
- The deadline is enforced before every NEW operation and inside the partial-send loop; one already-started operation may complete slightly past expiry, bounded by its own deadline-clamped timeout — documented as an honest limit, not claimed as a hard stop mid-byte. The real resolver's cancellation is by SIGKILL of the owned child (uncatchable), with a bounded (5 s) reap safety net and small spawn overhead per resolution.
- An INJECTED resolver (unit-test seam only; production never injects one) is called in-process and cannot be killed mid-call: the deadline is enforced around it and between it and the next action — a documented seam limit, while the production default-resolver path is fully interruptible.
- A NON-NUMERIC malformed `Location` header is refused by httpx's own redirect bookkeeping before our manual re-validation and surfaces as the safe `transport_error` (bounded retries, no raw target text); parseable but policy-violating targets (credentials/query/fragment/host/out-of-range port) carry their exact safe codes. Both behaviors are pinned by tests.
- The global-unicast classifier is positive `is_global` plus explicit exclusions under Python 3.12 semantics; consequently 6to4 (`192.88.99.0/16`) classifies global and is accepted — recorded here for transparency rather than as an exclusion the order required.

## Recommended strategic follow-up

Factual recommendation only: the next same-PR continuation can proceed to the remaining REQUIRED 181 items — actual collection versus intact replay (runner-measured acquisition versus supplied/replayed data, including the misleading live label) and exact installed tooling identity — per the strategic plan. Merge of PR 318 remains the strategic model's delegated decision after independent verification of the final (report) head and its fresh checks.
