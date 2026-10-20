# Image estimates and native video verification — 2026-10-20

The human requested a reasonable correction for base64 images being counted as
text tokens, then explicitly requested direct video-file input as well. Existing
credentials, key policies and throttling must stay unchanged.

A fork of the saved /tmp Lena conversation reproduced
responses_codex_context_window_exceeded on exact Codex 0.163.0 targeting Qwen A100.
The original session file hash stayed unchanged. Its 474,454-byte PNG appears as
a 632,630-character data URL. The existing byte/3 estimate accounts for about
210,900 input tokens for that media alone. A manual authenticated native
/tokenize probe, without inference, returned 314 tokens for the Lena image
prompt. A generated 1,670-byte MP4 with four requested frames returned 84 tokens.
No raw history, media, credentials, argument strings or raw IDs are copied into
this report. Request capture stays off.

The correction uses explicit bounded model-route media budgets for admission,
TPM and quota/cost reservation, preserving provider usage/cost finalization.
It defers only encoded-media token material until route selection, then checks
the complete estimate before side effects. URL, byte/count, replay, route and
key gates remain independent. Waiting revalidates current budgets. Default
unconfigured image routes retain their previous estimate. Native Chat video
requires explicit route permission, budget and a forwarded operator frame cap.
It is not direct video input in Codex Responses, whose deployed backend has no
video input type. No video-generation or arbitrary-provider claim follows.

## Final verification

The initial 542 focused tests passed. The first full run found missing setting
reference entries and an ordinary-Responses validation ordering regression;
both were corrected. A preliminary focused module test also lacked the linked
worktree metadata mount; the final run mounts both real worktree paths.

Final source regression at `5676edfb91fbef485c0aa6123b19e8055a617d27`:

- `pytest -p no:cacheprovider -n 4 tests/unit`: **5,345 passed, 1 skipped**
  in 161.43 seconds. The skip is the unavailable legacy Codex 0.148 CLI fixture.
- Five selected PostgreSQL integration files: **39 passed** in 22.45 seconds,
  including media reservation/actual-usage finalization. A uniquely owned
  disposable PostgreSQL 16 container was removed afterward; the production
  `DATABASE_URL` was not used by tests.
- Ruff check and `git diff --check` passed. Normal tests made no real upstream
  calls, invoked no live Codex CLI and sent no email. Manual native tokenizer,
  exact-client and video checks below are separate authorized live evidence.

This is not full browser/HPC/release qualification.

## Deployment and live results

At 22:11:41 UTC the operator deployment was updated to source
`5676edfb91fbef485c0aa6123b19e8055a617d27`, image
`sha256:ad43e51b073275f401e03f1dc30c117804bed2c1af620e9dbef923f5756ca25a`.
Ingress was drained, readiness and public HTTPS health passed, and no migration
ran. Targeted software/route rollback was prepared; no database restore was used.

Audited operator route updates added the shipped 16,896-token image budget to
four existing Qwen routes. One A100 `qwen3.8-27b` Chat route was added with native
video permission, a 65,536-token video budget and four-frame processing limit,
plus the same existing operator-confirmed zero local tariff. These budgets are
conservative operator admission values, not exact tokenizer/billing claims.
The live qualification below covers A100; RTX3090/V100 inference was not tested.

All **42 pre-existing key configurations** matched their pre-deployment
fingerprints after deployment and again after live checks. Concurrent new keys
would be retained. Existing endpoint permissions, credentials, quotas, 10-second
lazy throttling and concurrency settings were not changed. The external client
preset file SHA-256 remained
`a5fa52fa48c9518cbb9461101f783c4085540a016c89c5d3e9f71bb6b9b25d70`.

The actual saved Lena conversation was forked using exact Codex **0.163.0**, the
existing `qwen-students` profile, explicit **Qwen A100**, read-only sandbox and
no approvals. Its original history was retained, including the full PNG data
URL. The fork completed and described the hat. The source session SHA-256 stayed
unchanged. No conversation repair, context truncation or image re-encoding was
used. The successful gateway ledger recorded HTTP 200, finalized accounting,
49,052 input plus 823 output tokens (49,875 total), and zero remaining token or
request reservations. This verifies the context failure is resolved; it is not
a general model-answer quality assessment.

Direct video was tested through public HTTPS Chat Completions with the synthetic
MP4. It answered the expected main color, recorded HTTP 200 and finalized
accounting for 93 input plus 75 output tokens (168 total), and left zero
reservations. A temporary narrowly scoped key was used because the existing
student key permits only Responses/Models. That temporary key was immediately
revoked; plaintext existed only in process memory and no email was sent. The
student key gained no new endpoint permissions.

Draft PR #339 is stacked on #338 and remains unmerged. At the source-head check,
CodeQL passed and the remaining CI workflow was still running. This report-only
follow-up does not change the deployed runtime source.

Documentation impact: media estimation and direct-video policy are documented
in docs/media-input-estimation.md; Responses and forwarding/compatibility
contracts link that bounded policy. Runtime policy data ships as a separate
JSON resource and is not embedded in code or key metadata.
