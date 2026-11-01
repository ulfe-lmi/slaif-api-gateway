/**
 * SLAIF admin table sorting — shared fixed source.
 *
 * Dependency-free, display-only row sorting for tables marked
 * `data-sortable`. This exact source is also embedded verbatim into the
 * generated catalog report HTML (see services/catalog_refresh/rendering.py
 * and services/provider_catalog_proposal.py), so the report stays a single
 * self-contained file with no network, no eval, and no dynamic code.
 *
 * Behavior contract:
 * - First header click sorts that column ascending; the next click on the
 *   same header reverses to descending. Clicking a different column selects
 *   that column ascending. The initial business ordering is kept until the
 *   first click.
 * - Header controls are real focusable text hyperlinks (<a href="#ts-sort">,
 *   a safe local fragment target: no network, no navigation because the
 *   click handler always prevents the default). Native link activation is
 *   Enter; the direction is announced through <th aria-sort> and a visible
 *   marker. A subtle neutral sortability indicator is reserved BEFORE the
 *   first click (no header layout jump) and is replaced by the specific
 *   up/down marker after a column is sorted.
 * - Column types via <th data-sort-type="...">:
 *     text (default)  case-insensitive natural-order text (2 < 10)
 *     number          genuine numeric comparison; typed plain-decimal keys
 *                     inside the DB range (Numeric(18,9) money, integer
 *                     counts) compare EXACTLY via a scaled-BigInt
 *                     coefficient; decorated/exponent/out-of-range input
 *                     falls back to bounded Number() comparison
 *     money           numeric; currency letters/symbols/commas ignored
 *     percent         numeric; trailing % ignored
 *     date|datetime   ISO timestamp comparison, text fallback
 *     boolean         true/active/yes before false/suspended/no
 * - Typed raw sort keys: <td data-sort-value="raw"> overrides displayed
 *   text where decorated or composite text would mislead (Usage = request
 *   count, Limits = request limit, Validity = valid_from, ...). An empty or
 *   missing-marker raw key sorts as "missing".
 * - Missing values ("", "—", "N/A", "Unknown", "Unlimited", "Not set", ...)
 *   always sort last in BOTH directions (consistent explicit placement).
 * - Ties are stable: original row order is the final tie-breaker.
 * - Rows marked <tr data-no-sort> (empty-state, summary, footer) never
 *   move; <tr data-sort-group> moves together with its following
 *   consecutive <tr data-sort-group-continue> rows (multi-row units).
 * - Structural first-position ordinal column (194-a): a <th data-ordinal>
 *   in the leaf header row is PLAIN (no sort link, no aria-sort, no
 *   indicator). Its body cells carry the displayed logical row numbers
 *   1..N server-rendered for the initial business order (SSR/no-JS
 *   coherent); after a sort this script renumbers ONLY the positional
 *   values of the moved unit head cells (continuation cells stay empty),
 *   never changing any data cell, ID, URL, or form state.
 * - Grouped (multi-row) theads (194-a): the initializer reads only the LAST
 *   thead row (the leaf header row). The admin tables author that leaf row
 *   as one complete header cell per body column, so the leaf position
 *   equals the body position. Group and ordinal headings stay plain.
 * - Sorting only reorders the existing <tr> nodes of the DISPLAYED result
 *   set (existing filters/row limits stay in effect). Forms, inputs,
 *   checkboxes, links, and review selections move with their rows and keep
 *   their state. Each table is sorted independently.
 * - No network access, no eval/Function, no dynamic code generation, no
 *   inline event-handler attributes, no mutation of cell content.
 */
(() => {
  "use strict";

  const MISSING_MARKERS = new Set([
    "",
    "-",
    "\u2013",
    "\u2014",
    "n/a",
    "na",
    "none",
    "unknown",
    "unlimited",
    "not set",
    "no start",
    "no end",
    "no data",
  ]);
  const TRUE_WORDS = new Set(["true", "yes", "active", "enabled", "open", "1"]);
  const FALSE_WORDS = new Set([
    "false",
    "no",
    "inactive",
    "suspended",
    "disabled",
    "closed",
    "revoked",
    "0",
  ]);

  const normalize = (value) => String(value == null ? "" : value).replace(/\s+/g, " ").trim();

  const isMissing = (value) => {
    const v = normalize(value);
    if (v === "") {
      return true;
    }
    return MISSING_MARKERS.has(v.toLowerCase());
  };

  const numericValue = (text) => {
    const cleaned = String(text).replace(/,/g, "").replace(/[%\s]/g, "");
    const match = cleaned.match(/^[^\d-]*(-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)/);
    if (!match) {
      return null;
    }
    const parsed = Number(match[1]);
    return Number.isFinite(parsed) ? parsed : null;
  };

  /**
   * Bounded exact decimal comparison for TYPED raw numeric keys only.
   *
   * The database bounds the values that can appear: money/price columns are
   * Numeric(18, 9) and count columns are plain integers (BigInteger). Within
   * that bounded range a scaled-BigInt coefficient (9 fixed fraction
   * digits) compares EXACTLY, so distinct allowed values never collapse to
   * a tie the way Number() would (e.g. 999999999.000000001 vs
   * 999999999.000000002, or 9007199254740992 vs 9007199254740993).
   *
   * Inputs outside the bound (exponent notation, more than 9 fraction
   * digits, more than 18 significant digits for decimals, more than
   * 19 digits for plain integers) return null and the caller falls back
   * to the bounded Number() comparison. This is deliberately a
   * bounded key comparison, not a general arithmetic framework: no
   * formatting, no rounding, no operator parsing.
   */
  const MAX_FRACTION_DIGITS = 9;
  const MAX_TOTAL_DIGITS = 18;
  const SCALE_9 = 10n ** BigInt(MAX_FRACTION_DIGITS);

  const exactCoefficient = (text) => {
    const t = String(text).trim();
    if (!/^[+-]?\d+(\.\d+)?$/.test(t)) {
      return null;
    }
    const neg = t.startsWith("-");
    const body = t.startsWith("-") || t.startsWith("+") ? t.slice(1) : t;
    const dot = body.indexOf(".");
    const intPart = dot === -1 ? body : body.slice(0, dot);
    const fracPart = dot === -1 ? "" : body.slice(dot + 1);
    const trimmedInt = intPart.replace(/^0+(?=\d)/, "") || "0";
    // Decimals stay within the Numeric(18, 9) bound (18 significant digits);
    // plain integers additionally cover the full signed 64-bit range
    // (19 digits, e.g. 9223372036854775807) used by count columns.
    const maxDigits = fracPart.length === 0 ? 19 : MAX_TOTAL_DIGITS;
    if (trimmedInt.length + fracPart.length > maxDigits) {
      return null;
    }
    if (fracPart.length > MAX_FRACTION_DIGITS) {
      return null;
    }
    const magnitude =
      BigInt(trimmedInt) * SCALE_9 + BigInt(fracPart.padEnd(MAX_FRACTION_DIGITS, "0"));
    return neg && magnitude !== 0n ? -magnitude : magnitude;
  };

  const naturalCompare = (a, b) => {
    const al = String(a).toLowerCase();
    const bl = String(b).toLowerCase();
    if (al === bl) {
      return 0;
    }
    const ap = al.split(/(\d+)/);
    const bp = bl.split(/(\d+)/);
    const n = Math.min(ap.length, bp.length);
    for (let i = 0; i < n; i += 1) {
      const x = ap[i];
      const y = bp[i];
      if (x === y) {
        continue;
      }
      const xIsNum = /^\d+$/.test(x);
      const yIsNum = /^\d+$/.test(y);
      if (xIsNum && yIsNum) {
        const xn = Number(x);
        const yn = Number(y);
        if (xn !== yn) {
          return xn < yn ? -1 : 1;
        }
        continue;
      }
      return x < y ? -1 : 1;
    }
    if (ap.length !== bp.length) {
      return ap.length < bp.length ? -1 : 1;
    }
    return al < bl ? -1 : 1;
  };

  const booleanValue = (text) => {
    const v = normalize(text).toLowerCase();
    if (TRUE_WORDS.has(v)) {
      return 1;
    }
    if (FALSE_WORDS.has(v)) {
      return 0;
    }
    return null;
  };

  const dateValue = (text) => {
    const v = normalize(text);
    if (v === "") {
      return null;
    }
    const compact = v.includes("T") ? v : v.replace(" ", "T") + (/\d{2}:\d{2}$/.test(v) ? ":00" : "");
    const t = Date.parse(compact);
    return Number.isFinite(t) ? t : null;
  };

  /* Header sort markers: a neutral sortability indicator is shown BEFORE
     the first click (reserved space, no layout jump); after a sort the
     specific up/down marker replaces it. */
  const NEUTRAL_MARKER = "\u2195";
  const ASCENDING_MARKER = "\u2191";
  const DESCENDING_MARKER = "\u2193";
  const SORT_FRAGMENT = "#ts-sort";

  /** Parse one cell into {missing, value} for the given column type. */
  const parseCell = (cell, type) => {
    const rawAttr = cell.hasAttribute("data-sort-value")
      ? cell.getAttribute("data-sort-value")
      : null;
    const source = rawAttr !== null ? rawAttr : cell.textContent;
    if (isMissing(source)) {
      return { missing: true, value: 0 };
    }
    const text = normalize(source);
    switch (type) {
      case "number":
      case "money":
      case "percent": {
        // First try the bounded exact path (plain decimal in DB range).
        const exact = exactCoefficient(text.replace(/[%\s]/g, ""));
        if (exact !== null) {
          return { missing: false, value: { exact: true, n: exact } };
        }
        // Bounded fallback for decorated/exponent/out-of-range input.
        const n = numericValue(text);
        return n === null ? { missing: true, value: 0 } : { missing: false, value: { exact: false, n } };
      }
      case "date":
      case "datetime": {
        const t = dateValue(text);
        return t === null
          ? { missing: false, value: text }
          : { missing: false, value: t };
      }
      case "boolean": {
        const b = booleanValue(text);
        return b === null
          ? { missing: true, value: 0 }
          : { missing: false, value: b };
      }
      case "text":
      default:
        return { missing: false, value: text };
    }
  };

  /** Value comparison for two NON-missing parsed cells (see apply()). */
  const compareParsed = (a, b) => {
    const av = a.value;
    const bv = b.value;
    // Date/boolean parsed values are plain Numbers: direct numeric
    // comparison (pre-epoch and signed values included).
    if (typeof av === "number" && typeof bv === "number") {
      return av < bv ? -1 : av > bv ? 1 : 0;
    }
    if (av && typeof av === "object" && bv && typeof bv === "object") {
      // Both typed numeric. Same representation: exact. Mixed
      // exact/fallback within one column: bounded Number() comparison on
      // the UNSCALED decimal value (the exact coefficient is 10^9-scaled).
      if (av.exact && bv.exact) {
        return av.n < bv.n ? -1 : av.n > bv.n ? 1 : 0;
      }
      const an = av.exact ? Number(av.n) / 1e9 : av.n;
      const bn = bv.exact ? Number(bv.n) / 1e9 : bv.n;
      return an < bn ? -1 : an > bn ? 1 : 0;
    }
    return naturalCompare(String(av), String(bv));
  };

  /**
   * Split tbody rows into sort units. A unit is one row, or a
   * data-sort-group row with its consecutive data-sort-group-continue rows.
   * Rows with data-no-sort are excluded (they never move).
   */
  const collectUnits = (tbody) => {
    const children = Array.from(tbody.children);
    const units = [];
    let order = 0;
    let i = 0;
    while (i < children.length) {
      const row = children[i];
      if (row.tagName !== "TR") {
        i += 1;
        continue;
      }
      if (row.hasAttribute("data-no-sort")) {
        i += 1;
        continue;
      }
      if (row.hasAttribute("data-sort-group-continue")) {
        // Orphan continuation row without a group head: treated as a fixed
        // row (never moves) so malformed markup cannot duplicate itself.
        i += 1;
        continue;
      }
      const rows = [row];
      i += 1;
      while (
        i < children.length &&
        children[i].tagName === "TR" &&
        children[i].hasAttribute("data-sort-group-continue")
      ) {
        rows.push(children[i]);
        i += 1;
      }
      units.push({ rows, order: order++, head: row });
    }
    return { children, units };
  };

  /**
   * Move the sorted units into the non-fixed slots of tbody. Fixed rows
   * (data-no-sort) keep their relative positions; the sortable rows occupy
   * exactly the slots they originally occupied, in the new order.
   */
  const placeUnits = (tbody, children, units, sortedUnits) => {
    const fixedRows = children.filter(
      (row) => row.tagName === "TR" && row.hasAttribute("data-no-sort")
    );
    const unitByHead = new Map(units.map((unit, index) => [unit.head, index]));
    const slots = [];
    let current = [];
    for (const row of children) {
      if (row.tagName !== "TR") {
        continue;
      }
      if (row.hasAttribute("data-no-sort")) {
        slots.push(current);
        current = [];
        continue;
      }
      const unitIndex = unitByHead.get(row);
      if (unitIndex !== undefined) {
        current.push(unitIndex);
      }
      // Rows that are neither fixed nor a unit head (orphan continuation
      // rows) stay exactly where they are.
    }
    slots.push(current);

    let unitCursor = 0;
    for (let slot = 0; slot < slots.length; slot += 1) {
      const count = slots[slot].length;
      const anchor = slot < fixedRows.length ? fixedRows[slot] : null;
      for (let i = 0; i < count; i += 1) {
        const unit = sortedUnits[unitCursor++];
        for (const row of unit.rows) {
          if (anchor) {
            tbody.insertBefore(row, anchor);
          } else {
            tbody.appendChild(row);
          }
        }
      }
    }
  };

  const initTable = (table) => {
    if (table.dataset.tsInitialized === "1") {
      return;
    }
    const thead = table.tHead;
    const tbody = table.tBodies && table.tBodies[0];
    if (!thead || !tbody || thead.rows.length === 0) {
      return;
    }
    table.dataset.tsInitialized = "1";

    const headerRow = thead.rows[thead.rows.length - 1];
    const ths = Array.from(headerRow.cells);
    const state = { col: -1, dir: 1 };

    /* Structural ordinal column (194-a): plain header, never sortable; its
       body cells display 1..N for the displayed logical data rows. -1 when
       the table has no ordinal column. */
    const ordIdx = ths.findIndex((th) => th.hasAttribute("data-ordinal"));

    const updateAria = () => {
      ths.forEach((th, i) => {
        if (i === ordIdx) {
          // Structural ordinal header stays plain: no aria-sort state.
          return;
        }
        const active = i === state.col;
        th.setAttribute(
          "aria-sort",
          active ? (state.dir === 1 ? "ascending" : "descending") : "none"
        );
        const indicator = th.querySelector(".ts-indicator");
        if (indicator) {
          indicator.textContent = active
            ? (state.dir === 1 ? ASCENDING_MARKER : DESCENDING_MARKER)
            : NEUTRAL_MARKER;
        }
      });
    };

    const apply = () => {
      const { children, units } = collectUnits(tbody);
      const th = ths[state.col];
      const type = (th && th.dataset.sortType) || "text";
      const sorted = units
        .map((unit) => {
          const head = unit.rows[0];
          const cell = head.cells[state.col];
          const parsed = cell ? parseCell(cell, type) : { missing: true, value: 0 };
          return { unit, parsed };
        })
        .sort((a, b) => {
          // Missing values always sort last in BOTH directions
          // (consistent explicit placement, never reversed).
          if (a.parsed.missing !== b.parsed.missing) {
            return a.parsed.missing ? 1 : -1;
          }
          if (a.parsed.missing) {
            return a.unit.order - b.unit.order;
          }
          const primary = compareParsed(a.parsed, b.parsed);
          if (primary !== 0) {
            return state.dir === 1 ? primary : -primary;
          }
          // Stable: original row order, independent of direction.
          return a.unit.order - b.unit.order;
        })
        .map((entry) => entry.unit);
      placeUnits(tbody, children, units, sorted);
      // 194-a ordinal bookkeeping: renumber ONLY the positional values of
      // the moved unit head cells (1..N in the new displayed order).
      // Continuation cells stay empty; fixed/no-sort rows are untouched.
      if (ordIdx !== -1) {
        // 214-a opt-in: a paged table supplies the accepted server page
        // offset via data-ordinal-offset so renumbering continues the
        // page ordinal (offset + 1 ...). Tables without the attribute
        // keep the exact pre-214 1..N behavior (default 0).
        const ordinalOffset = Number(table.dataset.ordinalOffset) || 0;
        let n = ordinalOffset;
        for (const unit of sorted) {
          n += 1;
          const cell = unit.head.cells[ordIdx];
          if (cell) {
            cell.textContent = String(n);
          }
        }
      }
      updateAria();
    };

    const selectColumn = (index) => {
      if (state.col === index) {
        state.dir = -state.dir;
      } else {
        state.col = index;
        state.dir = 1;
      }
      apply();
    };

    ths.forEach((th, index) => {
      if (index === ordIdx) {
        // 194-a: the ordinal header is plain (no sort link, no neutral
        // marker); the mockup-verified column order is preserved.
        return;
      }
      const label = normalize(th.textContent);
      // A real focusable text hyperlink (193-a): safe local fragment
      // target, no network. Enter activates it natively; the click
      // handler prevents ordinary navigation (mouse or Enter) and
      // toggles the sort.
      const link = document.createElement("a");
      link.className = "ts-link";
      link.href = SORT_FRAGMENT;
      const labelSpan = document.createElement("span");
      labelSpan.className = "ts-label";
      labelSpan.textContent = label;
      const indicator = document.createElement("span");
      indicator.className = "ts-indicator";
      indicator.setAttribute("aria-hidden", "true");
      indicator.textContent = NEUTRAL_MARKER;
      link.appendChild(labelSpan);
      link.appendChild(indicator);
      link.setAttribute("aria-label", "Sort by " + label);
      th.textContent = "";
      th.appendChild(link);
      th.classList.add("ts-col");
      th.setAttribute("aria-sort", "none");
      link.addEventListener("click", (event) => {
        event.preventDefault();
        selectColumn(index);
      });
    });

    // Initial business ordering is preserved until the first click.
  };

  const initAll = () => {
    for (const table of document.querySelectorAll("table[data-sortable]")) {
      initTable(table);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }

  // Test hook (no behavior change): exposes the pure helpers read-only.
  window.SlaifTableSort = {
    init: initTable,
    parseCell,
    naturalCompare,
    numericValue,
    exactCoefficient,
    isMissing,
  };
})();
