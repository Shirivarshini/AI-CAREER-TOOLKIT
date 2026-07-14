/**
 * navbar.js
 * Shared chrome behavior: marketing nav mobile menu, app-shell sidebar
 * toggle on small screens, and active-link highlighting.
 */
window.Navbar = (() => {
  function markActiveLinks() {
    const current = window.location.pathname.split("/").pop() || "index.html";
    DOM.qsa("[data-nav-link]").forEach((link) => {
      const href = link.getAttribute("href");
      if (href === current) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  function initMobileMenu() {
    const toggle = DOM.qs("[data-nav-toggle]");
    const links = DOM.qs("[data-nav-links]");
    if (!toggle || !links) return;
    toggle.addEventListener("click", () => {
      const isOpen = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });
  }

  function initSidebar() {
    const toggle = DOM.qs("[data-sidebar-toggle]");
    const sidebar = DOM.qs("[data-sidebar]");
    const scrim = DOM.qs("[data-sidebar-scrim]");
    if (!toggle || !sidebar) return;

    const close = () => {
      sidebar.classList.remove("is-open");
      scrim?.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    };
    const open = () => {
      sidebar.classList.add("is-open");
      scrim?.classList.add("is-open");
      toggle.setAttribute("aria-expanded", "true");
    };

    toggle.addEventListener("click", () => {
      sidebar.classList.contains("is-open") ? close() : open();
    });
    scrim?.addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
  }

  function init() {
    markActiveLinks();
    initMobileMenu();
    initSidebar();
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", Navbar.init);
