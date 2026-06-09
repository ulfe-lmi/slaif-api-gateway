(() => {
  const surfaces = document.querySelectorAll("[data-policy-selector-surface]");
  if (!surfaces.length) {
    return;
  }

  const dimensions = ["providers", "endpoints", "models"];
  const modelsEndpoint = "/v1/models";
  const modelBackedEndpoints = new Set([
    "/v1/chat/completions",
    "/v1/responses",
    "/v1/responses/input_tokens",
    "/v1/responses/compact",
  ]);

  const parseList = (value) =>
    (value || "")
      .replaceAll(",", "\n")
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);

  const uniqueValues = (values) => {
    const seen = new Set();
    const result = [];
    for (const value of values) {
      if (seen.has(value)) {
        continue;
      }
      seen.add(value);
      result.push(value);
    }
    return result;
  };

  for (const surface of surfaces) {
    const groups = {};
    for (const dimension of dimensions) {
      groups[dimension] = {
        container: surface.querySelector(`[data-policy-selector-group="${dimension}"]`),
        available: surface.querySelector(`[data-policy-available="${dimension}"]`),
        selected: surface.querySelector(`[data-policy-selected="${dimension}"]`),
        manual: surface.querySelector(`[data-policy-manual="${dimension}"]`),
        toggle: surface.querySelector(`[data-policy-toggle="${dimension}"]`),
        addButton: surface.querySelector(`[data-policy-add="${dimension}"]`),
        removeButton: surface.querySelector(`[data-policy-remove="${dimension}"]`),
        emptyAvailable: surface.querySelector(`[data-policy-empty="${dimension}-available"]`),
        emptySelected: surface.querySelector(`[data-policy-empty="${dimension}-selected"]`),
        emptySelectedAway: surface.querySelector(`[data-policy-empty="${dimension}-selected-away"]`),
      };
    }
    groups.models.emptyNone = surface.querySelector('[data-policy-empty="models-none"]');
    groups.models.emptyFiltered = surface.querySelector('[data-policy-empty="models-filtered"]');

    const choiceLabels = {
      providers: new Map(),
      endpoints: new Map(),
      models: new Map(),
    };

    const registerChoiceLabels = (dimension) => {
      for (const option of groups[dimension].available?.querySelectorAll("option") || []) {
        if (dimension === "models") {
          const token = option.dataset.modelToken || "";
          if (token && !choiceLabels.models.has(token)) {
            choiceLabels.models.set(token, `${token} | allowed model token`);
          }
        } else if (option.value) {
          choiceLabels[dimension].set(option.value, option.textContent || option.value);
        }
      }
      for (const option of groups[dimension].selected?.querySelectorAll("option") || []) {
        if (option.value && !choiceLabels[dimension].has(option.value)) {
          choiceLabels[dimension].set(option.value, option.textContent || option.value);
        }
      }
    };

    const selectedValues = (dimension) =>
      Array.from(groups[dimension].selected?.options || []).map((option) => option.value);

    const setSelectedValues = (dimension, values) => {
      const selected = groups[dimension].selected;
      if (!selected) {
        return;
      }
      selected.replaceChildren();
      for (const value of uniqueValues(values)) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = choiceLabels[dimension].get(value) || value;
        selected.appendChild(option);
      }
    };

    const syncManualFromSelected = (dimension) => {
      const manual = groups[dimension].manual;
      if (!manual) {
        return;
      }
      manual.value = selectedValues(dimension).join("\n");
    };

    const syncSelectedFromManual = (dimension) => {
      const manual = groups[dimension].manual;
      if (!manual) {
        return;
      }
      setSelectedValues(dimension, parseList(manual.value));
    };

    const refreshAvailableAgainstSelected = (dimension) => {
      const available = groups[dimension].available;
      if (!available) {
        return;
      }
      const selected = new Set(selectedValues(dimension));
      for (const option of available.querySelectorAll("option")) {
        const optionValue =
          dimension === "models" ? option.dataset.modelToken || "" : option.value;
        const hidden = selected.has(optionValue);
        option.hidden = hidden;
        option.disabled = hidden;
      }
    };

    const currentProviderFilter = () => {
      if (groups.providers.toggle?.checked) {
        return null;
      }
      const selected = selectedValues("providers");
      return selected.length ? new Set(selected) : new Set();
    };

    const currentEndpointFilter = () => {
      if (groups.endpoints.toggle?.checked) {
        return null;
      }
      const selected = selectedValues("endpoints");
      if (!selected.length) {
        return new Set();
      }
      const modelBacked = selected.filter((endpoint) => modelBackedEndpoints.has(endpoint));
      if (modelBacked.length) {
        return new Set(modelBacked);
      }
      if (selected.includes(modelsEndpoint)) {
        return null;
      }
      return new Set();
    };

    const refreshModelFilters = () => {
      const available = groups.models.available;
      if (!available) {
        return;
      }
      const providerFilter = currentProviderFilter();
      const endpointFilter = currentEndpointFilter();
      for (const option of available.querySelectorAll("option")) {
        const matchesProvider =
          providerFilter === null ? true : providerFilter.has(option.dataset.provider || "");
        const matchesEndpoint =
          endpointFilter === null ? true : endpointFilter.has(option.dataset.endpoint || "");
        const selected = new Set(selectedValues("models"));
        const alreadySelected = selected.has(option.dataset.modelToken || "");
        const visible = matchesProvider && matchesEndpoint && !alreadySelected;
        option.hidden = !visible;
        option.disabled = !visible;
      }
      for (const group of available.querySelectorAll("optgroup")) {
        const visibleOptions = Array.from(group.querySelectorAll("option")).some(
          (option) => !option.hidden
        );
        group.disabled = !visibleOptions;
      }
    };

    const visibleOptionCount = (select) =>
      Array.from(select?.querySelectorAll("option") || []).filter((option) => !option.hidden).length;

    const setHidden = (element, hidden) => {
      if (!element) {
        return;
      }
      element.hidden = hidden;
    };

    const refreshEmptyStates = () => {
      for (const dimension of ["providers", "endpoints"]) {
        if (groups[dimension].toggle?.checked) {
          setHidden(groups[dimension].emptyAvailable, true);
          setHidden(groups[dimension].emptySelectedAway, true);
          setHidden(groups[dimension].emptySelected, true);
          continue;
        }
        const availableVisible = visibleOptionCount(groups[dimension].available);
        const selectedCount = selectedValues(dimension).length;
        const totalAvailableChoices = Array.from(
          groups[dimension].available?.querySelectorAll("option") || []
        ).length;
        const hasNoChoices = totalAvailableChoices === 0;
        const allAlreadySelected =
          totalAvailableChoices > 0 && availableVisible === 0 && selectedCount > 0;
        setHidden(groups[dimension].emptyAvailable, !hasNoChoices);
        setHidden(
          groups[dimension].emptySelectedAway,
          !allAlreadySelected
        );
        setHidden(groups[dimension].emptySelected, selectedCount > 0);
      }

      const modelsVisible = visibleOptionCount(groups.models.available);
      const modelsSelected = selectedValues("models").length;
      const totalModelOptions = Array.from(
        groups.models.available?.querySelectorAll("option") || []
      ).length;
      if (groups.models.toggle?.checked) {
        setHidden(groups.models.emptySelected, true);
        setHidden(groups.models.emptyNone, true);
        setHidden(groups.models.emptyFiltered, true);
        setHidden(groups.models.emptySelectedAway, true);
        return;
      }
      setHidden(groups.models.emptySelected, modelsSelected > 0);
      setHidden(groups.models.emptyNone, totalModelOptions > 0);
      setHidden(
        groups.models.emptyFiltered,
        !(totalModelOptions > 0 && modelsVisible === 0 && modelsSelected === 0)
      );
      setHidden(
        groups.models.emptySelectedAway,
        !(totalModelOptions > 0 && modelsVisible === 0 && modelsSelected > 0)
      );
      setHidden(
        groups.models.emptyAvailable,
        !(totalModelOptions > 0 && modelsVisible === 0)
      );
    };

    const refreshButtonStates = () => {
      for (const dimension of dimensions) {
        if (groups[dimension].addButton) {
          groups[dimension].addButton.disabled =
            groups[dimension].toggle?.checked ||
            !Array.from(groups[dimension].available?.selectedOptions || []).length;
        }
        if (groups[dimension].removeButton) {
          groups[dimension].removeButton.disabled =
            groups[dimension].toggle?.checked ||
            !Array.from(groups[dimension].selected?.selectedOptions || []).length;
        }
      }
    };

    const syncGroupDisabled = (dimension) => {
      const group = groups[dimension];
      if (!group.container || !group.toggle) {
        return;
      }
      const disabled = group.toggle.checked;
      group.container.classList.toggle("policy-selector-disabled", disabled);
      for (const element of [group.available, group.selected, group.addButton, group.removeButton]) {
        if (element) {
          element.disabled = disabled;
        }
      }
    };

    const refreshAll = () => {
      refreshAvailableAgainstSelected("providers");
      refreshAvailableAgainstSelected("endpoints");
      refreshAvailableAgainstSelected("models");
      refreshModelFilters();
      for (const dimension of dimensions) {
        syncGroupDisabled(dimension);
      }
      refreshEmptyStates();
      refreshButtonStates();
    };

    const addSelected = (dimension) => {
      const available = groups[dimension].available;
      if (!available) {
        return;
      }
      const nextValues = [...selectedValues(dimension)];
      for (const option of Array.from(available.selectedOptions)) {
        const value = dimension === "models" ? option.dataset.modelToken || "" : option.value;
        if (!value) {
          continue;
        }
        nextValues.push(value);
      }
      setSelectedValues(dimension, nextValues);
      syncManualFromSelected(dimension);
      refreshAll();
    };

    const removeSelected = (dimension) => {
      const selected = groups[dimension].selected;
      if (!selected) {
        return;
      }
      for (const option of Array.from(selected.selectedOptions)) {
        option.remove();
      }
      syncManualFromSelected(dimension);
      refreshAll();
    };

    for (const dimension of dimensions) {
      registerChoiceLabels(dimension);
      syncSelectedFromManual(dimension);
      groups[dimension].manual?.addEventListener("input", () => {
        syncSelectedFromManual(dimension);
        refreshAll();
      });
      groups[dimension].addButton?.addEventListener("click", () => addSelected(dimension));
      groups[dimension].removeButton?.addEventListener("click", () => removeSelected(dimension));
      groups[dimension].toggle?.addEventListener("change", refreshAll);
      groups[dimension].available?.addEventListener("change", refreshButtonStates);
    }

    groups.providers.selected?.addEventListener("change", refreshAll);
    groups.endpoints.selected?.addEventListener("change", refreshAll);
    groups.models.selected?.addEventListener("change", refreshAll);

    refreshAll();
  }
})();
