# Image geometry admission verification — 2026-11-15

Implementation commit: `ca18f356382b54c81c8c271fdba8e69a51ffa240`.
Base: canonical `main` at `73297bb7c6e99d7fa2c83cfec70c6c5800fb5236`.
Branch: `fix/dimension-aware-image-estimation-20261115`.
The connected GitHub integration published the implementation because shell
Git credentials were unavailable. Its tree
`a56c315173760b5fea8e91a6f200d1b8982d1253` exactly matches the locally tested
implementation tree; publication changed commit metadata, not source content.

## Problem and resulting behavior

The fixed V100 image allowance was 16,896 tokens for every image. Manually
authorized Codex 0.167.1 probes used the actual `early-beta` profile, `--yolo`
and explicit `--model qwen3.8-27b-V100`. PostgreSQL accounting correlated the
successful requests to the original `gputest` route:

| Inline PNG | Upstream-reported input increase | Reservation increase |
|---|---:|---:|
| 256×256 | 104 | 16,926 |
| 512×512 | 296 | 16,925 |
| 1024×1024 | 1,066 | 16,926 |

The 512×512 compressed/noisy PNG pair had identical reservations despite
3,354 versus 787,252 source-file bytes. These are observations of provider
usage, not exact universal vision-token counts. The original private failing
request's image composition was not captured. Separate boundary experiments
hit the existing image-count and per-item text limits; those are not evidence
that the original request was reproduced.

The opt-in `patch_grid` policy now reads bounded PNG/JPEG/static-WebP headers
and applies operator-specified patch, spatial merge, minimum and overhead
values. The shipped example gives 128/320/1,088 image tokens for the three
sizes above. Unknown, remote, animated and overly long headers retain the
existing maximum allowance. No image pixels are decoded or rewritten.

The regression uses two bounded text items and 16 images. The fixed policy
rejects this history even at a 400,000-token ceiling; the new policy admits it
at 196,608 while still rejecting genuine text overflow. User and tool-result
images share the same estimator, which remains idempotent on route revalidation.

`--media-policy-file` provides a reviewed partial CLI edit that preserves
unrelated metadata; `--clear-media-image-geometry` restores the fixed policy.
Existing `codex_profile` declarations validate against the unchanged immutable
registry, so configuring media does not discard them or register new aliases.

## Final validation

| Check | Result | Duration |
|---|---|---:|
| Full unit suite, native user-local Python 3.12.16, 8 workers | 8,019 passed, 1 skipped | 178.63 s |
| PostgreSQL accounting finalization, including geometry reservation → actual usage | 6 passed, no skips | 3.58 s |
| Real CLI/PostgreSQL configuration workflows, including geometry file/partial merge/rollback/pinned declaration | 32 passed, no skips | 44.00 s |
| Ruff, application and tests | Passed | — |
| `git diff --check` | Passed | — |
| `alembic heads` | One head: `0028_demo_web_control` | — |

Test commands (with the stated environment/interpreter):

```text
python -m pytest tests/unit -n 8 --junitxml=unit-native-py312-final.xml
python -m pytest tests/integration/test_accounting_finalization_postgres.py -q --junitxml=accounting-geometry.xml
python -m pytest tests/integration/test_cli_provider_route_configuration_postgres.py -q --junitxml=cli-pinned-geometry-final.xml
python -m ruff check app tests
python -m alembic heads
git diff --check
```

`DATABASE_URL`, real upstream key variables and `RUN_UPSTREAM_TESTS` were unset
for these invocations; `APP_ENV=test` and `ENABLE_EMAIL_DELIVERY=false` were set.
The native Python environment's `bin` directory was on `PATH`. Accounting used
an explicit isolated `TEST_DATABASE_URL` on a new loopback-bound tmpfs PostgreSQL
16 container; the CLI module created and removed its own labeled PostgreSQL 16
container. The CLI fixture's `DATABASE_URL` referred only to that owned test DB.
Production databases were not used for destructive setup.

The one unit skip is the pre-existing
`test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`: Codex 0.148
is unavailable. No normal test invokes a real upstream model or sends email.
Focused estimator/config/CLI suites also passed; they overlap the full suite
and are not added to its count.

## Earlier environment attempts

These results are retained separately, not rewritten as passes:

- The initial host Python 3.14.4 full run had 8,005 passes, 4 failures and
  1 skip. All four failures reproduced on an untouched checkout of the exact
  base commit: two deep-JSON expectations and two subprocess checks with
  `python` unavailable on that host `PATH`.
- An existing Python 3.12 test image was unsuitable for final verification:
  it lacked `jsonschema`/`ps`, ran as root, and could not resolve the linked
  worktree's Git metadata. It recorded 7,836 passes, 8 failures, 2 skips and
  4 collection errors. It was replaced by the complete native user-local
  Python 3.12 environment above.
- One native run was deliberately interrupted before the final pinned-profile
  rollout validation changes. It is not counted as a completed result.

## Scope and rollout

The implementation adds no dependencies, database migrations, endpoints,
client dialect revisions, key grants or provider-body rewrites. Direct video
keeps its current policy; extracted frames represented as images use geometry.
The accounting and CLI tests verify durable reservations/final usage and safe
configuration storage, not new real-provider qualification.

The PR does not change production routes, gateway ceilings, client profiles,
keys, prices or quotas. After deploying reviewed code, enable the media policy
on the original and repaired V100 routes using a reviewed CLI plan. Verify the
affected conversation before removing the old ceiling padding. The separate
illustrative V100 qualification catalog still advertises 245,760 tokens;
lowering a route below that catalog minimum changes its static readiness and
requires explicit catalog/route alignment. Do not raise conservative client
limits to match the padded gateway estimate.

Documentation impact: README branding is preserved; media estimation,
CLI reference, accounting, forwarding, OpenAI/Responses compatibility,
compatibility matrix and security contracts are updated. Database schema is
unchanged. `docs/provider-routing.md` is absent; the relevant forwarding
contract and existing routing behavior were checked.
