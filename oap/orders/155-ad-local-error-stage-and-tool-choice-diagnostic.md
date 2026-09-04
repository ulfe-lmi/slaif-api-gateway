# OAP Work Order — 155-ad

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 1708eea898d6f1403518dd78897a119366a62652

## Human-authorized exact exception and scope

The human explicitly authorized `155-ad` on existing PR #291 after the restored
immutable 155-ac FAILED report head
`1708eea898d6f1403518dd78897a119366a62652`.

This is one exact OAP naming/scope exception and diagnostic-harness correction only.
It does not authorize `155-ae`, a general multi-letter continuation scheme, any
Gateway product change, Local Coding change, Qwen or Codex change, reasoning-
placeholder canonicalization, fabricated reasoning identity, validation relaxation,
architectural refactor, merge, auto-merge, cutover, or release.

Preserve every previous activated order and report as immutable. Publish exactly one
155-ad report and never edit that report after its first publication commit, including
after context compaction, restart, wording review, pending CI, or a failed final
reconciliation.

## Objective and reason

Answer one bounded question reliably:

> Why does the exact pinned Codex 0.149.0 first request receive a Local Coding 4xx
> before protected Qwen inference is invoked?

155-ac proved the protected runner actually invoked task-local
`@openai/codex@0.149.0`; host-default 0.149.1 was not used. Its exact pinned first
turn still produced Gateway 1 / 2xx SSE, Local 1 / 4xx JSON, Qwen 0, with three
message input items and top-level tool taxonomy custom 1, function 5, tool-search 1,
and web-search 1. It did not reach the second request or prove the ID-less reasoning
placeholder predicate.

The 155-ac diagnostic was insufficient because it projected Local response errors
through `_SUMMARY_GATEWAY_ERROR_CODE_CLASSES`, collapsing a fixed Local rejection to
`other`, and it did not implement the required Local rejection-stage classifier.
Correct only this evidence apparatus. Do not attempt to make the integration green.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, without auto-merge, at
  restored report head `1708eea898d6f1403518dd78897a119366a62652`.
- That report commit's first parent is diagnostic implementation head
  `b32c50b92cccba229b37a9abb642611f3f8dc588`; it changes only
  `oap/reports/155-ac-pinned-provenance-first-turn-stabilization-and-predicate.md`.
  The protocol-violating later amendment was removed by an exact human-authorized
  force-with-lease repair and is not the branch head.
- All ten restored report-head checks pass. Remote `main` remains
  `7ffce834915b74809109e8b579d8541cdcfa9df7`; the Gateway worktree is clean.
- Local Coding PR #7 remains read-only and clean at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`, checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- The 155-ac verifier-only provenance implementation remains on the branch; no
  Gateway `app/` product file changed in 155-ac. The system host Codex reports 0.149.1
  but is diagnostic only.
- The repository selector test currently allows ordinary one-letter identifiers plus
  exact `155-aa`, `155-ab`, and `155-ac`; add only exact `155-ad` and continue to
  reject `155-ae` and every generalized/malformed multi-letter form.
- The private protected-runtime reference will be supplied as an owner-only mode-0600
  regular file with its exact two-key shape. Never render or retain its values.

## 1. Dedicated Local error vocabulary

Derive a new Local-Coding-specific closed error-code vocabulary from the production
paths at immutable Local head `4d3ab2f...`. Keep it independent of
`_SUMMARY_GATEWAY_ERROR_CODE_CLASSES`; add a source/AST or other deterministic check
against that exact immutable checkout so the mapping cannot silently drift.

The closed Local vocabulary must distinguish exact fixed codes or tightly bounded
source-defined families needed for:

- service Bearer authentication/unavailability;
- signed-identity header, method, path, version, field, timestamp, nonce, signature,
  secret/clock, route, and replay rejection;
- endpoint/body-size/JSON/nesting/model/route/image-policy rejection;
- Responses tool-policy invalidity and disabled-tool-choice rejection;
- observation/constitution/injection rejection, with constitution suffixes allowed
  only from the immutable Local source enum;
- upstream credential, timeout, transport, response-size, or returned-error paths;
- `none` for non-errors and `other` for everything not explicitly source-reviewed.

Do not reuse or widen the Gateway code set. An unknown, malformed, non-string,
oversized, duplicate, or source-unproved Local value maps to `other` and makes final
classification fail closed. Retain no Local error message or arbitrary code text.

Add pure tests proving representative exact Local codes map only to their correct
closed Local class, every cross-class substitution fails, Gateway-only codes do not
enter the Local vocabulary, Local-only codes do not enter the Gateway vocabulary,
and unknown values remain `other`.

## 2. Local rejection-stage projection and boundary evidence

Map the source-reviewed Local code plus existing bounded Local/Qwen metrics to exactly
one stage from:

    service_auth
    signed_identity
    json_route_image
    tool_policy
    observation_constitution
    upstream
    other

The mapping must follow immutable Local execution order, not inference from HTTP
status alone. Add tests that mechanically bind every supported mapping to the exact
Local source path and reject ambiguous or contradictory combinations.

Retain bounded boundary states for Local Responses tool policy, observation,
constitution/compiler, and upstream inference. Each is one of a closed set such as
`not_reached`, `entered`, `transformed`, `rejected`, or `succeeded`, but expose only
states supported by an existing fixed response code and/or before/after metric delta.
In particular, for route policy `drop_disabled_codex_search`, distinguish whether the
policy was not reached, reached unchanged, transformed by removing disabled search
declarations, or rejected before observation/constitution/upstream.

Query only existing Local metrics. Do not add logging, metrics, hooks, code, or other
instrumentation to Local Coding. Metric names/labels must be source-reviewed and
allowlisted; retain only bounded delta classes and never raw metric text or arbitrary
labels.

## 3. Bounded first-request tool-choice classifier

Add a privacy-safe classifier for the first request's top-level `tool_choice` with
exactly these result classes:

    absent
    automatic_none
    required
    explicit_disabled_search
    explicit_retained_local
    malformed_other

Use the immutable Codex/Gateway request contract and Local
`drop_disabled_codex_search` policy. The classifier may traverse only bounded,
allowlisted structural fields and must apply deterministic precedence when a shape
references both disabled and retained tools or is otherwise ambiguous; ambiguous
shapes are `malformed_other` and fail closed.

It may transiently compare an explicit choice to the bounded declarations in task
memory, but may not retain names, values, schemas, descriptions, namespaces,
arguments, IDs, prompt/content, or the request body. Add tests for absent; string and
reviewed object automatic/none; required; exact disabled `tool_search` and
`web_search`; reviewed retained function/custom forms; mixed/smuggled/duplicate,
nested, malformed, oversized, unknown, and control-character forms.

This is evidence only. Do not modify Gateway or Local tool policy or hosted-tool
authority.

## 4. Preserve and complete provenance/signing evidence

Retain the 155-ac executable invariant and tests:

- exact requested package `@openai/codex@0.149.0`;
- package metadata, raw version, and invoked version all exact 0.149.0;
- verified task-local executable object is the one used for model catalog and command;
- host-default 0.149.1 is not invoked and is diagnostic only;
- mismatch or fallback stops before any network/provider activity.

For the captured Gateway-to-Local first request, independently verify in task memory:

- exact service Bearer equality;
- exactly one of every required signed header and no extra internal signed header;
- method/path/query and exact raw body participate in canonical signing bytes;
- independently reconstructed canonical bytes verify the HMAC signature;
- signed route matches the configured Local route;
- version, timestamp, and nonce shapes are valid.

Retain only closed service-auth/signed-identity classes and booleans. Never retain or
emit the service token, signing secret, signature, canonical bytes, body or body
digest, principal/session/repository/route values, nonce/timestamp values, raw header
names/values beyond fixed allowlisted boolean tests, or request identifiers. These
independent checks do not bypass Local authentication or replay protection.

## 5. Pre-protected acceptance of the diagnostic apparatus

Before any protected request:

1. update exact 155-ad topology/order/active/task/temp anchors and the selector test;
2. add pure/fake tests for independent Local/Gateway vocabularies and every Local
   stage mapping against immutable Local source;
3. cover service-auth failure; signed header/field/signature/timestamp/replay failure;
   route/model/JSON/image rejection; tool-policy malformed and disabled choice;
   observation/constitution/injection rejection; upstream rejection; unknown fallback;
4. cover every tool-choice class and mixed/smuggled/malformed/unbounded negatives;
5. cover successful and failed independent exact-body/signature verification without
   retaining inputs;
6. cover compiler-only versus inference boundary states, contradictory/duplicate/
   misaligned evidence, cardinality/order/size bounds, and privacy canaries;
7. keep all existing pure/fake qualification, provenance, replay, accounting, route,
   stream, and privacy gates green;
8. run full Ruff, compilation, focused verifier/capture/governance tests, and at least
   one normal fake two-turn qualification plus the relevant forced Local failure
   matrices;
9. prove by diff/source checks that no `app/`, Local, Qwen, product contract, fixture,
   dependency, or lockfile changed.

Commit and push the diagnostic implementation head and require all ten PR checks
green on that exact head. No protected traffic occurs first.

## 6. Exactly one protected process

On the exact clean, green diagnostic head, execute one zero-retry process only:

real task-local Codex 0.149.0 -> Gateway -> unchanged Local Coding at
`4d3ab2f...` -> unchanged protected Qwen.

Do not change prompt, tool declarations, Local configuration, constitution/compiler,
route, model, credentials, or runtime behavior to steer around the failure. Run direct
stdout only without redirection, piping, command substitution, or prohibited-value
retention.

If turn 1 again yields Gateway 1 / Local 1-4xx / Qwen 0, publish only:

- exact safe task-local Codex provenance class;
- first request profile, bounded input/tool taxonomy, and tool-choice class;
- exact allowlisted Local error class and Local rejection stage;
- service-auth, required-header, exact-body/signature, route, timestamp/nonce, and
  extra-internal-header verification booleans/classes;
- tool-policy, observation/constitution/compiler, and upstream boundary states;
- Qwen compiler/inference count and status classes;
- accounting terminal class and zero-pending state.

Then stop. Do not fix the diagnosed owner in 155-ad.

If the first turn unexpectedly reaches Local 2xx and Qwen inference 2xx SSE with
normal close, allow that same Codex process to naturally issue at most one second
request. Collect only the already-authorized reasoning-placeholder predicate:

- item type `reasoning`;
- ID absent/null/other;
- content empty-array/nonempty/absent/malformed;
- summary empty-array/nonempty/absent/malformed;
- encrypted content null/non-null/absent/malformed;
- exact allowed-key-set and unexpected-state-bearing-field booleans;
- unique-candidate and adjacent function-call/output chronology booleans.

Do not canonicalize or synthesize an ID regardless of the result. No second protected
process, retry loop, hook-free acceptance, product correction, or 155-ae follows.

## Privacy, security, accounting, and cleanup

Retain no prompts, request/response bodies, reasoning content, tool names/content,
IDs, credentials, endpoints, raw headers/SSE, body/signature digests, canonical bytes,
nonce/timestamp values, arbitrary exceptions/errors, package logs, or temporary paths.
Unknown evidence fails closed. Preserve signed identity/replay, exact route/pair,
hosted-tool denial, request bounds, privacy, Local cache isolation, reservation/
finalization, and PostgreSQL authority. All task reservations must be terminal with
zero pending.

Remove the protected runtime reference and all 155-ad roots, installed Codex files,
summaries, processes, listeners, containers, databases, and other task artifacts
before reporting. Preserve unrelated state.

## Allowed paths

    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_oap_governance.py
    oap/active
    oap/orders/155-ad-local-error-stage-and-tool-choice-diagnostic.md
    oap/reports/155-ad-local-error-stage-and-tool-choice-diagnostic.md

No Gateway `app/` file, capture fixture/script, schema, migration, dependency,
lockfile, documentation contract, Local Coding checkout, Qwen/Codex product,
previous order/report, AGENTS/OAP protocol, merge, auto-merge, release, or next
continuation is authorized.

## Immutable report and response contract

Before creating the report, assert that no `oap/reports/155-ad-*` path exists. Create
exactly one report, commit it exactly once as a report-only `SELF` commit whose first
parent is the diagnostic implementation head, and push it once. After publication,
never reopen, rewrite, amend, format, replace, or recommit that report. If execution
resumes and the report already exists, perform read-only topology reconciliation only;
do not modify it.

`RESULT=PASSED` means the diagnostic question was conclusively answered with the
required bounded Local code, stage, tool-choice, signing/provenance, boundary, and
accounting evidence. It does not mean the integration or any product is accepted.
`RESULT=FAILED` applies if the Local class or stage remains `other`, evidence is
incomplete/contradictory, privacy validation fails, or a new unclassified condition
appears.

Record exact activation/implementation/report topology, Local-source authority,
tests/checks, safe provenance, first-turn classification, optional second-turn
predicate, accounting, cleanup, limitations, and the fact that no product correction
was made. Do not merge, hand off a green integration, activate 155-ae, or infer the
next objective. Require all ten checks on the immutable report head, send exactly two
response FIFO bytes `OK` once, return to one blocked control-FIFO read, and stop.
