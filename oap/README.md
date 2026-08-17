# Versioned OAP transcript

This directory is the repository-visible transcript for Orchestrated Agentic
Programming (OAP) in `ulfe-lmi/slaif-api-gateway`. Full coding-agent behavior
is defined by
[`OAP-COMMUNICATION-coding-agent.md`](../OAP-COMMUNICATION-coding-agent.md).
The strategic-side protocol is stored outside the repository at:

```text
/home/ubuntu/codex-supervision/slaif-api-gateway/OAP-COMMUNICATION-strategic.md
```

## Activation lifecycle

Before the first activation, the scaffold is intentionally inactive until the
strategic model publishes the first work order.

- Before activation, `orders/` and `reports/` contain only non-executable README
  placeholders.
- Before activation, `active` is intentionally absent; do not create an empty,
  placeholder, or syntactically invalid selector.
- The first activation atomically publishes exactly one `000-a-*.md` order,
  atomically creates `active` containing exactly `000-a`, and only then sends
  the exact two-byte `OK` signal to `control.fifo`.
- Merely creating this directory or finding the external FIFOs does not
  authorize the coding agent to run.
- After activation, `active` is the authoritative work selector and changes
  only through atomic publication by the strategic model before a control
  signal.

## Directory contract

- `active` is authored by the strategic model and is the sole selector of the
  executable order. The coding agent never infers work from filenames, mtimes,
  numbering, or directory order.
- `orders/` contains immutable, strategic-model-authored work orders.
- `reports/` contains immutable, coding-agent-authored execution reports.
- `NNN-a` creates one branch and one PR for numeric objective `NNN`;
  `NNN-b` through `NNN-z` amend that same branch and PR.
- The activated order, `active`, and corresponding report are committed and
  pushed on the objective PR. Committing strategic artifacts does not transfer
  their authorship or permit the coding agent to edit them.
- Canonical GitHub is authoritative for software/project state; this directory
  is authoritative only for OAP orchestration state.

FIFO `OK` messages provide synchronization only. The two FIFO objects live
outside the repository at:

```text
/home/ubuntu/codex-supervision/slaif-api-gateway/control.fifo
/home/ubuntu/codex-supervision/slaif-api-gateway/response.fifo
```

The strategic model writes `control.fifo`; the coding agent writes
`response.fifo`. Neither message selects work or records project state. The
wire payload is exactly the ASCII bytes `OK`, with no newline or metadata.

## Report publication

Each report records:

```text
Implementation head SHA: <literal 40-hex commit before the report commit>
Report publication commit: SELF
```

`SELF` avoids impossible Git commit self-reference. Reviewers resolve it to
the GitHub commit containing the exact report. When that round sends FIFO
`OK`, the commit must be the current PR head, must change only the new report
file, and must have the recorded implementation head as its first parent. A
later activated continuation adds commits to the same PR, so the earlier
`SELF` will no longer be the current head; it remains immutable and reachable
in PR/Git history.

## Gateway-specific safety

OAP artifacts must never contain secrets, credentials, gateway or provider
keys, capability tokens, session cookies, database URLs, private keys,
prompts/completions, media payloads, personal data, or private artifact URLs.
They must not include generated `.local-provider-catalog/` content unless an
explicit human-approved work order names a reviewed artifact for publication.
