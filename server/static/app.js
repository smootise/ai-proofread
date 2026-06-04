/**
 * Proofreader V2 — minimal vanilla JS.
 *
 * The only runtime JS in V2: wire up delete-confirmation on any
 * .js-confirm-delete buttons that were not already handled by the inline
 * onclick attribute in the template. The confirm page (GET /delete) remains
 * the authoritative no-JS fallback — deletion is never one-click.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // Belt-and-suspenders: any button/link with data-confirm gets a
    // JS confirm() dialog. Templates may also use inline onclick=
    // for the same purpose; this catches any missed cases.
    document.querySelectorAll("[data-confirm]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        var msg = el.dataset.confirm || "Are you sure?";
        if (!window.confirm(msg)) {
          e.preventDefault();
        }
      });
    });
  });
})();
