# 219-c immutable report — Chromium installation repair (same PR #376)

Execution: strategic/root directly, explicitly requested by the human. No
coding agent, helper agent, control FIFO signal, response FIFO signal or extra
reader was used. This human-directed execution exception is scoped in the
immutable219-c order; permanent startup authority/protocols are unchanged.

Implementation head SHA: 3a2034ff501fc4c20e576fe3944924428a58843e
Report publication commit: SELF
Implementation tree: 91861586fd958d4117ac19f0dd68793f6ebc1e61
Final application product: 34cbf03078a47ebee5a52faf5bd00a1188ec1216 (unchanged)
Base main: 663c673494d4c0daeb4d5b1269b428ee13277448
PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/376
Branch: oap/219-gui-completion-gate; same numeric objective219, no new PR.

## Diagnosis and repair

The failed219-b browser jobs130614803637/130622138392/130629861588 all
failed BEFORE tests and BEFORE Chromium download, in the --with-deps apt
phase. All26 queried runtime packages were already installed. The9 new
packages were font/Xfont bundles; Ubuntu archive/security DNS failures
prevented fetching them. The earlier outage-only conclusion was premature:
a browser-only install and real launch had not been tried.

Only .github/workflows/ci.yml browser installation step changes behavior:
python -m playwright install chromium, then a real Chromium launch and
minimal rendered title assertion. The full unchanged browser command follows:
python -m pytest tests/browser -m playwright. Normal host validation remains
on; missing libraries, download/launch errors and test failures still fail.
No ignored failures, test skips, mocks, DNS changes, runner replacements,
permissions/triggers/other-job changes or dependency changes.

## Verification actually performed

- Fresh owned cache /tmp/slaif219/root-chromium-install: Playwright1.65.0
  downloaded Chromium158.0.8127.18/build1254, matching headless shell and
  FFmpeg1013 successfully, direct tool exit0. Actual fresh browser launch,
  title and heading assertions: CHROMIUM_INSTALL_OK158.0.8127.18, exit0.
  Local Ubuntu26.04.1; no apt/system package changes.
- EXACT edited CI script, extracted from workflow, executed locally with the
  fresh cache: Chromium launch OK:158.0.8127.18; PREFLIGHT_EXIT=0.
  /tmp/slaif219/root-ci-chromium-preflight.log SHA256
  93ac2de5bd11e6c4c6a3f5521a25143032fbdbf4c1ebd14ae772052e3382ce8b.
- Existing system PyYAML6.0.3 parsed the workflow; structural old/new comparison
  proves ONLY the browser install step changed and full browser command is
  unchanged. Initial qualification-venv YAML probe failed because PyYAML was
  absent there; it performed no validation. Corrected existing-system probe
  passed, no package installed.
- OAP governance + documentation_asof/contract_drift/inventory:53 passed,
  zero failures/errors/skips; direct PYTEST_EXIT=0. JUnit start
  2026-11-11T17:43:37.531098Z, duration2.802s,
  /tmp/slaif219/root-219c-focused.xml SHA256
  e2e579eda8bd16f442c089af26203840e5c1e4ce4836b0d5b438f07454632711.
  These checks ran on the working changes later committed as IMPL; the
  documentation receipt paragraph was appended afterward. Final-head CI docs
  remains required. No invented later commit as an earlier run source.
- git diff --check passed. App AND test bytes unchanged from34cbf030;
  all prior219-a/219-b order/report hashes and all3 protected untracked-file
  hashes independently rechecked unchanged; none staged/read as content.
- Reuse accepted219-b461units/4nativeChromium/19installed and207-218 component
  evidence at exact scope. No repeated installed workflow/wheel rebuild: final
  app bytes still equal selected wheel8a364a97ee70610c3ccfa569246b01bbe93ce50588141d63b1f8cda42e6e8e06.

Local download/rendering proves this path locally. Hosted-runner browser
qualification is PENDING, NOT PASS, at publication. All final-head checks,
review/material gates and actual-main verification remain REQUIRED.

## Preservation, publication and delivery

Documentation updated: docs/verification/gui-cli-parity.md records the actual
installer failure, bounded fix, local-vs-CI evidence and unchanged upgrade.
Only workflow + that existing record + root order + active pointer in IMPL.
No app/schema/accounting/replay/auth/provider/permission changes or migration.
No provider/mail/production calls or secrets in receipts. Ordinary application
restart/recreate remains sufficient, no key-policy migration or rotation.

Order oap/orders/219-c-chromium-installation.md5777bytes SHA256
1e0695dec631261d759e5e879856b520e532ab52581ab1625c13d4576de0e241;
oap/active exact219-c5bytes. Previous artifacts remain immutable. Report
prepared outside final path, published via same-directory temp+filefsync+
atomic replace+directoryfsync. SELF must have IMPL as SOLE parent and ONLY
this report diff. Push append-only and verify remote bytes/head. No FIFO
signals; coding waiter remains idle. Root owns final-head CI, guarded merge
and actual-main9checks/3workflows. No release/tag/deployment authorization.
