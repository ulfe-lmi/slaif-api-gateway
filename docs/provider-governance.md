# Provider-governance foundation

> **Status:** Standalone validation foundation; not part of ordinary route resolution
> **Audience:** Maintainers evaluating post-MVP governance integration

The provider-governance model can validate reviewed metadata such as residency,
retention/training claims, approved destinations, evidence dates, and reviewers.
Its validation rejects missing, invalid, or stale evidence.

The current OpenAI/OpenRouter route resolver and provider-forwarding pipeline do
not consume this service. Ordinary runtime policy remains the key/route/provider
contract documented in [provider forwarding](provider-forwarding-contract.md).
Provider-governance metadata must not be described as an enforced residency or
retention control until it is wired and proven at that boundary.

This foundation stores no provider secret and offers no interpretation or
warranty concerning provider terms, residency, retention, or legal compliance.
