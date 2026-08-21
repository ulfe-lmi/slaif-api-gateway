# OAP 022-a execution report

Implementation head SHA: `526d751d3bd7e7711ebda726ece52fffda457ec8`
Report publication commit: SELF

## Scope and outcome

Objective 022-a prepared the bounded Codex 0.148.0 / Qwen3.8-27B text
qualification candidate. The candidate is immutable, credential-free, uses
Responses only, remains outside `CODEX_PROFILE_REGISTRY`, and is therefore not
available to production route selection or CLI/admin configuration. Live
qualification remains required.

The exact target variables were checked without printing values:

- `SLAIF_QWEN38_TEXT_BASE_URL`: absent
- `SLAIF_QWEN38_TEXT_API_KEY`: absent
- live target state: `live_target_absent`
- real provider/LAN calls: not run

No production registry entry, migration, provider call, email, or release
action was made. This round leaves the live phase for a same-PR continuation.

## Candidate evidence

- Profile ID: `qwen3.8-27b-text-codex-0.148-v1`
- Codex CLI: `0.148.0`
- Public model: `qwen3.8-27b-text`
- Upstream model: `qwen3.8-27b`
- Wire API: Responses `/v1/responses`
- Provider kind: `openai_compatible`
- Context window: `150000`
- Default/max output: `32768` / `128000`
- Client-local compaction threshold: `125000`
- Input modalities: text only
- Route gates: request envelope, client tools, streaming tool events
- Compaction: client-local
- Reasoning replay, remote compaction, image input, parallel tools, search,
  hosted/MCP tools, apps/plugins, and freeform patching: unavailable
- Sanitized fixture: `tests/fixtures/codex/0.148.0/qwen3.8-27b-text-api-key-responses.json`
- Sanitized fixture digest: `9bd5f49ca90c3448cc6ad6559ef87868295a45da54676463eed301a9fb6b2959`

The replacement model catalog contains only bounded safe metadata and no
credentials, URLs, prompts, responses, tool arguments, or provider content.

## Tests and checks

Exact local commands and results:

```text
.venv/bin/python -m pytest -q tests/unit/test_qwen38_text_codex_candidate.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py
85 passed

.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py scripts/verify_qwen38_text_codex.py tests/unit/test_qwen38_text_codex_candidate.py
All checks passed

git diff --check
passed

PYTHONPATH=app .venv/bin/python scripts/verify_qwen38_text_codex.py
RESULT=LIVE_TARGET_ABSENT
LIVE_TARGET_PRESENT=false
REAL_PROVIDER_CALLED=false
```

The initial system-Python pytest attempt was not a test result: collection
could not import `structlog`. The declared development environment was then
installed into the existing `.venv`; the focused run above passed.

PostgreSQL setup/cleanup: not required and not run. Redis setup/cleanup: not
required and not run. No destructive database setup targeted `DATABASE_URL`.
No broad local suite, browser suite, Docker suite, or upstream suite was run;
routine broad coverage is delegated to GitHub CI.

GitHub checks on PR #248 at report publication: all nine required checks were
`pending` and none was reported failed: Analyze (javascript-typescript),
Analyze (python), Analyze Python, Docker Compose smoke, Documentation hygiene,
OpenAI-compatible E2E tests, Playwright browser smoke, PostgreSQL integration
tests, and Unit, lint, and migration head.

## Security, privacy, and accounting evidence

The verifier accepts no CLI URL/key arguments, rejects public/non-numeric,
credential-bearing, query, and fragment targets, and emits fixed low-cardinality
status lines without reflecting environment values. The absent-target path made
no network request. No raw fixture traffic, secrets, prompts, responses,
headers, tool arguments/results, provider credentials, or personal data were
persisted or committed. PostgreSQL accounting and quota behavior were not
exercised because the live target was absent.

Documentation impact: the candidate and verifier are self-documenting in code;
no existing compatibility or production qualification claim was changed.

## PR and merge state

- PR: [#248](https://github.com/ulfe-lmi/slaif-api-gateway/pull/248)
- Branch: `oap/022-qwen38-text-codex-qualification`
- Base: `main`
- No merge performed.
- Auto-merge not enabled.

This report is the only file changed by the publication commit, whose first
parent is the implementation head above. The report publication commit is
the remote PR head at publication time.
