# Objective189: bounded 0.162 Local provider declaration lowering

Strategic implementation decision 2026-10-18T11:09:34.218416+00:00, within the human-authorized expanded 0.162.1/197-tool objective. Same active189-a, same uniquePR, no newFIFO. Commit this strategic-authored file unchanged; preserve both earlier authority files.

## Demonstrated integration gap

The registered parser accepts the 197-tool shape and actual official0.162.1 request. However, the Local Coding proxy at4d3ab2fd97d249710f952dd3d2c28936138cc8fa has no additional_tools translator and preserves input. Historical already-qualified vLLM0.27.1 source caches show declaration handling through request.tools; its namespace flattening/tool-name map reads that field. These sources are evidence for the existing canonical declaration contract, not proof of the user's current backend version. A mock returning200 for arbitrary raw additional_tools input does not establish translation correctness.

## Approved bounded normalization

For ONLY codex-0.162-responses-v1 paired with local-coding-v1, lower ONE validated initial additional_tools developer prefix to the existing top-level tools namespace array. Preserve all validated namespace/tool definitions and all subsequent input items in order. The additional_tools item and its ID are deliberately omitted from the provider body after validation; the ID remains in the canonical policy representation and never acquires identity, replay or audit authority. This is the exact bounded local declaration translation requested by the human.

Only an INITIAL prefix is eligible: actual0.162.1 source constructs it before the instruction/history items. A later or repeated additional_tools item, or mixed top-level declarations, must fail closed. Do not flatten declarations across history or silently change when tools become available. A request with no prefix remains unchanged.

Run every existing key/route/tool/field/schema/description/depth/count/byte gate and normal admission/accounting first. Retain conservative estimation of original validated declaration material; do not lose declaration cost when adapting the body. Lower before final provider serialization and HMAC signing, never afterward. No new headers, routes, authority, credentials, hosted execution, model/price/quota behavior or provider transport. Generic/default/0147/0149 and other pairs retain existing behavior.

Use a small pure version-owned helper in codex_0162.py (or already approved client helper) and minimal neutral wiring at the existing core/provider-body seam. No new generic transformation framework. Existing allowed module/service paths cover this change; additionally authorize docs/provider-forwarding.md ONLY the precise new normalization/signing/estimation contract and a focused tests/unit/test_upstream_payloads.py change if that is the actual existing harness path. No other repository edits.

## Required proof and reporting

Test exact provider-bound tools, namespace names/types/counts, schema/description preservation, remaining input order and absence of the prefix ID there. Prove validation precedes discard with invalidID/unknownfield/missingkeyorroutepermission negatives that make no backend/admission side effects. Prove no-prefix behavior and wrong-position/mixed/duplicate declarations. Check signature against the final provider bytes using synthetic test secrets without logging them. Account for the original declaration material conservatively. Ordinary zero-argument/replay/stream relaxations must not be broadened blindly to dynamic namespaces; preserve existing bounds and verify the chosen stream path.

Label actualofficialCLI->mock, synthetic197->realGateway/ownedPG/mockbackend, realPGupgrade, and realdeployedbaseline separately. No claim of currentbackendversion, actual197installedplugins, fullnewerCodexqualification or productiondeployment. The fixed commit plus build/restart/exact-keymigration and rollback instructions remains the deliverable.

## Current independent E2E diagnosis

Fresh root run reached two gateway/backend HTTP200 calls, so the earlier400 is not reproduced in that run. The current assertion incorrectly expects a single UsageLedger row.total_tokens to be10 after two requests eachreport5; fix the test to two finalized rows of5 and keyaggregate10, not the accounting implementation. Owned PG cleanup confirmed removed:d3322056d540. This historical run is stillFAIL and the raw-input mock did not prove the normalization described above. Preserve that distinction.
