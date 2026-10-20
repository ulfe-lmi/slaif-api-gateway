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
