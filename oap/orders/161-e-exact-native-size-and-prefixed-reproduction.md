# OAP Work Order — 161-e

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 to correct the single order-owned native
artifact size predicate exposed by immutable 161-d. Replace the guessed 128
MiB ceiling with exact byte-size equality for the already authenticated Codex
0.149.0 Linux x64 native executable, preserve every other provenance,
catalog, fixture, command, observer, fake-Local, privacy, accounting, and
cleanup gate, then run exactly one fresh zero-retry pre-fix reproduction.

This remains prove-before-fix. Do not modify Gateway production code or
documentation and do not implement assistant `output_text` history acceptance.
If exact provenance passes and the actual full-image/resumed-crop sequence
reproduces the expected Gateway rejection before Local, publish PASSED and stop
for strategic review. Any other result is FAILED and stops this round.
Immutable 161-d remains FAILED and must not be rerun, amended, or relabeled.

## Exact current state and strategic review

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-e`; amend existing PR #298. Do not create another PR.
- PR/branch: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`,
  `oap/161-codex-assistant-output-history`.
- Base and current remote `main`:
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-d starting head:
  `b564a33e72c4d2e91ba15133cf26c5df97bba865`.
- 161-d implementation head:
  `e6b2f94b9999dca6aa857706c79d80eff81261e7`.
- Immutable 161-d FAILED report/current PR head:
  `b26a016a2b753ce5a33d6bafaeec344b32c5060b`.
- Report path:
  `oap/reports/161-d-attest-native-codex-and-reproduce-history.md`.
- The report commit changes only that report and has the literal implementation
  head as its first parent. The implementation commit changed only the 161-d
  order/active pointer and the two verifier/test paths.
- All ten normal checks are successful on both the 161-d implementation head
  and current report head. PR #298 is open, non-draft, CLEAN/mergeable, with no
  review threads, reviews, or auto-merge, and is the only Objective-161 PR.
- Remote `main`, the only release `v0.1.0-rc.1`, unrelated PRs #224/#250, and
  historical PR #291 are unchanged and out of scope.
- Frozen Local PR #7 remains at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`, with successful CI.
- No Objective-161 round has changed an `app/`, dependency, schema, migration,
  CI, contract, accepted fixture, Local, Qwen, or documentation path.

161-d correctly implemented a bounded exact-package provenance helper and 58
verifier tests. It proved all of these public facts before stopping:

- root `@openai/codex@0.149.0` manifest and npm integrity;
- Linux x64 alias `@openai/codex@0.149.0-linux-x64`, manifest, lock entry, and
  npm integrity;
- exact `.bin/codex` link and source-selected launcher path;
- launcher SHA-256
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`;
- exact source tag `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`, target
  `x86_64-unknown-linux-musl`;
- native SHA-256
  `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`;
- native regular, non-symlink, executable file shape.

It then failed closed before version probes and before any reproduction because
the exact native artifact exceeded the order's guessed `128 * 1024 * 1024 =
134217728` byte maximum. Zero client, Gateway, Local, provider, or protected
requests occurred. No production behavior changed.

Independent strategic reinstallation of the exact public package after the
report proves:

```text
native path class = exact source-selected Linux x64 path
native byte size = 258322048
native SHA-256 = bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827
native mode/type = executable regular non-symlink file
launcher byte size = 7236
launcher SHA-256 = 134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477
root/platform npm integrity = exact 161-d expected values
platform distribution unpacked size metadata = 323045810
```

The matching manifests, two npm integrity records, source mapping, and both
digests rule out package drift. The impossible 128 MiB ceiling is an order
defect. Correcting it to exact native byte-size equality narrows provenance;
it is not risk acceptance or an arbitrary higher ceiling.

Abort and report any discrepancy in PR/base/head/report topology, exact public
package identity, source mapping, integrity, digest, or frozen Local authority.
Never create a replacement PR.

## Exact allowed paths

Only these paths may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-e-exact-native-size-and-prefixed-reproduction.md`
- `oap/reports/161-e-exact-native-size-and-prefixed-reproduction.md`

Do not change any app, accepted fixture, Objective-160 verifier/test, Local
module, replay/HMAC, database/schema/migration, dependency/lockfile, CI,
doctrine, contract, or documentation path.

## Required exact-size correction

Preserve the complete 161-d provenance implementation and every negative. Make
only the bounded changes needed to represent and verify the exact native size:

1. Introduce an explicit public expected native artifact size of exactly
   `258322048` bytes. Do not express the correction as an arbitrary larger
   maximum, percentage tolerance, filesystem-block size, MiB rounding, lower
   bound, or range.
2. Require native size equality before reading/hashing or invoking the file.
   A file one byte smaller or one byte larger fails with a fixed provenance
   error. Retain a hard read ceiling no greater than the exact expected size.
3. Preserve regular-file, non-symlink, executable-mode, root containment,
   exact lexical path, exact resolved path, package manifests, npm lock
   integrities, launcher link/digest, native digest, and launcher/native exact
   version probes.
4. Keep `.bin/codex` as the actual reproduction entrypoint. Do not invoke the
   host Codex, use `npx`, change package acquisition, search for executables,
   or substitute the native path as a behavioral workaround.
5. Allow the pure synthetic-tree tests to inject their synthetic expected
   native size without allocating the real 258322048-byte artifact. The real
   install path must always use the non-overridable public default.
6. Add explicit positive and negative tests for exact size, one-byte-under,
   one-byte-over, non-integer/boolean injection where applicable, and fixed
   error/privacy behavior. Preserve all 58 existing verifier tests and every
   161-b through 161-d negative unchanged in meaning.
7. Keep safe evidence limited to public package/source identities,
   integrities/digests, exact public expected byte sizes, equality booleans,
   fixed classes/counts, and the existing closed diagnostics. Never expose
   private paths, package output, or arbitrary errors.

Do not remove the size check, weaken digest/integrity checks, modify expected
digests, change the package version/platform, or steer the client scenario.

## Required preflight

Before the one reproduction, complete all of:

- complete `tests/unit/test_codex_0149_assistant_output_history.py`;
- active OAP governance tests;
- Ruff check and repository format check on both changed Python paths;
- Python compilation on both changed Python paths;
- exact size/provenance topology/integrity/digest/version tests;
- all retained catalog, image, command, source, observer, privacy, accounting,
  and cleanup tests;
- `git diff --check`, exact allowed-path proof, and no report collision;
- task-local package preflight proving exact root/platform identities,
  integrities, launcher/native topology, exact sizes, digests, and both version
  lines without making a Gateway request;
- push the final non-report implementation head to PR #298 and require all ten
  normal Gateway CI/CodeQL checks successful on that exact head.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or
environment-blocked required evidence is not a pass. In-scope failures may be
repaired, reverified, and repushed before the reproduction. Once the real run
begins, no verifier, test, product, order, or active-pointer mutation is
authorized.

## One exact reproduction

After every preflight passes, run exactly one fresh zero-retry 161-e
reproduction:

```text
exact task-local Codex 0.149.0 launcher
  -> exact attested 258322048-byte Linux x64 native executable
       -> exact validated Local-005-q vision catalog
            -> unchanged Gateway production behavior
                 -> signed fake Local
                      -> fake provider
```

This is a newly authorized 161-e run. It is not a rerun or amendment of 161-d,
which ran zero reproductions and remains immutable FAILED. Acceptance requires:

- exact root/platform package manifests and npm integrity equality;
- exact source tag/commit and Linux-x64 launcher-to-native mapping;
- exact launcher link, resolved target, 7236-byte size, SHA, version, and file
  shape, retaining the existing bounded launcher check;
- exact native target, 258322048-byte equality, SHA, version, regular/
  non-symlink/executable shape;
- exact 161-c Local-proven vision catalog facts;
- one private session, initial valid full-image command, natural function/
  result and assistant-message lifecycle, then natural `resume --last` with
  the distinct crop;
- actual Gateway progression `200,200,400`, request/stream retry count zero;
- first request full-image wire class and rejected resumed request crop-image
  wire class;
- resumed prior role `assistant`, exact content part `output_text`, exact
  fields `type,text`, bounded nonempty valid-Unicode text classification, and
  exactly one expected crop image;
- exact safe rejection code
  `responses_input_content_part_not_supported` and parameter
  `input[5].content[0].type`;
- fake Local exactly two signed requests with no rejected-turn advance;
- rejected pre-admission request creates no reservation, ledger, replay, or
  other side effect;
- exact fixed success line and complete task-owned cleanup.

Retain only public source/package/integrity/digest/size facts, booleans,
ordinals, bounded count/size/hash-equality classes, field/type/role enums,
status/code/parameter classes, Local delta, retry count, and cleanup facts.
Never retain or print prompts, assistant text, images/data URLs, bodies/SSE,
IDs/call IDs, headers, credentials/signatures, endpoints, DB URLs, private
paths, package-manager output, or arbitrary errors.

If any required predicate fails, publish FAILED and stop. Do not run a second
reproduction, make a second correction, or alter implementation/tests after
the run begins. PASSED proves only the exact pre-fix rejection and does not
authorize production acceptance by itself.

## Setup, security, privacy, and accounting boundaries

Routine task-local npm/network installation and safe disposable PostgreSQL
setup are authorized. Use only the existing verifier's generated test database
path; never run destructive setup against `DATABASE_URL`, never use production
data, and verify cleanup. No apt-based PostgreSQL install is requested.

No production/protected credential, Local PR mutation, Qwen/protected model,
real upstream provider, hosted tool, connector, deployment, cutover, release,
or production system is authorized. Synthetic local credentials remain
ephemeral. PostgreSQL remains accounting truth, and the expected rejected
request remains pre-admission/no-side-effect.

No prompt, completion, assistant text, reasoning, media, body, stream, tool
argument/result, raw identifier, secret, signature, endpoint, database URL,
private path, package-manager output, or arbitrary failure text may enter logs,
reports, commits, or durable evidence. Documentation is checked and no update
is needed because this round is verifier-only and makes no implemented
compatibility claim.

## Publication and stop law

Preserve every prior order/report byte-for-byte. Commit and push the unchanged
strategic 161-e order and `oap/active` with the verifier/test implementation to
the same PR branch. Record the literal final non-report implementation head,
including any pre-reproduction repair. Run the reproduction only from that
exact clean committed head after all ten checks pass. After the run begins,
publish exactly one immutable report with no other mutation:

`oap/reports/161-e-exact-native-size-and-prefixed-reproduction.md`

The report must contain `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, exact topology/diff, package/source/
launcher/native size and provenance evidence, preflight and implementation-
head checks, one-run result, full/crop/history/error/Local/no-side-effect/
privacy/cleanup evidence, documentation impact, every skip/deviation, and:

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
parent, and is the verified remote PR #298 head before response `OK`. Checks
triggered by the report-only commit may be pending at response time; strategic
must verify every final-head check. Coding never merges or enables auto-merge.
Return to the control wait. Strategic alone decides the next continuation.
