# OAP Coding-Agent Report — 178-a

## Work order
- Identifier: 178-a
- Work-order file: `oap/orders/178-a-documentation-productization.md` (committed unchanged; md5 `7c975ef986e62f57000e293eee66c571` before and after commit)
- Numeric objective: 178
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Objective 178 productized the public documentation so an external engineer can
understand SLAIF immediately, boot it provider-free, log in as admin, and make
one ordinary OpenAI-client request in one sitting. The canonical short
quickstart, installation overview, and contributor entry now live at the
repository root (`QUICKSTART.md`, `INSTALL.md`, `CONTRIBUTING.md`); the old
669-line `docs/quickstart.md` walkthrough became a clearly titled detailed
first-time operator guide (`docs/first-time-operator-guide.md`) with its
commands repaired (Docker-only secret generation via a mounted CLI helper,
interactive hidden admin prompt with documented `--password-stdin` EOF
semantics, optional institution/cohort, mounted pricing CSV, standardized
`OPENAI_API_KEY` client examples), and `docs/quickstart.md` is now a
compatibility stub so historical links keep working. Task navigation was
reworked (README, docs home, deployment references, cli-reference,
demo-journey, onboarding), stale current-facing claims were corrected against
executable sources (rc-beta "latest evidence" now points at the September 2026
qualification/identity records; support/configuration/deployment no longer
direct current readers to the historical beta-readiness record; release
documents now distinguish wired behavior from bounded post-MVP foundations),
and the documentation checker gained the three root entry points plus
conditional front-door navigation rules with focused positive/negative test
coverage. The full documented path was executed literally from a fresh
disposable checkout of the exact final implementation head (AP-6): provider-free
boot, secrets, build, migrations, health/readiness, interactive admin creation,
authenticated dashboard login, reviewed-pricing bootstrap with reapply
`exists`/`conflict` verification, narrow key creation, and one `models.list()`
request through the official OpenAI client. Live provider inference was NOT
RUN. No runtime, deployment, or dependency path changed; the negative runtime
diff from starting `main` is empty.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 315
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/315
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/178-documentation-productization`
- Starting remote SHA: `70f16102d975e3d59268f71de8ff1efd37432d3c` (remote `main`, merge of PR #314 / objective 177)
- Implementation head SHA: `ea0b040461ba6789b9ba5a4de6c880af2880d307`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `cc1f43f` — `oap: activate 178-a documentation productization` (strategic order + `oap/active`, bytes unchanged)
  - `ea0b040` — `obj178: make installation and user journeys the public front door` (all functional changes)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
1. New root public entry points: `QUICKSTART.md` (canonical short quickstart,
   two milestones), `INSTALL.md` (canonical installation overview),
   `CONTRIBUTING.md` (concise contributor entry).
2. `README.md` rewritten: brand block first, identity/audience/benefits,
   prominent QUICKSTART/INSTALL links in the first screenful, conceptual
   architecture, bounded API-family table, task navigation, project status,
   license/maintainers/acknowledgement; no objective/PR/SHA/history ledger or
   internal classification vocabulary.
3. `docs/first-time-operator-guide.md` (new, 584 lines): preserves the useful
   detailed tutorial from the old quickstart with repaired commands (single
   Docker-only secret workflow using the mounted `run-cli` helper; interactive
   hidden admin prompt; `--password-stdin` documented as EOF-reading
   non-interactive; institution/cohort explicitly optional; mounted pricing
   command; `GATEWAY_KEY` replaced by `OPENAI_API_KEY`; placeholder-pricing
   caveats; reapply `exists`/`conflict` behavior; full "No Models Are Visible"
   checklist; Mailpit; refresh workflows; tests pointer; stop/cleanup).
4. `docs/quickstart.md`: 669-line walkthrough replaced by a 17-line
   compatibility stub pointing to root QUICKSTART, INSTALL, and the operator
   guide (historical links keep working).
5. `docs/deployment.md`: beginner walkthrough replaced by pointers to the
   QUICKSTART/operator guide; deployment-level reference facts (services,
   ports, Mailpit, refresh semantics, production notes, nginx streaming,
   worker/scheduler, backups, limitations) preserved.
6. `docs/deployment-production.md`: navigation link to root `INSTALL.md`.
7. `docs/configuration.md`: intro now points to the root QUICKSTART/operator
   guide and the current implemented/deferred/unsupported classification.
8. `docs/product-scope.md`: "New here?" pointer to the root entry points
   (navigation only; no semantic scope change).
9. `docs/compatibility-matrix.md`: the two documentation rows updated to
   describe the new hierarchy (documentation/navigation rows only).
10. `docs/rc-beta.md`: the false "latest merged production-path evidence =
    2026-08-24" claim replaced by pointers to the 2026-09-17 integrated
    requalification (candidate `2b61312e...`, `RESULT=QUALIFIED-RC-POSTURE`)
    and the 2026-09-20 identity record (candidate `db0bd3ae...`,
    `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`) with their exact scope; the
    2026-08-24 and 2026-08-17 paragraphs remain immutable historical evidence
    (explicit `RESULT=FAIL` wording and archive link retained).
11. `docs/support-policy.md`: release-state line now points to the product
    scope and the dated verification index (not the historical
    beta-readiness record).
12. `docs/release-notes.md`: distinguishes wired gateway behavior from bounded
    post-MVP service foundations; keeps `Untagged draft` and
    non-certification wording.
13. `docs/release-decision-brief.md`: current-facing preamble now points to
    the current verification index (September 2026 records), the RC2 feature
    scope, and exact candidate checks; superseded historical body preserved.
14. `docs/releases/README.md`: index gains truthful one-liner entries for the
    2026-09-17 and 2026-09-20 records; existing archive entries preserved.
15. `docs/verification/README.md`: new "Current evidence (newest first)"
    section with the two September records; all existing record links and
    truthful outcomes preserved.
16. `docs/cli-reference.md`: related-documentation quickstart link replaced by
    root QUICKSTART + first-time operator guide (subcommand inventory intact).
17. `docs/demo-journey.md`, `docs/onboarding.md`: quickstart links updated to
    the root QUICKSTART (foundation-limit text preserved).
18. `scripts/check_documentation.py`: `ROOT_DOC_NAMES` gains QUICKSTART/INSTALL/
    CONTRIBUTING; two conditional navigation rules added (root README must
    reference QUICKSTART.md/INSTALL.md when present; the docs/quickstart.md
    stub must point to `../QUICKSTART.md`, `../INSTALL.md`,
    `first-time-operator-guide.md` when present). Rules are conditional on the
    files existing in the checked tree so synthetic checker trees keep working;
    no existing rule weakened.
19. `tests/unit/test_documentation_inventory.py`: new focused tests for the
    root entry points, the stub pointers, and the operator guide's required
    `## Pricing`/`## Troubleshooting` sections.
20. `tests/unit/test_documentation_contract_drift.py`: the objective-001 drift
    test now requires the full historical fact ledger (`RESULT=FAIL`, `PR #226`,
    report head `24431512...`, "all ten", merge commit `adaefdc...`) in the
    immutable sources (`AGENTS.md`,
    `docs/verification/2026-08-17-current-main-baseline.md`) and requires
    current indexes (`docs/rc-beta.md`, `docs/releases/README.md`) to keep the
    explicit `RESULT=FAIL` outcome plus a working archive link, instead of
    duplicating the history ledger.
21. `tests/unit/test_documentation_asof.py`: two new synthetic-tree tests
    covering the new front-door/stub navigation rules (positive and negative);
    the real-repository `check() == []` assertion now also exercises the new
    rules.
22. `oap/orders/178-a-documentation-productization.md`, `oap/active`:
    committed exactly as authored by the strategic model.

## Files changed
Commit `cc1f43f` (activation):
- `oap/orders/178-a-documentation-productization.md` (added, unchanged)
- `oap/active` (`177-a` → `178-a`, unchanged strategic bytes, no trailing newline)

Commit `ea0b040` (implementation):
- `QUICKSTART.md` (new)
- `INSTALL.md` (new)
- `CONTRIBUTING.md` (new)
- `docs/first-time-operator-guide.md` (new)
- `README.md`
- `docs/README.md`
- `docs/quickstart.md`
- `docs/deployment.md`
- `docs/deployment-production.md`
- `docs/configuration.md`
- `docs/product-scope.md`
- `docs/compatibility-matrix.md`
- `docs/rc-beta.md`
- `docs/support-policy.md`
- `docs/release-notes.md`
- `docs/release-decision-brief.md`
- `docs/releases/README.md`
- `docs/verification/README.md`
- `docs/cli-reference.md`
- `docs/demo-journey.md`
- `docs/onboarding.md`
- `scripts/check_documentation.py`
- `tests/unit/test_documentation_inventory.py`
- `tests/unit/test_documentation_contract_drift.py`
- `tests/unit/test_documentation_asof.py`

Every changed path is inside the work order's allowlist. No other path was
touched (see AP-8 identity proof).

## Information architecture changes
- Canonical hierarchy: root `QUICKSTART.md` (short, one-sitting) →
  `docs/first-time-operator-guide.md` (detailed tutorial) with root
  `INSTALL.md` as the installation overview; `docs/quickstart.md` demoted to a
  compatibility stub; root `CONTRIBUTING.md` as the contributor entry.
- README: brand → identity → "Get started" (QUICKSTART/INSTALL links + the two
  standard OpenAI env vars) → how it works → why → bounded API families → task
  navigation → security/accounting boundaries → project status → license.
- Docs home order: Getting started, Using SLAIF, Operating SLAIF, Security,
  Development and architecture, Project status and evidence; authority map and
  reading rules preserved; every pre-existing document remains intentionally
  reachable (checker orphan check).
- Deployment docs now split roles: deployment.md = detailed
  development/self-hosted reference (walkthrough moved out),
  deployment-production.md = detailed appliance procedure, INSTALL.md =
  overview, QUICKSTART/operator guide = execution.
- Current-facing release/verification navigation: support-policy,
  configuration, deployment, rc-beta, release-decision-brief, releases index,
  and verification index now direct current readers to the product scope, the
  verification index, and the September 2026 records; historical records
  remain reachable and immutable behind user navigation.

## Acceptance-criteria evidence
### AP-1 — Professional README
- Result: PASS
- Evidence: README opens with the retained brand block (checker brand rules
  pass: first `<div align="center">`, slaif.si link, logo `alt="SLAIF"`,
  product-scope + docs-home fragments), states the identity, audience, and
  benefits in normal user language, links QUICKSTART/INSTALL in the first
  screenful, shows one conceptual architecture, a bounded API-family table,
  task navigation, and a short honest project status; contains no
  objective/PR/SHA/history ledger, no OAP mechanics, no internal
  classification vocabulary (CI `Documentation hygiene` and the focused docs
  tests pass on the head).

### AP-2 — Distinct quickstart/install roles
- Result: PASS
- Evidence: root `QUICKSTART.md` is the only canonical short quickstart;
  `INSTALL.md` is the installation overview (prerequisites, persistence,
  production topology, upgrades, stop/cleanup); `docs/quickstart.md` is a
  clearly labeled compatibility stub; the detailed tutorial is preserved in
  `docs/first-time-operator-guide.md` and linked from README, docs home,
  QUICKSTART, and cli-reference. The checker now enforces the front-door links
  and stub pointers (new conditional rules), with positive/negative synthetic
  coverage in `test_documentation_asof.py` and positive inventory coverage.

### AP-3 — Copy/paste-correct commands; true distinctions; corrected stale claims
- Result: PASS
- Evidence: AP-6 executed every documented command literally from the final
  head (see clean-room evidence below). Provider/key distinction standardized
  (`OPENAI_API_KEY` = gateway-issued client key everywhere; the undefined
  `GATEWAY_KEY` is gone); pricing examples use the mounted helper;
  `--password-stdin` documented as EOF-reading (matches
  `sys.stdin.read().rstrip("\n")` in `app/slaif_gateway/cli/admin.py`);
  interactive hidden prompt is the documented default (matches
  `typer.prompt("Password", hide_input=True, confirmation_prompt=True)`);
  institution/cohort documented optional (verified: clean-room owner created
  with empty `institution_id`); stale current-facing claims corrected per the
  stale-claim audit table.

### AP-4 — Coherent task navigation
- Result: PASS
- Evidence: README, docs home, QUICKSTART, INSTALL, and deployment references
  cross-link into one graph; `scripts/check_documentation.py` passes
  (`DOCUMENTATION_CHECK=OK files=89`, including link/anchor/orphan
  validation); SECURITY.md, CHANGELOG.md, LICENSE, and CONTRIBUTING.md remain
  at their paths and are referenced (SECURITY/CHANGELOG in README,
  CONTRIBUTING in README task navigation + docs home).

### AP-5 — Historical immutability
- Result: PASS
- Evidence: `git diff 70f16102..ea0b040 -- docs/beta-readiness.md` is empty
  (byte-for-byte, including its as-of marker); all dated records under
  `docs/verification/` except `README.md` (expressly allowed index) are
  unchanged; `docs/releases/` only `README.md` changed; `docs/security/`
  unchanged; all previous OAP orders/reports unchanged (only `oap/active`
  changed and the new 178-a order added); the updated drift test still
  validates the historical failure/outcome facts and working archive links.

### AP-6 — Clean-room execution of the documented path
- Result: PASS
- Evidence: full clean-room record in the "Clean-room (AP-6) evidence" section
  below, executed from a fresh clone of exactly `ea0b040461ba6789b9ba5a4de6c880af2880d307`.

### AP-7 — Checker, links, focused tests, whitespace, CI
- Result: PASS
- Evidence:
  - `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=89`
    (the three new root documents are in the file graph; 89 = 85 prior docs +
    4 new: QUICKSTART, INSTALL, CONTRIBUTING, first-time-operator-guide).
  - Focused pytest (exact work-order selection):
    `tests/unit/test_documentation_inventory.py test_documentation_contract_drift.py test_documentation_asof.py test_product_scope_docs.py test_rc2_feature_scope_docs.py test_oap_governance.py test_local_docker_debug_ux.py test_cli_bootstrap_openai_completions_catalog.py test_cli_secrets.py test_cli_keys_secret_output.py`
    → **96 passed in 10.02s**, 0 failed.
  - `python -m ruff check scripts/check_documentation.py tests/unit/test_documentation_inventory.py tests/unit/test_documentation_contract_drift.py tests/unit/test_documentation_asof.py` → All checks passed.
  - `git diff --check 70f16102` → clean.
  - CI hygiene grep `SLAIF_API_KEY|SLAIF_BASE_URL` over `README.md docs .env.example pyproject.toml Makefile` → no matches.
  - All 10 GitHub checks for the implementation head passed (see CI section).

### AP-8 — Runtime/deployment/dependency identity
- Result: PASS
- Evidence:
  - `git diff --name-only 70f16102d975e3d59268f71de8ff1efd37432d3c ea0b040461ba6789b9ba5a4de6c880af2880d307 -- app migrations Dockerfile docker-compose.yml docker-compose.production.yml deploy nginx pyproject.toml requirements.txt requirements-dev.txt Makefile alembic.ini .env.example .dockerignore VERSION` → **EMPTY**.
  - All scripts except `check_documentation.py` unchanged; all tests except the three named documentation tests unchanged; `.github/` and `sbom/` unchanged.
  - `python scripts/check_sbom.py` → `SBOM_CHECK=OK components=60` (no regeneration).
  - Packaged-doc exception: the Dockerfile `COPY`s `README.md` and pyproject
    packaging uses it as project description, so descriptive README bytes in a
    rebuilt image can change; this is documented metadata, not executable
    runtime. Executable runtime, deployment configuration, and dependency
    input identity are proven by the empty diff above; no whole-image
    byte-identity claim is made, and the existing live dependency
    resolution/SBOM limitations are preserved.

## Clean-room (AP-6) evidence
- Checkout: fresh `git clone` of `https://github.com/ulfe-lmi/slaif-api-gateway.git`
  into task-owned disposable directory `/tmp/obj178-cleanroom-142611`,
  `git checkout ea0b040461ba6789b9ba5a4de6c880af2880d307`; clean tree
  (`git status --short` empty) before execution. The directory name served as
  the unique Compose project (`obj178-cleanroom-142611`); no shared `.env`,
  DB, secrets, provider catalog, built image, or runtime configuration was
  reused.
- Environment: Ubuntu 24.04 on WSL2 (kernel
  `6.18.33.2-microsoft-standard-WSL2`, x86_64); Docker
  `29.1.3, build 29.1.3-0ubuntu3~24.04.2`; Docker Compose
  `2.40.3+ds1-0ubuntu1~24.04.1`; host Python `3.12.3`; all documented host
  ports (8000, 15432, 16379, 1025, 8025) verified free before start — no
  documented port-override steps were needed.
- Literal documented path, in order (all commands exactly as documented):
  1. `cp .env.example .env` + `chmod 600 .env` → `-rw-------`.
  2. `docker compose build` → api/worker/scheduler images Built.
  3. Documented `run-cli()` helper defined verbatim; then
     `run-cli slaif-gateway secrets generate hmac --version 1 --env-file .env --write`,
     `... secrets generate admin-session ... --write`, `... secrets generate one-time ... --write`,
     `run-cli slaif-gateway secrets validate-env --env-file .env` →
     `Updated TOKEN_HMAC_SECRET_V1 in .env`, `Updated ADMIN_SESSION_SECRET in .env`,
     `Updated ONE_TIME_SECRET_ENCRYPTION_KEY in .env`,
     `OK: TOKEN_HMAC_SECRET_V1 configured`, `OK: ADMIN_SESSION_SECRET configured`,
     `OK: ONE_TIME_SECRET_ENCRYPTION_KEY decodes to 32 bytes`.
  4. `docker compose up -d postgres redis mailpit` → all started, healthy.
  5. `docker compose run --rm api slaif-gateway db upgrade` → Alembic through
     `0024_quota_reservation_accounting_facts`.
  6. `docker compose up -d api worker scheduler` → started.
  7. `curl --fail http://localhost:8000/healthz` → `{"status":"ok"}`;
     `curl --fail http://localhost:8000/readyz` →
     `{"status":"ok","database":"ok","schema":"ok","redis":"ok","alembic_current":"0024_quota_reservation_accounting_facts","alembic_head":"0024_quota_reservation_accounting_facts"}`
     (first try; no retry needed).
  8. `docker compose run --rm api slaif-gateway admin create --email admin@example.org --display-name "Gateway administrator"`
     driven via a pty test driver supplying the hidden `Password:` and
     `Repeat for confirmation:` responses (password redacted everywhere;
     generated `Obj178-Admin-<16 random chars>`, 29 bytes, persisted to a
     0600 temp file only for the login step and deleted afterwards). Output:
     `Password: <hidden>`, `Repeat for confirmation: <hidden>`, then record
     `id: ce01806a-30ce-472f-b673-4e70de326067, email: admin@example.org,
     display_name: Gateway administrator, is_active: True, is_superadmin: False,
     role: admin, created_at: 2026-09-20T13:29:10Z`.
  9. Authenticated dashboard login via an HTTP form/session driver (real
     GET/form-CSRF/POST/session behavior):
     `GET /admin/login` → 200 with `csrf_token` hidden field;
     `POST /admin/login` (csrf_token + email + password, cookie jar) →
     `303` → `/admin`; `GET /admin` with the session → **200** rendering the
     authenticated dashboard (contains `admin@example.org` and
     `Gateway administrator`); unauthenticated `GET /admin` → 303 redirect to
     login (correctly denied); the admin password does not appear in any
     served page.
  10. Milestone 2 (local metadata only, no provider contact):
     - `.env` gained `OPENAI_UPSTREAM_API_KEY=sk-local-cleanroom-fake-not-real`
       (disposable fake value; no real credential was used and no provider
       call was made), applied with the documented
       `./scripts/docker-refresh.sh --env-only`; after service recreation
       `/healthz` + `/readyz` passed and the API container confirmed the
       variable is set.
     - `cp docs/examples/openai-completions-pricing.example.csv local-openai-pricing.csv`,
       then the documented edit: every zero placeholder replaced with
       operator-reviewed local EUR per-million prices (clean-room assumptions,
       e.g. `gpt-4o-mini` 0.15/0.60 EUR).
     - `run-cli slaif-gateway bootstrap openai-completions-catalog --pricing-file local-openai-pricing.csv --apply`
       → `mode: applied`, `provider: created`,
       `chat.completions routes: 10 created, 0 exists, 0 conflicts`,
       `completions routes: not implemented`,
       `pricing: 10 created, 0 exists, 0 missing, 0 conflicts`.
     - `run-cli slaif-gateway providers list` → openai provider,
       `api_key_env_var: OPENAI_UPSTREAM_API_KEY` (env var name only —
       credential isolation holds), `enabled: True`; `routes list` → exact
       `/v1/chat/completions` routes per model; `pricing list` → EUR rows with
       the reviewed prices.
     - Documented reapply verification: identical reapply →
       `provider: exists`, `routes: 0 created, 10 exists, 0 conflicts`,
       `pricing: 0 created, 10 exists, 0 missing, 0 conflicts` (idempotent);
       one changed price (`gpt-4o-mini` input 9.99) →
       `pricing: 0 created, 9 exists, 0 missing, 1 conflicts` and
       `blocked: resolve missing/conflicting rows and rerun the command`
       (blocked as documented); price restored, reapply → `10 exists`.
     - `run-cli slaif-gateway owners create --name Ada --surname Lovelace --email ada@example.org`
       → `id: fd1d0175-ed73-4045-bc94-ce5065455e6f`, `institution_id:` empty
       (institution/cohort confirmed optional).
     - `run-cli slaif-gateway keys create --owner-id fd1d0175-ed73-4045-bc94-ce5065455e6f --valid-days 30 --cost-limit-eur 5.00 --request-limit-total 100 --allowed-endpoint /v1/models --allowed-endpoint /v1/chat/completions --allowed-model gpt-4o-mini`
       → `Warning: plaintext key is shown once. Store it now; it cannot be
       recovered later.`, `gateway_key_id: 339f2461-6427-40c1-9861-98566b59e0cf`,
       30-day validity, plaintext key displayed once (redacted in this report).
     - Disposable client environment (documented option):
       `python3 -m venv .venv-client`, `python -m pip install -q openai`
       (openai 3.16.2, Python 3.12.3), then
       `export OPENAI_API_KEY="sk-slaif-..."` (the issued key),
       `export OPENAI_BASE_URL="http://localhost:8000/v1"`, and the documented
       snippet `client = OpenAI(); models = client.models.list()` →
       returned `['gpt-4o-mini']` — exactly the model the key allows. This was
       one real gateway request exercising authentication, key policy, and the
       local model catalog; it does not contact a provider.
  11. `docker compose down` → all containers removed; the named volumes
      `obj178-cleanroom-142611_postgres-data` and
      `obj178-cleanroom-142611_redis-data` were preserved (non-destructive
      stop confirmed).
  12. Final cleanup: `docker volume rm` on exactly those two test-owned
      volumes; afterwards `docker volume ls | grep obj178-cleanroom-142611`
      and `docker ps -a | grep obj178-cleanroom-142611` are both empty
      (no test-owned resources remain; no global prune was used). The
      disposable directory and all credential-bearing temp files (admin
      password, issued key, cookie jars, CSRF tokens, captured pages) were
      deleted; none remain.
- Live provider inference: **NOT RUN** (explicit). No real upstream provider
  key was present; the upstream key value was a disposable fake; no
  `chat.completions` or other forwarded request was sent; no real email was
  sent (Mailpit was running but no delivery was enqueued).
- No documented step required repair. Two harness-side observations (not app
  or documentation defects) are recorded under Setup UX findings.

## Stale-claim audit table
| # | Confirmed finding | Where fixed |
|---|---|---|
| 1 | README boot sequence omitted required local secret setup | README rewritten; QUICKSTART step 4 (Docker-only mounted secret generation) is the canonical sequence |
| 2 | Old docs duplicated host-Python and Docker secret workflows | Single Docker-only workflow in QUICKSTART + operator guide; `deployment.md` points to them; host-venv path removed from the beginner path |
| 3 | Beginner path required unnecessary institution/cohort steps | Bare `owners create` documented (QUICKSTART, operator guide); institutions/cohorts explicitly optional (verified: empty `institution_id`) |
| 4 | Pricing-file command used a host CSV without mounting it | All pricing examples use the mounted `run-cli` helper (verified working); operator guide states a plain unmounted `docker compose run` would not see the host CSV |
| 5 | Old quickstart used undefined `GATEWAY_KEY` after documenting `OPENAI_API_KEY` | Standardized on `OPENAI_API_KEY` (gateway-issued) throughout; `GATEWAY_KEY` removed |
| 6 | `--password-stdin` presented as an interactive password prompt | Documented as EOF-reading non-interactive (matches code); interactive hidden prompt is the documented default |
| 7 | `docs/rc-beta.md` called 2026-08-24 the latest merged production-path evidence | Now points to the 2026-09-17 requalification (`RESULT=QUALIFIED-RC-POSTURE`) and 2026-09-20 identity record (`RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`) with exact scope; 08-24/08-17 retained as immutable history with `RESULT=FAIL` validation; no claim that 178 reran that matrix |
| 8 | README/docs home/support/config/deployment directed current readers to historical beta-readiness | Support-policy, configuration, and deployment now point to product scope + verification index; beta-readiness remains reachable as dated historical evidence |
| 9 | Superseded release-decision preamble called beta-readiness latest | Preamble now points to the current verification index (September 2026 records), RC2 feature scope, and exact candidate checks |
| 10 | Untagged release notes implied all listed capabilities are deployed features | Now distinguishes wired gateway scope from bounded post-MVP service foundations; `Untagged draft` + non-certification wording kept |
| 11 | Configuration intro mentioned still-missing RC2 endpoint families | Now points to the current implemented / explicitly deferred / unsupported-by-policy classification |
| 12 | Compatibility matrix documentation rows described the old hierarchy | Rows updated to the new QUICKSTART/stub/operator-guide/INSTALL hierarchy |

## Local verification
- `python scripts/check_documentation.py`: PASSED — `DOCUMENTATION_CHECK=OK files=89`
- `python -m pytest tests/unit/test_documentation_inventory.py tests/unit/test_documentation_contract_drift.py tests/unit/test_documentation_asof.py tests/unit/test_product_scope_docs.py tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_oap_governance.py tests/unit/test_local_docker_debug_ux.py tests/unit/test_cli_bootstrap_openai_completions_catalog.py tests/unit/test_cli_secrets.py tests/unit/test_cli_keys_secret_output.py`: PASSED — 96 passed in 10.02s
- `python -m ruff check scripts/check_documentation.py tests/unit/test_documentation_inventory.py tests/unit/test_documentation_contract_drift.py tests/unit/test_documentation_asof.py`: PASSED — All checks passed
- `git diff --check 70f16102d975e3d59268f71de8ff1efd37432d3c`: PASSED — clean
- `git grep -E 'SLAIF_API_KEY|SLAIF_BASE_URL' -- README.md docs .env.example pyproject.toml Makefile`: PASSED — no matches
- `python scripts/check_sbom.py`: PASSED — `SBOM_CHECK=OK components=60` (no regeneration)
- Negative runtime diff (starting main → implementation head, 15 runtime/deployment/dependency paths): PASSED — EMPTY
- Immutability diffs: `docs/beta-readiness.md` EMPTY; `docs/verification/` (non-README) EMPTY; `docs/releases/` (non-README) EMPTY; `docs/security/` EMPTY; `oap/` (orders/reports, non-active) EMPTY; `.github/` EMPTY; `sbom/` EMPTY; all scripts except `check_documentation.py` EMPTY; all tests except the three named documentation tests EMPTY
- Full local test matrix / HPC harness / integrated production qualification: NOT RUN (explicitly out of scope for this documentation objective; not repeated)

## GitHub CI / required checks
- Check state observed for implementation head `ea0b040461ba6789b9ba5a4de6c880af2880d307` (PR #315, run IDs in URLs):
- Analyze (javascript-typescript): SUCCESS (40s) — run 35510586870
- Analyze (python): SUCCESS (2m9s) — run 35510586870
- Analyze Python: SUCCESS (1m14s) — run 35510587498
- CodeQL (rollup): SUCCESS (2s) — run 35510586870 / check-run 106077815508
- Docker Compose smoke: SUCCESS (1m0s) — run 35510587513
- Documentation hygiene: SUCCESS (4s) — run 35510587513
- OpenAI-compatible E2E tests: SUCCESS (1m38s) — run 35510587513
- Playwright browser smoke: SUCCESS (1m32s) — run 35510587513
- PostgreSQL integration tests: SUCCESS (2m43s) — run 35510587513
- Unit, lint, and migration head: SUCCESS (2m25s) — run 35510587513
- All required checks green for the implementation head at report drafting: yes (10/10, including the CodeQL rollup)
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report

## Local setup / dependencies
- Packages/tools/services installed or configured: none on the shared host; the clean room used only the repository's own Docker build (Docker 29.1.3 / Compose 2.40.3), a disposable client venv (Python 3.12.3, `openai==3.16.2`), and disposable Compose containers/volumes under the unique project name `obj178-cleanroom-142611`.
- `sudo`-level setup performed: none required.
- Durable setup changes committed/documented: none.

## Documentation
- Documentation updated: `README.md`, `QUICKSTART.md` (new), `INSTALL.md` (new), `CONTRIBUTING.md` (new), `docs/README.md`, `docs/quickstart.md`, `docs/first-time-operator-guide.md` (new), `docs/deployment.md`, `docs/deployment-production.md`, `docs/configuration.md`, `docs/product-scope.md`, `docs/compatibility-matrix.md`, `docs/rc-beta.md`, `docs/support-policy.md`, `docs/release-notes.md`, `docs/release-decision-brief.md`, `docs/releases/README.md`, `docs/verification/README.md`, `docs/cli-reference.md`, `docs/demo-journey.md`, `docs/onboarding.md`, plus checker/test mechanics in `scripts/check_documentation.py` and the three named documentation tests.
- Documentation intentionally deferred: no public documentation work is deferred by this objective. Known deliberately-out-of-scope items (not deferred documentation, but recorded): (a) a future one-command setup/bootstrap helper is a product decision for the strategic model (this objective documents the current manual path and records the setup friction as a UX finding); (b) Objective 179 identity follow-up, if the strategic model deems it warranted after merge, is explicitly not pre-activated here.

## Setup UX findings
1. Interactive admin creation through `docker compose run` with TTY
   forwarding on this WSL2 + Docker host delivered keystrokes unreliably when
   the test driver wrote input immediately after the prompt bytes appeared; a
   quiescence window (no new output for ~15–30s) before writing, then writing
   each line once, made the documented interactive flow deterministic. This is
   a TTY-forwarding/test-harness delivery characteristic, not an application
   defect: the app's hidden prompt, confirmation, and success payload behaved
   exactly as documented, and a human typing at the visible prompt is
   unaffected. No documentation change was warranted.
2. The documented `admin create` flow creates the account only after the
   confirmation prompt is answered; a partially driven interactive session
   leaves no partial state (verified: repeated aborted attempts left
   `admin list` empty until the successful run).
3. `./scripts/docker-refresh.sh --env-only`'s final `/healthz` probe can race
   service recreation (observed one `Connection reset by peer` immediately
   after recreation; readiness succeeded within ~10s). The script output
   already shows the recreated services; a human retry is sufficient. This is
   an existing helper behavior, not a defect introduced by this objective.

## Known limitations / blockers
- None blocking. The objective's scope is documentation and navigation only;
  the runtime is unchanged by construction (empty negative diff).

## Safety and scope confirmations
- Unrelated files changed: no (every changed path is on the work-order allowlist; see AP-8)
- Production secrets accessed: no (clean-room secrets generated fresh; upstream key was a disposable fake)
- Production systems accessed: no
- Required tests skipped/not run: yes — full local matrix, HPC harness, and integrated production qualification were NOT RUN by explicit work-order scope; the focused documentation test selection (10 files) was run and passed; live provider calls were NOT RUN
- Scope deviation: no
- Extra PR created for same numeric objective: NO (PR #315 is the only PR for objective 178)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (committed exactly as authored; md5 verified before/after)
- Report-publication commit changes only this report file: yes (verified at commit time)
- No tag created, no release published, no real provider call made, no real email sent

## Recommended strategic follow-up
Factual only, for the strategic model's decision: after merge, the README
packaging note (AP-8) means the next identity-only objective, if one is
deemed warranted (as anticipated by this order), would re-derive the release
candidate identity over the post-merge main. No further documentation gaps
were found by this objective's audit; the bounded bootstrap-helper idea from
the Setup UX findings remains a candidate product decision, not a documentation
gap.
