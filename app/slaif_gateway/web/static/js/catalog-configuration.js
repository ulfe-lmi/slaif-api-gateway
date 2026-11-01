/* Reviewed route-configuration form sync (objective 210-a).
 *
 * Progressive enhancement ONLY: the server renders every control
 * accessible and enabled (the no-JS form is complete and valid). This
 * script adds hiding/disabling state so inactive controls read as
 * inactive:
 *
 * - capability source radios hide the guided / complete-replacement
 *   groups that are not active;
 * - notes intent radios disable the replacement textarea unless the
 *   intent is "replace";
 * - action selects disable their paired value control unless the action
 *   equals the active value (default "set").
 *
 * It never converts, fills, or clears values; the server parser remains
 * the authority (an inactive value that is submitted anyway is ignored
 * by its action select). Record-choice controls are never disabled here
 * (they keep the current value visible); their action select decides.
 */
(function () {
  "use strict";

  const root = document.querySelector("form[data-cfg-root]");
  if (!root) return;

  const guided = root.querySelector("#cfg-guided-group");
  const full = root.querySelector("#cfg-full-group");
  const notesArea = root.querySelector('textarea[name="notes"]');

  function checkedValue(name) {
    const el = root.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : "";
  }

  function setGroup(el, active) {
    if (!el) return;
    el.hidden = !active;
    // A disabled fieldset disables every descendant control, including
    // the record-choice managed hidden inputs after adoption, so an
    // inactive source never submits stale values.
    el.disabled = !active;
  }

  function sync() {
    const source = checkedValue("capabilities_source") || "unchanged";
    setGroup(guided, source === "guided");
    setGroup(full, source === "full");
    if (notesArea) notesArea.disabled = checkedValue("notes_intent") !== "replace";
    for (const sel of root.querySelectorAll("select[data-cfg-action]")) {
      const target = sel.getAttribute("data-cfg-target");
      if (!target) continue;
      const el = root.querySelector(target);
      if (!el || !("disabled" in el)) continue;
      const active = sel.getAttribute("data-cfg-active") || "set";
      el.disabled = sel.value !== active;
    }
  }

  root.addEventListener("change", sync);
  root.addEventListener("rc-change", sync);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
