(() => {
  const surfaces = document.querySelectorAll("[data-streaming-live-burn-surface]");

  for (const surface of surfaces) {
    const checkbox = surface.querySelector("[data-streaming-live-burn-enabled]");
    const fields = surface.querySelector("[data-streaming-live-burn-margin-fields]");
    if (!checkbox || !fields) continue;

    const inputs = Array.from(fields.querySelectorAll("input"));
    const sync = () => {
      const enabled = checkbox.checked;
      fields.classList.toggle("live-burn-fields-disabled", !enabled);
      for (const input of inputs) {
        input.disabled = !enabled;
      }
    };

    checkbox.addEventListener("change", sync);
    sync();
  }
})();
