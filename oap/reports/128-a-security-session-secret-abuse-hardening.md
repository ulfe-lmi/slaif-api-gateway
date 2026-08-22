# OAP execution report — 128-a

Implementation head SHA: e78c1ccd9b4cb794292e7169b50aa33b45f4b49f
Report publication commit: SELF

## Scope

Added focused security-hardening primitives for the expanded SME surface:

- restrictive security headers;
- bounded login/identity abuse tracking;
- safe admin redirect validation;
- provider base-URL boundary (HTTPS public hosts or explicit numeric loopback only);
- fail-closed startup secret validation with default/example rejection outside development.

Added `docs/security-hardening.md` and incident-response runbooks for
credential compromise, suspected session hijack, and suspected DLP bypass.
No production certification, penetration-test, or compliance claim is made.

## Verification

Focused unit suite passed:

```text
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_security_hardening.py
# 8 passed
```

Ruff on changed paths passed. `git diff --check` passed.

All ten final-head GitHub checks were verified successful on implementation
head `e78c1ccd9b4cb794292e7169b50aa33b45f4b49f`.

## Security evidence

- Security headers include CSP with `frame-ancestors 'none'`, nosniff, DENY,
  and no-referrer.
- Abuse tracker blocks after threshold and can be cleared during compromise response.
- Open redirects are rejected; relative admin paths remain allowed.
- Provider URLs reject credentials, queries, fragments, paths, and non-loopback HTTP.
- Secret validation rejects missing or short values and example/default material in production mode.

No provider secrets or raw content are stored by these controls.

## Privacy/accounting evidence

No prompt/completion content was introduced or persisted. PostgreSQL remains
accounting truth. Existing lifetime limits and accounting behavior were unchanged.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
