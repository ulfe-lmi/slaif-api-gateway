# OAP Work Order — 138-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/138-sme-control-plane-release-closure`
Base: main @ 6939b2dc5b04

## Objective and reason

Assemble final evidence so the human can decide whether to publish the SME
release candidate. Reconcile every accepted objective, audit finding, known
limitation, and GitHub check. Produce a release decision brief. No feature work.

## Verified state

- main = 6939b2dc5b04; no open non-Dependabot PR.
- Objectives 118–137 merged. All phase gates passed.
- Audit findings matrix exists (136-a); supply chain gate closed (137-a).

## Scope

1. Reconcile all accepted objectives:
   - 000–023: governance, Codex/Responses, external tools, generic providers, Qwen qualifications.
   - 118–137: org model through supply chain.
2. Compile release decision brief:
   - Every contractual SME MVP requirement and its evidence.
   - Every known limitation (honest).
   - Every unresolved audit finding (if any).
   - Candidate commit SHA.
3. Prepare version/changelog/release notes/upgrade guidance.
4. Human makes the release/do-not-release decision.

## Exact requirements

1. Every contractual SME MVP requirement is evidenced on the exact candidate.
2. Required checks are green; audit blockers closed; limitations public.
3. The human receives a clear release/do-not-release decision with no hidden unknowns.
4. No silent release, production deployment, or tag without explicit human approval.

## Allowed paths

```
docs/release-decision-brief.md
CHANGELOG.md
VERSION
docs/release-notes.md
oap/orders/138-a-sme-control-plane-release-closure.md
oap/reports/138-a-sme-control-plane-release-closure.md
oap/active
```

## Non-goals

No silent release. No production deployment. No unresolved blocker waiver.

## Observable acceptance

- Release decision brief covers all requirements with evidence references.
- Known limitations stated honestly and completely.
- Changelog/version/release notes prepared.
- Human receives clear go/no-go recommendation.
- All required final-head CI checks green.

## Verification commands

```bash
git diff --check
ls -la docs/release-decision-brief.md CHANGELOG.md VERSION docs/release-notes.md
```

## OAP contract

Objective 138-a creates one PR; remediation uses 138-b–z same PR.
Coding agent never merges. Tag/release requires separate explicit human authority.
