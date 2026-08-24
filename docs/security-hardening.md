# Security hardening controls

> **Status:** Current implementation guide
> **Authority:** [Security model](security-model.md) for the complete trust and privacy contract
> **Not:** A certification, penetration-test report, or deployment approval

This page identifies hardening that is reachable in the deployed Gateway and
separates it from reusable security primitives that are not wired into runtime
entrypoints.

## Deployed controls

- Production Nginx terminates TLS, redirects HTTP to HTTPS, exposes only ports
  80/443, keeps PostgreSQL, Redis, and the API on the internal network, and
  attaches CSP, `X-Content-Type-Options`, `X-Frame-Options`, and
  `Referrer-Policy` headers.
- Admin login uses a CSRF cookie/form-token pair. Failed-attempt and lockout
  decisions are derived from PostgreSQL audit rows by normalized email and
  client address; blocked attempts return HTTP 429.
- Admin sessions and CSRF tokens are random, stored only as hashes, expire
  server-side, and use configurable secure, HTTP-only, SameSite cookies.
- Production startup validates required HMAC, admin-session, one-time-secret,
  provider, database, Redis, and request-cap settings. Placeholder or short
  secrets fail validation; direct production secret environment variables are
  rejected by the production Compose entrypoint in favor of `*_FILE` inputs.
- Gateway keys are hashed, upstream provider credentials are resolved
  server-side, and provider authorization headers replace client credentials.
- Generic OpenAI-compatible provider URLs must be exact
  `http(s)://host[:port]/v1` URLs without embedded credentials, query, fragment,
  whitespace, or control characters. Plain HTTP for a generic backend requires
  explicit operator confirmation and a non-empty audit reason. This is an
  operator trust decision, not an SSRF-safe host allow-list.
- Native-module URLs receive the same syntax and credential/query/fragment
  checks but may include a module path. The facial-scoring adapter disables
  redirects; generic discovery also disables redirects and bounds the response.
  Consult the [provider-forwarding contract](provider-forwarding-contract.md)
  for each supported adapter rather than assuming one global URL policy.

The production qualification harness exercises the Nginx/TLS boundary, startup
secret loading, admin login, PostgreSQL/Redis behavior, and content/secret
canary scans. It is appliance evidence for one exact commit, not formal
security assurance.

## Standalone primitives

`app/slaif_gateway/services/security.py` contains small header, redirect, URL,
secret-strength, and in-process abuse-tracking helpers. They have unit tests,
but the production app does not import that module. They therefore do not prove
that a runtime control exists. The deployed controls above are backed by their
actual Nginx, configuration, admin-session, provider-config, and adapter paths.

## Evidence and limits

CI runs CodeQL and focused security, integration, browser, and production
qualification checks. Dependabot is configured. CI does not currently run
`pip-audit` or Safety, sign images, generate attestations, or provide an
independent penetration test. See [supply-chain evidence](supply-chain.md) and
the [security-review archive](security/reviews/README.md).
