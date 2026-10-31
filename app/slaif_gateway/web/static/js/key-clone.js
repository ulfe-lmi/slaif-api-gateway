// Key-clone guided form (208-a): progressive enhancement only.
//
// Highlights the selected validity mode by disabling the OTHER modes'
// inputs (disabled inputs are not submitted, so a JS submission carries
// only the selected mode's values - the same law the no-JS fallback must
// satisfy manually by leaving other modes' fields blank). The server
// enforces the single-mode law in every case; this script never converts,
// groups, or scales any value.
(() => {
  const root = document.querySelector("[data-clone-validity]");
  if (!root) return;
  const radios = root.querySelectorAll('input[name="validity_mode"]');
  const durationFields = root.querySelectorAll("[data-clone-duration]");
  const absoluteFields = root.querySelectorAll(
    'input[name="valid_from"], input[name="valid_until"]'
  );
  const sync = () => {
    const checked = root.querySelector('input[name="validity_mode"]:checked');
    const mode = checked ? checked.value : "";
    for (const field of durationFields) {
      for (const control of field.querySelectorAll("input, select")) {
        control.disabled = mode !== "duration-from-now";
      }
    }
    for (const control of absoluteFields) {
      control.disabled = mode !== "absolute";
    }
  };
  for (const radio of radios) radio.addEventListener("change", sync);
  sync();
})();
