# OAP Work Order — 161-d

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 to correct the verifier-owned Codex
executable-provenance target proven by immutable 161-c. Preserve the exact
Codex 0.149 package entrypoint and all accepted 161-b/161-c catalog, image,
command, observer, fake-Local, accounting, privacy, and cleanup behavior; attest
both the published launcher and the exact Linux x64 native executable selected
by that launcher; then run exactly one fresh zero-retry pre-fix reproduction.

This remains a prove-before-fix verifier round. Do not modify production code
or documentation and do not implement assistant-history acceptance. If the
actual first full image and resumed crop reach Gateway and the exact assistant
`output_text` rejection is reproduced before Local, publish PASSED and stop for
strategic review. Any other result is FAILED and stops this round. Immutable
161-c must not be rerun, amended, or represented as anything other than FAILED.

## Exact current state and reason

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-d`; amend existing PR #298. Do not create a new PR.
- PR/branch: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`,
  `oap/161-codex-assistant-output-history`.
- Base: exact `main` commit
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-c activation head: `1f5ebed154406bfebc5a71d3cbacfd5ae7cf2254`.
- 161-c verifier implementation head:
  `1f74626f1bc9d180aef3fe85d2a67e056efe6fdc`.
- Immutable 161-c FAILED report/current PR head:
  `b564a33e72c4d2e91ba15133cf26c5df97bba865`.
- Report path:
  `oap/reports/161-c-vision-catalog-prefixed-reproduction.md`.
- The report commit changes only that report and its first parent is the
  literal implementation head. All ten checks on the current report head are
  successful.
- PR #298 is open, non-draft, mergeable/CLEAN, has no review threads or
  auto-merge, and remains the only Objective-161 PR.
- Objective 161 currently changes nine paths: its immutable OAP transcript,
  one verifier, and one verifier unit-test file. No production or documentation
  path has changed.
- Unrelated open PRs #224, #250, and historical #291 remain out of scope.
  Branch protection and repository rulesets are not enforced; this does not
  relax strategic merge authority or any review gate.
- The only release remains `v0.1.0-rc.1`; no release action is authorized.
- Frozen Local PR #7 remains open/CLEAN at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, with implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec` and successful CI.

161-c correctly added and tested the exact Local-005-q vision catalog facts.
Its one authorized run reached exact package version `0.149.0` but stopped
before client launch because `codex_binary_sha_mismatch`; no Gateway, Local,
provider, or protected request occurred. The report retained no actual digest
or installation path and made no production claim.

Independent strategic inspection of the exact public packages and exact
release source proves that the pin was applied to the wrong file class:

- root distribution `@openai/codex@0.149.0` has npm integrity
  `sha512-i4dryj2Y1j+00Mb5n+0n71EYnTK9/KDc2cdFo/dXD0d1oTog2bhUssKDEIOnKmnEf51P0Z/HJTWvTKw/UHyOvQ==`;
- its manifest maps `codex` to `bin/codex.js` and maps Linux x64 through the
  optional alias `@openai/codex-linux-x64` to
  `@openai/codex@0.149.0-linux-x64`;
- that Linux x64 artifact has npm integrity
  `sha512-uZXaN9JPxu0/jjnqqJeTd4kRYPnjVZK3MiVndfG1mHhEaoDKL7ScWHfPqvAEOjwsSDEmQSlMfUkmvYp/CHciYw==`;
- `node_modules/.bin/codex` is the relative link
  `../@openai/codex/bin/codex.js`; the resolved launcher SHA-256 is
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`;
- exact release source tag `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`, maps Linux/x64 to target
  `x86_64-unknown-linux-musl` and package `@openai/codex-linux-x64`, then
  launches `vendor/x86_64-unknown-linux-musl/bin/codex`;
- that exact native executable SHA-256 is the already accepted
  `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`.

The current verifier calls `read_bytes()` on the `.bin/codex` entrypoint, so it
follows the symlink and hashes the JavaScript launcher while comparing it to
the native-executable digest. This fully explains 161-c's fixed mismatch and
does not authorize weakening or removing executable provenance.

Abort and report any discrepancy in PR/base/head/report topology, unique-order
state, frozen Local authority, public package metadata, or exact Codex source
mapping. Never create a replacement PR.

## Exact allowed paths

Only these paths may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-d-attest-native-codex-and-reproduce-history.md`
- `oap/reports/161-d-attest-native-codex-and-reproduce-history.md`

Do not change any app, accepted fixture, Objective-160 verifier/test, Local
module, replay/HMAC, database/schema/migration, dependency/lockfile, CI,
doctrine, contract, or documentation path.

## Required provenance correction

Preserve the exact task-local `npm install --ignore-scripts --no-audit
--no-fund @openai/codex@0.149.0` acquisition and the `.bin/codex` launcher as
the client entrypoint. Do not use the host Codex, `npx`, a latest tag, a global
installation, an alternate architecture, or a broad filesystem search.

Implement one bounded fail-closed provenance helper used by the real run:

1. Require runtime platform Linux and architecture x86_64/x64. Any other
   platform/architecture is an explicit fixed failure for this profile.
2. Resolve only the task-root paths dictated by the exact package/source
   contract. Require every lexical and resolved path to remain beneath the
   task-owned installation root; reject path escape, unexpected symlink,
   missing, duplicate, non-regular, non-executable, or oversized targets.
3. Validate the root package manifest as exact distribution
   `@openai/codex@0.149.0` with `bin.codex = bin/codex.js` and the exact Linux
   x64 optional alias above. Validate the installed platform manifest as exact
   package version `0.149.0-linux-x64`, Linux, x64, with no inferred platform.
4. Validate the task-local package-lock entries, if the current npm creates
   the lock, against both exact public npm integrity values above. Missing,
   malformed, ambiguous, or unequal integrity is a fixed failure; do not
   disable the lock merely to avoid validation.
5. Require `.bin/codex` to be exactly the relative link
   `../@openai/codex/bin/codex.js`, resolving to the exact root launcher.
   Require launcher SHA-256
   `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`
   and a conservative launcher size bound.
6. Resolve exactly
   `node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex`
   as the source-selected native executable. Require a regular, non-symlink,
   executable file below the task root, a conservative 128 MiB maximum, and
   SHA-256
   `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`.
7. Require both the launcher and native executable to produce the exact bounded
   version line `codex-cli 0.149.0\n`. The immutable launcher hash plus exact
   package topology and source mapping must bind the invoked launcher to that
   native executable; continue invoking the launcher for catalog generation
   and the reproduction so client startup semantics remain unchanged.
8. Return only typed internal paths needed for invocation. Safe evidence may
   retain package names/versions, source tag/commit, public integrity/digest
   equality booleans, platform/target class, file type/size classes, and exact
   public expected digests. Never retain or print task/install paths, package
   output, environment values, or arbitrary errors.

Do not simply replace the existing constant with the launcher digest, remove
the native pin, hash whichever executable is found first, trust `--version`
alone, or accept a path from inherited environment state.

## Required tests and preflight

Add pure, synthetic-tree tests proving the exact positive launcher/native
topology and fail-closed cases for at least:

- wrong/missing root package name, version, bin mapping, or optional alias;
- wrong/missing platform package version, OS, CPU, or source-selected target;
- missing/malformed/ambiguous/wrong package-lock integrity for either package;
- entrypoint not a symlink, absolute/wrong symlink, symlink/path escape, or
  unexpected resolved launcher;
- launcher missing, non-regular, symlinked unexpectedly, oversized, or digest
  mismatch;
- native target missing, non-regular, symlinked, non-executable, oversized, or
  digest mismatch;
- unsupported runtime platform/architecture;
- launcher/native version nonzero or exact-output mismatch;
- no broad search, host executable substitution, raw path/value retention, or
  arbitrary-error emission.

Tests may inject synthetic expected digests or a bounded process runner so they
do not need digest preimages, npm, network, or a real Codex installation.
Preserve all 31 existing verifier/governance tests and every 161-b/161-c
negative. Do not weaken a pre-existing assertion.

Before the one reproduction, complete all of:

- complete `tests/unit/test_codex_0149_assistant_output_history.py`;
- active OAP governance tests;
- Ruff check and repository format check on both changed Python paths;
- Python compilation on both changed Python paths;
- exact provenance topology/integrity/digest/version tests;
- catalog canonicalization/source/privacy tests;
- `git diff --check`, exact allowed-path proof, and no report collision;
- push the final non-report implementation head to PR #298 and require all ten
  normal Gateway CI/CodeQL checks successful on that exact implementation head.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or
environment-blocked required evidence is not a pass. In-scope pre-reproduction
test or CI failures may be repaired, reverified, and repushed before the real
run. Once the real run begins, no verifier/test/product mutation is authorized.

## One exact reproduction

After every preflight above passes, run exactly one fresh zero-retry
reproduction for 161-d:

```text
exact task-local Codex 0.149.0 launcher
  -> exact attested Linux x64 native executable
       -> exact validated vision catalog
            -> unchanged Gateway base behavior
                 -> signed fake Local
                      -> fake provider
```

This is a newly authorized 161-d run, not a rerun or amendment of 161-c.
Acceptance requires all of:

- exact root and platform package identities and npm integrity equality;
- exact source tag/commit and Linux-x64 launcher-to-native mapping;
- exact launcher link, resolved target, SHA, version, and bounded-size facts;
- exact native target, SHA, version, regular/executable/bounded-size facts;
- validated exact Local-proven vision catalog facts from 161-c;
- one private session, initial valid full-image command, natural function/
  result and assistant-message lifecycle, then natural `resume --last` with
  the distinct crop;
- actual Gateway progression `200,200,400`, request/stream retry count zero;
- actual first request full-image wire class and actual rejected resumed
  request crop-image wire class;
- resumed request prior role `assistant`, exact content part `output_text`,
  exact fields `type,text`, bounded nonempty valid-Unicode text classification,
  and exactly one expected crop image;
- exact safe rejection code
  `responses_input_content_part_not_supported` and parameter
  `input[5].content[0].type`;
- fake Local remains exactly two signed requests and does not advance on the
  rejected turn;
- rejected pre-admission request creates no reservation, ledger, replay, or
  other side effect;
- exact fixed success line and complete task-owned cleanup.

Retain only public versions/integrities/digests/source pins, booleans, ordinals,
count/size/hash-equality classes, field/type/role enums, status/code/parameter
classes, Local delta, retry count, and cleanup facts. Never retain or print
prompts, assistant text, images/data URLs, bodies/SSE, IDs/call IDs, headers,
credentials/signatures, endpoints, DB URLs, private paths, package-manager
output, or arbitrary errors.

If any required predicate fails, publish FAILED and stop. Do not run a second
real reproduction, make another correction, or alter the verifier/test after
the run begins. PASSED proves only the exact pre-fix rejection and authorizes
no production correction by itself.

## Setup, security, privacy, and accounting boundaries

Routine task-local npm/network installation and safe disposable PostgreSQL
setup are authorized. Use only a generated test database under the existing
verifier's bounded setup; never run destructive setup against `DATABASE_URL`,
never use production data, and verify cleanup. No apt-based PostgreSQL install
is requested.

No production/protected credential, Local PR mutation, Qwen/protected model,
real upstream provider, external connector/tool, deployment, cutover, release,
or production system is authorized. Synthetic local credentials remain
ephemeral. The fake provider executes no hosted tool. PostgreSQL remains the
only accounting truth, and the expected rejected request remains
pre-admission/no-side-effect.

No prompt, completion, assistant text, reasoning, image, body, stream, tool
argument/result, raw identifier, secret, signature, endpoint, database URL,
private path, package-manager output, or arbitrary failure text may enter logs,
reports, commits, or durable evidence. Documentation is checked and no update
is needed because this round changes only verifier provenance and makes no
implemented compatibility claim.

## Boundaries and publication

No production behavior, documentation, accepted fixture, Local code,
protected service/traffic, provider inference, PR #291, release, newer Codex,
OpenCode, Antigravity, or future Gateway objective is authorized. Coding never
merges or enables auto-merge.

Preserve every prior order/report byte-for-byte. Commit and push the unchanged
strategic 161-d order and `oap/active` with the verifier/test implementation to
the same PR branch. Record the literal final non-report implementation head,
including any pre-reproduction repairs. Run the one reproduction only from
that exact clean committed implementation head after its ten checks pass.
After the run begins, publish exactly one immutable report without any other
mutation:

`oap/reports/161-d-attest-native-codex-and-reproduce-history.md`

The report must contain `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, exact topology/diff, package/source/
launcher/native provenance, preflight and implementation-head check statuses,
the one-run result, full/crop/history/error/Local/no-side-effect/privacy/cleanup
evidence, documentation impact, all deviations/skips, and these labels:

```text
PREFX-PROVENANCE-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = YES|NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The final commit changes only that report, has the implementation head as first
parent, and is the verified remote PR #298 head before exact response `OK`.
Checks triggered by the report-only commit may be pending at response time;
strategic independently waits for every final-head check. Return to the control
FIFO. Strategic alone decides the next continuation.
