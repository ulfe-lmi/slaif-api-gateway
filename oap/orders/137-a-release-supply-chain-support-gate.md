# OAP Work Order — 137-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/137-release-supply-chain-support-gate`
Base: main @ 4e763842407a

## Objective and reason

Close release supply-chain, vulnerability, licensing, and support gates so the
SME release candidate has a trustworthy provenance chain and a defined support
boundary. No feature work — gate closure only.

## Verified state

- main = 4e763842407a; no open non-Dependabot PR.
- Objectives 118–136 merged. Phase 6 underway.

## Scope

1. Supply chain:
   - SBOM generation verified and reproducible.
   - Dependency license compatibility check.
   - Container image signing (cosign or equivalent).
2. Vulnerability management:
   - No critical/high vulnerabilities in dependencies.
   - Vulnerability disclosure policy documented.
3. Support boundary:
   - Supported deployment/version/upgrade window documented.
   - Issue/security reporting process defined.
4. Licensing:
   - All dependencies have compatible licenses.
   - Project license file present and correct.

## Exact requirements

1. SBOM generated and committed.
2. No critical/high vulnerabilities in dependency scan.
3. License compatibility verified for all direct/transitive dependencies.
4. Support policy documented with version/upgrade window.

## Allowed paths

```
docs/supply-chain.md
docs/support-policy.md
sbom/
oap/orders/137-a-release-supply-chain-support-gate.md
oap/reports/137-a-release-supply-chain-support-gate.md
oap/active
.github/workflows/*.yml
```

## Non-goals

No feature work. No release/tag decision.

## Observable acceptance

- SBOM generated and reproducible.
- Dependency vulnerability scan passes (no critical/high).
- License compatibility verified.
- Support policy documented.
- All required final-head CI checks green.

## Verification commands

```bash
ls -la sbom/
git diff --check
```

## OAP contract

Objective 137-a creates one PR; remediation uses 137-b–z same PR.
Coding agent never merges.
