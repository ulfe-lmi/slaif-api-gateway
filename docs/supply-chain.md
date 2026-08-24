# Supply-chain evidence

> **Status:** Bounded repository evidence; not signed provenance or vulnerability certification
> **Audience:** Maintainers and security reviewers

The repository contains a CycloneDX SBOM at `sbom/cyclonedx.json`, Dependabot
configuration, CodeQL analysis, pinned versions for selected development tools,
and standard GitHub dependency metadata. The application is Apache-2.0 licensed.

Current CI does **not** run pip-audit or Safety, does not sign container images,
does not publish attestations, and does not prove that no high-severity advisory
exists. Regenerate and review the SBOM and dependency advisories for the exact
release candidate before a release decision.

Do not describe the current artifacts as signed provenance, a complete license
audit, an accepted vulnerability-risk register, or supply-chain certification.
