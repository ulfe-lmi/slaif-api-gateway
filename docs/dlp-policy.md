# Optional DLP and PII policy

DLP is optional and bounded. Local regex-based detectors can identify simple
email, phone, card-like, and SSN-like patterns. Modes:

- `block`: deny egress when a finding occurs; fail closed on scanner failure.
- `flag`: allow but audit the finding.
- `monitor`: audit-only.

Findings are always redacted: audits store detector name and confidence, never
matched content. Scanning buffers are ephemeral. This is not a claim of complete
PII detection or legal compliance.
