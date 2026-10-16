# OAP Work Order — 186-a

## Objective, reason and authority

Repair README logo rendering and the checks broken by the human's manual logo
URL correction. The human reports a stale external logo and asks for help with
failing checks. Use the existing tracked SVG locally, preserve top SLAIF branding,
and correct the obsolete literal URL expectations. This is one bounded repair,
not a documentation-checker redesign. Standing OAP delegation covers execution
and strategic merge after final-head review/checks.

## Verified GitHub/OAP state

PR mode: `CREATE_NEW_PR`
Repository: ulfe-lmi/slaif-api-gateway
Base: main at fb3fa979e39cf00d3415e3e7be1811ee039f7701
Branch: oap/186-readme-logo
Title: fix: use repository logo in README and documentation checks

Predecessor185 PR323 merged2026-10-16T00:28:46Z as312a31f; all actual main
checks SUCCESS at that time. Immutable185 report SELFb55ebab first parent31561af,
reportSHA2565970b7d2f07c574c34958dfcfab800434f949be2126af1b12c6e1ad2241642b5.
Latest mainfb3fa97 is human README-only commit: external image changed from
https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg to
https://slaif.si/assets/slaif-logo.svg. Existing tracked logo is
app/slaif_gateway/web/static/img/slaif-logo.svg (blob0d114503215fa4c0227b51b22dcc975c4476fc60).
Only unrelatedDependabot319 open; no186 PR. Ruleset23580289 deletion/nonFF,
no bypass; only releasev0.1.0-rc.1, unchanged. Local branch still185 SELF with
only CODEX-SESSIONS.md/codex.sh untracked: preserve them and other local resources.

Failed main CI38926388109: Documentation hygiene117058894432 requires OLDsrc;
unit117058894276 has6failures/4738passes/1skip, same cause:5asof checks and
product-scope brand assertion. PG/E2E/browser/Compose/CodeQL/codequality pass.
Skipped Ruff/Alembic after unit failure are not passes. Logs via gh api
repos/ulfe-lmi/slaif-api-gateway/actions/jobs/JOBID/logs (gh run log empty here).

## Read and exact permitted paths

Read applicable AGENTS hierarchy, coding OAP protocol, current README branding
contract(section5.1), strategic compact OAP/architecture, relevant checker/tests,
and matching185 terminal state before Git work. Human intent permits changing
logo SOURCE while retaining top block, alt and SLAIF homepage link.

Allowed product paths only:
- README.md (logo src only unless unavoidable small correction is justified)
- scripts/check_documentation.py
- tests/unit/test_product_scope_docs.py
- tests/unit/test_documentation_inventory.py
- tests/unit/test_documentation_asof.py (only if minimal fixture adjustment needed)
- tests/unit/test_documentation_logo.py (optional small focused regression file)
OAP: this order, oap/active, unique oap/reports/186-a-readme-logo.md.
Existing SVG bytes must remain unchanged. No other product path without prior
strategic scope decision. Preserve every prior OAP order/report and message.txt.

## Requirements and acceptance

1. README top centered logo/link/width/alt preserved. Reference tracked SVG by
repository-relative path app/slaif_gateway/web/static/img/slaif-logo.svg so GitHub
and cloned README do not depend on the stale external image host. Do not add
another logo, download external assets or change the image contents.
2. Replace obsolete external-src assertions in checker/product test with the
intended local asset contract and a real file-existence check. Missing logo or
broken src must fail clearly; brand position, SLAIF homepage and navigation
requirements remain enforced. No skip, xfail, blanket checker disable or
allow-any-URL workaround. Preserve synthetic-tree/readiness semantics; keep
change minimal and do not build generic HTML/link crawling infrastructure.
3. Demonstrate checked-in local source resolves and is a valid nonempty SVG,
with exact tracked blob unchanged. Reproduce original failure on new base,
then run documentation checker + affected documentation/product/asof unit
files, Ruff on changed Python, git diff --check. Add only meaningful missing
asset/broken-source control needed to protect the repaired checker boundary.
No DB/browser/provider matrix needed for this static change; normal final-head
GitHub CI remains required. Do not rerun complete local suites.
4. No runtime, financial, authorization, secret, dependency, workflow, schema,
service or accounting changes. No external fetch, live provider/model/email,
production data, release/tag/deploy. Security/privacy/accounting evidence is
bounded diff inspection proving those paths unchanged, not invented runtime tests.
5. Documentation impact: README only; existing runtime contracts unaffected.
Report exact paths checked/changed and why no other docs need updates.

## Setup, publication and report duties

Coding agent owns Git execution: reconcile current main and user work before
creating the unique branch/PR. Never reset/clean/stash unrelated local changes.
Reuse /tmp/slaif-181c-strategic-venv Python3.12 for focused checks; no routine
services or new dependency needed. Preserve shared activation bytes exactly
when committing/pushing. Activation files intentionally dirty are strategic input.

Create exactly one186 PR; never merge or enable auto-merge. Update PR body to
final accurate behavior/evidence using REST JSON/bodyfile if old gh pr edit
fails on retired projectCards. Resolve in-scope CI failures; report missing or
pending checks honestly. Publish unique immutable report with literal
Implementation head SHA: <full SHA> and Report publication commit: SELF.
Its report-only publication commit first parent must equal that implementation
head and only report file may differ. Push and verify remote PR head equals
SELF before signaling exact two-byte OK once on response.fifo; attach sole
control waiter afterward using existing wait-control-and-wake.sh. Strategic
model independently reviews final SELF checks/topology/diff and owns merge.
