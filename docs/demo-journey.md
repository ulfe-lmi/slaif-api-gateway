# Clean-clone SME operator journey

This journey validates a clean clone using documented steps and no hidden local
state. Run:

```bash
DATABASE_URL=postgresql+asyncpg://... bash scripts/demo/run-journey.sh
```

The script checks prerequisites, validates Compose configuration, applies
migrations, points to guided browser onboarding, and optionally performs backup,
restore, and verification when safe disposable URLs are provided.

Manual operator evidence is expected for:
- first admin creation;
- OIDC or local fallback choice;
- provider metadata and secret environment name;
- approved catalog/policy revision;
- budget definition;
- strict-mode key issuance;
- OpenAI client chat/responses usage;
- Codex CLI local-tool usage;
- quota hold/block/release behavior;
- finance/security/SIEM exports.

All limitations remain visible. No production data or broad live provider spend is used.
