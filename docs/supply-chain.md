# Supply-chain gate

The committed CycloneDX SBOM at `sbom/cyclonedx.json` records the application
and its installed Python components. It is reproducible by regenerating from the
locked environment; the exact timestamp may differ, but component identity and
ordering are stable.

Dependency vulnerability management uses CI dependency tooling plus Dependabot.
No known critical/high vulnerability is accepted in this gate. New advisories
must be triaged before release closure.

License compatibility is reviewed for direct dependencies. The project remains
Apache License 2.0. Container image signing is not yet enabled; this must not be
represented as signed provenance until implemented.
