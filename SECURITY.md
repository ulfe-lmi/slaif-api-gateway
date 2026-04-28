# Security Policy

SLAIF API Gateway is an open-source OpenAI-compatible gateway for institutional AI
access. It handles gateway-issued bearer keys, upstream provider API keys,
quota/accounting data, admin users, email delivery metadata, encrypted one-time
secrets, and operational logs.

Security reports are welcome. Please report vulnerabilities privately to the
maintainer. If no dedicated security email is configured yet, open a private
channel with the maintainer before sharing exploit details. Do not invent or
publish working exploit payloads against live systems.

## What To Report

Examples of useful reports include:

- plaintext gateway key storage or leakage
- provider API key leakage
- `Authorization` or other sensitive header forwarding bugs
- quota bypass, quota overspend, or accounting integrity failures
- Redis rate-limit bypasses when Redis rate limiting is enabled
- prompt or completion storage contrary to the documented policy
- accidental OpenAI/OpenRouter upstream calls in normal tests or local tooling
- authentication, HMAC validation, or key parsing bypasses
- admin authentication, CSRF, or session bugs once dashboard routes exist
- email/Celery plaintext key payload leakage
- logs or metrics exposing secrets

## What Not To Report Publicly

Do not post any of the following in public issues, pull requests, logs, or
screenshots:

- real gateway keys
- upstream provider secrets
- live credentials
- exploit payloads containing secrets
- personal data

## Supported Versions

This project is pre-release. No production release versions are supported yet
unless a release tag exists. The `main` branch is under active development, and
security-relevant pull requests are reviewed as part of normal development.

## Security Model References

- [Security model](docs/security-model.md)
- [Provider forwarding contract](docs/provider-forwarding-contract.md)
- [OpenAI compatibility](docs/openai-compatibility.md)
- [Compatibility matrix](docs/compatibility-matrix.md)
- [Review remediation matrix](docs/security/reviews/remediation-matrix.md)

## Reviews And Audits

External review documents in this repository are quality/security-oriented
mid-development reviews. They are not formal certifications, compliance audits,
or penetration tests.
