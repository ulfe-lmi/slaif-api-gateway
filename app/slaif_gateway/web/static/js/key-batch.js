// Key batch guided form (209-a): progressive enhancement only.
//
// ONE composed disabled-state sync (syncAll) derives the active/inactive
// state of EVERY batch control from the CURRENT form values: input mode
// (guided policy controls vs advanced configuration document), selection
// kind (cohort vs explicit keys), action/value pairs (a value input is
// enabled only for "set"), the allow-list record controls (submitted
// values only for "allow_list"), lazy waiting, and live-burn margins.
// Disabled inputs are never submitted, so a submission carries only the
// selected source's values. Toggling an outer group (guided <-> advanced,
// keys <-> cohort) re-derives every subordinate state in the SAME pass,
// so it can never re-enable a still-inactive value. Re-activating a group
// preserves its selection (record-choices keeps state in its managed
// hidden fields/chips). The no-JS fallback must satisfy the same law
// manually by leaving the other fields at defaults/blank; the server
// enforces every single-source law in all cases. This script never
// converts, groups, or scales any value.
(() => {
  const doc = document;

  const setDisabled = (root, disabled) => {
    for (const control of root.querySelectorAll("input, select, textarea")) {
      if (control.type !== "radio" && control.type !== "checkbox") {
        control.disabled = disabled;
      }
    }
  };

  const checkedValue = (name) => {
    const el = doc.querySelector(`input[name="${name}"]:checked`);
    return el ? el.value : "";
  };

  const ACTION_PAIRS = [
    ["cost_action", "cost_value"],
    ["token_action", "token_value"],
    ["request_action", "request_value"],
    ["rate_action_requests", "rate_value_requests"],
    ["rate_action_tokens", "rate_value_tokens"],
    ["rate_action_concurrency", "rate_value_concurrency"],
    ["rate_action_window", "rate_value_window"],
  ];
  const LIST_PAIRS = [
    ["providers_mode", "providers_value"],
    ["models_mode", "models_value"],
    ["endpoints_mode", "endpoints_value"],
  ];

  const syncAll = () => {
    // 1. Selection kind: cohort picker vs explicit key UUID list. This
    // scope is INDEPENDENT of the policy source (guided vs advanced) -
    // every batch names exactly one target scope - so it is synced
    // BEFORE the advanced early return below.
    const keys = checkedValue("selection_kind") === "keys";
    const cohortControl = doc.querySelector("[data-batch-cohort-control]");
    const keysControl = doc.querySelector("[data-batch-keys-control]");
    if (cohortControl) setDisabled(cohortControl, keys);
    if (keysControl) setDisabled(keysControl, !keys);

    // 2. Input mode: advanced makes the strict configuration document
    // the sole policy source, so every guided policy control goes
    // inactive in one pass and no subordinate POLICY state is re-derived
    // underneath it.
    const advanced = checkedValue("input_mode") === "advanced";
    const policyRoot = doc.querySelector("[data-batch-policy]");
    const advancedTextarea = doc.querySelector("[data-batch-advanced] textarea");
    if (advanced) {
      if (policyRoot) setDisabled(policyRoot, true);
      if (advancedTextarea) advancedTextarea.disabled = false;
      return;
    }
    // Guided mode: base-enable, then re-derive each subordinate state so
    // an outer toggle can never leave a subordinate stale.
    if (policyRoot) setDisabled(policyRoot, false);
    if (advancedTextarea) advancedTextarea.disabled = true;

    // 3. Action selects: the paired value input is enabled only for
    // "set".
    for (const [actionName, valueName] of ACTION_PAIRS) {
      const action = doc.querySelector(`select[name="${actionName}"]`);
      const value = doc.querySelector(`input[name="${valueName}"]`);
      if (action && value) value.disabled = action.value !== "set";
    }

    // 4. Allow-list record controls: with JavaScript the record-choices
    // control has adopted the field, so the SUBMITTED value lives in the
    // managed hidden .rc-value field(s) it creates at adoption (record-
    // choices is deferred and adopts BEFORE DOMContentLoaded, so they are
    // present for the initial sync below). Disable them whenever the mode
    // is not "allow_list" - otherwise a stale allow-list value would ride
    // along with unrestricted/deny_all/all/unchanged and trip the
    // server's single-source refusal. Re-activating preserves the current
    // selection. The no-JS textarea (pre-adoption) keeps its name and is
    // disabled directly.
    for (const [modeName, valueName] of LIST_PAIRS) {
      const mode = doc.querySelector(`select[name="${modeName}"]`);
      if (!mode) continue;
      const active = mode.value === "allow_list";
      const rcEl = doc.querySelector(`[data-rc][data-input-name="${valueName}"]`);
      if (rcEl) {
        for (const hidden of rcEl.querySelectorAll(".rc-value")) {
          hidden.disabled = !active;
        }
        const entry = rcEl.querySelector(".rc-input");
        if (entry) entry.disabled = !active;
      }
      const legacy = doc.querySelector(`textarea[name="${valueName}"]`);
      if (legacy) legacy.disabled = !active;
    }

    // 5. Lazy throttling: wait values only for "wait" mode.
    const lazyMode = doc.querySelector('select[name="lazy_mode"]');
    if (lazyMode) {
      for (const wrap of doc.querySelectorAll("[data-batch-lazy-wait]")) {
        const input = wrap.querySelector("input");
        if (input) input.disabled = lazyMode.value !== "wait";
      }
    }

    // 6. Live-burn: margins only for enable/disable.
    const liveBurnMode = doc.querySelector('select[name="live_burn_mode"]');
    if (liveBurnMode) {
      for (const wrap of doc.querySelectorAll("[data-batch-live-burn]")) {
        const input = wrap.querySelector("input");
        if (input) input.disabled = liveBurnMode.value === "unchanged";
      }
    }
  };

  // One delegated listener re-derives EVERY state on any change, so an
  // outer-group toggle (guided/advanced, keys/cohort) and per-member or
  // list-mode changes always compose into one consistent submission.
  const form = doc.querySelector('form[action="/admin/key-batch/plan"]');
  if (form) {
    form.addEventListener("change", syncAll);
    // record-choices announces ACTUAL value changes (chip add/remove,
    // clear, selection) with a bubbling rc-change custom event, NOT a
    // native change, and rebuilds its managed hidden .rc-value fields
    // ENABLED on every write. Re-applying the composed state keeps a
    // chip removed while its list mode is inactive from leaving a
    // resubmittable stale value, and preserves active selections.
    form.addEventListener("rc-change", syncAll);
  }

  // This (non-deferred) script's first pass runs before record-choices.js
  // (deferred) adopts the list controls and creates the managed hidden
  // fields, so the initial full sync waits for DOMContentLoaded, which
  // fires only after the deferred scripts have run.
  if (doc.readyState === "loading") {
    doc.addEventListener("DOMContentLoaded", syncAll, { once: true });
  } else {
    syncAll();
  }
})();
