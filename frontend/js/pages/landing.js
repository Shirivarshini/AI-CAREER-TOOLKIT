/**
 * landing.js
 * The landing page is primarily static marketing content. This module
 * only wires up the small bits of interactivity: guest-mode CTA click
 * tracking hook (no-op placeholder) and animated hero score readouts
 * are pure CSS. Nothing here talks to the backend.
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    // Smooth-scroll to sections for in-page anchor links (progressive enhancement;
    // CSS scroll-behavior already covers most browsers).
    DOM.qsa('a[href^="#"]').forEach((link) => {
      link.addEventListener("click", (e) => {
        const id = link.getAttribute("href").slice(1);
        const target = document.getElementById(id);
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
      });
    });
  });
})();
