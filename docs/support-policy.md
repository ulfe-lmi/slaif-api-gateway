# Support policy

> **Status:** Current project support boundary
> **Release state:** Pre-release; see [current readiness](beta-readiness.md)

The documented deployment model is self-hosted Docker Compose on Linux from a
published tag or an exact reviewed commit. Operators own the host, TLS,
provider agreements and credentials, backups, monitoring, capacity decisions,
and change approval.

Security vulnerabilities should be reported privately through GitHub security
advisories. Do not open a public issue containing exploit details, credentials,
prompts, provider responses, or personal data. See [SECURITY.md](../SECURITY.md)
for the reporting and disclosure process.

Community support may cover documented setup, migrations, configuration,
backup/restore, and reproducible defects. It does not include:

- a response-time or resolution-time SLA;
- managed operations, incident command, or provider support;
- compliance certification or interpretation of provider terms;
- custom forks, unsupported endpoint behavior, or hostile multi-tenant use;
- guaranteed downgrade across migrations; or
- invoice-grade billing or reconciliation with provider invoices.

Rehearse upgrades and restore procedures on disposable infrastructure before
changing an important deployment. The [operator runbooks](runbooks/README.md)
describe recovery boundaries but are not a commercial support commitment.
