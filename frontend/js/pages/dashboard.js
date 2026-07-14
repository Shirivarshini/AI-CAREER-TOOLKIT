/**
 * dashboard.js
 * GET /api/history and render a summary + trend chart + history table.
 * If the user isn't authenticated, the backend returns 401 and we show a
 * guest-mode empty state instead of a broken dashboard.
 *
 * Expected response shape (backend contract):
 * {
 *   stats: { total_analyses, avg_score, best_score, return_visits_7d },
 *   trend: [{ date, score }],
 *   history: [{ id, tool: 'resume'|'github'|'linkedin'|'skillgap', label, score, created_at }]
 * }
 */
(function () {
  document.addEventListener("DOMContentLoaded", async () => {
    const statsRow = DOM.qs("#dashboard-stats");
    const trendCard = DOM.qs("#trend-card");
    const historyBody = DOM.qs("#history-body");
    const historyEmpty = DOM.qs("#history-empty");
    const guestState = DOM.qs("#dashboard-guest");
    const contentEl = DOM.qs("#dashboard-content");

    try {
      const data = await Api.get(window.APP_CONFIG.ENDPOINTS.HISTORY);
      renderDashboard(data);
    } catch (err) {
      if (err instanceof Api.ApiError && err.status === 401) {
        showGuestState();
      } else {
        Toast.error(err.message || "Couldn't load your dashboard.");
        showGuestState(true);
      }
    }

    function showGuestState(isError = false) {
      contentEl.hidden = true;
      guestState.hidden = false;
      if (isError) {
        DOM.qs("#dashboard-guest-title", guestState).textContent = "Couldn't load your history";
        DOM.qs("#dashboard-guest-copy", guestState).textContent =
          "Something went wrong on our end. Please try again in a moment.";
      }
    }

    function renderDashboard(data) {
      guestState.hidden = true;
      contentEl.hidden = false;

      const s = data.stats || {};
      statsRow.innerHTML = "";
      [
        { label: "Total analyses", value: s.total_analyses ?? 0 },
        { label: "Average score", value: s.avg_score ?? "\u2013" },
        { label: "Best score", value: s.best_score ?? "\u2013" },
        { label: "Return visits (7d)", value: s.return_visits_7d ?? 0 },
      ].forEach((stat) => {
        statsRow.appendChild(
          (() => {
            const card = DOM.el("div", { class: "card stat-card" });
            card.innerHTML = `
              <div class="stat-card__label">${DOM.escapeHTML(stat.label)}</div>
              <div class="stat-card__value">${DOM.escapeHTML(String(stat.value))}</div>
            `;
            return card;
          })()
        );
      });

      const trend = data.trend || [];
      if (trend.length) {
        trendCard.hidden = false;
        Charts.scoreTrendLine("trend-chart", trend);
      } else {
        trendCard.hidden = true;
      }

      const history = data.history || [];
      historyBody.innerHTML = "";
      if (!history.length) {
        historyEmpty.hidden = false;
      } else {
        historyEmpty.hidden = true;
        const toolLabels = {
          resume: "Resume Analyzer",
          github: "GitHub Analysis",
          linkedin: "LinkedIn Optimizer",
          skillgap: "Skill Gap",
        };
        history.forEach((row) => {
          const tr = DOM.el("tr");
          tr.innerHTML = `
            <td>${DOM.escapeHTML(toolLabels[row.tool] || row.tool)}</td>
            <td>${DOM.escapeHTML(row.label || "\u2014")}</td>
            <td class="text-mono">${row.score ?? "\u2013"}</td>
            <td class="text-muted">${DOM.formatDate(row.created_at)}</td>
            <td><a href="#" data-report-id="${DOM.escapeHTML(String(row.id))}" class="btn btn-ghost btn-sm">Download PDF</a></td>
          `;
          historyBody.appendChild(tr);
        });

        DOM.qsa("[data-report-id]", historyBody).forEach((link) => {
          link.addEventListener("click", async (e) => {
            e.preventDefault();
            const id = link.dataset.reportId;
            try {
              const blob = await Api.getBlob(`${window.APP_CONFIG.ENDPOINTS.REPORT}/${id}`);
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `career-toolkit-report-${id}.pdf`;
              a.click();
              URL.revokeObjectURL(url);
            } catch (err) {
              Toast.error(err.message || "Couldn't download that report.");
            }
          });
        });
      }
    }
  });
})();
