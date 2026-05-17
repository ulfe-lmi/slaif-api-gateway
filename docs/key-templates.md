# Key Templates

Status: template persistence and create-from-calibration are implemented for
RC2-beta foundation work. Participant-key creation from templates is future
work.

Key templates make complex key policies repeatable and reviewable. Current
support stores durable template records and immutable revisions that can be
created from a reviewed trusted-calibration proposal. The template tables store
safe policy metadata only; they do not create participant keys yet.

## Why Templates Exist

Current single-key and bulk-key workflows can set policy fields directly. That
is workable for Chat Completions, but Responses API policies need more
structure:

- endpoint enablement;
- allowed models and providers;
- allowed tool types;
- tool-call caps;
- maximum output/input caps;
- maximum single-request cost;
- Redis operational rate-limit defaults;
- clear admin-visible overrun assumptions.

Templates let workshop organizers define that policy once, test it, then issue
many keys from the same reviewed snapshot.

## Workshop Organizer Workflow

Current and planned workflow:

1. Run a trusted calibration key through the intended workflow.
2. Preview the calibration summary and strict participant-policy proposal.
3. Review the proposal, warnings, assumptions, and local accounting limits.
4. Create a durable key template and immutable revision from the reviewed
   proposal with confirmation and an audit reason.
5. Future work: create individual test/participant keys from a template
   revision.
6. Future work: bulk-create workshop keys from an approved template revision.

## Deriving Templates From Calibration-Key Usage

Admins should also be able to derive a template from observed trusted
calibration-key usage. Trusted calibration keys are real gateway keys for
trusted organizers/admins only; they are short-lived, request-limited, use
normal gateway auth/routing/accounting/profiling, and may use broad Chat
Completions discovery policy to observe routed hosted-capability needs. They can
be created from the CLI or admin key creation page, both with explicit
confirmation. They are not safe participant keys, and bulk key import does not
create them.

Current Chat Completions requests persist safe `usage_profiles` rows after
successful accounting finalization. Those rows provide the first source table
for future recommendation summaries: endpoint, provider/model, sanitized
provider host/path, token counts, safe tool counts/function names, and
provider/SLAIF cost fields when available. For calibration keys, rows may also
include safe key purpose, policy mode, and observed capability type names.
Missing provider metrics remain unknown/null and the rows are not invoice-grade
billing truth.

Admins can preview a calibration summary and strict participant-policy proposal
from the CLI and from a trusted calibration key detail page. The preview accepts
a source key, optional time window, and multiplier, then shows observed
endpoints/models/providers/capabilities plus proposed request, token,
per-request, and local-accounting cost limits. Preview remains non-mutating.

After review, admins can create a durable key template from that proposal in
the CLI or dashboard. Creation re-runs/re-validates the proposal server-side,
requires explicit confirmation and a non-empty audit reason, creates a
`key_templates` row plus revision 1 in `key_template_revisions`, and writes a
safe audit row. It does not create participant keys, update existing gateway
keys, alter routes/pricing, or apply policy changes.

The recommendation workflow should capture:

- source key and source owner;
- source time window;
- multiplier, such as 1.5x, 2x, 3x, or a custom value;
- observed usage summary;
- recommended quotas and per-request caps;
- Responses endpoint/model/provider/tool policy;
- bounded-overrun assumptions;
- admin edits and final confirmation.

Generated templates are normal templates. They create an immutable template
revision and record safe provenance: source key, source owner display metadata,
source time window, multiplier, observed summary snapshot, proposed strict
policy snapshot, warnings, assumptions, actor admin id, and audit linkage.
Bulk key creation from templates remains future work.

Recommendations must not mutate existing keys automatically. Admins must review
the assumptions and explicitly confirm template creation. Editing templates or
bulk key creation are separate future workflows.

## Snapshot And Revision Semantics

Templates are versioned.

Rules:

- each edit creates a new template revision or immutable snapshot;
- keys created from a template are future work and should record `template_id`
  and `template_revision_id` or equivalent metadata;
- historical keys remain explainable even after a template is edited;
- editing a template does not silently change existing keys;
- disabling a template prevents future key creation from that template but does
  not alter existing keys.

Current revision 1 stores:

- allowed endpoints, models, and providers from the reviewed proposal;
- hosted capabilities requiring review;
- an empty participant hosted-capability allowlist by default;
- request, token, per-request, and cost limits from local accounting metadata;
- optional validity and email-delivery defaults;
- a safe proposal snapshot with warnings and assumptions.

Observed hosted capabilities are not silently allowed for participant
templates. They are preserved as review-required metadata. External
MCP/connectors remain denied by default.

## Existing Keys

Existing keys must not be silently mutated when a template changes.

A future "apply template update" workflow may update existing keys only if it is:

- explicit;
- CSRF-protected in the dashboard;
- confirmed by the admin;
- accompanied by a non-empty audit reason;
- previewed before mutation;
- audited with old/new sanitized values;
- tested for no secret leakage.

## Bulk Keys From Templates

Bulk key import should eventually allow rows to reference a template revision.
The row can then focus on owner/cohort/validity fields while the template supplies
the reviewed request policy.

If a bulk row overrides a template field, the override must be explicit in the
preview and audit output. Silent overrides are not acceptable.

## Security Boundaries

Templates must not contain plaintext gateway keys, provider API keys, SMTP
passwords, session tokens, token hashes, encrypted payloads, nonces, prompt
content, completion content, or raw request/response bodies.

Template derivation must also avoid storing messages, tool schemas, tool
arguments, tool results, raw chain-of-thought, full URLs with query strings or
fragments, signed URLs, bearer tokens, password hashes, or email bodies.

Template previews should show safe summaries only:

- allowed endpoint/model/provider/tool lists;
- quota limits;
- rate-limit limits;
- validity defaults;
- bounded-overrun assumptions;
- pricing catalog references;
- template revision IDs.
