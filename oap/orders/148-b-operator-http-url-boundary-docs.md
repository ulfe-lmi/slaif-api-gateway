# OAP Work Order — 148-b

PR mode: `CONTINUE_EXISTING_PR`
PR: [#283](https://github.com/ulfe-lmi/slaif-api-gateway/pull/283)
Branch: `oap/148-facial-manipulation-scoring-adapter`
Base: `main @ 67561d7718af2eac0947b6f1ae31051df59356ca`
Current head: `f5af8494d0c5b4965d6e49ba401ff8a168d6bcbf`
Title: `feat: add facial-manipulation-scoring Chat adapter`

## Objective and reason

Correct one operator-documentation ambiguity found during independent review
of 148-a. The verified facial service currently answers over HTTP on the
internal network, while the new configuration paragraph says only “HTTPS
origin.” The docs must state both the secure deployment recommendation and the
existing explicit-audit boundary for internal HTTP without changing runtime
behavior or enabling an endpoint.

## Reconciled current state

- 148-a implementation head `45dfa9806ef3f661f0f41e5672b02d3ea429c552`
  and report publication head `f5af8494d0c5b4965d6e49ba401ff8a168d6bcbf`
  are pushed to PR #283.
- The report publication commit changes only the immutable 148-a report.
- The focused adapter/capability/forwarding tests, Ruff, compile, and diff
  checks independently pass. Final GitHub checks for the current PR head are
  green; this continuation will trigger fresh checks.
- The current verified candidate service addresses are
  `http://maelstrom1.lmi.link:8000` and `http://10.8.132.72:8000`. They are
  configuration observations only and must not be added to docs, code,
  fixtures, reports, or committed provider rows.

## Requirements

1. Update only the facial scoring provider-setup paragraph in
   `docs/configuration.md` to say that operators should prefer an HTTPS origin,
   while an internal HTTP origin is permitted only through the existing
   explicit confirmation, non-empty audit-reason, and operator firewall/
   reverse-proxy boundary.
2. Preserve the existing statements that the base URL is operator-selected,
   `FACIAL_SCORING_API_KEY` is server-side only, `max_retries=0` is required,
   and provider/route/pricing activation does not make a live score request.
3. Do not add either observed service address, credentials, image/data-URL
   material, or any runtime/application/test change.

## Exact allowed paths

```text
docs/configuration.md
oap/orders/148-b-operator-http-url-boundary-docs.md
oap/reports/148-b-operator-http-url-boundary-docs.md
oap/active
```

No other path may change.

## Acceptance and verification

- The paragraph accurately distinguishes HTTPS recommendation from explicitly
  audited internal HTTP configuration and does not imply that the gateway
  fetches or probes the service during setup.
- The implementation diff contains only the one bounded documentation edit.
- Run `git diff --check`; the final PR-head required CI, including
  documentation hygiene, must be green. Pending, skipped, missing, cancelled,
  or environment-blocked checks are not passes.

## Security and publication contract

No credentials, service addresses, images, data URLs, raw request/response
bodies, or production configuration may be added. The coding agent must keep
PR #283, never merge or enable auto-merge, and publish a final report whose
SELF commit changes only `oap/reports/148-b-operator-http-url-boundary-docs.md`.
The 148-a order/report remain immutable.
