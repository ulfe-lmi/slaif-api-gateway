# OAP Work Order — 134-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/134-clean-clone-sme-onboarding-demo`
Base: main @ fe1a6c2a9068

## Objective and reason

Validate the complete operator journey with no maintainer memory or hidden
local state. Execute clean-clone deployment, initialization, identity/provider/
catalog/policy/budget setup, key issue, client usage, usage/billing, export,
backup, and upgrade demonstrations. This is the Phase 5 gate.

## Verified state

- main = fe1a6c2a9068; no open non-Dependabot PR.
- Objectives 118–133 merged. Phase 5 underway.

## Scope

1. Clean-clone deployment:
   - Fresh VM/clone → install prerequisites → deploy production Compose profile.
2. Initialization and setup:
   - Run guided onboarding wizard (org, OIDC or local admin, provider, catalog, policy, budget, key).
3. Usage demonstrations:
   - OpenAI client chat + responses.
   - Codex CLI with local tools through gateway.
   - Quota blocking, hold, and release.
   - Export (finance/security/SIEM).
   - Backup → restore verification.
   - Upgrade rehearsal.
4. Operator evidence:
   - Timing for each step.
   - Failure recovery demonstrated.
   - All limitations visible.

## Exact requirements

1. A new operator can complete the documented SME journey from a clean machine.
2. Workshop strict mode, organization mode, Codex local tools, and external-tool blocking are demonstrable.
3. All limitations and manual decisions are visible.

## Allowed paths

```
docs/demo-journey.md
scripts/demo/
oap/orders/134-a-clean-clone-sme-onboarding-demo.md
oap/reports/134-a-clean-clone-sme-onboarding-demo.md
oap/active
```

## Non-goals

No production customer data. No broad live provider spend. No release/tag decision.

## Observable acceptance

- Clean-clone deployment succeeds from documented prerequisites.
- Guided onboarding completes end-to-end in browser.
- All demonstrations pass with evidence.
- All required final-head CI checks green.

## Verification commands

```bash
bash scripts/demo/run-journey.sh
git diff --check
```

## OAP contract

Objective 134-a creates one PR; remediation uses 134-b–z same PR.
Coding agent never merges.
