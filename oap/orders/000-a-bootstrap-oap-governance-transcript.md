# OAP Work Order — 000-a

## Objective

Bootstrap the SLAIF API Gateway OAP governance and versioned transcript in
exactly one new GitHub pull request.

This objective adopts the already prepared gateway-specific repository
constitution, coding-agent communication protocol, and `oap/` scaffold; adds
narrow repository tests for the OAP invariants; protects local Codex and
provider-catalog state from accidental commits; publishes the active order and
pointer; and returns an immutable evidence report.

This is governance/bootstrap only. It must not change application behavior.

## GitHub objective state

- Numeric objective: `000`
- Execution round: `000-a`
- PR mode: `CREATE_NEW_PR`
- Existing objective PR: N/A
- Required head branch: `oap/000-bootstrap-oap-governance-transcript`
- Base branch: `main`
- Required PR title: `[OAP 000] Bootstrap gateway OAP governance`
- Required PR readiness: non-draft (`draft: false`)
- Repository: `ulfe-lmi/slaif-api-gateway`
- Canonical remote: `https://github.com/ulfe-lmi/slaif-api-gateway.git`

## Current verified state

The strategic model independently verified immediately before activation:

- remote default branch: `main`;
- remote/local baseline:
  `0c921ea1827cf13e645b20b653660194873d38fd`;
- that commit is the merge commit for PR #220,
  `Harden Realtime client-secret admission accounting`;
- the only open PR is unrelated Dependabot PR #224 on
  `dependabot/github_actions/github-actions-e91bde37dc`;
- PR #224 is not part of this objective and currently has a failed
  `Unit, lint, and migration head` check;
- the only published release is `v0.1.0-rc.1`;
- no prior SLAIF API Gateway OAP objective exists;
- repository `oap/active` and objective reports are absent before this
  activation;
- both external synchronization objects exist as FIFO files owned by
  `ubuntu:ubuntu` with mode `0644`.

The primary checkout intentionally contains these prepared bootstrap inputs:

```text
 M AGENTS.md
?? OAP-COMMUNICATION-coding-agent.md
?? oap/
?? .local-provider-catalog/
```

The strategic model has now authored this active order and `oap/active`.
Those two files are also intended bootstrap inputs.

`AGENTS.md`, `OAP-COMMUNICATION-coding-agent.md`, and the `oap/` scaffold were
prepared deliberately for objective 000. They are not unrelated dirty state.
The existing `.local-provider-catalog/` directory is unrelated generated local
state: preserve it byte-for-byte, do not inspect its content unless needed only
to confirm path existence, never commit it, and do not clean/reset/stash/delete
it.

If `git fetch origin` shows that remote `main` moved away from the verified SHA,
or if any additional tracked modification exists beyond `AGENTS.md` plus the
strategic-authored active order/pointer, stop without modifying anything and
publish/report the exact blocker according to the protocol. Do not rebase or
discard prepared governance automatically.

## Strategic context

The gateway has grown from a workshop-oriented RC-beta into the foundation for
an SME organizational AI access and usage control plane. Before feature work
continues, the human has selected the same automatic bidirectional OAP model
used by `slaif-agent-site`.

The paired protocol establishes:

- GitHub as authoritative software/project truth;
- `oap/active` as the sole work selector;
- one numeric objective as exactly one PR;
- continuation letters as amendments to the same PR;
- immutable orders/reports and report-only `SELF` commits;
- coding-agent prohibition on merge;
- strategic independent review and delegated merge authority;
- human ownership of intent, risk, and release.

Objective 000 makes those rules durable in the coding repository. It does not
implement Codex-through-gateway support, external tools, SME identities,
budgets, or other roadmap features.

## Governing instructions

Read completely before editing:

1. repository `AGENTS.md`;
2. `OAP-COMMUNICATION-coding-agent.md`;
3. `oap/README.md`;
4. `oap/orders/README.md`;
5. `oap/reports/README.md`;
6. this active work order;
7. relevant existing repository test and documentation conventions.

Do not read or execute inert strategic proposals under
`/home/ubuntu/codex-supervision/slaif-api-gateway/workorders/` as work orders.

## Required start sequence

From the existing primary checkout:

1. run `git fetch origin`;
2. verify local `HEAD` and `origin/main` are both exactly the verified baseline;
3. inspect `git status --short --branch`;
4. verify only the intended bootstrap files plus `.local-provider-catalog/` are
   present;
5. create the required branch directly from the current `main` checkout:

```bash
git switch -c oap/000-bootstrap-oap-governance-transcript
```

Do not run `git pull`, reset, stash, clean, checkout-over, or create a linked
worktree for this objective. The prepared files in this checkout are the
authorized objective inputs.

If the required branch already exists locally or remotely unexpectedly, inspect
GitHub and stop/report rather than overwriting or inventing another branch.

## Allowed path scope

Only these paths may change in implementation/governance commits:

```text
.gitignore
AGENTS.md
OAP-COMMUNICATION-coding-agent.md
oap/README.md
oap/active
oap/orders/README.md
oap/orders/000-a-bootstrap-oap-governance-transcript.md
oap/reports/README.md
tests/unit/test_oap_governance.py
```

The final report-publication commit may add only:

```text
oap/reports/000-a-bootstrap-oap-governance-transcript.md
```

Do not touch any application, migration, dependency, workflow, deployment,
provider-catalog artifact, handover, strategic file, or unrelated documentation
path.

## Required implementation

### A. Review and finalize the prepared constitution

Review the prepared `AGENTS.md` for internal consistency with:

- the coding-agent OAP protocol;
- current repository paths and canonical GitHub identity;
- the explicit pre-activation/bootstrap transition;
- coding-agent never-merge behavior;
- strategic OAP-only merge authority after activation;
- GitHub and live contract-document authority;
- preservation of local generated state;
- no claim that creating files alone activates execution.

Make only corrections required for objective-000 consistency. Do not rewrite
the product roadmap or add feature behavior.

### B. Review and finalize the coding-agent protocol

Review `OAP-COMMUNICATION-coding-agent.md` completely.

It must preserve at least:

- exact fixed repository/strategic/FIFO paths;
- exact FIFO payload `OK` with no newline;
- `oap/active` sole-selector rule;
- `NNN-a` creates one PR and `NNN-b...z` amend it;
- strategic ownership of orders/active;
- coding ownership of reports;
- unchanged strategic artifacts committed by the coding agent;
- literal implementation head plus `Report publication commit: SELF`;
- final report-only commit and parent/path verification;
- checks triggered by the report commit may be pending for strategic review;
- coding-agent absolute merge prohibition;
- passwordless-sudo/local autonomy without production boundary expansion.

Do not weaken or shorten away these invariants.

### C. Finalize the versioned OAP scaffold

The repository must contain:

```text
oap/
├── README.md
├── active
├── orders/
│   ├── README.md
│   └── 000-a-bootstrap-oap-governance-transcript.md
└── reports/
    └── README.md
```

Before the report-publication commit, `oap/reports/` contains only its README.
The coding agent later adds the one immutable `000-a` report as the final
round commit.

`oap/active` must contain exactly:

```text
000-a
```

An optional final LF is harmless. Do not edit the active order or pointer; they
are strategic-model-authored and already published.

The OAP README must explain the pre-activation transition without claiming the
now-active pointer is absent forever. It must state that after activation the
pointer is authoritative and changes only through strategic atomic publication.

### D. Protect local execution artifacts

Update `.gitignore` with explicit project-local entries for:

```text
.codex/
.local-provider-catalog/
```

Do not delete or move either directory. Do not add a broad pattern that would
ignore versioned OAP transcript files, repository `agents/` skills, or other
legitimate artifacts.

After the ignore change, verify the existing local
`.local-provider-catalog/` data still exists and is not staged.

### E. Add repository OAP governance tests

Add `tests/unit/test_oap_governance.py` using repository test conventions and
standard-library/path parsing where practical.

The tests must prove at least:

1. required OAP governance/scaffold files exist;
2. `oap/active` contains a syntactically valid `NNN-L` identifier;
3. exactly one order matches the active identifier;
4. the matching order heading/identifier and filename agree;
5. current active `NNN-a` states `CREATE_NEW_PR` and one-objective/one-PR;
6. repository `AGENTS.md` and coding protocol both state that the coding agent
   never merges;
7. the coding protocol contains exact `OK`/no-newline FIFO semantics;
8. the coding protocol contains the implementation-head/`SELF` report rule;
9. `.gitignore` protects `.codex/` and `.local-provider-catalog/`;
10. strategic `handover/` and `workorders/` directories are not part of the
    repository OAP transcript.

Tests must not require a report before the coding agent publishes the final
report commit. They may validate a report if present, but must not make the
implementation-head test fail merely because report publication is the next
protocol step.

Do not hardcode future active IDs or assume `000-a` remains active forever when
a general invariant can be tested.

### F. Keep changes narrow and reviewable

Review the prepared diff carefully. Correct spelling, paths, contradictory
activation wording, Markdown whitespace, and protocol mismatches only where
needed.

Do not opportunistically modify product/API/accounting/provider behavior,
current RC2 feature claims beyond an objective-000 contradiction, or the
strategic roadmap.

## Explicit non-goals

- No application feature or bug fix.
- No migration or database operation.
- No package/dependency change.
- No CI workflow change unless impossible to run the existing unit suite without
  it; if so, stop and report rather than expanding silently.
- No real OpenAI/OpenRouter/provider call.
- No production/staging/local catalog import.
- No modification, deletion, staging, or commit of
  `.local-provider-catalog/`.
- No README product-positioning rewrite.
- No update to repository `docs/` behavior contracts.
- No release, tag, issue, deployment, GitHub setting, or PR #224 action.
- No strategic `ARCHITECTURE.md`, strategic `AGENTS.md`, handover, workorder
  backlog, or timing-ledger commit.
- No second PR.
- No merge or auto-merge.

## Acceptance criteria

1. The exact OAP governance/protocol/scaffold is versioned on one non-draft PR
   from the verified `main` baseline.
2. `oap/active` selects exactly one `000-a` order and no heuristic is needed.
3. The coding agent can follow the protocol without path, merge-authority,
   active-pointer, or report-publication ambiguity.
4. Repository tests enforce the high-value OAP invariants without freezing
   `000-a` as the permanent active identifier.
5. `.codex/` and `.local-provider-catalog/` are ignored while the existing
   provider-catalog data remains untouched and unstaged.
6. Only allowed paths change; no application/dependency/schema/CI behavior
   changes.
7. Local verification is honest and required GitHub checks are inspected.
8. The final immutable report commit changes only the `000-a` report, has the
   recorded implementation head as first parent, and is the remote PR head
   before the response FIFO signal.
9. The coding agent never merges; strategic review remains pending after the
   report signal.

## Required local verification

Run at minimum:

```bash
python -m pytest tests/unit/test_oap_governance.py -q
python -m pytest tests/unit -q
python -m ruff check app tests
python -m alembic heads
git diff --check
```

Also run:

- exact active/order uniqueness inspection;
- Markdown trailing-whitespace and control-character scan for changed files;
- `git status --short` before staging;
- staged-path inspection before each commit;
- `git diff --cached --check`;
- secret/path scan over changed files;
- confirmation that `.local-provider-catalog/` exists but is ignored and
  unstaged.

If the full unit suite exposes a pre-existing failure unrelated to allowed
paths, report it exactly and do not widen scope.

Database, Redis, browser, Docker, and real-provider tests are not required
because this objective changes governance/docs/tests only. Do not claim they
passed unless actually run.

## Git and commit requirements

Stage only explicit allowed paths with `git add -- <paths>`. Never use
`git add .`, `git add -A`, or `git add --all`.

Implementation/governance commits must include:

- finalized prepared governance/scaffold files;
- `.gitignore`;
- OAP governance tests;
- unchanged strategic-authored active order and pointer.

Before report publication:

1. push implementation/governance commits;
2. record the literal 40-hex remote implementation head SHA;
3. create exactly one non-draft PR with the required title/base/head;
4. verify PR URL, number, base, head, and remote implementation head;
5. inspect GitHub check state and repair in-scope failures when safe;
6. never merge.

Then atomically publish the report at:

```text
oap/reports/000-a-bootstrap-oap-governance-transcript.md
```

The report must contain:

```text
Implementation head SHA: <literal 40-hex implementation commit>
Report publication commit: SELF
```

Create one final commit changing only that new report file. Push it and verify:

- it is the current remote PR head;
- its first parent is the recorded implementation head;
- its changed path is only the new report;
- the committed report bytes match the published report.

No repository mutation or push is permitted after that report commit for this
round.

## Required report

Use the full report contract from
`OAP-COMMUNICATION-coding-agent.md` and include:

- identifier and exact order filename;
- status;
- branch, PR number/URL/state, base/head;
- starting baseline;
- literal implementation head;
- `Report publication commit: SELF`;
- implementation commits;
- exact files changed;
- acceptance-criteria evidence;
- exact local commands/results;
- GitHub checks observed for implementation head;
- any checks pending on the report-only head;
- documentation impact;
- local setup/dependencies;
- final local status and ignored generated-state confirmation;
- no schema/dependency/application behavior change;
- no production/provider access;
- no unrelated path;
- no extra PR;
- no merge;
- active order/pointer unchanged;
- report-only commit path/parent verification;
- blockers/limitations and factual strategic follow-up.

## Final safety confirmations

Confirm explicitly:

- no production/staging data or credential access;
- no real provider/API/email call;
- no application, migration, dependency, or CI workflow change;
- no `.local-provider-catalog/` modification, staging, or commit;
- no strategic-side file committed;
- no secret or local Codex state committed;
- one objective branch and one PR only;
- coding agent did not merge or enable auto-merge;
- report was published and pushed before exact response FIFO `OK`.

After the report commit is verified remotely, send exactly two ASCII bytes
`OK` with no newline to:

```text
/home/ubuntu/codex-supervision/slaif-api-gateway/response.fifo
```

Then return to blocking listener mode on `control.fifo`.

