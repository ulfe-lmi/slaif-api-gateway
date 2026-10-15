(() => {
  for (const surface of document.querySelectorAll("[data-lazy-throttling-surface]")) {
    const modes = Array.from(surface.querySelectorAll("[data-lazy-throttling-mode]"));
    const groups = Array.from(
      surface.querySelectorAll("[data-lazy-throttling-field-group]"),
    );
    const fields = Array.from(surface.querySelectorAll("[data-lazy-throttling-field]"));
    if (modes.length === 0) continue;

    const sync = () => {
      const waitSelected = modes.some(
        (input) => input.checked && input.value === "wait",
      );
      for (const group of groups) {
        group.hidden = !waitSelected;
        // The page stylesheet sets display on the grid class, which would
        // override the hidden attribute; the inline style makes the
        // hide/reveal actually apply without CSS changes.
        group.style.display = waitSelected ? "" : "none";
      }
      for (const field of fields) {
        field.disabled = !waitSelected;
      }
    };

    for (const input of modes) {
      input.addEventListener("change", sync);
    }
    sync();
  }
})();
