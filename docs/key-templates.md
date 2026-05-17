# Key Templates

Status: planned for RC2-beta; not implemented on current `main`.

Key templates are the planned way to make complex key policies repeatable and
reviewable, especially for Responses API policies that include model, provider,
tool, quota, and bounded-overrun controls.

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

Planned workflow:

1. Create a key template for a workshop, course, or cohort.
2. Configure endpoint/model/provider/tool policy.
3. Review the quota and bounded-overrun preview.
4. Create a test key from the template.
5. Run normal OpenAI-compatible client examples against the test key.
6. Bulk-create workshop keys from the approved template revision.

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

The recommendation workflow should capture:

- source key and source owner;
- source time window;
- multiplier, such as 1.5x, 2x, 3x, or a custom value;
- observed usage summary;
- recommended quotas and per-request caps;
- Responses endpoint/model/provider/tool policy;
- bounded-overrun assumptions;
- admin edits and final confirmation.

Generated templates remain normal templates. They should create an immutable
template revision and record the source key, source owner, source time window,
multiplier, and observed summary used to generate the proposal. Bulk key
creation can then issue classroom, workshop, seminar, or worksite participant
keys from that generated template revision.

Recommendations must not mutate existing keys automatically. Admins must review
the assumptions, edit values if needed, and explicitly confirm template creation
or bulk key creation.

## Snapshot And Revision Semantics

Templates should be versioned.

Rules:

- each edit creates a new template revision or immutable snapshot;
- keys created from a template record `template_id` and `template_revision_id`
  or equivalent metadata;
- historical keys remain explainable even after a template is edited;
- editing a template does not silently change existing keys;
- disabling a template prevents future key creation from that template but does
  not alter existing keys.

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
