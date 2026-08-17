# OAP Work Order — 000-b

## Objective

Repair the two dependency-drift GitHub Actions failures on the existing
objective-000 PR by pinning the compatibility-critical development tools to the
versions independently proven by the accepted local baseline.

Amend PR #225 only. Do not create a new PR.

## GitHub objective state

- Numeric objective: `000`
- Execution round: `000-b`
- PR mode: `AMEND_EXISTING_PR`
- Existing PR: `#225`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/225`
- Required head branch: `oap/000-bootstrap-oap-governance-transcript`
- Base branch: `main`
- Starting remote PR head:
  `4bd59f28f01a3c0b07e0645e026559716440d647`
- Prior implementation head:
  `6d3c3288709c20afbe6415844a0d10a16cbf7062`
- Prior round: `000-a`
- Repository: `ulfe-lmi/slaif-api-gateway`

## Why 000-a is insufficient

The `000-a` governance implementation is correctly scoped and its report-only
commit has the required parent/path relationship. Eight checks succeeded and
the changed paths are correct. It must not be merged because two required CI
checks fail on both the implementation and report heads.

Independent GitHub evidence:

- implementation-head CI run:
  <https://github.com/ulfe-lmi/slaif-api-gateway/actions/runs/32057628943>
- report-head CI run:
  <https://github.com/ulfe-lmi/slaif-api-gateway/actions/runs/32058395557>

Failure 1 — `Unit, lint, and migration head`:

- CI performs an unbounded `pip install -e ".[dev]"`;
- it installed Ruff `0.16.3`;
- `python -m ruff check app tests` reports 940 findings in pre-existing
  application/test paths;
- local Ruff `0.15.16` passes the complete configured lint command;
- objective 000 did not change those 940 paths and must not mechanically rewrite
  them to follow an unreviewed linter release.

Failure 2 — `OpenAI-compatible E2E tests`:

- the same unbounded dev install selected OpenAI `3.1.0` and its new HTTP stack;
- 37 existing E2E tests fail because their expected `127.0.0.1` RESPX routes
  are unused; 6 pass;
- the established local compatibility baseline is OpenAI `2.41.0`,
  RESPX `0.23.1`, and HTTPX `0.28.1`;
- the full local unit suite and governance tests pass;
- objective 000 did not change E2E/application code.

The current `pyproject.toml` dev extras list `openai`, `respx`, and `ruff` with
no bounds. This continuation makes the tested CI compatibility line explicit.
It does not claim permanent supply-chain closure; later roadmap gates may
introduce a complete lock/update process.

The prior strategic-authored `000-a` order has an immutable trailing blank line
that `git show --check` reports. It was preserved correctly. Do not edit that
order or the prior report. GitHub documentation hygiene passed, so this is not
one of the two CI blockers.

## Governing instructions

Re-read completely:

1. repository `AGENTS.md`;
2. `OAP-COMMUNICATION-coding-agent.md`;
3. `oap/README.md`;
4. prior `000-a` order and immutable report;
5. this `000-b` order;
6. current `pyproject.toml` and CI install/test commands.

Verify the named PR, branch, current remote head, and failed checks before
editing. If PR #225 is closed, merged, missing, or points elsewhere, stop and
report. Never create a replacement PR.

## Required start sequence

```bash
git fetch origin
gh pr view 225
git switch oap/000-bootstrap-oap-governance-transcript
git pull --ff-only origin oap/000-bootstrap-oap-governance-transcript
```

The strategic model has already atomically published `oap/active=000-b` and
this order in the shared checkout. Preserve their bytes and include them in the
implementation commit.

If pull cannot fast-forward because of these strategic-authored uncommitted
files, first verify local `HEAD` equals the required starting remote head and
that the only uncommitted paths are `oap/active` and this `000-b` order. In that
case do not pull or discard them; continue from the verified head. Any other
dirty tracked path is a blocker.

## Allowed path scope

Implementation/dependency commits may change only:

```text
pyproject.toml
oap/active
oap/orders/000-b-pin-ci-development-dependencies.md
```

The final report-publication commit may add only:

```text
oap/reports/000-b-pin-ci-development-dependencies.md
```

Do not edit:

- application or existing test code;
- `.github/workflows/ci.yml`;
- prior `000-a` order/report;
- `AGENTS.md` or either OAP protocol;
- migrations, deployment, README, or behavior contracts;
- `.local-provider-catalog/` or any strategic-side file.

## Required implementation

### A. Pin the proven development compatibility line

In `[project.optional-dependencies].dev`, replace only the current unbounded
entries for the affected tools with exact tested versions:

```toml
respx==0.23.1
openai==2.41.0
ruff==0.15.16
```

Preserve the existing ordering unless standard formatting requires the three
entries to remain where their unbounded forms already exist.

Do not pin or change unrelated dependencies. Do not introduce a lockfile,
constraints file, dependency updater, or CI workflow change in this
continuation.

### B. Explain the narrow compatibility decision

Update PR #225's body or add one concise PR comment explaining:

- fresh unbounded CI dependencies caused the failures;
- the selected exact versions match the proven local compatibility baseline;
- no application/E2E/lint-rule rewrite is included;
- a future dependency-upgrade objective must deliberately test newer major/tool
  versions rather than inheriting them silently.

Do not modify public product documentation solely for these development pins.
The final report must state:

```text
Documentation checked, no update needed because this continuation only pins
the already-tested CI development-tool compatibility line and changes no
runtime or public behavior.
```

### C. Preserve immutable OAP history

Do not edit:

- `oap/orders/000-a-bootstrap-oap-governance-transcript.md`;
- `oap/reports/000-a-bootstrap-oap-governance-transcript.md`.

Commit the strategic-authored `000-b` order and updated `oap/active` unchanged
with `pyproject.toml`.

## Explicit non-goals

- No Ruff autofix or repository-wide lint remediation.
- No OpenAI 3.x/httpx2 migration.
- No RESPX/E2E rewrite.
- No runtime dependency change other than the dev-extra lines named above.
- No CI workflow change.
- No application, schema, migration, provider, API, accounting, security,
  deployment, or product documentation change.
- No production/provider/database/email call.
- No generated artifact cleanup.
- No second PR, merge, auto-merge, release, tag, issue, or PR #224 action.
- No correction of immutable `000-a` files.

## Acceptance criteria

1. `pyproject.toml` contains exactly the three required proven dev pins and no
   unrelated dependency change.
2. A fresh isolated environment installed from `.[dev]` resolves:
   - Ruff `0.15.16`;
   - OpenAI `2.41.0`;
   - RESPX `0.23.1`.
3. `python -m ruff check app tests` passes in that fresh environment.
4. The full unit suite and OAP governance tests pass.
5. The full mocked OpenAI-compatible E2E suite passes against a safe disposable
   PostgreSQL/Redis test environment, or any genuine environment blocker is
   reported exactly and CI supplies the required evidence.
6. Alembic remains one head and `pip check` passes.
7. PR #225 is amended on the same branch; no second PR exists.
8. The final `000-b` report-only commit has the required implementation parent,
   one changed report path, and remote-head verification.
9. All required GitHub checks on the final PR head become successful before
   strategic merge; the coding agent still never merges.

## Required local verification

Create a fresh isolated virtual environment outside tracked project paths,
install from the amended checkout, and verify the actual resolved line. A
temporary directory or ignored local environment is acceptable; do not commit
it.

Run at minimum in the fresh environment:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
python -c 'import openai, respx, ruff; print(openai.__version__, respx.__version__, ruff.__version__)'
python -m pytest tests/unit/test_oap_governance.py -q
python -m pytest tests/unit -q
python -m ruff check app tests
python -m alembic heads
git diff --check
```

For E2E:

- use an existing safe `TEST_DATABASE_URL` when available;
- otherwise follow the repository's allowed disposable PostgreSQL setup order;
- use safe local/test Redis according to repository rules;
- run:

```bash
python -m pytest tests/e2e -q
```

Do not call real providers.

If local DB/Redis E2E is genuinely blocked after allowed setup attempts, report
it as blocked/not-run and rely on the fresh GitHub E2E check; never call it
passed locally.

Also verify:

- `git diff -- pyproject.toml` contains only the three intended pins;
- staged paths are exactly `pyproject.toml`, `oap/active`, and this order;
- `.local-provider-catalog/` remains ignored, present, unstaged, and unchanged;
- no new secret/control-character/whitespace issue exists in changed files;
- prior `000-a` order/report hashes are unchanged.

## GitHub and report workflow

1. Commit the three implementation paths to the existing branch.
2. Push to the existing PR #225.
3. Verify the new literal implementation head remotely.
4. Inspect required checks and repair only this continuation's in-scope pin
   errors if necessary.
5. Never merge.
6. Atomically publish:

```text
oap/reports/000-b-pin-ci-development-dependencies.md
```

7. Record:

```text
Implementation head SHA: <literal 40-hex implementation commit>
Report publication commit: SELF
```

8. Commit only that new report file.
9. Push and verify it is the PR head, its first parent is the recorded
   implementation head, and it changes only that report.
10. Send exact two-byte `OK` to `response.fifo`.
11. Return to listener mode.

Checks triggered by the report-only commit may still be running at signal time;
report their actual observed state. The strategic model will wait for and
verify the final head before merge.

## Required report

Use the complete coding-agent report contract and include:

- exact dependency root cause and evidence;
- prior and new implementation/report heads;
- PR #225 identity and same-PR confirmation;
- exact `pyproject.toml` diff;
- fresh-environment resolved versions and `pip check`;
- every local command/result, including E2E environment details;
- required GitHub checks observed;
- unchanged prior order/report hashes;
- documentation-impact sentence above;
- no application/test/CI/schema/runtime behavior change;
- no real provider/production/catalog action;
- no extra PR or merge;
- report-only commit parent/path verification;
- residual risks and future deliberate upgrade requirement.

## Final safety confirmations

Confirm explicitly:

- only the existing PR #225 and branch were amended;
- no prior immutable OAP artifact was edited;
- no application or existing test file changed;
- no CI workflow changed;
- no real provider/API/email call;
- no production/staging data or credentials;
- no `.local-provider-catalog/` modification/staging/commit;
- no strategic-side file committed;
- no second PR;
- coding agent did not merge or enable auto-merge;
- immutable `000-b` report was remotely verified before FIFO `OK`.

After remote report publication, write exact `OK` without newline to:

```text
/home/ubuntu/codex-supervision/slaif-api-gateway/response.fifo
```

