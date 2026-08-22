# Security hardening

Admin responses include a restrictive CSP, `X-Content-Type-Options`,
`X-Frame-Options`, and `Referrer-Policy`. Admin redirects are relative-path only
or explicitly allow-listed. Provider base URLs permit HTTPS public hosts or
explicit numeric loopback; redirects, credentials, queries, and paths are
rejected.

Login throttling uses bounded failure tracking per subject and can be cleared
after credential-compromise response. Required startup secrets must exist and
meet minimum length; default/example values are rejected outside development.

Dependency scanning should run in CI using pip-audit or Safety. These controls
do not claim penetration testing or compliance certification.
