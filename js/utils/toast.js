/**
 * toast.js
 * Accessible toast notifications. Injects a single live region into the
 * page (once) and renders dismissible, auto-expiring toasts into it.
 */
window.Toast = (() => {
  let region = null;

  function ensureRegion() {
    if (region) return region;
    region = DOM.el("div", {
      class: "toast-region",
      role: "status",
      "aria-live": "polite",
      "aria-atomic": "false",
    });
    document.body.appendChild(region);
    return region;
  }

  const ICONS = {
    success:
      '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M16.7 5.3 8.3 13.7 3.7 9.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    error:
      '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 6v5m0 3h.01M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    warning:
      '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 7.5v4M10 14.5h.01M8.6 2.9 1.8 15a1.6 1.6 0 0 0 1.4 2.4h13.6a1.6 1.6 0 0 0 1.4-2.4L11.4 2.9a1.6 1.6 0 0 0-2.8 0Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    info:
      '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 9v5m0-8h.01M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };

  const TITLES = {
    success: "Success",
    error: "Something went wrong",
    warning: "Heads up",
    info: "Note",
  };

  function show(message, { type = "info", title, duration } = {}) {
    const host = ensureRegion();
    const life = duration ?? window.APP_CONFIG?.TOAST_DURATION_MS ?? 5000;

    const toastEl = DOM.el("div", {
      class: `toast toast-${type}`,
      role: type === "error" ? "alert" : "status",
    });

    toastEl.innerHTML = `
      <span class="toast__icon">${ICONS[type] || ICONS.info}</span>
      <div class="toast__body">
        <div class="toast__title">${DOM.escapeHTML(title || TITLES[type])}</div>
        <div class="toast__msg">${DOM.escapeHTML(message)}</div>
      </div>
    `;

    const closeBtn = DOM.el(
      "button",
      {
        class: "toast__close",
        type: "button",
        "aria-label": "Dismiss notification",
        onClick: () => dismiss(toastEl),
      },
      []
    );
    closeBtn.innerHTML =
      '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M1 1l12 12M13 1 1 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
    toastEl.appendChild(closeBtn);

    host.appendChild(toastEl);

    const timer = setTimeout(() => dismiss(toastEl), life);
    toastEl._timer = timer;

    return toastEl;
  }

  function dismiss(toastEl) {
    if (!toastEl || toastEl.classList.contains("is-leaving")) return;
    clearTimeout(toastEl._timer);
    toastEl.classList.add("is-leaving");
    toastEl.addEventListener(
      "animationend",
      () => toastEl.remove(),
      { once: true }
    );
  }

  return {
    show,
    success: (msg, opts) => show(msg, { ...opts, type: "success" }),
    error: (msg, opts) => show(msg, { ...opts, type: "error" }),
    warning: (msg, opts) => show(msg, { ...opts, type: "warning" }),
    info: (msg, opts) => show(msg, { ...opts, type: "info" }),
  };
})();
