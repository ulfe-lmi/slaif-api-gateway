# OAP Work Order — 178-b

PR mode: `AMEND_EXISTING_PR`

## Objective and reason

Complete Objective 178 on its existing PR. The public information architecture
is substantially improved, but independent strategic review found concrete
acceptance failures. Correct the user journey and commands without changing
runtime behavior. In particular, the maintainer required milestone 2 to SEND
A MODEL REQUEST, not stop at model discovery. Do not reinterpret that outcome.

The full 178-a scope, architecture/security/privacy/accounting boundaries,
historical immutability and runtime-neutrality requirements continue to apply;
this order narrows the correction work below. The 178-a order and report are
immutable. Do not rewrite the previous COMPLETE claim; this report must state
what independent review found and how this round closes it.

## Reconciled live state and PR identity

Verified 2026-09-20 during strategic review after exact response `OK`:

- Repository `ulfe-lmi/slaif-api-gateway`; main remains
  `70f16102d975e3d59268f71de8ff1efd37432d3c`.
- Unique open objective PR: #315,
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/315.
- Base `main`; branch `oap/178-documentation-productization`.
- Current report/PR head:
  `a7f1a78a25599a6eb1b320a3ff6eb9aa20fe60fc`.
- Its sole first parent, implementation head:
  `ea0b040461ba6789b9ba5a4de6c880af2880d307`.
- GitHub verified report publication changes only
  `oap/reports/178-a-documentation-productization.md`.
- Shared active before this activation: `178-a`; clean tracked tree.
- All nine stable final-head checks and CodeQL rollup success (10/10).
  PR MERGEABLE; no submitted reviews or inline review comments at inspection.
- Independent strategic execution: documentation checker OK files=89,
  SBOM_CHECK=OK components=60, focused 178-a test selection 96 passed in
  10.27s, whitespace clean, runtime-path diff empty, no historical body edits,
  strategic 178-a order SHA256 unchanged
  `82ec176884ead9e474993e197211b1cae79975ff5038af1ffc4bae37e9b8e7b8`.
- Prior qualified/runtime and release-identity anchors remain the exact
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` and
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` specified in 178-a.
- Main ruleset prevents deletion/non-fast-forward only; strategic review and
  final-head checks are mandatory. No settings/release authority is delegated.

Amend PR #315; DO NOT create another PR or switch to a new numeric objective.
Start from its verified current head, preserve all prior commits/reports,
commit the new strategic order/active pointer unchanged, then make corrections.

## Exact allowed paths for this round

- `README.md`
- `QUICKSTART.md`
- `INSTALL.md`
- `CONTRIBUTING.md`
- `docs/README.md`
- `docs/first-time-operator-guide.md`
- `docs/deployment.md`
- `docs/deployment-production.md` (only directly necessary command/prerequisite
  clarification, no deployment semantics change)
- `docs/rc-beta.md` (current-facing navigation/preamble only)
- `scripts/check_documentation.py` (only if a direct correction needs it)
- `tests/unit/test_documentation_inventory.py`
- `tests/unit/test_documentation_contract_drift.py`
- `tests/unit/test_documentation_asof.py`
- `oap/orders/178-b-complete-model-workflow-and-command-truth.md` (unchanged)
- `oap/active` (unchanged strategic bytes `178-b`)
- `oap/reports/178-b-complete-model-workflow-and-command-truth.md` (new)

No other paths. Keep all executable, deployment, dependencies, scripts other
than the documentation checker, and non-documentation tests unchanged. Test
drivers may exist only as disposable task-owned artifacts; safe evidence must
be reproduced in the report. No historical/OAP body mutation.

## Mandatory corrections

### R1 — The requested second milestone and a short quickstart

QUICKSTART currently labels both milestones provider-free and finishes at
`client.models.list()`. It then requires a real key "now" despite claiming
none is needed. This contradicts both the human request and 178-a requirements.

- Milestone 1 remains genuinely provider-free through admin login.
- Milestone 2 must give the minimum supported path through provider/catalog/
  reviewed pricing, owner/key, `/v1/models`, and a bounded ordinary
  `OpenAI().chat.completions.create(...)` request displaying the response.
- Clearly label `/v1/models` as LOCAL discovery and the actual inference call
  as EXTERNAL and requiring a real server-side provider credential. Put the
  credential prerequisite at the proper boundary; don't claim both milestones
  need no provider key. Keep gateway-issued client and provider keys distinct.
- Put executable model-call code in root QUICKSTART, not only a deeper link.
  Use the existing supported Chat subset with a small output cap and selected
  model. Never run the real-provider call yourself.
- Choose one recommended reviewed-pricing path. Move optional placeholder
  branch, unnecessary FX example, detailed rotation cautions, noninteractive
  admin alternative, and other nonessential reference detail into INSTALL or
  the operator guide. The current ~367-line quickstart still carries too much
  tutorial material. Shorten substantively while adding the missing call;
  do not turn brevity into omitted prerequisites or hidden steps.
- Mention host Python/venv requirements when choosing the client workflow.
  Prefer the repository's qualified SDK version `openai==3.14.1` for the
  reproducible example (this is documentation, not a dependency change).
  Do not extend compatibility claims to the unpinned latest SDK merely because
  178-a's `models.list` succeeded under 3.16.2.
- Catalog bootstrap currently requires reviewed prices for every selected
  catalog model (10 default rows), even though the example key permits one.
  State that honestly in the detailed guide and report it as evaluation setup
  friction. Do not invent a nonexistent single-model bootstrap switch or
  implement one. Recommend a bounded future single-model evaluation bootstrap
  if warranted, outside this objective.
- Update dependent landing/docs-home wording so first success means local boot
  and then an explicitly credentialed model call, not a misleading promise of
  provider-free inference. Add a concise audience sentence in README (SMEs,
  institutions, research/workshop teams) so first-screen identity is concrete.

### R2 — README runnable examples

README's `bash` fence contains shell exports followed directly by Python
`from openai import OpenAI` and `client = OpenAI()`, which is not executable
Bash. Separate shell/Python fences with execution context, use a real Python
heredoc, or remove the redundant example and link the canonical quickstart.
Do not show a successful workflow without the setup prerequisites. Validate
syntax without performing provider inference.

### R3 — INSTALL command and interface truth

- The local Compose API port is published on host interfaces, not just
  localhost. `/readyz` has no auth/IP dependency at the application route;
  local default Compose does not put NGINX in front. Correct the false claim
  that local `/readyz` and `/metrics` are "internal/allowlisted". Distinguish
  network publication, application metrics authentication settings, and
  production NGINX's actual allow/deny behavior. No exposure change in code.
- Add actual copy/paste local update commands, not just a mention of flags:
  explain `docker-refresh.sh --pull` requires clean tracked main and runs
  migrations/build/recreate; `--env-only` skips build/migrations. State the
  observed post-recreation health probe race and give a bounded wait/retry
  that confirms health/readiness without hiding persistent errors. Keep the
  helper unchanged. Align quickstart/operator guide where this helper is used.
- "No host Python except development/testing" is false for the chosen host
  SDK tutorial, and production secret instructions use Python. Make all
  prerequisites accurate for each selected path, without adding unnecessary
  Python to provider-free boot.
- Keep production upgrade distinct from local helper. Provide/clarify an
  executable controlled outline on disposable/reviewed target code: backup/
  rehearsal links, build, explicit one-shot migration and check success,
  recreate correct services/profiles, health/readiness. Don't imply the
  linked generic runbook's default Compose commands are the full production
  command sequence. Inspect `--force-recreate` dependency behavior; prefer a
  bounded command that doesn't unnecessarily recreate DB/Redis. No live
  production execution or integrated harness required.
- Remove the inaccurate universal "slaif-gateway db upgrade is the only
  migration path" wording: production actually runs `alembic upgrade head`.
  Explain the separate documented paths precisely.

### R4 — Contributor bootstrap from a fresh clone

CONTRIBUTING currently installs into the system Python (fails on standard
externally managed Linux Python) and runs Compose config without creating the
required `.env`. Document a venv and required local template copy or another
verified valid Compose invocation. Verify the setup and selected commands
from a fresh task-owned directory with no shared .env. Do not start services
or require provider credentials just for docs/unit/lint/config checks. Keep
ordinary contributors free of OAP prerequisites. Distinguish focused checks
from the full unit suite; do not require a full local suite for a docs patch.

### R5 — Detailed operator-guide accuracy and navigation

- `--cohort-id` belongs to `keys create`, not `owners create`. Correct the
  optional-grouping instructions and verify both command helps.
- Replacing placeholder pricing is not solved by the vague instruction to
  "update existing pricing rows" using a CLI group with no update command.
  Give a concrete supported procedure in the detailed guide, with exact flags
  or actual UI controls and matching scope. Verify it in disposable state;
  don't disable unrelated pricing, fabricate an update command, or leave the
  reader trapped after placeholder bootstrap. This is an alternative detailed
  path; keep root quickstart on one reviewed-price path.
- Ensure build/secret/startup ordering and client Python prerequisites align
  with QUICKSTART; do not introduce a second competing recommended sequence.
- Move the compatibility-stub link out of prominent Getting started choices
  in docs home while retaining intentional reachability lower down. Link
  configuration directly from Getting started.
- docs/rc-beta.md's preamble still directs readers first to August readiness
  as "the detailed readiness verification pass"; use the current verification
  index in that preamble and label the old record explicitly historical.
  Do not change the historical body or its as-of data.

## Verification and acceptance

AP-1 through AP-8 of 178-a remain required; additionally R1–R5 must each have
specific evidence, not merely editorial assurance.

1. Read source/help for every corrected command. Execute all local preparatory
   commands for the selected model workflow on disposable PostgreSQL state;
   verify narrow model discovery. Test the documented inference snippet with
   an existing mocked provider mechanism / focused official-client E2E fixture
   wherever possible, proving it constructs an accepted Chat request and
   handles a completion. No real provider key/call. Record mock wiring
   separately from user steps: mocks are test instrumentation, not an
   undocumented installation dependency. Existing focused E2E coverage may
   supplement direct snippet structural execution; do not claim a live call.
2. Execute the detailed placeholder-to-reviewed-pricing procedure on separate
   disposable metadata state and prove resulting effective prices are reviewed
   test assumptions; verify safe local metadata only.
3. After all non-report changes are committed/pushed, run the provider-free
   quickstart from a NEW disposable clone of the EXACT final implementation
   head through build, config, secret generation, migrations, startup, health,
   readiness, first admin, real CSRF/session login, non-destructive down and
   owned-volume cleanup. No shared image/env/DB/secret reuse, hidden repair,
   or test-only application mutation. Record literal commands and safe output.
   The earlier exact-head proof cannot substitute for this corrected head.
4. Verify fresh contributor setup and Compose config invocation using a new
   disposable environment. Check all documented shell/Python snippets for
   syntax/flag validity. Do not execute destructive/update examples against
   the shared repository or production systems.
5. Run documentation checker/links/anchors/reachability, the focused docs and
   CLI tests named in 178-a, changed-Python Ruff, SBOM check, and diff --check.
   Add a meaningful regression assertion for the model-call milestone if
   needed within the allowed documentation tests; do not overfit prose.
6. Re-prove exact allowed-path scope, empty runtime/deployment/dependency diff
   from starting main, immutable historical docs and previous OAP artifacts,
   no workflow/SBOM changes, and README's descriptive packaged-byte exception.
7. Every ordinary final-head check must pass before strategic merge. Inspect
   implementation CI before report and final report-head CI after publication;
   report pending honestly. No expensive integrated qualification/full local
   matrix, no runtime fix, no 179 work, no release/tag.

## Setup, stop boundaries, and report

Same disposable setup authority as 178-a; no production systems, real provider
calls or email, shared .env access, protected credentials, global prune, or
unrelated worktree manipulation. If an application defect or mandatory runtime
change is found, stop broadening and report for strategy. Correcting prose
with existing behavior is authorized. Don't dismiss observed command failures
as harmless without documenting actionable recovery or a genuine blocker.

Report exact start/current implementation SHA, same PR identity, full paths,
per-R and per-AP outcomes, new exact-head clean-room and contributor proof,
mocked Chat execution, pricing replacement evidence, command audit, focused
check results, runtime/history identity, truthful UX friction and deferred
product recommendation. State live-provider NOT RUN and merge/tag NO.

Publish all non-report claimed GitHub state first. Then atomically publish
one immutable `178-b` report with literal implementation SHA and
`Report publication commit: SELF`; final commit changes only this report,
first parent equals implementation SHA, and pushed PR head equals SELF at
signal time. Do not mutate afterward or rewrite 178-a. Send exact two-byte
`OK` to response FIFO and leave PR #315 open for strategic review.
