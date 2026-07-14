/**
 * theme.js
 * Dark-mode toggle. Preference is a non-sensitive UI setting, so it is
 * the one thing this app deliberately persists in localStorage.
 */
window.Theme = (() => {
  const KEY = "theme"; // stored under act:theme via Storage_

  function apply(mode) {
    document.documentElement.setAttribute("data-theme", mode);
    DOM.qsa("[data-theme-toggle]").forEach((btn) => {
      btn.setAttribute("aria-pressed", String(mode === "dark"));
    });
  }

  function init() {
    const prefersDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    const saved = Storage_.get(KEY, prefersDark ? "dark" : "light");
    apply(saved);

    DOM.qsa("[data-theme-toggle]").forEach((btn) => {
      btn.addEventListener("click", toggle);
    });
  }

  function toggle() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    Storage_.set(KEY, next);
    apply(next);
  }

  return { init, toggle, apply };
})();

document.addEventListener("DOMContentLoaded", Theme.init);
