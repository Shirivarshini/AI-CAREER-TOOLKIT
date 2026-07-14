/**
 * chips.js
 * Renders lists of chips (matched/missing skills, keywords) into a
 * container. Presentation only — matching logic comes from the API.
 */
window.Chips = (() => {
  /**
   * @param {HTMLElement} container
   * @param {string[]} items
   * @param {'matched'|'missing'|'nice'|'neutral'} variant
   * @param {object} [opts] - { emptyText }
   */
  function render(container, items, variant = "neutral", opts = {}) {
    DOM.clear(container);
    if (!items || items.length === 0) {
      container.appendChild(
        DOM.el("p", { class: "text-muted", style: "font-size: var(--fs-sm); margin: 0;" }, [
          opts.emptyText || "Nothing here yet.",
        ])
      );
      return;
    }
    items.forEach((item) => {
      container.appendChild(DOM.el("span", { class: `chip chip-${variant}` }, [item]));
    });
  }

  return { render };
})();
