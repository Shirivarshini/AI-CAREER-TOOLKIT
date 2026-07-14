/**
 * modal.js
 * Minimal accessible modal: focus trap, Escape to close, restores focus
 * to the trigger element on close, closes on overlay click.
 */
window.Modal = (() => {
  let activeOverlay = null;
  let lastFocused = null;

  function open(overlayEl) {
    if (!overlayEl) return;
    lastFocused = document.activeElement;
    overlayEl.classList.add("is-open");
    activeOverlay = overlayEl;
    document.body.style.overflow = "hidden";

    const dialog = overlayEl.querySelector(".modal");
    dialog?.setAttribute("role", "dialog");
    dialog?.setAttribute("aria-modal", "true");

    const focusTarget = overlayEl.querySelector("[autofocus]") || overlayEl.querySelector("input, button, select, textarea");
    focusTarget?.focus();

    document.addEventListener("keydown", handleKeydown);
    overlayEl.addEventListener("click", handleOverlayClick);
  }

  function close() {
    if (!activeOverlay) return;
    activeOverlay.classList.remove("is-open");
    document.body.style.overflow = "";
    document.removeEventListener("keydown", handleKeydown);
    activeOverlay.removeEventListener("click", handleOverlayClick);
    activeOverlay = null;
    lastFocused?.focus();
  }

  function handleOverlayClick(e) {
    if (e.target === activeOverlay) close();
  }

  function handleKeydown(e) {
    if (e.key === "Escape") {
      close();
      return;
    }
    if (e.key === "Tab" && activeOverlay) {
      const focusable = activeOverlay.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  function initTriggers() {
    DOM.qsa("[data-modal-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = document.getElementById(btn.dataset.modalOpen);
        open(target);
      });
    });
    DOM.qsa("[data-modal-close]").forEach((btn) => {
      btn.addEventListener("click", close);
    });
  }

  return { open, close, initTriggers };
})();

document.addEventListener("DOMContentLoaded", Modal.initTriggers);
