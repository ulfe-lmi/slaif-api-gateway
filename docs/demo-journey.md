# Disposable production-appliance journey

> **Status:** Current wrapper for the production qualification harness
> **Audience:** Maintainers and reviewers
> **Not:** A guided onboarding demo, deployment command, or production certification

`scripts/demo/run-journey.sh` delegates directly to the strict disposable
production-appliance qualification:

```bash
bash scripts/demo/run-journey.sh
```

The harness creates a unique Compose project, generated TLS and secrets,
PostgreSQL, Redis, the production API image, NGINX, worker/scheduler processes,
and a socket-level provider double. It exercises supported Chat and Responses
flows, accounting failure paths, Redis controls, process interruption,
persistence, backup/restore, dashboard access, metrics, privacy canaries, key
lifecycle, and exact cleanup.

It refuses inherited production/database/upstream-test configuration and makes
no real OpenAI or OpenRouter call. See the
[production qualification record](verification/2026-08-24-production-appliance-qualification.md)
for the exact evidence and limitations.

For human first-time setup, use the [quickstart](quickstart.md). For production
deployment preparation, use [Production Compose deployment](deployment-production.md).
