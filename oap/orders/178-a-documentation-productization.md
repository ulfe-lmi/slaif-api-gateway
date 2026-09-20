# OAP Work Order — 178-a

PR mode: `CREATE_NEW_PR`

## Objective and reason

Productize the public documentation so an external engineer immediately
understands SLAIF, can boot it and log in without provider credentials, and
can follow a truthful second milestone to an ordinary OpenAI-client request.
This is a coherent documentation/navigation/checker objective, not another
readiness ledger. Preserve engineering and historical evidence while putting
users ahead of governance. The maintainer explicitly authorized this work
after release closure 175–177 and before any RC tag.

## Verified starting state and authority

Strategic verification on 2026-09-20, refreshed at 11:37 UTC:

- GitHub repository: `ulfe-lmi/slaif-api-gateway`.
- Remote main: `70f16102d975e3d59268f71de8ff1efd37432d3c`.
- Zero open PRs. Objectives 175/176/177 are terminal, merged respectively in
  PRs #312/#313/#314; 177 merged at 2026-09-20T11:12:20Z.
- Shared and remote `oap/active` before activation: `177-a`; unique matching
  order and immutable report exist. Shared checkout is at 177 report head
  `4b754a47be70d9e7cd0c5d64bf2d8de8bd2dad86`, tree-identical to main,
  with no tracked changes. Preserve ignored local state and credentials.
- Main's nine stable checks are completed/success: Unit, lint, and migration
  head; Documentation hygiene; OpenAI-compatible E2E tests; Playwright browser
  smoke; Docker Compose smoke; PostgreSQL integration tests;
  Analyze (javascript-typescript); Analyze (python); Analyze Python.
- Classic branch protection returns 404; active ruleset `protect main`
  protects deletion/non-fast-forward only. It does not enforce CI/review gates.
  Strategic review still requires every ordinary final-head CI gate, including
  the CodeQL rollup, to pass. Do not alter GitHub settings.
- RC2 classification independently read through GitHub: 27 implemented,
  0 missing, 21 deferred, 3 unsupported by policy, 0 maintainer decisions.
- Only published release is `v0.1.0-rc.1`. No new tag/release is authorized.
- Integrated qualification anchor:
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`, recorded in
  `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`.
- Objective 177 identity candidate:
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`, recorded in
  `docs/verification/2026-09-20-release-identity-db0bd3ae.md`.
  Both records are immutable. Existing qualification used mocked upstreams,
  has its documented environment exceptions, and is not certification.

Reconcile these facts yourself before implementation. Read repository
AGENTS.md, OAP-COMMUNICATION-coding-agent.md, the compact strategic architecture,
and applicable current contracts. The human's new direction supersedes the
earlier strategic timing-ledger statement that no further coding objective was
warranted. This order does not change product contracts or scope classification.

## PR and publication contract

Create exactly one PR for Objective 178 from the verified main above:

- Base: `main`, starting SHA as above.
- Branch: `oap/178-documentation-productization`.
- Suggested title: `docs: make installation and user journeys the public front door`.
- Commit unchanged strategic order and active pointer before/with implementation.
- Any continuation amends this same PR; never create another PR for 178.
- Coding agent never merges or enables auto-merge.

## Exact allowed paths

Public entry points:

- `README.md`
- `QUICKSTART.md` (new)
- `INSTALL.md` (new)
- `CONTRIBUTING.md` (new, concise)

Documentation restructuring and current-facing corrections:

- `docs/README.md`
- `docs/quickstart.md` (compatibility stub)
- `docs/first-time-operator-guide.md` (new, preserves useful detailed tutorial)
- `docs/deployment.md`
- `docs/deployment-production.md`
- `docs/configuration.md` (navigation and installation/bootstrap command truth only)
- `docs/product-scope.md` (navigation/wording only, no semantic scope change)
- `docs/compatibility-matrix.md` (documentation/navigation rows only)
- `docs/rc-beta.md`
- `docs/support-policy.md`
- `docs/release-notes.md` (untagged draft, correct overclaims and navigation)
- `docs/release-decision-brief.md` (current-facing preamble/navigation only;
  preserve superseded historical body)
- `docs/releases/README.md` (index/navigation; preserve archive access)
- `docs/verification/README.md` (navigation with newest qualification/identity
  easy to find, preserving all existing record links and truthful outcomes)
- `docs/cli-reference.md` (quickstart/operator-guide links and any installation
  example correction directly required by this objective only)
- `docs/demo-journey.md` (quickstart link only)
- `docs/onboarding.md` (quickstart link only; preserve foundation limits)

Documentation mechanics:

- `scripts/check_documentation.py`
- `tests/unit/test_documentation_inventory.py`
- `tests/unit/test_documentation_contract_drift.py`
- `tests/unit/test_documentation_asof.py`

Orchestration:

- `oap/orders/178-a-documentation-productization.md` (commit unchanged)
- `oap/active` (commit exact strategic `178-a` bytes unchanged)
- `oap/reports/178-a-documentation-productization.md` (new immutable report)

No blanket docs authorization. Changes outside this list require a strategic
continuation. Existing SECURITY.md, CHANGELOG.md, LICENSE, AGENTS.md,
AGENTIC_CLIENT_INTEGRATION.md, and OAP-COMMUNICATION-coding-agent.md remain at
their paths and unchanged. Their root paths have governance/contract/test
meaning; public navigation must not foreground agent instructions.

## Required information architecture

1. README: retained compact required SLAIF brand block; clear identity as a
   self-hosted OpenAI-compatible organizational AI access control plane;
   audience/problem/benefits; prominent QUICKSTART and INSTALL links within
   the first screenful; one simple conceptual architecture; compact supported
   API-family table; task navigation; short project status near the bottom;
   license, maintainers, acknowledgement. One organization per deployment,
   provider credentials server-side, PostgreSQL accounting, no default content
   storage, and bounded compatibility remain accurate. Do not imply wired
   enterprise RBAC/SSO or one-click modes. Avoid long command duplication.
2. README must contain no objective/PR/SHA/history/test-count ledger, stale
   failed-run chronology, OAP mechanics, or internal classification vocabulary.
   Explain current benefits normally and link precise limitations. Preserve
   brand/navigation checks and ordinary OpenAI environment names.
3. Root QUICKSTART is the only canonical short quickstart. Linux, Git, Docker
   Compose v2, Bash/curl as actually needed; do not claim untested macOS/Windows
   support. Use one recommended Docker-only secret-generation method, with a
   real host bind mount and working directory. No host application Python
   install merely to boot. A short inline shell loop is acceptable if simple,
   explained, and executed exactly; no new product/bootstrap script.
4. Milestone 1: clone, copy/restrict config, build, generate/validate the three
   runtime secrets, start PostgreSQL/Redis/Mailpit as actually required by
   Compose, migrate explicitly, start API, check health/readiness, create admin
   safely (interactive hidden prompt is supported), log into `/admin/login`.
   No provider key needed. Document any required readiness wait/retry. State
   that development Compose publishes host ports and is for a trusted local
   evaluation environment, not a hardened public deployment.
5. Milestone 2: use existing provider/catalog bootstrap plus minimal owner/key
   state; institution and cohort are optional, not mandatory setup. Establish
   provider, route, model, pricing and any actually necessary FX. Prefer EUR
   local assumptions to an unnecessary FX detour. Clearly distinguish local
   metadata operations and `/v1/models` from external inference. Use a narrow
   model/endpoint policy and finite evaluation quota. Explain gateway-issued
   OPENAI_API_KEY versus server OPENAI_UPSTREAM_API_KEY and environment reload.
   Ordinary `OpenAI()` client using OPENAI_BASE_URL must perform one request.
   Explain SDK execution prerequisites explicitly; a disposable client container
   or a clearly introduced client Python environment is acceptable.
6. Placeholder pricing is demo wiring only, never reviewed pricing, spend
   protection, or invoice truth. Before the real-call step require reviewed
   pricing using an existing supported CLI flow; do not hide an operator
   decision behind fabricated current prices. Verify whether bootstrap
   reapplication actually updates or conflicts with existing placeholder rows.
   Do not leave readers trapped between placeholder initialization and live
   setup. Host CSV paths require a container mount; verify every example.
   Put detailed pricing instructions in the operator guide and make the
   quickstart's prerequisite/link explicit without turning it into a manual.
7. QUICKSTART stays achievable in one sitting. Exclude full testing, HPC,
   qualification, SBOM, backup, exhaustive CLI/config, OAP, and release history.
   Include simple non-destructive stop instructions and link deeper docs.
8. Move useful current docs/quickstart.md material into a clearly titled
   detailed first-time operator guide, repair its commands, and replace the old
   path with a compatibility stub pointing to root QUICKSTART, INSTALL, and
   the detailed guide. Update current-facing links in the exact allowed paths.
   Historical links keep working via the stub; historical files stay unchanged.
9. INSTALL is the canonical installation overview: verified prerequisites,
   local config/secrets/startup/migrations/persistence/health, production
   topology with TLS/file secrets/PostgreSQL/Redis/NGINX/migration/API and
   optional async profile, interface exposure, configuration reference,
   concrete upgrade/refresh, non-destructive stop and conspicuously destructive
   volume deletion, and operator/security/runbook links. Local refresh helper
   is not a production upgrade tool. Production migrations may require an
   explicitly recreated one-shot service; verify documented instructions.
   Explain .env.example is a template, not paste its inventory.
10. docs/deployment.md remains detailed development/self-hosted reference;
    docs/deployment-production.md remains detailed appliance procedure;
    configuration is exhaustive settings; runbooks own ongoing operation.
    Eliminate needless duplicated quickstart sequences. Preserve actual
    production requirements, including nonempty file-backed provider secrets,
    without pretending the local provider-free promise applies to production.
11. Docs homepage order: Getting started, Using SLAIF, Operating SLAIF,
    Security, Development and architecture, Project status and evidence.
    Preserve authority semantics below task navigation. Keep all docs reachable
    intentionally; don't make users traverse verification to learn installation.
12. CONTRIBUTING: small normal contributor entry, development environment,
    focused unit/lint/docs checks, PR expectations, architecture links. OAP is
    a maintainer workflow, not a prerequisite for a conventional patch.

## Semantic truth audit and known findings

Inspect current executable sources, not just old prose. Required audit inputs
include repository root, all listed public docs, beta-readiness (read-only),
release/verification indexes and records, .env.example, Dockerfile, both Compose
files, Makefile, bootstrap/secret CLI implementations, docker-refresh.sh,
preflight.sh, deploy/production/load-secrets.sh, relevant deployment/upgrade
helpers, and every CLI operation used in installation instructions.

Confirmed issues to resolve in prose:

- README boot sequence omits required local secret setup.
- Old docs duplicate host Python and Docker secret workflows, and require
  unnecessary institution/cohort steps in the beginner path.
- Pricing-file command uses a host CSV without mounting it into the container.
- Old quickstart contains an undefined GATEWAY_KEY after documenting
  OPENAI_API_KEY. Standardize public client key examples.
- Admin `--password-stdin` reads to EOF; do not present it as an interactive
  password prompt. CLI without password flags provides a hidden prompt.
- docs/rc-beta.md falsely calls August 24 the latest merged production-path
  evidence. Point to September integrated requalification and September 20
  identity record with their exact scope; don't claim 178 reruns that matrix.
- README/docs home/support/config/deployment direct current readers to historical
  beta-readiness; use current scope and verification index instead. Preserve
  docs/beta-readiness.md byte-for-byte, including its as-of marker.
- Superseded release-decision preamble calls beta-readiness latest; fix only
  that current-facing direction. Untagged release notes must distinguish wired
  behavior from post-MVP service foundations, not claim all are deployed features.
- Configuration intro mentions still-missing RC2 families despite closed
  required scope; point to current supported/deferred/unsupported classifications.
- Compatibility matrix documentation rows must describe the new hierarchy.

Audit all command blocks that remain in changed current-facing installation
docs against executable behavior: flags, mounts, paths, ports, stdin/TTY,
service names, health URLs, pricing currency, secret output and cleanup.
Use read-only code inspection/help and disposable dry-run/fixture execution
for alternatives, never a live production deployment to verify prose.
Do not broaden product claims while shortening language.

## Hard acceptance predicates

- AP-1: Professional README passes first-screen comprehension, prominent
  QUICKSTART/INSTALL links, concise supported benefits, no history ledger.
- AP-2: Distinct root quickstart/install roles, no competing canonical
  quickstart, useful detailed tutorial preserved and linked.
- AP-3: Copy/paste-correct commands; true provider/key/pricing distinction;
  corrected stale current claims; supported scope neither narrowed nor widened.
- AP-4: README/QUICKSTART/INSTALL/docs-home/deployment references form coherent
  task navigation. Meaningful SECURITY/CHANGELOG/LICENSE/contributor entry paths.
- AP-5: Historical records/OAP reports/orders remain immutable and reachable;
  evidence appears behind user navigation. August readiness body unchanged.
- AP-6: From a fresh disposable checkout of the EXACT final implementation
  head, execute the documented provider-free path with no hidden setup steps:
  config, secrets, build, infra, migrations, API, health, readiness, admin,
  successful authenticated dashboard login, stop and owned-resource cleanup.
- AP-7: Documentation checker, internal links/anchors/reachability, focused
  documentation tests, diff whitespace, and all ordinary final-head CI pass.
- AP-8: Empty runtime/deployment/dependency diff with explicit path proof,
  complete changed-path classification, immutable history proof, and safe
  documentation-only packaged README exception explained precisely.

## Verification plan and economical execution

1. Check every referenced CLI and helper against current source/help. Execute
   every local preparatory command for milestone 2 against the disposable DB.
   Exercise `/v1/models` with the issued key. Use existing doubles/mock tests
   for request structure; never send a live provider request. Record exactly
   which end-to-end and structural cases ran and which live call did not.
2. Commit/push all non-report changes, capture full implementation SHA, then
   clone that exact commit into a NEW task-owned disposable directory. No
   reuse of shared .env, DB, secrets, provider catalog, built image, or runtime
   configuration. Ensure clean Git tree before execution; record SHA, OS,
   Docker/Compose versions, command sequence, statuses, and outcomes.
3. Run the literal documented path. Test harness may supply interactive
   responses and assert results, but must not secretly alter configuration,
   insert SQL, install app extras, bypass secrets/migrations, or repair the
   path. If documented ports are occupied, use only documented override steps
   and record them, or stop conflicting test-owned services; never disrupt
   unrelated services. Use a unique project name via the disposable directory
   or a documented Compose project override. Preflight resource ownership.
4. Successful login requires real GET/form-CSRF/POST/session/dashboard behavior
   through the started API. Browser automation or an HTTP form/session driver
   may prove it. Credentials/cookies/CSRF and issued keys stay out of published
   logs. Plaintext key issuance is checked but output must be redacted.
5. Verify non-destructive stop preserves named data volumes. Delete ONLY
   test-owned volumes/networks during final cleanup and prove none remain.
   No global prune or destructive cleanup of another project.
6. If prose corrections are necessary after trial execution, make a new
   implementation commit and repeat the provider-free test on a fresh checkout
   of that exact final head. AP-6 cannot cite an earlier draft as final proof.
   Keep final evidence in the immutable report to avoid a self-reference loop.
7. `python scripts/check_documentation.py` must include QUICKSTART, INSTALL,
   CONTRIBUTING in its file graph. Add focused positive/negative coverage for
   the added root documents and stub/navigation rules as needed; preserve
   as-of marker and historical archive rules. Do not weaken checker protections.
8. Focused tests: `python -m pytest tests/unit/test_documentation_inventory.py
   tests/unit/test_documentation_contract_drift.py
   tests/unit/test_documentation_asof.py tests/unit/test_product_scope_docs.py
   tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_oap_governance.py
   tests/unit/test_local_docker_debug_ux.py
   tests/unit/test_cli_bootstrap_openai_completions_catalog.py
   tests/unit/test_cli_secrets.py tests/unit/test_cli_keys_secret_output.py`.
   Run additional targeted existing mocked-client cases only as needed for the
   selected example. Record exact selections/counts. No full local matrix.
9. Existing drift test forces old PR/SHA facts into rc-beta and release index.
   It may be updated to require those facts in immutable historical sources
   and working archive links from current indexes, rather than duplicate a
   history ledger. Keep historical failure/outcome validation intact; don't
   delete checks to force green.
10. `python -m ruff check` on changed Python checker/test paths;
    `git diff --check <starting-sha> <implementation-head>`;
    `python scripts/check_sbom.py` (no regeneration); required CI on pushed
    implementation and final report head, with states/run IDs reported honestly.
11. Negative runtime proof, both from starting main and qualified anchor:
    `git diff --name-only <base> <implementation-head> -- app migrations
    Dockerfile docker-compose.yml docker-compose.production.yml deploy nginx
    pyproject.toml requirements.txt requirements-dev.txt Makefile alembic.ini
    .env.example .dockerignore VERSION` must be EMPTY for this objective's
    starting-main delta. For qualified-anchor comparisons classify any already
    existing differences separately; never attribute them to this objective.
    All scripts except check_documentation.py unchanged; all tests except the
    three named documentation tests unchanged; .github and sbom unchanged.
    Check every changed path against the allowlist and classify every delta.
12. Show empty diff for docs/beta-readiness.md, every existing dated record in
    docs/verification, historical releases/security reviews, and all previous
    OAP orders/reports. The indexes may change as expressly allowed.

## Runtime qualification distinction

No runtime/deployment/dependency semantics may change. README.md is copied by
Dockerfile and used by pyproject packaging as project description; acknowledge
that README/documentation metadata bytes in a rebuilt image can change.
Do not call whole images byte-identical, pretend build COPY excludes README,
or erase the existing live dependency resolution/SBOM limitations. Executable
runtime, deployment configuration, and dependency input identity are the
relevant proof; classify descriptive README bytes separately.

This quickstart proof is a documentation execution test, NOT repetition of the
expensive integrated production qualification. Do not run that harness or full
local suites. After 178 merges, strategy will inspect the full candidate delta
and decide whether a tiny separate identity-only 179 is warranted. Do not
pre-activate, implement, or publish Objective 179 now. Do not tag or release.

## Security, privacy, accounting, setup and non-goals

Preserve provider credential isolation, local/hosted-tool separation,
deny-by-default hosted authority, PostgreSQL quota truth, unknown-price/cost
failure behavior, and content-minimizing defaults. No app/provider/accounting
or API change, migration, dependency, Compose, NGINX, production script,
workflow, or SBOM change. No new setup/bootstrap product functionality.

Authorized setup: normal disposable VM tooling/containers, local test-only
secrets/databases, browser assets if needed for login proof, and dependency/
image downloads necessary for the documented build. No real provider calls,
real email, production/staging systems or protected credentials. Do not read
the shared local .env for this objective. Preserve unrelated worktrees,
.local-provider-catalog and all unrelated local state. No screenshots needed.
Never commit credentials, session material, raw content, or private artifacts.

## Stop and report boundaries

Stop broadening work and return a truthful PARTIAL/BLOCKED report if commands
expose an application defect requiring runtime/deployment/dependency changes,
the bootstrap cannot support a reasonable short path without new product
functionality, scope ambiguity cannot be resolved from current contracts, or
moving an internal path would break tooling. Correcting an erroneous command
in prose using existing supported behavior remains in scope. Document setup
friction as a product UX finding, with a bounded future bootstrap recommendation
if warranted; do not implement that follow-up here.

## Report obligations and final protocol

The immutable report must contain: exact starting SHA and implementation SHA;
PR identity/base/branch; complete changed-path list; information architecture
changes; AP-1 through AP-8 verdicts with concrete evidence; exact clean-room
checkout identity, versions, literal commands and redacted outputs; admin login
and cleanup outcomes; milestone-2 command/metadata/double evidence and explicit
live-provider NOT RUN; checker/link/test/whitespace results; stale-claim audit
table; full runtime/packaged-doc/history identity proof; setup UX findings;
deliberately deferred documentation work; setup/tools used; CI states/run IDs;
and no merge/tag/release/provider-call confirmation. Avoid vague perfection
claims. Temporary evidence paths alone are insufficient: embed durable safe
outcomes and commands in the report.

Publish all claimed implementation GitHub state before composing the report.
Atomically publish exactly one report with literal implementation SHA and
`Report publication commit: SELF`. Its final report-only commit must have that
SHA as first parent, change only this new report, be pushed and be the unique
PR head when signalling. Do not mutate after publication. Inspect final-head
checks without rewriting the report; pending/missing/skipped are not passes.
Write exactly two bytes `OK` to the verified response FIFO per coding protocol.
Leave the PR OPEN for independent strategic review and delegated merge.
