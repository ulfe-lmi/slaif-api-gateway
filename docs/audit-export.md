# Audit and usage export boundaries

> **Status:** Dashboard usage/audit CSV is wired; broader export builders are foundations
> **Audience:** Operators, security reviewers, and maintainers

The current admin dashboard exposes confirmed, audited CSV exports for filtered
usage and audit activity. They enforce row limits, neutralize spreadsheet
formula prefixes, and omit prompt/completion content, request/provider bodies,
plaintext keys, token hashes, encrypted one-time-secret material, credentials,
password hashes, and session tokens.

`services/audit_export.py` separately provides safe-column CSV builders for
finance, security, and project rows plus a bounded CEF formatter. No current API,
dashboard, or CLI route exposes those finance/project/CEF builders as named
products. SIEM delivery and retention-driven pseudonymization are not automated
by the current Gateway.

PostgreSQL usage and audit metadata remains the source for any operator export.
Exports are not invoices, compliance reports, or complete SIEM integrations.
