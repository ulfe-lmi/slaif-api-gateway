# OAP Work Order — 156-b

## Objective and reason

Continue existing Objective 156 on PR #293 solely to reconcile the false
formatter/equivalence conflict in immutable 156-a. Do not change product,
tests, fixtures, doctrine, or documentation.

156-a correctly preserved the mandatory accepted source blobs and all
repository-required checks passed, but its order simultaneously required
`ruff format --check`. Ruff 0.15.16 would rewrite six selected accepted-source
files, while the decomposition contract requires those files—and ultimately
the accepted `app/` tree—to remain byte-identical. Repository CI requires
`python -m ruff check`, not `ruff format --check`. Reformatting would therefore
violate the stronger frozen-equivalence requirement without correcting product
behavior.

The purpose of 156-b is to verify that diagnosis, apply the repository's actual
lint contract, preserve the implementation unchanged, and publish a truthful
same-PR acceptance report.

## Verified starting state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- PR: #293, open and non-draft.
- Branch: `oap/156-agentic-doctrine-codex-0149-client-contract`.
- Base: current authorized main
  `2823b1b8ca95aeb795b2df8bba49c2d9f2cb9ddf`.
- Immutable 156-a implementation head:
  `5e37809e339a29178036a8793b223be8c3776a4a`.
- Immutable 156-a FAILED report head/current starting head:
  `2d987e71f19181a3c26723110fdd4cfb0e338b60`.
- The 156-a report is report-only, its first parent is the implementation head,
  and all ten final-head GitHub checks are successful.
- PR #292's inherited `AGENTIC_CLIENT_INTEGRATION.md` remains unchanged at blob
  `7c48c679d14aa127f0c31fc3260e4a3fb01ee25f`.
- PR #291 remains the untouched Objective-155 evidence branch.

## PR mode

- PR mode: `AMEND_EXISTING_PR`
- Amend only PR #293 and its existing branch.
- Do not create another PR.
- Do not merge or enable auto-merge.
- Preserve immutable 156-a order/report and every existing commit.

## Allowed paths

- `oap/active`
- `oap/orders/156-b-accepted-blob-format-gate-reconciliation.md`
- `oap/reports/156-b-accepted-blob-format-gate-reconciliation.md`

No non-OAP path may change relative to implementation head `5e37809...`.

## Required reconciliation

1. Verify the exact 156-a report topology, PR identity, base, branch, remote
   head, changed paths, and ten successful checks.
2. Verify every non-OAP path at current PR head is byte-identical to
   implementation head `5e37809...`.
3. Verify the selected accepted source/tool/fixture blobs remain:

   | Path | Required blob |
   |---|---|
   | `app/slaif_gateway/modules/clients/codex_0149.py` | `c196eb2f9608248303d6d9f2126d1d7596438866` |
   | `app/slaif_gateway/modules/contracts.py` | `653ec8f8770c2c5c464663d614bda126d6e5ace7` |
   | `app/slaif_gateway/services/responses_request_policy.py` | `88f3ff334818aa31b06dbf12066beb224e6b5bc1` |
   | `scripts/capture_codex_protocol.py` | `7bc06d39fedbe3d6d6957137c5afc0e751f38f77` |
   | `tests/fixtures/codex/0.149.0/responses-structural-v2.json` | `c182dd195312368d58c80f25c915e83e8474a470` |
   | `tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json` | `a0073a638b82750b3752ac5b78f5df91f97d7d56` |

4. With exact Ruff 0.15.16, reproduce `ruff format --check` on the seven
   Python paths named by 156-a and retain only the bounded path/count result.
   Confirm that it proposes formatting changes to accepted-source files; do
   not apply those changes.
5. Inspect current `pyproject.toml`, `.github/workflows/ci.yml`, repository
   governance, and the normal check suite. Prove the repository-authoritative
   lint gate is Ruff `check` and does not impose `ruff format --check`.
6. Run the repository-authoritative Ruff check on all changed Python paths and
   run Python compilation on those paths. Both must pass.
7. Re-run the focused doctrine governance test and the focused no-active-pair
   runtime denial tests. Re-run
   `tests/integration/test_codex_client_modules_postgres.py` in the
   repository-standard disposable PostgreSQL environment with no required
   skip/xfail/failure.
8. Do not repeat the task-local live capture merely to reproduce unchanged
   evidence. Instead verify that the capture tool/fixture blobs are unchanged
   and carry forward the immutable 156-a zero-provider-call structural/session
   capture results.
9. Push an activation-only commit containing this order and `oap/active`, then
   publish the final report-only commit. Require all ten GitHub checks on the
   exact report head to be successful before signalling completion.

## Acceptance law

`RESULT=PASSED` requires:

- no non-OAP diff from `5e37809...`;
- all mandatory blob identities unchanged;
- inherited doctrine unchanged;
- the formatter conflict reproduced without rewriting files;
- repository-required Ruff check and compilation green;
- focused doctrine/no-pair/PostgreSQL evidence green;
- all ten exact report-head checks green;
- PR #293 open, unmerged, no auto-merge;
- no Objective 157 work.

The non-gating formatter diagnostic must be documented honestly as existing
formatting debt inherited from the frozen accepted source snapshot. This is
not permission to ignore Ruff lint, introduce new formatting debt, or weaken
future repository policy. Any later formatting/refactor must occur only after
the accepted-behavior reconstruction and its own reviewed equivalence method.

## Non-goals and prohibitions

Do not:

- change or reformat any non-OAP file;
- amend the immutable 156-a report;
- alter Codex behavior, client policy, fixtures, governance prose, or docs;
- activate Local Coding, add a server/pair, or implement streaming/reasoning/
  replay behavior;
- activate Objective 157 or any later objective;
- modify PR #291 or `AGENTIC_CLIENT_INTEGRATION.md`;
- run protected/provider/Local/Qwen traffic;
- merge or auto-merge.

## Report duties

Publish exactly one immutable report:

`oap/reports/156-b-accepted-blob-format-gate-reconciliation.md`

It must record:

- `RESULT=PASSED` or `RESULT=FAILED`;
- repository/PR/base/branch and exact starting/report/implementation heads;
- `Report publication commit: SELF`;
- report-only topology;
- exact non-OAP zero-diff proof from `5e37809...`;
- actual blob identities;
- bounded Ruff format diagnostic count/paths and confirmation no rewrite was
  applied;
- source-reviewed repository lint contract and exact Ruff-check/compile
  results;
- focused test and executed PostgreSQL result counts;
- carried-forward immutable capture evidence and why no provider call/retry was
  needed;
- all ten final-head check states;
- documentation impact statement: no documentation change because this is a
  verification-contract correction only;
- limitations and explicit no-157/no-merge state.

The final report commit must change only that report and have the activation
commit as its first parent because no implementation change is authorized.
Verify it is the remote PR head and all claimed state exists, then write exactly
`OK` to the response FIFO and return to one blocking control-FIFO read.
