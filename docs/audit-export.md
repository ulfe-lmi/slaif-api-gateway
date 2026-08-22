# Audit, finance, project, and SIEM exports

Exports contain safe metadata only: timestamps, identifiers, provider/model
names, token/cost totals, event types, and outcomes. They never include prompt
or completion content, raw request bodies, credentials, or secrets.

Formats:

- Finance CSV: cost and usage by organizational unit and key.
- Security CSV: administrative lifecycle events.
- Project CSV: model/provider/tool usage metadata.
- SIEM JSON or CEF: authentication failures, permission denials, and fence events.

Spreadsheet injection is prevented by prefixing formula-leading text. Owner
identifiers can be pseudonymized after the configured retention window while
ledger totals remain immutable.
