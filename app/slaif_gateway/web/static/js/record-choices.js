/**
 * SLAIF admin record choices — shared searchable combobox behavior
 * for known-record and known-option fields.
 *
 * Dependency-free, progressive enhancement for controls rendered by the
 * `_record_choice.html` macro (`[data-rc]`). The control pairs a visible
 * search/entry input with a hidden form input that carries the submitted
 * value, so the server-rendered form remains fully usable without
 * JavaScript and existing server validation stays authoritative.
 *
 * Behavior contract:
 * - The initial option list is the server-rendered latest ~100 eligible
 *   records (created_at DESC with a deterministic tie-breaker) embedded as
 *   `data-initial-options`. A current selection that falls outside that
 *   batch is preserved through `data-selected-id`/`data-selected-label`
 *   and is re-hydrated from the server when the menu opens (`selected=`
 *   parameter).
 * - Server search reaches OLDER records: typing issues bounded GET
 *   requests to /admin/record-choices (kind, q, optional selected and
 *   dependency parameters, at most 100 results per request). Results
 *   replace the menu list; the form is never auto-submitted.
 * - data-allow-new="1": the visible input also accepts a typed new value;
 *   the hidden form input then carries the typed text and the server
 *   validation decides. data-allow-new="0": selection only; the hidden
 *   input always carries a known option id.
 * - Multi-value controls (data-multi="1") manage a chip list plus either
 *   one hidden input per value (default) or a single newline-serialized
 *   hidden input (data-serialize="newline") so existing server-side
 *   parsing and policy semantics are not broadened or corrupted.
 * - Dependent controls (data-depends-on="<rc-id>") refetch their options
 *   when the referenced control's value changes and clear their own
 *   selection by default (data-clear-on-dep="0" opts out). The parent's
 *   value is sent under data-depends-param (whitelisted to "provider" or
 *   "target_type", default "provider"), matching the documented lookup
 *   parameters.
 * - Keyboard: the input is a combobox (ArrowDown/ArrowUp navigate,
 *   Home/End jump, Enter selects the active option while the menu is
 *   open, Escape and Tab close it); the open/clear buttons are ordinary
 *   buttons. Clear is offered wherever the form currently allows empty.
 * - Empty database, no match, loading, and failure states are announced
 *   through a visible status line; selected state is preserved in all of
 *   them. No network traffic other than the documented lookup GET; no
 *   eval/Function, no dynamic code, no inline event-handler attributes.
 */
(() => {
  "use strict";

  const LOOKUP_PATH = "/admin/record-choices";
  const SEARCH_DEBOUNCE_MS = 200;
  const MAX_QUERY_LENGTH = 200;

  const escapeHtml = (value) =>
    String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const readOptions = (rc) => {
    try {
      const raw = rc.dataset.initialOptions;
      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed
        .filter((item) => item && typeof item === "object" && typeof item.id === "string")
        .map((item) => ({
          id: item.id,
          label: typeof item.label === "string" ? item.label : item.id,
          sub: typeof item.sub === "string" ? item.sub : "",
        }));
    } catch {
      return [];
    }
  };

  const initControl = (rc) => {
    if (rc.dataset.rcInitialized === "1") {
      return;
    }
    rc.dataset.rcInitialized = "1";
    // 193-a: marks the JS-enhanced mode so CSS can collapse the multi
    // box to one integrated line. Without JavaScript this class is never
    // added and the no-JS fallback keeps its natural multi-line height.
    rc.classList.add("rc-js");

    const kind = rc.dataset.kind || "";
    const inputName = rc.dataset.inputName || "";
    const multi = rc.dataset.multi === "1";
    const allowNew = rc.dataset.allowNew === "1";
    const newline = rc.dataset.serialize === "newline";
    const clearLabel = rc.dataset.clearLabel || "Clear";
    const dependsOn = rc.dataset.dependsOn || "";
    const dependsParam =
      rc.dataset.dependsParam === "target_type" ? "target_type" : "provider";
    const clearOnDep = rc.dataset.clearOnDep !== "0";

    // Progressive enhancement: the visible input is the form field until
    // this script takes over (no-JS operators keep a plain text field).
    const input = rc.querySelector(".rc-input");
    const clearButton = rc.querySelector(".rc-clear");
    const openButton = rc.querySelector(".rc-open");
    const menu = rc.querySelector(".rc-menu");
    const searchInput = rc.querySelector(".rc-search");
    const list = rc.querySelector(".rc-list");
    const status = rc.querySelector(".rc-status");
    const selectedArea = rc.querySelector(".rc-selected");
    if (!input || !menu || !list) {
      return;
    }

    let options = readOptions(rc);
    let selected = []; // array of {id, label}
    let initializing = true;
    let justClosedAt = 0;
    let rendered = []; // options actually in the menu right now

    if (input.name) {
      input.removeAttribute("name");
    }

    const announceChange = () => {
      // Bubbles from the control so dependent controls (listening on the
      // referenced [data-rc-id] element, or anywhere downstream) receive it
      // on every ACTUAL value change: select, clear, keyboard, typing.
      rc.dispatchEvent(new CustomEvent("rc-change", { bubbles: true, detail: { kind, value: selected.map((v) => v.id) } }));
    };
    let activeIndex = -1;
    let menuOpen = false;
    let searchTimer = null;
    let searchInFlight = null;
    let searchSeq = 0;

    const listId = `rc-list-${rc.dataset.rcId || "x"}`;
    list.id = listId;
    input.setAttribute("aria-controls", listId);

    // ---- selection / hidden form state ---------------------------------

    // The managed hidden field(s) live inside the control itself (not as
    // direct form children) so they can be re-queried and removed on every
    // write and so dependent lookups find them via .rc-value.
    const writeHidden = (values) => {
      const serialized = newline
        ? [values.map((v) => v.id).join("\n")]
        : values.map((v) => v.id);
      for (const el of Array.from(rc.querySelectorAll(".rc-value"))) {
        el.remove();
      }
      const parts = serialized.length > 0 ? serialized : [""];
      for (const value of parts) {
        const el = document.createElement("input");
        el.type = "hidden";
        el.className = "rc-value";
        el.name = inputName;
        el.value = value == null ? "" : value;
        rc.appendChild(el);
      }
      if (!initializing) {
        announceChange();
      }
    };

    // 195-a: rebuilds ONLY the visible chip area. Label-only refreshes
    // (e.g. the server re-hydrating an older selection's authoritative
    // label after a lookup) call this directly so they never rewrite the
    // managed hidden fields, never emit rc-change (the value did not
    // change), and never disturb input text/focus/caret.
    const renderChips = () => {
      if (selectedArea) {
        selectedArea.replaceChildren();
        selectedArea.hidden = selected.length === 0;
        for (const value of selected) {
          const chip = document.createElement("span");
          chip.className = "rc-chip";
          chip.innerHTML = `${escapeHtml(value.label || value.id)}<button type="button" class="rc-chip-remove" aria-label="Remove ${escapeHtml(value.label || value.id)}">×</button>`;
          chip.querySelector(".rc-chip-remove").addEventListener("click", () => {
            selected = selected.filter((v) => v.id !== value.id);
            syncFromSelection();
          });
          selectedArea.appendChild(chip);
        }
      }
    };

    const renderSelected = () => {
      renderChips();
      writeHidden(selected);
    };

    const syncFromSelection = () => {
      if (multi) {
        input.value = "";
        renderSelected();
        refreshClearVisibility();
        return;
      }
      // 193-a: a single currently selected value remains a CHIP below the
      // box; the integrated box keeps a BLANK search prompt for the next
      // search instead of duplicating the value in the input. The scalar
      // form authority is the managed hidden field (writeHidden), which is
      // unchanged: selection, replacement, and no-JS submissions all keep
      // their exact server-side semantics.
      input.value = "";
      renderSelected();
      refreshClearVisibility();
    };

    const refreshClearVisibility = () => {
      if (!clearButton) {
        return;
      }
      clearButton.hidden =
        selected.length === 0 && input.value === "";
    };

    // ---- option list rendering ------------------------------------------

    const renderList = (items, note) => {
      list.replaceChildren();
      activeIndex = -1;
      rendered = items;
      if (items.length === 0) {
        status.textContent = note || "No matching records.";
        status.hidden = false;
        return;
      }
      status.textContent = "";
      status.hidden = true;
      for (let i = 0; i < items.length; i += 1) {
        const item = items[i];
        const li = document.createElement("li");
        li.id = `${listId}-opt-${i}`;
        li.setAttribute("role", "option");
        li.className = "rc-option";
        li.dataset.optionIndex = String(i);
        const selectedHere = selected.some((v) => v.id === item.id);
        if (selectedHere) {
          li.classList.add("rc-option-selected");
        }
        const main = document.createElement("span");
        main.className = "rc-option-label";
        main.textContent = item.label;
        li.appendChild(main);
        if (item.sub) {
          const sub = document.createElement("span");
          sub.className = "rc-option-sub";
          sub.textContent = item.sub;
          li.appendChild(sub);
        }
        if (!multi) {
          li.addEventListener("mousedown", (event) => {
            event.preventDefault(); // keep input focus
            selectItem(item);
          });
        } else {
          li.addEventListener("mousedown", (event) => {
            event.preventDefault();
            toggleItem(item);
          });
        }
        list.appendChild(li);
      }
      if (note) {
        status.textContent = note;
        status.hidden = false;
      }
    };

    const selectItem = (item) => {
      selected = [{ id: item.id, label: item.label }];
      syncFromSelection();
      justClosedAt = Date.now();
      closeMenu();
      input.focus();
    };

    const toggleItem = (item) => {
      if (selected.some((v) => v.id === item.id)) {
        selected = selected.filter((v) => v.id !== item.id);
      } else {
        selected = [...selected, { id: item.id, label: item.label }];
      }
      syncFromSelection();
      renderList(options, null);
    };

    // ---- menu open/close --------------------------------------------------

    const openMenu = () => {
      menuOpen = true;
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (openButton) {
        openButton.setAttribute("aria-expanded", "true");
      }
      if (searchInput) {
        // Single-select: the menu carries its own search field. Start from
        // an EMPTY query so the full (hydrated) list shows; the previous
        // display value must not pre-filter the options.
        searchInput.value = "";
      }
      renderList(options, null);
      if (searchInput) {
        if (allowNew) {
          // Free-typing control: the primary entry field IS the
          // search/entry field. Keep focus there so physical keystrokes
          // reach its input handler, which updates the candidate value,
          // the managed hidden form field, and the bounded server search.
          input.focus();
        } else {
          // Known-only picker: the popup search field is the entry point.
          searchInput.focus();
        }
      }
      if (selected.length > 0) {
        // Re-hydrate the selection(s) that may live outside the initial
        // batch (single, or every multi chip; 195-a).
        runSearch("", { selectedIds: selected.map((v) => v.id) });
      }
    };

    const closeMenu = () => {
      menuOpen = false;
      menu.hidden = true;
      justClosedAt = Date.now();
      input.setAttribute("aria-expanded", "false");
      if (openButton) {
        openButton.setAttribute("aria-expanded", "false");
      }
      activeIndex = -1;
      highlightActive();
    };

    const highlightActive = () => {
      const items = Array.from(list.querySelectorAll(".rc-option"));
      items.forEach((li, i) => {
        li.classList.toggle("rc-option-active", i === activeIndex);
        li.setAttribute("aria-selected", i === activeIndex ? "true" : "false");
      });
      if (activeIndex >= 0 && items[activeIndex]) {
        items[activeIndex].scrollIntoView({ block: "nearest" });
      }
    };

    // ---- server search ------------------------------------------------------

    const depValues = () => {
      if (!dependsOn) {
        return null;
      }
      const root = rc.closest("form") || rc;
      const dep = root.querySelector(`[data-rc-id="${CSS.escape(dependsOn)}"]`);
      if (!dep) {
        return null;
      }
      // 195-a: return ALL managed values of the parent control (multi
      // parents submit one hidden field per accepted value) so the
      // dependent lookup keeps the full parent scope.
      const values = Array.from(dep.querySelectorAll(".rc-value"))
        .map((el) => el.value)
        .filter((value) => value !== "");
      return values.length > 0 ? values : null;
    };

    const runSearch = (query, { selectedIds = [] } = {}) => {
      const q = String(query == null ? "" : query).slice(0, MAX_QUERY_LENGTH);
      status.textContent = "Searching…";
      status.hidden = false;
      const params = new URLSearchParams();
      params.set("kind", kind);
      if (q) {
        params.set("q", q);
      }
      for (const id of selectedIds) {
        params.append("selected", id);
      }
      const dep = depValues();
      if (dep) {
        // 195-a: every accepted parent value is sent as a repeatable
        // scope parameter; the server applies its own explicit
        // per-value/count bounds, so a valid selection is never
        // truncated client-side.
        for (const value of dep) {
          params.append(dependsParam, value);
        }
      }
      const seq = ++searchSeq;
      if (searchInFlight) {
        searchInFlight.abort();
      }
      searchInFlight = new AbortController();
      fetch(`${LOOKUP_PATH}?${params.toString()}`, {
        headers: { Accept: "application/json" },
        signal: searchInFlight.signal,
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`status ${response.status}`);
          }
          return response.json();
        })
        .then((payload) => {
          if (seq !== searchSeq) {
            return;
          }
          const items = Array.isArray(payload.choices) ? payload.choices : [];
          options = items.map((item) => ({
            id: String(item.id),
            label: String(item.label),
            sub: item.sub ? String(item.sub) : "",
          }));
          // 195-a: label-only refresh. Selected entries the server
          // re-hydrated (selections older than the initial batch, or a
          // parent-scoped refetch) get their authoritative labels. IDs
          // and order are untouched; unknown/manual values keep their
          // fallback label. Value did not change: no hidden-field
          // rewrite, no rc-change, no input text/focus/caret change.
          const labelById = new Map();
          for (const item of items) {
            labelById.set(String(item.id), String(item.label));
          }
          let labelsChanged = false;
          for (const value of selected) {
            const next = labelById.get(value.id);
            if (next && next !== value.label) {
              value.label = next;
              labelsChanged = true;
            }
          }
          if (labelsChanged) {
            renderChips();
          }
          if (menuOpen) {
            renderList(options, items.length === 0 ? "No matching records." : null);
          }
        })
        .catch(() => {
          if (seq !== searchSeq) {
            return;
          }
          status.textContent = "Search unavailable — retry or type a known value.";
          status.hidden = false;
        });
    };

    const scheduleSearch = (query) => {
      if (searchTimer) {
        clearTimeout(searchTimer);
      }
      searchTimer = setTimeout(() => runSearch(query, { selectedIds: selected.map((v) => v.id) }), SEARCH_DEBOUNCE_MS);
    };

    // ---- events --------------------------------------------------------------

    openButton?.addEventListener("click", () => {
      if (menuOpen) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    clearButton?.addEventListener("click", () => {
      // Clearing must also drop stale SEARCH state: a pending debounce
      // or an in-flight response for the old query (whose plain-value
      // selected-preservation can carry the old typed text back as an
      // option) must not reintroduce it after the value is cleared.
      if (searchTimer) {
        clearTimeout(searchTimer);
        searchTimer = null;
      }
      searchSeq += 1; // invalidate any in-flight response
      if (searchInFlight) {
        searchInFlight.abort();
        searchInFlight = null;
      }
      // The option set must come back scoped to the CURRENT context:
      // - dependent controls: the initial batch carries the parent
      //   scope from page load (or none), which may no longer be the
      //   current parent, so re-fetch the latest choices with the
      //   current dependency value and never render the stale initial
      //   (unscoped/old-scope) set while that lookup is in flight;
      // - plain controls: the server-rendered latest batch again,
      //   never the stale filtered set from the cleared query.
      if (dependsOn) {
        options = [];
        if (menuOpen) {
          renderList([], "Loading choices…");
        }
        runSearch("", { selectedIds: [] });
      } else {
        options = readOptions(rc);
        if (menuOpen) {
          renderList(options, null);
        }
      }
      selected = [];
      input.value = "";
      syncFromSelection();
      input.focus();
    });

    input.addEventListener("focus", () => {
      // Ignore the programmatic focus that follows a selection or Escape
      // so the menu does not immediately re-open on its own.
      if (!menuOpen && Date.now() - justClosedAt > 150) {
        openMenu();
      }
    });
    // A click is an explicit user action (and the only re-open path for an
    // already-focused input), so it always opens the menu.
    input.addEventListener("click", () => {
      if (!menuOpen) {
        openMenu();
      }
    });

    input.addEventListener("blur", () => {
      // Close on focus-out unless the focus moved somewhere INSIDE this
      // whole control (the primary entry field, the open/clear buttons,
      // or the menu). Checking only the menu would close the menu the
      // instant an open/click moves focus to the open button, which is a
      // sibling of the menu, not a child of it.
      setTimeout(() => {
        if (menuOpen && !rc.contains(document.activeElement)) {
          closeMenu();
        }
      }, 0);
    });

    input.addEventListener("input", () => {
      if (!menuOpen) {
        openMenu();
      }
      const text = input.value.trim();
      const local = text
        ? options.filter(
            (item) =>
              item.label.toLowerCase().includes(text.toLowerCase()) ||
              (item.sub || "").toLowerCase().includes(text.toLowerCase())
          )
        : options;
      renderList(local, null);
      if (!multi && allowNew) {
        // Typed text is the candidate value, preserved EXACTLY as typed:
        // model IDs, route aliases, and other known values may be opaque
        // and case-sensitive, so implicit label normalization must not
        // rewrite the entry. Only explicit option selection (mouse or
        // keyboard on a rendered option) maps a display label to its
        // stored id. The server validation decides on submit.
        selected = text ? [{ id: text, label: text, typed: true }] : [];
        // 195-a: re-render the visible chip from the typed candidate via
        // renderSelected (it rebuilds .rc-selected and the managed hidden
        // field only) so a typed replacement updates the chip WITHOUT
        // touching the input text/focus/cursor — syncFromSelection would
        // blank the input on every keystroke.
        renderSelected();
        // The typed candidate changed the value: the clear affordance
        // must track it (refreshClearVisibility only reads selected and
        // input.value, so focus/cursor/verbatim text are untouched).
        refreshClearVisibility();
      }
      scheduleSearch(text);
    });

    const onMenuKeydown = (event) => {
      const items = Array.from(list.querySelectorAll(".rc-option"));
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!menuOpen) {
          openMenu();
          return;
        }
        if (items.length === 0) {
          return;
        }
        if (event.key === "ArrowDown") {
          activeIndex = activeIndex + 1 >= items.length ? 0 : activeIndex + 1;
        } else {
          activeIndex = activeIndex - 1 < 0 ? items.length - 1 : activeIndex - 1;
        }
        highlightActive();
      } else if (event.key === "Home" && menuOpen) {
        event.preventDefault();
        activeIndex = items.length ? 0 : -1;
        highlightActive();
      } else if (event.key === "End" && menuOpen) {
        event.preventDefault();
        activeIndex = items.length ? items.length - 1 : -1;
        highlightActive();
      } else if (event.key === "Enter" && event.shiftKey === false) {
        if (menuOpen && activeIndex >= 0 && items[activeIndex]) {
          // The option index addresses the CURRENTLY RENDERED list (which
          // may be filtered), never the full option pool.
          event.preventDefault();
          const item = rendered[Number(items[activeIndex].dataset.optionIndex || "0")];
          if (item) {
            if (multi) {
              toggleItem(item);
            } else {
              selectItem(item);
            }
          }
        } else if (multi && allowNew) {
          // Typed new value: the textarea text IS the search text here.
          const text = input.value.trim();
          if (text) {
            event.preventDefault();
            if (!selected.some((v) => v.id === text)) {
              selected = [...selected, { id: text, label: text, typed: true }];
              input.value = "";
              syncFromSelection();
            }
          }
        }
      } else if (event.key === "Escape") {
        justClosedAt = Date.now();
        closeMenu();
        input.focus();
      } else if (event.key === "Backspace" && multi && input.value === "" && selected.length > 0) {
        // Multi: the focused control is the textarea itself, so its value
        // is the actual search text (empty => remove last chip).
        event.preventDefault();
        selected = selected.slice(0, -1);
        syncFromSelection();
      }
    };

    input.addEventListener("keydown", onMenuKeydown);
    if (searchInput) {
      searchInput.addEventListener("keydown", onMenuKeydown);
    }

    searchInput?.addEventListener("input", () => {
      const text = searchInput.value.trim();
      renderList(text ? options.filter((item) =>
        item.label.toLowerCase().includes(text.toLowerCase()) ||
        (item.sub || "").toLowerCase().includes(text.toLowerCase())
      ) : options, null);
      scheduleSearch(text);
    });

    document.addEventListener("click", (event) => {
      if (menuOpen && !rc.contains(event.target)) {
        closeMenu();
      }
    });

    // ---- dependent controls ----------------------------------------------------

    if (dependsOn) {
      const root = rc.closest("form") || rc;
      const onDepChange = () => {
        if (clearOnDep) {
          selected = [];
          input.value = "";
          renderSelected();
        }
        options = [];
        runSearch("", { selectedIds: [] });
      };
      const dep = root.querySelector(`[data-rc-id="${CSS.escape(dependsOn)}"]`);
      if (dep) {
        dep.addEventListener("rc-change", onDepChange);
      }
    }

    // ---- initial state (initializing flag flips AFTER this block) -----------

    if (multi) {
      // The no-JS field is a single newline-list text input; parse its
      // prefilled value into the managed chip list.
      for (const part of input.value.split("\n").map((v) => v.trim()).filter(Boolean)) {
        const known = options.find((item) => item.id === part);
        selected.push({ id: part, label: known ? known.label : part });
      }
      input.value = "";
      renderSelected();
      refreshClearVisibility();
    } else {
      const initialId = rc.dataset.selectedId || input.value.trim();
      const initialLabel = rc.dataset.selectedLabel || input.value.trim();
      if (initialId) {
        const known = options.find((item) => item.id === initialId);
        selected = [{ id: initialId, label: initialLabel || (known ? known.label : initialId) }];
      }
      syncFromSelection();
      refreshClearVisibility();
    }

    // Value-change events are announced from this point on.
    initializing = false;
  };

  const initAll = () => {
    let index = 0;
    for (const rc of document.querySelectorAll("[data-rc]")) {
      if (!rc.dataset.rcId) {
        rc.dataset.rcId = String(++index);
      }
      initControl(rc);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
