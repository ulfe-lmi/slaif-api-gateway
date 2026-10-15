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
