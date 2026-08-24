# Optional DLP and PII foundation

> **Status:** Standalone service foundation; not wired into Gateway egress
> **Audience:** Maintainers evaluating a future policy integration

`services/dlp.py` provides bounded regex detectors for email, phone, card-like,
and SSN-like text and returns redacted detector names/confidence. Its `block`,
`flag`, and `monitor` decisions have unit coverage.

No current API, policy, provider-forwarding, CLI, dashboard, audit, or storage
path calls this scanner. It therefore does **not** currently block provider
egress or create audit findings. Any integration must define bounded scan input,
failure policy, endpoint/capability scope, audit semantics, privacy tests, and
operator controls before this can become a product feature.

Regex detection is incomplete and is not legal, compliance, or PII-removal
assurance.
