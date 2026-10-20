# Responses stream failure follow-up — 2026-10-20

The human authorized a generic stream-error fix with a 30-minute target and
explicitly required that existing and newly created keys remain unchanged.
No key migration, policy update, rotation or database restoration is part of
this deployment.

Gateway evidence showed repeated upstream HTTP 400 responses whose sanitized
error was an unterminated JSON string at character 8. Structural examination of
the local client transcript found one malformed exec_command argument record
with exactly that parse position. No argument text, prompts, image bytes or
credentials were persisted in this report. This is separate from quota or
throttling. The old stream had already committed HTTP 200 before the provider
rejected the request, then emitted a typed error that the pinned consumer did
not treat as a general terminal API failure.

The exact Codex 0.163.0 consumer contract is source commit
`83086188ae0614bd882818ff1aa23f3194962012`, file
[codex-api/src/sse/responses.rs](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/codex-api/src/sse/responses.rs).
Its ordinary type:error branch handles Flex unavailability only, whereas
response.failed parses response.error. The server change uses that standard
failure envelope after streaming starts and preserves ordinary HTTP errors
before streaming starts.

The correction does not silently repair the already-damaged conversation.
Malformed replay returns a clear HTTP 400 explaining how to start a new
conversation or rewind. Files on the client remain intact. Valid new
conversations retain their normal tool loop and accounting behavior.

Validation: the full unit suite passed 5,290 tests with one skip (legacy Codex
0.148 binary unavailable), in 156.47 seconds. The final two new regression
files passed 34 tests, including transport-send failure cleanup, in 11.48
seconds. Existing focused HTTP/SSE/codec coverage passed 106 tests; the earlier
combined run passed 137. Relevant PostgreSQL integration coverage passed
37 tests in disposable isolated databases. Ruff and diff whitespace checks
passed. Normal tests made no real upstream calls and sent no real email.

The exact installed Codex 0.163.0 executable (SHA-256
`399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`)
was also manually tested against a local synthetic endpoint, with retries
explicitly disabled for that test. Early failure displayed the HTTP 400
message. Midstream failure displayed the actual response.failed error message
rather than the generic missing-completion message. The structural receipt is
`tests/fixtures/codex/presets/stream-error-consumer.json`. Synthetic sessions
and their local server were stopped. Ordinary transient retry behavior remains
client-controlled. This is not a release or full Codex qualification claim.


## Deployed trial and real-client verification

Software-only deployment finished at **16:05:41 UTC**, within the human's
30-minute target starting at 15:48:09 UTC. Readiness and public HTTPS health
checks passed. All five existing key credential/configuration digests matched
before and after deployment and again after the live checks. New-key creation
was allowed concurrently. No key mutations, migrations, database restoration,
or external-preset changes occurred. The active preset remains revision 12,
digest `763877f4d1cbddceae223b5b892355d61968cc0efb4a9d97ade6e091bed64634`;
the already-configured input-item ceiling remains 1,024.

The deployed image is
`sha256:03ffbda48e79211276119772b9ede12ce476d8161e69d83a0f5ad09bc9e19d5c`.
Its local build label is commit
`e07e9d8a1b847c5a4c88db9e6f2a0a6d43e84511`; canonical GitHub runtime source
is commit `7b2d69cacc91ab96e095de501d80c7c2b439646a`, with identical tree
`8bed479d7c3b609b8c088e62a24352dc81c6b42d`. All four changed runtime files
were individually SHA-256 compared between the running container and that
canonical source. Local backup/receipt paths are in the operator state directory;
no database backup or restore is involved in software rollback.

A fresh interactive **Codex 0.163.0**, using the existing `qwen-students`
profile and existing credential, explicitly showed model **qwen3.8-27b**.
It executed one harmless local printf command, consumed the tool result,
completed its reply, and answered a second user turn without reconnecting.
The gateway ledger records three corresponding successful HTTP 200 streams
at 16:06:20, 16:06:30 and 16:06:59 UTC, all routed through **neumann** to
**qwen3.8-27b**, with finalized accounting and finalized reservations. This
was real Qwen A100 inference, not the default OpenAI model. YOLO was selected
only for this isolated manual verification process; the profile default and
all key settings stayed unchanged. That verification process was stopped.

A separate intentionally malformed replay, using a valid recent same-key/
same-route reference, returned an ordinary **HTTP 400 application/json** with
`vllm_replay_arguments_invalid` and the fixed fresh-conversation/rewind guidance.
It did not open a successful SSE stream. A minimal replay of the old interrupted
call instead returned HTTP 404 `responses_codex_replay_reference_not_found`;
the same-key reference guard remains active, and this is not described as
successful recovery of damaged history. Existing damaged sessions still need
a fresh conversation or a rewind. Client files are unaffected.

Commands executed in the Python 3.12 test image included:

```text
python -m pytest -p no:cacheprovider -n4 tests/unit --junitxml=/evidence/stream-fix-unit.xml
python -m pytest -p no:cacheprovider tests/unit/test_responses_stream_failures.py tests/unit/test_vllm_function_arguments.py
python -m pytest -p no:cacheprovider tests/integration/test_compatibility_presets_postgres.py tests/integration/test_codex_module_upgrade_postgres.py tests/integration/test_codex_replay_references_postgres.py tests/integration/test_codex_context_accounting_postgres.py tests/integration/test_accounting_finalization_postgres.py
python -m ruff check --no-cache app tests
git diff --check HEAD^ HEAD
```

The full unit run preceded the final additional transport-send/accounting test;
the 34-test focused run includes that test. PostgreSQL used an owned disposable
PostgreSQL 16 container, subsequently removed, never the production DATABASE_URL.
This was targeted verification, not the full browser/HPC/release matrix.
Manual live Qwen inference is explicitly separate from the offline test suite.
The review is draft PR #337, stacked on unmerged PR #336. No PR was merged.
