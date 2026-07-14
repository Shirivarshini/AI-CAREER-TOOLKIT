/**
 * skill-gap.js
 * Posts a target role to /api/skills/gap and renders matched/missing
 * skills plus a prioritized learning path. The skill taxonomy and diff
 * logic live entirely on the backend.
 *
 * Expected response shape (backend contract):
 * {
 *   target_role: string,
 *   coverage_pct: 0-100,
 *   matched_skills: string[],
 *   missing_skills: string[],
 *   priorities: [{ skill, priority: 'must-have'|'nice-to-have', resource_url, resource_label }]
 * }
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = DOM.qs("#skillgap-form");
    if (!form) return;

    const roleSelect = DOM.qs("#role-select");
    const roleCustom = DOM.qs("#role-custom");
    const submitBtn = DOM.qs("#skillgap-submit");
    const resultsPanel = DOM.qs("#skillgap-results");

    roleSelect?.addEventListener("change", () => {
      const isOther = roleSelect.value === "other";
      roleCustom.hidden = !isOther;
      if (isOther) roleCustom.focus();
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const role =
        roleSelect.value === "other" ? roleCustom.value.trim() : roleSelect.value;
      if (!Validate.required(role)) {
        Toast.warning("Choose or enter a target role.");
        return;
      }

      setLoading(true);
      showLoadingState();
      try {
        const data = await Api.post(window.APP_CONFIG.ENDPOINTS.SKILLS_GAP, {
          target_role: role,
        });
        renderResults(data);
        Toast.success("Skill gap analysis ready.");
      } catch (err) {
        renderError(err);
        Toast.error(err.message || "Couldn't run that analysis.");
      } finally {
        setLoading(false);
      }
    });

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      submitBtn.innerHTML = isLoading
        ? '<span class="spinner" aria-hidden="true"></span> Analyzing\u2026'
        : "Find my skill gaps";
    }

    function showLoadingState() {
      resultsPanel.innerHTML = `
        <div class="loading-block">
          <span class="spinner spinner-lg" aria-hidden="true"></span>
          <p>Comparing your skills against the role taxonomy\u2026</p>
        </div>
      `;
    }

    function renderError(err) {
      resultsPanel.innerHTML = `
        <div class="alert alert-error" role="alert">
          <svg class="alert__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 6v5m0 3h.01M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Z" stroke="currentColor" stroke-width="1.6"/></svg>
          <div>
            <strong>Analysis failed.</strong>
            <p style="margin: 4px 0 0;">${DOM.escapeHTML(err.message || "Please try again.")}</p>
          </div>
        </div>
      `;
    }

    function renderResults(data) {
      resultsPanel.innerHTML = `
        <div class="coverage-summary">
          <div id="skillgap-dial"></div>
          <div>
            <h3>Coverage for ${DOM.escapeHTML(data.target_role || "target role")}</h3>
            <p class="text-muted">Matched vs. required skills for this role.</p>
          </div>
        </div>
        <div class="skill-columns mb-6">
          <div>
            <div class="skill-col__head">
              <span>Matched skills</span>
              <span class="skill-col__count" id="matched-count"></span>
            </div>
            <div id="matched-skills" class="chip-group"></div>
          </div>
          <div>
            <div class="skill-col__head">
              <span>Missing skills</span>
              <span class="skill-col__count" id="missing-count"></span>
            </div>
            <div id="missing-skills" class="chip-group"></div>
          </div>
        </div>
        <h4>Suggested learning path</h4>
        <div id="priority-list"></div>
      `;

      Gauge.render(DOM.qs("#skillgap-dial", resultsPanel), {
        score: data.coverage_pct ?? 0,
        max: 100,
        label: "Coverage",
        size: 120,
      });

      const matched = data.matched_skills || [];
      const missing = data.missing_skills || [];
      DOM.qs("#matched-count", resultsPanel).textContent = String(matched.length);
      DOM.qs("#missing-count", resultsPanel).textContent = String(missing.length);
      Chips.render(DOM.qs("#matched-skills", resultsPanel), matched, "matched", {
        emptyText: "No matched skills yet.",
      });
      Chips.render(DOM.qs("#missing-skills", resultsPanel), missing, "missing", {
        emptyText: "No gaps found \u2014 you're fully covered.",
      });

      const priorityList = DOM.qs("#priority-list", resultsPanel);
      const priorities = data.priorities || [];
      if (!priorities.length) {
        priorityList.appendChild(
          DOM.el("p", { class: "text-muted" }, ["No learning resources to suggest right now."])
        );
      } else {
        priorities.forEach((p) => {
          const row = DOM.el("div", { class: "priority-row" });
          row.innerHTML = `
            <div>
              <div class="priority-row__name">${DOM.escapeHTML(p.skill)}</div>
              ${p.resource_url ? `<div class="priority-row__resource"><a href="${DOM.escapeHTML(p.resource_url)}" target="_blank" rel="noopener noreferrer">${DOM.escapeHTML(p.resource_label || "View resource")}</a></div>` : ""}
            </div>
            <span class="priority-tag ${p.priority === "must-have" ? "must-have" : "nice-to-have"}">
              ${p.priority === "must-have" ? "Must-have" : "Nice-to-have"}
            </span>
          `;
          priorityList.appendChild(row);
        });
      }
    }
  });
})();
