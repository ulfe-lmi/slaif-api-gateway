# OAP Work Order — 024-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/024-model-qualification-hello-matrix`
Base: main @ 4044a94aa7ddad308b902bbefba593b1a85b95c9

## Objective and reason

Record the first-tier model qualification matrix: five external models
(NVIDIA Nemotron Super, MoonshotAI Kimi K3, OpenAI Luna/Terra/Sol) have been
verified through the SLAIF API gateway using Codex CLI "Reply with exactly:
HELLO" prompts. All five returned HTTP 200 with correct output and PostgreSQL
usage-ledger entries. This order publishes the evidence as a compatibility-matrix
docs update plus a structured qualification report. No gateway code changes.

## Human-authorized live targets (explicit approval received)

The human has authorized these exact debug/development targets:

- **OpenRouter** (`https://openrouter.ai/api/v1`):
  - API key stored in `.env` as `OPENROUTER_API_KEY` (already configured)
- **OpenAI API** (`https://api.openai.com/v1`):
  - API key stored in `/home/ubuntu/codex-work/slaif-openai-key.sh`
    (sourced at runtime; never committed or logged)

### Hard constraints on the live phase

- All calls strictly sequential.
- ≥15 s gap between calls to free-tier models.
- No concurrent requests against any single provider endpoint.
- If a provider returns 429/5xx, back off ≥30 s and retry once; do not hammer.

## Verified state

- main = 4044a94aa7ddad308b902bbefba593b1a85b95c9; no open non-Dependabot PR.
- Objective 121-a terminal (merged).
- Gateway running locally on :8000 from this commit with all migrations applied.
- Provider configs seeded for `openrouter` and `openai_pro` (kind=openai_compatible).
- Model routes seeded for all five models at `/v1/responses` with default Responses capabilities.
- Pricing rules seeded (zero-cost placeholders for Nemotron/Luna/Terra/Sol;
  €3/M input + €15/M output for Kimi K3 per published OpenRouter pricing).
- Gateway key issued for testing (hint: qualification-ladder-024).

## Scope

1. Add a new section to `docs/compatibility-matrix.md` titled
   **"Codex CLI model qualification — tier-1 hello"** with a table of five rows:

   | Model | Provider | Wrapper | Exit | Reply | Ledger tokens | Est. cost EUR | Date |
   |---|---|---|---|---|---|---|---|
   | nvidia/nemotron-3-super-120b-a12b:free | openrouter | openrouter | 0 | HELLO | 200 | 0 | 2026-08-22 |
   | moonshotai/kimi-k3 | openrouter | openrouter | 0 | HELLO | 163 | 0.0154 | 2026-08-22 |
   | gpt-5.6-luna | openai_pro | pro | 0 | HELLO | 18 | 0 | 2026-08-22 |
   | gpt-5.6-terra | openai_pro | pro* | 0 | HELLO | 18 | 0 | 2026-08-22 |
   | gpt-5.6-sol | openai_pro | pro* | 0 | HELLO | 18 | 0 | 2026-08-22 |

   Footnote: *Terra and Sol were verified through the gateway via explicit
   `/v1/responses` POST calls (ledger entries confirmed) after discovering that
   the `codex-subscription pro` wrapper ignores `OPENAI_BASE_URL` and sends
   directly to `api.openai.com`. The gateway-level proof is still valid because
   the same request shape was forwarded successfully with accounting recorded.

2. Create `oap/reports/024-a-model-qualification-hello-matrix.md` following
   the standard report structure with sections:
   - Objective
   - Changes (docs only)
   - Live verification evidence (per-model table above, plus chain description)
   - Test results (git diff --check only; no code changes)
   - Security review (no code change; no trust boundary widened)
   - Privacy/accounting evidence (usage_ledger rows exist for all 5 models;
     quota_reservations all finalized/released; no content persisted)

3. No changes to application code, migrations, tests, configuration defaults,
   profile registry, or any other file outside the two allowed paths below.

## Allowed paths

```
docs/compatibility-matrix.md
oap/orders/024-a-model-qualification-hello-matrix.md
oap/reports/024-a-model-qualification-hello-matrix.md
oap/active
```

## Non-goals

No gateway runtime behavior change.
No new profile registration or catalog artifact.
No tier-2 (basic task), tier-3 (tool-use), or vision qualification.
No auth-passthrough/BYOK feature.
No pricing accuracy improvement beyond what is already seeded.
No docs update to other files.

## Observable acceptance

- The compatibility-matrix table is present with exactly five data rows matching
  the verified evidence.
- The report file exists with all six required sections.
- `git diff --check` passes.
- All required final-head CI checks are green.
- No unresolved review threads on the final head.

## Verification commands

```bash
git diff --check
grep -c '^|' docs/compatibility-matrix.md  # should increase by 7 (header+sep+5 rows)
ls -la oap/orders/024-a-model-qualification-hello-matrix.md oap/reports/024-a-model-qualification-hello-matrix.md
```

No unit/integration test runs needed since only documentation changed.

## Boundaries

Non-production LAN/dev environment only. Provider credentials remain in env
vars or local shell scripts, never committed. No prompt/completion content is
persisted beyond existing accounting metadata. PostgreSQL remains the sole
accounting truth source.

## OAP/GitHub contract

Objective `024-a` creates exactly one new PR for numeric objective `024`.
Any remediation uses `024-b` through `024-z` on that same PR.
The coding agent commits the activated order and `oap/active` unchanged with
implementation/governance work.
The coding agent publishes exactly one immutable report in a final
report-only `SELF` commit and never merges or enables auto-merge.
The strategic model independently verifies GitHub, diff, evidence, and all
required final-head checks before merge.
