# Qwen Codex compatibility and clean profile verification

> **Status:** Bounded live and synthetic evidence; 2026-10-18
> **Client:** Official Codex CLI 0.162.1, Linux x86-64

This record covers the Local Coding pair and the
[clean examples](../../examples/codex/qwen38-27b/README.md).
It does not register a newly qualified backend or certify arbitrary client
versions, plugins, images, long context, or production fitness.

## Evidence sources

- **Operator-reported real client success:** after the sparse visible reasoning
  fix at `9384b8b`, the operator reported the original text smoke passed.
  This establishes that reported invocation only.
- **Direct backend observation:** a benign streamed request produced 33 SSE
  events, including visible reasoning deltas without `output_index` and
  a reasoning done item with empty encrypted content. Replaying those actual
  events through the updated validator succeeded. Private session bodies
  and reasoning content are not checked into this repository.
- **Synthetic regression coverage:** schema property-map label handling,
  continued rejection of real provider authority, exact custom apply_patch
  declaration/call/output/stream lifecycle, bounded sparse visible reasoning,
  empty-ciphertext continuation without encrypted replay authority, and
  ordinary Responses streaming with no specialized client policy.
- **Self-executed live tests:** isolated Codex homes loaded the repository
  profile/catalog files using `--strict-config`, with only the placeholder
  URL and catalog path replaced in private copies. A gateway-issued key was
  supplied in `OPENAI_API_KEY` at runtime. Both tests used the actual HTTPS
  gateway and Qwen backend, not a mock or a direct-backend bypass.

## Self-executed results

The successful source image with local build label
`dfd5f79945813375867b3deb687344dfef6cf7c3`
used packaged profile revision 8 with digest
`1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11`.
Temporary field-shape-only rejection instrumentation was removed before the
final successful repeat. The official CLI archive SHA-256 was
`86f268d81b898f3e144c5ecff2ad2fda2c5802e042d6195b72538fe0fa125057`.

| Profile | Actual result | Elapsed |
| --- | --- | --- |
| `qwen38-minimal` | Exit 0; exact `CLEAN_PROFILE_OK`; no tools executed | 16.8 s |
| `qwen38-coding` | Exit 0; successful custom `apply_patch`, successful `exec_command` readback, exact file and final `TOOL_ROUNDTRIP_OK` | 29.4 s |

The host blocked the CLI's bubblewrap/user-namespace sandbox even after its
matching resource was installed. For the final smokes, Codex ran
in a disposable container with only its CLI binary, isolated Codex home, and
test workspace mounted, and `--sandbox danger-full-access` as a **test-only override**.
The published coding profile retains workspace-write restrictions; this run
proves the gateway tool round trip, not this host's sandbox compatibility.
Noninteractive execution used no approvals. Request and stream retry counts
were overridden to zero so a rejection stopped the test immediately. These
runtime overrides are separate from the example profile configuration.

Earlier attempts exposed empty-ciphertext reasoning continuation and sparse
function argument deltas. Both received synthetic bounded regression tests;
no encrypted replay authority is created for empty ciphertext. Local patch
failures and gateway stream failures were recorded separately. Quota exhaustion
was also observed at the configured request cap: HTTP 429, followed by an
operator quota extension. No inference bypass was used to replenish quota.

## Repository checks

The compatibility source before the diagnostics merge passed 5,004 unit cases
(one skipped). Subsequent combined-tree checks are recorded in the PR. The focused
quota HTTP/mapping regressions cover all three hard limits; temporary rate-limit
checks remain separate. PostgreSQL integration, mocked E2E, native browser,
and static/deployment check results are recorded in the accompanying PR.
Those mocked tests are separate from the real gateway/Qwen runs above.

## Reproduce

Follow the [operator runbook](../runbooks/codex-qwen38.md), install all official
client resources for the pinned CLI, use a disposable workspace, and run both
named profiles. Require successful tool result statuses, exact file contents,
and a successful final turn. Keep the key outside configuration files and
record request correlation and final ledger outcome privately.

The namespace inventory in earlier 197-tool diagnostics is different evidence
from these clean profiles: apps and plugins are disabled here. No conclusion
about the complete 197-tool interactive workflow follows from these tests.

## Registered two-file configuration follow-up

The earlier minimal/coding names above describe historical tests. They are now
replaced by one `qwen38` profile: `qwen38.config.toml` plus `qwen38-models.json`.
On 2026-10-18, the exact registry-rendered files passed a real HTTPS gateway
test using pinned Codex CLI 0.162.1 in 36.0 seconds: successful `apply_patch`,
`exec_command` readback, exact file content and final marker, exit 0. The
relative catalog path resolved successfully from isolated Codex home. The
test used the previously documented disposable-container sandbox override;
it does not establish host sandbox compatibility or full live qualification.

After deployment, the live route was assigned the registered declaration through
the audited route service. Runtime readiness passed with full live qualification
still false. The files rendered from the live deployment settings passed the
same real gateway tool round trip in 33.4 seconds, exit 0. Authenticated download
responses, attachment filenames, unauthenticated redirects and not-ready 404s
are covered by focused HTTP tests; no production admin session was impersonated.
