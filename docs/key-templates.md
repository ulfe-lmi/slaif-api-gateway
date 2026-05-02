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

Template previews should show safe summaries only:

- allowed endpoint/model/provider/tool lists;
- quota limits;
- rate-limit limits;
- validity defaults;
- bounded-overrun assumptions;
- pricing catalog references;
- template revision IDs.
