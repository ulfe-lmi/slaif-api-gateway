/* SLAIF admin shared header: compact menu behavior (188-a).
 *
 * Presentational only. Without JavaScript the header navigation remains a
 * plain wrapping list (the .nav-ready class below is never added). With
 * JavaScript, at the narrow breakpoint the nav collapses behind a Menu
 * button:
 *   - the button is keyboard-operable and exposes the expanded state via
 *     aria-expanded;
 *   - Escape closes the menu and returns focus to the button;
 *   - choosing a link closes the menu (the page then navigates).
 */
(function () {
  "use strict";

  var header = document.querySelector(".admin-header");
  if (!header) {
    return;
  }

  var toggle = header.querySelector("[data-nav-toggle]");
  var nav = document.getElementById("admin-nav");
  if (!toggle || !nav) {
    return;
  }

  header.classList.add("nav-ready");
  toggle.hidden = false;

  function isOpen() {
    return header.classList.contains("is-open");
  }

  function setOpen(open) {
    header.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  toggle.addEventListener("click", function () {
    setOpen(!isOpen());
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isOpen()) {
      event.preventDefault();
      setOpen(false);
      toggle.focus();
    }
  });

  nav.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.closest && target.closest("a")) {
      setOpen(false);
    }
  });

  setOpen(false);
})();
