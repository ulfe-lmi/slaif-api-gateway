# OAP execution report — 134-a

Implementation head SHA: b2acde017de411dba41d828ae605d665b4b700be
Report publication commit: SELF

## Scope

Added a clean-clone operator journey:

- `scripts/demo/run-journey.sh` checks prerequisites, validates Compose,
  performs preflight, applies migrations, and points to the guided browser
  onboarding path;
- optional safe backup/restore verification when disposable URLs are provided;
- `docs/demo-journey.md` lists every manual operator decision and evidence point.

No production data, broad live provider spend, release/tag decision, or hidden
local state was introduced.

## Verification

Local disposable journey run passed with temporary secret files removed before
commit:

```text
DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway" \
  bash scripts/demo/run-journey.sh
# journey=ok elapsed_seconds=2
```

`bash -n scripts/demo/run-journey.sh` passed. `git diff --check` passed.

All ten final-head GitHub checks were verified successful on implementation head
`b2acde017de411dba41d828ae605d665b4b700be`.

## Honest operator limits

Browser onboarding, first admin, OIDC/local choice, provider metadata, approved
catalog/policy, budget, strict key issuance, OpenAI-client usage, Codex local
tools, quota hold/block/release, and exports require explicit manual operator
steps. The script does not fake those decisions. No compliance or production
certification is claimed.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
