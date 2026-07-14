/**
 * charts.js
 * Thin wrapper around Chart.js so every chart in the app shares the same
 * theme (colors pulled from CSS custom properties) and defaults. No data
 * transformation/business logic lives here — charts render exactly what
 * the backend returns.
 */
window.Charts = (() => {
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function palette() {
    return [
      cssVar("--signal-500"),
      cssVar("--status-good"),
      cssVar("--status-warn"),
      cssVar("--status-bad"),
      "#8FA4FF",
      "#A688E8",
      "#5FB8C9",
      "#D98A5F",
    ];
  }

  const registry = new Map();

  function destroy(canvasId) {
    const existing = registry.get(canvasId);
    if (existing) {
      existing.destroy();
      registry.delete(canvasId);
    }
  }

  /** Doughnut chart for GitHub language distribution. data: [{label, value}] */
  function languageDonut(canvasId, data) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx || typeof Chart === "undefined") return null;
    const colors = palette();
    const chart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: data.map((d) => d.label),
        datasets: [
          {
            data: data.map((d) => d.value),
            backgroundColor: data.map((_, i) => colors[i % colors.length]),
            borderWidth: 2,
            borderColor: cssVar("--surface"),
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (item) => ` ${item.label}: ${item.formattedValue}%`,
            },
          },
        },
      },
    });
    registry.set(canvasId, chart);
    return chart;
  }

  /** Line chart for score-history trend. series: [{date, score}] */
  function scoreTrendLine(canvasId, series) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx || typeof Chart === "undefined") return null;
    const accent = cssVar("--signal-500");
    const chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: series.map((s) => DOM.formatDate(s.date)),
        datasets: [
          {
            label: "Score",
            data: series.map((s) => s.score),
            borderColor: accent,
            backgroundColor: `color-mix(in srgb, ${accent} 15%, transparent)`,
            fill: true,
            tension: 0.35,
            pointRadius: 4,
            pointBackgroundColor: accent,
            pointBorderColor: cssVar("--surface"),
            pointBorderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            min: 0,
            max: 100,
            grid: { color: cssVar("--line") },
            ticks: { color: cssVar("--ink-500"), font: { family: "IBM Plex Mono" } },
          },
          x: {
            grid: { display: false },
            ticks: { color: cssVar("--ink-500") },
          },
        },
        plugins: { legend: { display: false } },
      },
    });
    registry.set(canvasId, chart);
    return chart;
  }

  /** Horizontal bar chart for score category breakdown. data: [{label, score, max}] */
  function breakdownBar(canvasId, data) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx || typeof Chart === "undefined") return null;
    const chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.map((d) => d.label),
        datasets: [
          {
            data: data.map((d) => d.score),
            backgroundColor: cssVar("--signal-500"),
            borderRadius: 6,
            maxBarThickness: 22,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { max: 100, grid: { color: cssVar("--line") }, ticks: { color: cssVar("--ink-500") } },
          y: { grid: { display: false }, ticks: { color: cssVar("--ink-900") } },
        },
        plugins: { legend: { display: false } },
      },
    });
    registry.set(canvasId, chart);
    return chart;
  }

  return { languageDonut, scoreTrendLine, breakdownBar, palette, destroy };
})();
