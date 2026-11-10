# OAP Work Order — 217-a

PR mode: CREATE_NEW_PR

## Objective, authorization and verified activation state

Implement G15 of docs/MISSING_GUI_FUNCTIONALITY.md: official provider-catalog
proposals and the complete sealed catalog-refresh workflow in the existing
admin GUI. The human approved all missing GUI elements, preserving working
behavior, SLAIF design and meaningful field guidance. This is the next bounded
objective of the approved 207–219 plan, not a release/deployment authorization.

Verified 2026-11-10T01:53:16Z: preceding objective216 (rounds216-a/b,
unique PR372) is TERMINAL/ACCEPTED. PR372 merged2026-11-10T01:38:11Z,
exact final SELF12e6774e250ec759ffd334b847063c4b604ca9d8 after10SUCCESS
PR checks/3SUCCESS workflows, material review5835308100 and all10 advisory
threads individually assessed/resolved. Actual remote main is
3b7a5e39189c5406641f4143d0b8ed1c3992e968, parents
f2df0e82df8766740d9ac169ea56ffd7a3cb1f1e and that final SELF. Main tree
04a70a91485d39a51c5856fd13f191be0c200fe4 EXACTLY equals the reviewed tree.
All9 main checks and all3 workflows SUCCESS: CI42737183043,
CodeQL42737183529 and CodeQuality42737183278; last main PG job completed
01:52:40Z. Root main watcher18027 CLOSEDexit0, terminal verification and
honest timing recorded in strategic ledger. B order8651bytes SHA256
0e54b9012074c9ac2feef7530b54250ab8c74ac71674863dea7ab55933dfd95b and
report9152bytes SHA256
48b1010301d26ce399b9177d4887a414e091c36fe5e9dc848adae89b393c54db
match local+remote immutable bytes; prior active exact216-b.

Fresh preflight: only open PR319 (unrelated Dependabot); no217 PR or branch.
Ruleset23580289 protect-main ACTIVE (deletion/non-fast-forward),19441572 and
15649613 disabled; no bypass/release authority. Only published release is
v0.1.0-rc.1 (2026-05-01). Shared tracked tree clean; preserve the three
protected untracked files and ignored local state. Coding CLI3308462 remains
in right%9; sole canonical control waiter3387236 (coder terminal96733),
verified cwd strategic root, TMUX_PANE=%9, healthy wait_for_partner. Both
canonical FIFOs verified actual types/inodes below. G14 is delivered, G15/G17
and final219 installed whole-GUI gate remain open; full goal stays ACTIVE.

Numeric objective217 has ONE new PR, base main at the verified SHA above,
branch oap/217-gui-catalog-refresh. Suggested title: Add controlled catalog
proposal and refresh workflows to the admin console. No218 activation while
217 is unresolved. Never amend a pushed commit, force-push, merge, enable
auto-merge or create a second PR. Root owns final-head gates and merge.

## Current source findings and bounded design decision

Current CLI catalog-refresh.py composes collect/review through
_finalize_review_pipeline. Collection resolves a baseline BEFORE retrieval;
collect_bundle owns ONE AcquisitionContext across all retrieval/research
phases. Reuse that composition through the smallest typed application seam;
keep CLI entrypoints/output/exit semantics, wrapper and existing commands
working. HTTP/worker code must not import/invoke CLI commands, spawn the CLI,
watchdog or shell, or implement a second validation/seal/publication engine.

Existing Core already owns transport, parsers, source evidence, baselines,
plan/readiness, renderer, anchored files, seals, atomic apply, idempotency and
committed status. Preserve these. Custody/background status is the necessary
GUI bridge, not permission for generic workflow infrastructure. Existing
Celery is sufficient; its result backend is OPTIONAL. AsyncResult PENDING
is not proof a worker is running. Web-router import must not eagerly import
module-level celery_app/settings, connect to brokers or initialize workers.

Provider-catalog proposal generation is a DISTINCT proposal-only service,
not the sealed refresh engine or existing OpenAI-assisted proposal pages.
Its injected http_client seam exists; its legacy default follows redirects.
Do not expose that unbounded default as the new GUI network boundary. Use a
small bounded integration reusing the existing vetted transport, verified
HTTPS and fixed official destinations; refusing redirects is acceptable for
this NEW GUI surface, never following an unvalidated destination. No new
transport, resolver/pinning engine, permissive URL proxy or research runner.
Keep existing proposal/CLI behavior compatible. Fixed official URL families
needed by this existing service may be narrowly declared at its integration
boundary; no browser/model-selected host, arbitrary path, port or URL.

## Allowed paths (bounded additions and direct composition)

- NEW app/slaif_gateway/api/admin_catalog_refresh.py;
- NEW app/slaif_gateway/services/admin_catalog_refresh.py for this specific
  GUI's custody/status/request orchestration (no general job platform);
- NEW app/slaif_gateway/services/catalog_refresh/application.py for the
  directly extracted collect/review/publication application composition;
- NEW app/slaif_gateway/workers/tasks_catalog_refresh.py and minimal
  workers/celery_app.py registration;
- app/slaif_gateway/cli/catalog_refresh.py: only backwards-compatible
  delegation to the shared composition. cli/catalog_refresh_admin.py and
  cli/provider_catalog.py only if demonstrably necessary for that extraction;
- services/catalog_refresh/sealing.py: minimal held-handle verification seam
  if required; execution_identity.py: fixed measured-file dependency update;
- services/provider_catalog_proposal.py: minimal injectable/composition seam
  if needed by bounded GUI proposal generation, no pricing/readiness redesign;
- config.py, main.py, api/admin.py ONLY settings, router composition and
  directly necessary legacy forwarding; api/admin_review_intent.py for one
  closed purpose-bound catalog intent; api/admin_record_choices.py and
  services/admin_record_choices.py ONLY a directly needed closed known-record
  kind/projection, not broad query expansion;
- NEW web/templates/catalog_refresh/*.html, existing
  web/templates/operations/index.html and shared navigation ONLY the new
  coherent workflow link; a scoped web/static/js/catalog-refresh.js only if
  needed for progressive enhancement. Existing shell/CSS/components remain;
- deploy/nginx/slaif-api-gateway.conf and its existing TLS sibling if present:
  narrowly scoped multipart allowance for this workflow's canonical input
  bounds; no global proxy limit/routing/security relaxation;
- .env.example, existing Compose API/worker service definitions ONLY explicit
  settings/shared operator-owned mounts if needed, no new service/dependency;
- tests/unit/test_admin_catalog_refresh_217.py (new),
  tests/integration/test_admin_catalog_refresh_217_postgres.py (new),
  tests/browser/test_admin_catalog_refresh_217.py (new), narrow sanitized
  fixtures under tests/fixtures/catalog_refresh/217/ if existing ones cannot
  be reused; existing test_cli_catalog_refresh.py, test_catalog_refresh_admin.py,
  test_catalog_refresh_execution_identity.py and directly affected catalog
  seal/apply/collection/provider-proposal tests only as required by extraction;
  tests/unit/test_admin_usability_inventory.py and test_admin_slaif_design.py;
  tests/unit/test_config.py and worker-configuration tests only new settings/
  registration/import boundary; no unrelated test rewrites or weakened guards;
- docs/MISSING_GUI_FUNCTIONALITY.md, docs/admin-usability.md,
  docs/verification/gui-cli-parity.md, docs/catalog-refresh.md,
  docs/provider-catalog-proposals.md, docs/configuration.md,
  docs/deployment.md, docs/security-model.md, docs/cli-reference.md,
  docs/compatibility-matrix.md, docs/rc2-feature-scope.md and README.md:
  only this workflow, actual shared-seam/identity/upgrade consequences and
  current status; preserve README logo and dated evidence limitations;
- root-authored oap/active + this order byte-unchanged; one matching report.

If a concrete necessary path is absent, report its exact direct need to root
within THIS order before editing it; do not add a repair round for clerical
scope/fixture/docs corrections. No schema/model/migration/dependency or
provider/client adapter, runtime request-policy/accounting changes authorized.

## Required operator workflows and acceptance

1. Operations has a coherent Catalog workspace with setup/status, Proposals,
   Collect, Review supplied bundle, and existing-run review/status navigation.
   Retain existing import and OpenAI-assisted pages and their working actions.
   No shell console or CLI-shaped wall of switches; guided common path with
   advanced finite options disclosed as needed.
2. Proposals call generate_provider_catalog_proposal for supported openai,
   openrouter/all, endpoint and package presets using current service rules.
   Explain paired-ready/ordinary-chat safety, model filters, currency, finite
   model/detail/web-call caps, zero/deprecated/ambiguous warnings and source
   choices. Optional assisted/API choices require existing deployment secrets
   and explicit acknowledgement; show unavailable honestly when unconfigured.
   No secret value, new browser credential/endpoint/executable field or new
   authority. Generate safe TSV/JSON/text artifacts and bridge generated
   route/pricing TSV to existing import preview WITHOUT automatic import.
3. Collect supports explicit bootstrap versus refresh, current standard-v1
   profile, nonempty supported provider subset, all-eligible or explicit
   known-model choices (latest100 + older search, selection hydration), live
   read-only DB baseline or supported exported-baseline upload. Explain
   bootstrap emptiness, refreshing existing metadata and source limitations.
   Resolve/capture baseline before collection and preserve collector-owned
   request/byte/deadline/cache budgets across all phases. Current target is
   cooperative120s plus per-operation limits; do not claim an in-library hard
   deadline. Existing operator watchdog300s/+5 for read-only collection is not
   permission to run/kill a CLI or mutating apply.
4. Standalone Review supplied bundle is real capability, not just displaying
   collected runs. Bounded multipart uploads retain strict bundle8MiB and
   baseline32MiB support, exact first-install/exported/live capture semantics,
   malformed/duplicate/nonfinite/unknown field rejection, deterministic
   validation and offline acquisition labels. Stream/limit before unbounded
   allocation; filenames are untrusted data, never host paths. Proxy allowance
   must carry the valid combined upload plus finite form overhead (e.g.48m
   only under the new catalog route), not silently shrink canonical bounds.
5. Collect/review yields a sealed server-owned run and structured safe admin
   rendering of the SAME authenticated canonical plan: target/mode, readiness,
   source provenance/freshness, changed/unchanged rows, warnings/blockers,
   prices/units, exact proposal counts and review identity. No arbitrary
   artifact HTML served inline at authenticated admin origin. Existing sealed
   REVIEW.html may be a verified attachment for local review. Do not silently
   rewrite/re-sign a run to make a new renderer verify.
6. Verify is explicit read-only, authenticates artifacts and shows truthful
   checks and ORIGINAL generator versus CURRENT verifier identity. Export
   baseline is a real consistent allowlisted DB export/download, read-only,
   never an empty bootstrap after failed DB contact. Authenticated bounded
   artifact downloads use closed file names, Content-Disposition attachment,
   no-store/nosniff, safe content types and held verified bytes; no seal key,
   DB URL, secrets or unrelated files/host paths.
7. Apply is explicit reviewed confirmation, bounded nonblank audit reason,
   server-derived authenticated admin actor/UUID and fresh EXISTING superadmin
   gate. Inspection/collect/review do not grant mutation privilege. Use the
   existing session-bound HMAC review purpose, <=15min expiry, exact run/
   canonical plan/target/warning-ack binding and current integrity/source
   rechecks. No durable token store or claim one-use merely from HMAC signing.
   Reuse apply_reviewed_run, supplying SAME HELD authenticated run context;
   preserve verified seal, renderer/version gates, supported plan, lock order,
   wrong-target/bootstrap/stale baseline/freshness/refused warnings, existing
   metadata/explicit-denial preservation, ONE atomic catalog transaction and
   durable application record. Never direct SQL/ORM catalog mutation in GUI.
8. Status uses apply_status on that same held lifecycle-bound context. Exact
   committed repeat returns the original result, no duplicate routes/pricing/
   audit; blocked/stale/tampered/canceled/unknown never looks applied. A broker
   ack loss, worker interruption or DB commit-ack failure is unconfirmed until
   authoritative committed status resolves it. Never promise rollback, retry
   mutation automatically, kill apply to implement cancellation, or translate
   any generic303/200 to success without persisted-outcome verification.

## Operator custody, bounded background work, identity and privacy

Default off with explicit operator enable/root/seal configuration. Root and
seal key live OUTSIDE repo/database under documented operator-owned restrictive
permissions and shared API/worker mounts. GUI opens an EXISTING properly owned
root and exact existing0600 seal key; missing/unsafe config gives useful setup
help and no network/job/mutation. Never silently create/replace a seal key,
repair permissions, choose API/worker home or accept host paths/DB URLs/keys
from browser or task payload. Root/service-user boundary is existing same-uid
trusted-operator model, not protection against root or seal-key custodian.

Use existing anchored no-follow/held-handle reads and safe private staging,
NEW-ONLY publication and identity-checked cleanup. Validate canonical browser
run UUID -> own server custody; no path concatenation as authentication, no
symlink/special-file/traversal shortcuts. Existing public apply/status already
accept AnchoredDir. Reassert name/lifecycle bindings around boundary crossings;
load_verified_capture alone does not create a directory lifecycle guarantee.
No duplicated private raw-fd crypto/filesystem implementation.

Use one closed Celery task family (no helpers/agents), IDs-only broker payloads
and a small run-specific local metadata/status record within operator custody
if necessary, not new DB tables or generic job/results infrastructure. Settings
must explicitly bound active jobs (default1), retained count(default20), total
bytes(default1GiB) and read-only work duration(default300s), with validated
finite ranges and documented tuning. Enforce under concurrent requests/workers,
including uploads/staging/failures; full capacity refuses explicitly, never
partial output labeled complete. Preserve Core per-file/run64/128MiB limits.
One status distinguishes queued/running/ready/warnings/blocked/failed/canceled/
unavailable/unconfirmed; broker admission is not completion or live-worker
proof. Canceled queued work cannot later execute on delayed delivery. Late
worker/duplicate delivery must not overwrite published sealed artifacts or
claim another task's outcome. Expose safe progress and server-refresh/no-JS
fallback. Cancellation is READ-ONLY work only; use phase/checkpoint cancellation
and existing Celery facilities rather than inventing a kill/watchdog process.
An in-flight library operation may finish before cancellation is observed:
show cancel-requested/unconfirmed until an actual terminal fact is known, and
gate publication so a canceled task cannot publish ready output later. If a
minimal existing AcquisitionContext cancellation checkpoint is demonstrably
needed, report its exact sources.py path/seam to root in THIS order before edit;
never reset budgets or rewrite transport to achieve cancellation. Document
real cancellation limits, stale/unknown worker state and no hard-bound claims
beyond evidence.

Research remains opt-in/NOT_RUN by default. Where enabled, resolve only fixed
operator-configured existing isolated runner executable, HTTPS endpoint/model
and credential-ENV-NAME; the browser has a finite enable choice and explanation,
not path/command/endpoint/key controls. Preserve outer isolation, semantic-only
research scope, source grounding, budgets and measured identity. Reuse accepted
research tests; no real model call in this qualification. Existing OpenAI
assisted proposal calls use their existing separate explicit policy/secret.

The measured code identity is a FIXED directly relevant owned file list:
include extracted application generation/publication semantics and the concrete
renderer dependency web/static/js/table-sort.js, staying<=32files. Do not hash
whole app/environment/Git or pretend browser/UI/worker attestation. State
upgrade consequences honestly: changed measured identity/renderer may refuse
old artifacts; verify/review/regenerate using supported original baseline and
same protected seal key, never bypass/re-sign mismatches. No key-policy/module
migration or DB schema change is expected; existing key material/quota/usage/
replay/provider restrictions remain byte-preserved by this work.

No prompts/reasoning/session metadata/provider secrets/browser credentials in
artifacts, task args, ordinary logs, error responses or downloads. Treat source
text/schema/notes/filenames/errors as untrusted. Escape projections, withhold
known incoming opaque authentication aliases/credential-shaped values using
existing pure guards; canaries must prove full-secret absence across full
responses/downloads/task payloads/captured logs, not only chosen snippets.
Signed intent is reviewed data, not identity or authority. Downloads/status
lookups authenticate without rotating CSRF of an already displayed form;
prove download/poll -> same-page apply/edit remains functional.

## Ergonomics and meaningful guidance

Retain SLAIF cream/teal/lime shared shell/local fonts. Use existing searchable
record choices/latest100+olderlookup for DB references, finite native selects
for finite enums, clear labels and associated aria-describedby help for EVERY
new visible field: purpose, mode, units, limits/defaults, blank/inherit meanings,
consequences and concise examples where useful. Explain current target/live vs
exported/offline and proposal vs applied. Do not show readonly IDs as editable
paths. Readable sortable tables have first ordinal, shared hyperlink sort
headers/neutral arrows/raw typed values, separate request/token columns where
applicable, comma numbers/exactzero and M-token readouts while edits/downloads
retain exact raw units. Bounded views must never imply complete inventory.

Desktop/narrow/keyboard/no-JS flows and error recovery are acceptance gates.
Keep screenshots synthetic under /tmp/slaif217 for root inspection. Preserve
existing working forms, styles, nav, ordinary imports/proposals and CLI.

## Verification economy and required evidence

Start with source inspection and a concise implementation sequence in THIS
order. Routine fixtures/docs/qualification fixes stay in current217-a/PR.
Reuse accepted transport/parser/grounding/baseline/seal/filesystem/atomic apply
proofs; do not invent infrastructure or rerun entire unchanged matrices.

- Focused new service/ASGI tests cover setup/defaultoff, auth/fresh role/CSRF,
  actor/reason/session/expiry/tamper/warning gates, uploads and all six verbs
  plus separate proposals, safe scope/run ID, storage/count/concurrent
  admission, broker/write failures, worker-unknown/cancel/late delivery and
  complete secret canaries. Explicitly establish intended validator reached.
- Native owned-PG workflow uses real HTTP/service/application operations and
  SYNTHETIC official-source bytes at existing injection seams: collect/review/
  verify/export/apply/status, exact catalog rows/audit/application receipt,
  idempotent repeat, wrong target/nonempty bootstrap/stale baseline/warnings,
  blocked missing/tampered artifacts, held-handle boundary refusal, unchanged
  key material/policy/quota/usage/replay, failure rollback and honest unknown
  commit outcome. No mocked ORM result labeled native. Reuse existing owned
  PG16 fixture, explicit label/fullID verified before use/cleanup; no ambient
  DATABASE_URL or old containers. Missing/skipped tests are NOT passes.
- Actual Chromium over real app/ownedPG + synthetic sources exercises those
  workflows (including supplied-bundle review and proposal-to-import-preview),
  keyboard/narrow/no-JS, status/download then same-page form mutation,
  persisted outcomes/refusal, safe readable review. Freeze working visuals
  once root accepts; no repeated nits/screenshots without concrete defect.
- Existing focused affected consumers: test_cli_catalog_refresh.py,
  test_catalog_refresh_admin.py, test_catalog_refresh_execution_identity.py;
  the directly affected seal/collection/apply/provider-proposal cases if
  extraction touched their boundary. Run inventory/design TWO existing modules
  once after final new tables, exact counts from actual templates, retaining
  ALL structural/ordinal/leaf-column/sort/empty-row/colspan/scroll guards.
  No >=, ignores, skip/xfail or replacement inventory framework.
- Scoped Ruff/compile, OAP governance, diff/docs, packaging assets identity if
  directly changed. No full local unit/integration/browser/CLI/Codex/provider
  matrix; final219 owns ONE installed whole-GUI gate. A receipt filename is
  disposable: cite/rename, never rerun unchanged tests solely for its name.

Commands use current fresh /tmp/slaif216-qualification-venv (Python3.12.15,
pytest9.2.0, Playwright1.65.0/installed matchingChromium, Ruff0.16.7).
Clear ambient DATABASE_URL/TEST_DATABASE_URL for tests; own DB fixture only.
Retain actual exits/JUnit counts/timestamps/source snapshots; report mock vs
native vs browser vs installed/live honestly. No real public-source network,
provider inference, real Codex/research worker, SMTP, production apply or deploy.
No global feature-level request-capture content or provider credential change.

## Documentation, GitHub and immutable handoff

Keep the single living coverage map and existing shared proof file. Update
only G15/current behavior, clear setup/mounts/serviceuid/permissions/sealkey
creation OFFLINE, exact restart/recreate scope for API+workers/proxy, workflow,
finite knobs, retention and safe owned cleanup, cancellation/unknown recovery,
old-artifact identity refusal, rollback limits and legacy CLI/API compatibility.
State no schema migration/key-policy migration if true. Update directly
required security/config/CLI/current-feature contracts; do not claim all GUI
parity complete while G17 and final219 remain. Include the repository-required
exact documentation-impact statement in report.

Coder owns Git: reconcile actual remote baseline, create branch/unique PR,
commit complete root order+active unchanged with implementation; never reset/
clean/stash unrelated state. Preserve protected untracked CODEX-SESSIONS.md,
codex.sh, uv.lock: HASH ONLY, never read/stage/modify (expected hashes in
strategic STATE). Preserve ignored.env/.codex/catalogs/auxiliary worktrees.
Use SAME existing coding CLI3308462 in right%9 unchanged early-beta/qwen3.8-27b
A100(Q8)/medium. No helper agents, subagents, nested Codex, profile/model/effort
or config changes. Native /compact or /new only context maintenance; reread
active order after compaction. No infrastructure/dependency installation is
needed; routine disposable test setup within qualified tools is authorized.

Build the complete report away from final path; atomically publish/fsync ONE
new immutable oap/reports/217-a-gui-catalog-refresh.md. Commit it in final
report-only SELF whose SOLE parent is literal implementation head. Include:
Implementation head SHA: <literal 40-hex>
Report publication commit: SELF
Report exact PR/branch/base, changed paths, actual commands/exits/counts,
negative/security/privacy/accounting proofs, limitations/reused snapshots and
setup/upgrade instructions. Verify remote PR head/topology/report bytes/order/
active before sending exactly two bytes OK ONCE to canonical response.fifo.
Pending CI never counts as pass. Re-arm ONE canonical control waiter after
handoff, no duplicate FIFO reader. Root owns exact final CI/material/review/
guarded merge and actual-main checks; full goal stays ACTIVE through219.

## Strategic activation and fixed synchronization

Only when root replaces activation state and publishes this complete order
under shared REPO/oap/orders/217-a-gui-catalog-refresh.md and exact active217-a
may one controlOK be sent. No execution from this unactivated draft/proposal.
Canonical FIFO paths /home/janezp/codex-supervision/slaif-api-gateway/
control.fifo inode4501469 and response.fifo inode4501470, verified true FIFOs.
Sole existing coder reader3387236 (retained terminal96733) in right%9; blocked
builtin open is healthy, no fd/child until peer. Never poll root terminals or
resignal completed216-a/b. Prior root response88095 and oldCI25552/response20174
and main watcher18027 are CLOSED; NEVER REPOLL. Root final216B CI71949 is
also CLOSEDexit0. Preceding216 merge and actual-main9checks/3workflows/timing
are now independently verified as above. This shared217 activation, followed
by exactly one controlOK, is the sole authority for execution of217-a.
