/**
 * gauge.js
 * Renders the "score dial" — a radial gauge with a mono-font readout.
 * This is the one visual signature reused across Resume/GitHub/LinkedIn/
 * Skill-Gap results so a score always looks and behaves the same way.
 *
 * Usage:
 *   Gauge.render(containerEl, { score: 78, max: 100, label: 'ATS Score', size: 160 });
 *   Gauge.update(containerEl, 84); // animate to a new score later
 */
window.Gauge = (() => {
  const RADIUS_RATIO = 0.4;

  function bandFor(score, max) {
    const pct = (score / max) * 100;
    if (pct >= 75) return { color: "var(--status-good)", band: "good" };
    if (pct >= 45) return { color: "var(--status-warn)", band: "warn" };
    return { color: "var(--status-bad)", band: "bad" };
  }

  function render(container, { score = 0, max = 100, label = "", size = 160 } = {}) {
    const r = size * RADIUS_RATIO;
    const cx = size / 2;
    const cy = size / 2;
    const circumference = 2 * Math.PI * r;
    const { color, band } = bandFor(score, max);

    container.classList.add("score-dial");
    container.dataset.max = max;
    container.innerHTML = `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img"
           aria-label="${DOM.escapeHTML(label)}: ${score} out of ${max}">
        <circle class="score-dial__track" cx="${cx}" cy="${cy}" r="${r}"></circle>
        <circle class="score-dial__fill" cx="${cx}" cy="${cy}" r="${r}"
                stroke="${color}"
                stroke-dasharray="${circumference}"
                stroke-dashoffset="${circumference}"></circle>
      </svg>
      <div class="score-dial__readout">
        <span class="score-dial__value">${Math.round(score)}</span>
        <span class="score-dial__max">/ ${max}</span>
        ${label ? `<span class="score-dial__label">${DOM.escapeHTML(label)}</span>` : ""}
      </div>
    `;

    // Animate on next frame so the transition actually runs.
    requestAnimationFrame(() => {
      const fill = container.querySelector(".score-dial__fill");
      const offset = circumference - (score / max) * circumference;
      requestAnimationFrame(() => {
        fill.style.strokeDashoffset = String(offset);
      });
    });

    return band;
  }

  function update(container, score) {
    const max = Number(container.dataset.max || 100);
    const svg = container.querySelector("svg");
    const size = Number(svg.getAttribute("width"));
    render(container, {
      score,
      max,
      label: container.querySelector(".score-dial__label")?.textContent || "",
      size,
    });
  }

  return { render, update, bandFor };
})();
