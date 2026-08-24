# 2026-08-24 documentation architecture and truth audit

> **Status:** Baseline audit for the documentation-modernization PR  
> **Code baseline:** `8f2813bf745b90221da33a7cfaf40726c5b1b480` (`origin/main`)  
> **Purpose:** Record discrepancies before prose and navigation are changed.  
> **Evidence boundary:** Repository documentation and merged code only; unmerged PRs are excluded.

## Method

The first pass reviewed every Markdown file under `docs/`, the public root
documents, `.env.example`, package metadata, API and admin route declarations,
Typer commands, settings, SQLAlchemy models, migrations, provider adapters,
accounting services, Compose files, entrypoints, tests, and release state.

The audit also ran the existing documentation-contract tests and a relative-file
link scan. Those checks passed, but they do not establish semantic consistency:
the current CI documentation job checks whitespace, one exact README logo block,
and forbidden public environment-variable names only.

Claims are classified as:

- **Current contract:** intended to describe merged behavior now.
- **Current guide:** operator, integrator, maintainer, or security procedure for
  merged behavior.
- **Foundation only:** code exists but is not wired into the defining runtime or
  operator workflow claimed by the prose.
- **Design reference:** investigation or approved direction, not current behavior.
- **Historical evidence:** immutable release, review, or dated verification text.

## Documentation inventory and disposition

### Public root documents

| Files | Classification | Disposition |
|---|---|---|
| `README.md`, `SECURITY.md`, `CHANGELOG.md` | Current public documentation | Rewrite or reconcile. README becomes the concise landing page. |
| `.env.example`, `pyproject.toml` description, `VERSION` | Public configuration/package metadata | Audit for consistency; do not make an implicit release decision. |
| `AGENTS.md`, OAP communication files, `oap/**` | Governance/transcript | Audit input only; excluded from edits by maintainer decision. |

### Canonical contracts

| Files | Classification | Disposition |
|---|---|---|
| `product-scope.md`, `rc2-feature-scope.md` | Product scope and target classification | Preserve authority; remove duplicated implementation inventory elsewhere. |
| `compatibility-matrix.md`, `openai-compatibility.md`, `responses-compatibility.md` | Endpoint and field-level API contracts | Reconcile against routes, registries, capabilities, and tests; normalize structure. |
| `provider-forwarding-contract.md` | Provider wire contract | Reconcile adapters, headers, body mutation, retry, and accounting boundaries. |
| `accounting.md`, `streaming-live-burn-margin.md` | Accounting and streaming contracts | Separate current contract from historical staged acceptance text. |
| `security-model.md` | Security and privacy contract | Retain precise boundaries; remove duplicated product/status prose. |
| `configuration.md`, `database-schema.md` | Settings and schema contracts | Add omitted settings/table and restructure for reference use. |

### Current user, operator, and maintainer guides

| Files | Classification | Disposition |
|---|---|---|
| `quickstart.md`, `deployment.md`, `deployment-production.md`, `backup-restore.md`, `upgrade-runbook.md` | Setup and lifecycle guides | Reconcile commands with real scripts/Compose; remove overlap and add clear prerequisites/verification. |
| `onboarding.md`, `demo-journey.md` | Operator journey | Correct foundation/runtime status and align the demo guide with its actual script. |
| `observability.md`, `sizing.md`, `support-policy.md`, `incident-response.md` | Operations | Replace unsupported claims; add evidence and limitation boundaries. |
| `key-templates.md`, `pricing-catalog.md`, `provider-catalog-proposals.md`, `provider-governance.md` | Provider/key governance | Reconcile current wiring versus standalone foundations and roadmap behavior. |
| `audit-export.md`, `dlp-policy.md`, `security-hardening.md`, `supply-chain.md` | Security/governance guides | Distinguish callable foundations from integrated product workflows and remove assurance overclaims. |
| `testing-parallelism.md`, `testing-hpc.md` | Verification guides | Keep executable procedures; separate historical outcomes from current commands. |
| `codex-compatibility.md`, `real-provider-qualification.md` | Qualification boundaries | Reconcile exact evidence and preserve mocked/live distinctions. |

### Runbooks

All files under `docs/runbooks/` are current operator guides and remain at
stable paths. Existing procedures are preserved; the index and each runbook
receive explicit current-status and safety framing:

`admin-access.md`, `ambiguous-email-delivery.md`, `codex-openai-pilot.md`,
`database-backup-restore.md`, `docker-nginx-troubleshooting.md`,
`external-tool-hold-reconciliation.md`, `gateway-key-leak.md`,
`hmac-secret-rotation.md`, `metrics-alert-thresholds.md`,
`one-time-secret-encryption-key.md`, `postgresql-pool-readiness.md`,
`provider-completed-reconciliation.md`, `provider-key-rotation.md`,
`rc-beta-upgrade.md`, `redis-outage.md`, and
`stale-reservation-reconciliation.md`.

### Design and investigation references

`chat-completions-custom-tools-investigation.md` and
`chat-completions-multimodal-investigation.md` remain stable-path design
references. They will receive explicit non-authoritative status and links to the
current compatibility contracts.

### Status, audit, and release documents

| Files | Classification | Disposition |
|---|---|---|
| `beta-readiness.md` | Current verification/readiness owner | Reconcile with merged evidence and make it the single current readiness summary. |
| `rc-beta.md` | Release checklist/history | Remove duplicate current-feature inventory; retain release-gate purpose. |
| `release-decision-brief.md`, `release-notes.md` | Untagged RC2 draft artifacts | Mark clearly as untagged drafts or superseded proposals; do not present them as a release. |
| `audit-findings.md`, `audit-matrix.md`, `boundary-invariant-matrix.md` | Dated audit artifacts without date/status framing | Reclassify and link to current contracts; do not use them as current certification/readiness truth. |
| `docs/releases/**`, `docs/security/reviews/2026-*.md`, `docs/verification/2026-*.md` | Historical evidence | Preserve bodies verbatim. Improve only archive indexes and current-facing links. |
| `security/reviews/remediation-matrix.md` | Historical remediation index | Keep as review history, not implementation authority. |

## Discrepancy matrix

| ID | Domain | Finding | Authoritative evidence | Required resolution |
|---|---|---|---|---|
| DOC-001 | README | README is 644 lines and acts as status matrix, API reference, admin manual, CLI manual, test guide, roadmap, and acknowledgements. A backend section appears after acknowledgements. | File structure and specialized docs | Replace with a balanced 200–250-line landing page and move detail to owning docs. |
| DOC-002 | Navigation | There is no root `docs/README.md`; current documents are not organized by audience or authority. | `docs/` tree | Add a documentation home and make every current document reachable from it. |
| DOC-003 | Status ownership | README, `rc-beta`, `beta-readiness`, RC2 scope, compatibility docs, release drafts, and audits repeat competing current-status inventories. | Product-scope authority and code | Assign one owner per truth domain and convert other files to summaries/links. |
| DOC-004 | Document structure | Accounting, compatibility, Responses, forwarding, and security files contain later top-level H1 sections appended by implementation passes. | Heading inventory | Normalize to one H1 and a coherent heading hierarchy. |
| DOC-005 | Historical/current mixing | `streaming-live-burn-margin.md` and several canonical contracts mix current rules with long staged acceptance histories. | File headings and current services | Keep current contract prominent; move or clearly isolate historical records. |
| DOC-006 | README branding | CI and unit tests require an exact five-line 400×400 logo block, preventing accessible/proportional README design. | CI docs-hygiene job and product-scope test | Preserve logo/link semantically; test href/src/alt instead of exact presentation bytes. |
| DOC-007 | Release truth | Repository version signals conflict: `VERSION`/CHANGELOG say `0.1.0rc2`, package/CLI say `0.1.0`, while only `v0.1.0-rc.1` is tagged/published. | Git tags/releases, package metadata | Document only the published release as released; label RC2 documents as untagged drafts. Do not change runtime version in this docs PR. |
| DOC-008 | Release artifacts | `release-decision-brief.md` points to PR #277 and makes a conditioned recommendation that is no longer a current release decision. | Current `main`, GitHub release state | Reclassify as superseded/draft and direct readers to current readiness evidence. |
| DOC-009 | Verification index | The verification and release indexes omit the merged 2026-08-24 production-appliance qualification. | `docs/verification/2026-08-24-production-appliance-qualification.md` | Add indexed, bounded evidence without turning it into certification. |
| DOC-010 | Schema | `database-schema.md` omits the real `oidc_identities` table. | SQLAlchemy model and migration `0017` | Add the table, relationships, constraints, and privacy notes. |
| DOC-011 | Configuration | Eight live settings are absent from `configuration.md`: `ONE_TIME_SECRET_KEY_VERSION` and seven OIDC/local-fallback settings. | `Settings` model | Add exact semantics/defaults/production boundaries. |
| DOC-012 | Environment template | Fifty-six settings are absent from `.env.example`, primarily detailed Chat caps and OIDC fields; the template does not explain whether it is exhaustive. | `Settings`, `.env.example` | Keep the template curated, add essential OIDC entries, and explicitly point to the exhaustive configuration reference. |
| DOC-013 | CLI | Twenty-seven implemented commands have no exact invocation in current docs, including provider setup, route/pricing mutation, key lifecycle, and DB diagnostics. | Typer command decorators | Add a concise CLI command index with safe examples and links; do not duplicate every option. |
| DOC-014 | Demo | `demo-journey.md` describes a guided DATABASE_URL workflow, while `scripts/demo/run-journey.sh` now execs the strict production qualification harness. | Script entrypoint | Rewrite the guide around the actual disposable harness and its evidence limits. |
| DOC-015 | Observability | `observability.md` claims opt-in OTLP export, but there is no OpenTelemetry dependency, setting, or runtime integration. The SLO catalog is a standalone service foundation. | Package dependencies and code search | State foundation-only behavior; document real Prometheus/logging surfaces separately. |
| DOC-016 | DLP | `dlp-policy.md` describes block/flag/monitor egress and audit behavior, but the DLP scanner has no runtime consumer outside tests. | `services/dlp.py` consumer search | Label it as an unwired optional foundation; do not claim egress enforcement/auditing. |
| DOC-017 | Onboarding | `onboarding.md` says the dashboard provides a guided setup path, but the state-machine service has no API/dashboard/CLI consumer. | Consumer search | Label the state machine as foundation-only and point to actual manual setup surfaces. |
| DOC-018 | Audit exports | `audit-export.md` describes finance/project/SIEM formats as product exports without distinguishing standalone helpers from wired CLI/dashboard exports. | Export services and admin routes | Document exact wired CSV surfaces and label unwired formats as foundations. |
| DOC-019 | Real-provider evidence | `real-provider-qualification.md` and Objective 140 claim PostgreSQL verification, but the merged verifier accepts no DB input, emits no streaming request ID/usage, and omits Responses streaming. | Merged verifier source | Reclassify Objective 140 as historical partial evidence and remove current qualification overclaim. |
| DOC-020 | Audit conclusions | `audit-findings.md` says no material contract drift and frames penetration testing/retention automation as release blockers without current scope context. | Product scope and this audit | Mark it dated/superseded and distinguish external assurance from current product completeness. |
| DOC-021 | Supply chain | `supply-chain.md` implies stronger CI vulnerability assurance than the workflow proves; CI has CodeQL/Dependabot but no pip-audit/Safety gate. | Workflow search | State exact implemented controls and avoid “no known high vulnerability” assurance without evidence. |
| DOC-022 | Foundations vs MVP | Organization/team/project, OIDC, RBAC, budgets, DLP, onboarding, governance, and observability extensions are mixed into current SME MVP/release prose. | Product scope and merged modules | Document them as post-MVP extensions or bounded foundations without redefining the original one-organization MVP. |
| DOC-023 | Production deployment | Production Compose qualification is merged, but top-level navigation emphasizes development Compose and does not clearly separate the two paths. | Production Compose and Objective 151 evidence | Provide distinct local-development and production-appliance guides with explicit evidence limits. |
| DOC-024 | Link quality | Relative file links currently resolve, but anchors, orphans, heading structure, and external redirects are not checked. | Audit script and CI job | Add a standard-library documentation checker and CI/Make entrypoint. |
| DOC-025 | Test quality | Existing semantic tests prove selected phrases but also lock stale prose and allow contradictory documents to remain green. | Documentation tests | Replace brittle exact-text assertions with inventories, authority checks, and bounded semantic invariants. |
| DOC-026 | Tiny statusless docs | Multiple 10–35-line files present strong product claims without audience, wiring, evidence, or status. | File inventory and consumer searches | Add status/authority metadata and expand, merge, or downgrade each claim. |
| DOC-027 | Historical archives | Old release/security reviews correctly contain now-false implementation statements, but readers can reach them without a strong current-truth route. | Archive contents/indexes | Preserve historical bodies verbatim; strengthen archive indexes and current-contract links. |
| DOC-028 | Dormant docs branch | The local `docs/current-state-truth-reconciliation` branch is based on incompatible old state and deletes large portions of current code/docs. | Branch diff against `main` | Do not reuse or stack it; implement from a fresh `main` branch only. |

## Second-pass findings

The implementation pass deliberately repeated consumer and entrypoint searches
after the first edits. It found additional drift that a link-only review would
have missed:

| ID | Domain | Finding | Resolution |
|---|---|---|---|
| DOC-029 | Security hardening | `security-hardening.md` presented isolated helpers in `services/security.py` as deployed controls and described a URL rule that differs from provider configuration/runtime. | Document real Nginx, admin-session, settings, provider-config, and adapter paths; label the helper module standalone. |
| DOC-030 | Schema structure | The schema called `background_jobs` future/recommended although it is migrated, described nonexistent automatic seed expectations, and appended newer tables after the document conclusion. | Reorder tables, list all 31 current models, distinguish migrated foundations from wired workflows, and describe explicit operator configuration. |
| DOC-031 | Qualification consistency | The compatibility matrix still repeated Objective 140's unproven finalized-ledger claim after the dedicated qualification guide was corrected. | Downgrade it to historical transport evidence and add a regression assertion across both documents. |
| DOC-032 | CLI inventory | The initial command test ignored nested Typer groups and the new reference consequently omitted key-policy, external-tool, and secret-generation commands. | Inventory nested groups and the root `version` command; test exact invocations. |
| DOC-033 | Production topology | The production guide called only ports 80/443 “exposed” without distinguishing the host-loopback API diagnostic binding and overstated preflight permission/certificate validation. | Document public versus loopback bindings and exact preflight checks. |

## Resolution status on the modernization candidate

All documentation defects above are closed on this branch as documentation
work. Closure means the prose, structure, navigation, or regression check was
corrected; it does not convert an acknowledged software/evidence limitation
into implemented functionality.

| Findings | Status | Resolution summary |
|---|---|---|
| DOC-001–006 | Closed | Concise README, documentation home, authority map, one-H1 structure, explicit historical sectioning, and semantic brand checks. |
| DOC-007–009 | Closed | Published/tagged truth separated from untagged drafts; current appliance evidence indexed. Runtime/package versions were intentionally not changed. |
| DOC-010–013 | Closed | OIDC table/settings documented, `.env.example` classified as curated, and complete root/nested Typer inventory added. Disabled OIDC settings were not promoted into the runnable template. |
| DOC-014–018 | Closed | Demo, observability, DLP, onboarding, and export prose now matches actual consumers and entrypoints. |
| DOC-019–023 | Closed | Real-provider evidence downgraded honestly; stale audits framed; foundations separated from the MVP; production and development paths separated. The underlying real-provider accounting evidence gap remains explicit. |
| DOC-024–028 | Closed | Link/anchor/heading/orphan checker, semantic inventory tests, status framing, archive navigation, and fresh-main branch discipline added. External URL availability remains a one-time review check rather than a flaky CI gate. |
| DOC-029–033 | Closed | Second-pass security, schema, qualification, nested-CLI, and production-topology drift corrected and covered where mechanically enforceable. |

## Facts already verified as consistent

- The merged `/v1` route registry and FastAPI router match bidirectionally.
- Every registered client endpoint is named in the compatibility contracts.
- All 31 model tables except `oidc_identities` are named in the schema document.
- Current relative Markdown file links resolve; no broken relative file target
  was found in README or `docs/**/*.md`.
- Historical release and security-review bodies are intentionally stale evidence
  and will not be rewritten as current truth.
- PostgreSQL remains the documented authoritative quota/accounting store; Redis
  remains operational acceleration/throttling.

## Modernization acceptance criteria

The audit is complete only when every finding above is resolved or explicitly
left as a documented software/product decision, every current document is
reachable from the documentation home, current contracts agree with merged code,
historical evidence remains intact, README is concise, and durable checks prevent
the mechanically detectable drift from recurring.
