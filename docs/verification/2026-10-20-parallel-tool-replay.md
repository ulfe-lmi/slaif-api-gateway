# Parallel tool replay follow-up — 2026-10-20

The reported HTTP 400 at input[10] is the core adjacent-pair validator, not
throttling or a network disconnect. Two real Qwen A100 requests near 21:12 UTC
completed with finalized usage before the next history request was rejected.
Ordinary logs do not retain the rejected request body, so its exact item order
is not claimed as captured evidence.

A separate natural-client reproduction used the installed exact Codex 0.162.1
binary in exec mode, its shipped revision-10 preset, explicit qwen3.8-27b model
selection, and a synthetic local SSE endpoint. Two harmless printf calls were
returned in one response, naturally executed by Codex, and then replayed as
call-call-result-result. The existing core validator rejected that next request
with responses_codex_tool_roundtrip_invalid. The client sent
parallel_tool_calls=false: current generation preference cannot be used to
invalidate already-present parallel history. No production capture was enabled.

The fixed core validates preceding-call identity and result kind, exactly one
result per call, unique invocation/item IDs, declared taxonomy and independent
capabilities. Pending calls cannot cross new user/system/developer input,
declarations or compaction. Existing input/byte ceilings bound all maps.
Reasoning and assistant commentary retain their positions. Existing HMAC
same-key/route/expiry ownership verification still runs for every replay call.
No history is repaired, reordered, dropped or synthesized. This is a producer/
consumer state-machine correction; it introduces no new preset settings,
operator ceilings, credentials or authorization capabilities.

After restarting the synthetic endpoint with the corrected validator, the exact
same failed Codex conversation resumed, consumed both existing tool outputs and
completed successfully. A later turn also completed. A separate fresh two-call
run completed naturally. The structural receipt, including executable digest,
is tests/fixtures/codex/presets/parallel-tool-replay.json. The receipt stores no
raw invocation/item/session IDs, prompt bodies, arguments, output or secrets.
This is exact exec-mode consumer evidence, not a claim that every interactive
CLI configuration is qualified. Initial interactive fixture attempts encountered
an unrelated mcp__codex_tui declaration; those are excluded from this receipt.

Focused existing/new request-policy checks passed 255 tests. The final new
regression file passed 18 cases, covering natural parallel history, reversed
result order, mixed function/custom output, preserved context, invalid graphs
and independent gates. Relevant disposable PostgreSQL checks passed 37 tests
in 23.23 seconds. The first full unit run had 5,305 passes, one skip and
one documentation failure: the newly linked verification file had not yet been
written when the checker ran. No runtime test failed. A complete stable-tree
rerun and live-deployment results follow after execution.
Only the explicit manual Codex calls use Codex; normal pytest never invokes it.

Documentation impact: the Responses and forwarding contracts now describe
identity-based parallel pairing, and AGENTIC_CLIENT_INTEGRATION.md replaces the
incorrect adjacency requirement while retaining all ownership requirements.
No new compatibility profile, full-release/HPC qualification or merge is claimed.


The stable-tree full rerun passed **5,309 tests**, with one skip and 12 warnings,
in **155.73 seconds**. The skip is the unavailable legacy Codex 0.148 binary.
This rerun includes all 18 final new regressions. Ruff and whitespace checks
also passed. Both full-run outcomes remain recorded separately; the first
documentation failure is not relabeled as a successful run. Normal tests used
no real upstream inference, production test database or email. The owned
PostgreSQL 16 container was removed. Full browser/HPC qualification was not run.

Executed test commands inside the isolated Python 3.12 image included:

```text
python -m pytest -p no:cacheprovider -n4 tests/unit --junitxml=/evidence/parallel-unit-final.xml
python -m pytest -p no:cacheprovider tests/unit/test_codex_parallel_tool_replay.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_multiturn_replay.py
python -m pytest -p no:cacheprovider tests/unit/test_codex_parallel_tool_replay.py
python -m pytest -p no:cacheprovider tests/integration/test_compatibility_presets_postgres.py tests/integration/test_codex_module_upgrade_postgres.py tests/integration/test_codex_replay_references_postgres.py tests/integration/test_codex_context_accounting_postgres.py tests/integration/test_accounting_finalization_postgres.py
python -m ruff check --no-cache app tests
git diff --check
```

The review is draft PR #338, stacked on unmerged PR #337. The runtime source
commit is `58c45db770b55c0b449b037af2d9a4f336b89aaa`; no PR was merged.


## Software-only deployment and live inference

Deployment completed at **21:29:05 UTC**. Source commit
`58c45db770b55c0b449b037af2d9a4f336b89aaa` is running in image
`sha256:25eb31e0d44ca5ca0287a2fa135b8fcc28f00b14167b4e5a8c3a70748b4346d5`.
Five relevant runtime files were SHA-256 compared to canonical source.
Readiness and public HTTPS health checks passed. Existing preset revision 12,
digest `763877f4d1cbddceae223b5b892355d61968cc0efb4a9d97ade6e091bed64634`,
and the input-item ceiling of 1,024 remain unchanged. All **42** pre-deployment
key credential/configuration digests matched after deployment and again after
live tests. New keys were permitted concurrently and no key, credential,
throttling policy, preset pin, quota policy or migration was modified.
Software rollback uses the saved prior image/Compose file, never DB restoration.
Incoming request capture stayed off.

The existing qwen-students credential/profile, exact Codex **0.162.1 exec** and
explicit model **qwen3.8-27b** completed a real inference sequence. Qwen emitted
two exec_command calls in one response; Codex executed harmless printf commands
and naturally saved/replayed call A, call B, result A, result B. The tool-result
request completed, then a resumed follow-up turn completed. The gateway ledger
shows three successful HTTP 200 streams at 21:29:23, 21:29:30 and 21:29:56 UTC,
all requested/resolved to qwen3.8-27b through **neumann**, with finalized
accounting and finalized reservations. This is real Qwen A100 verification,
not the default OpenAI model. The structural receipt records that ordering
without tool bodies or raw identifiers. YOLO was selected only on these owned
verification processes; profile and key defaults were not changed.

The user can retry/resume valid parallel history without starting a new chat,
provided its ordinary ownership/expiry/route checks still pass. This does not
repair malformed JSON or bypass expired/missing replay references. The earlier
malformed-history limitation remains distinct from this corrected valid-history
rejection. No claim is made that the user's rejected body was captured or that
its exact hidden item ordering was directly observed.
