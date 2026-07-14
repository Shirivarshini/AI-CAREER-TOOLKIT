/**
 * resume-analyzer.js
 * Wires the resume upload form to POST /api/resume/analyze. Renders the
 * score dial, category breakdown, fix list, and matched/missing keywords
 * from whatever the backend returns. No parsing or scoring happens here.
 *
 * Expected response shape (backend contract):
 * {
 *   overall_score: 0-100,
 *   breakdown: [{ label, score, max }],
 *   fixes: [{ severity: 'high'|'medium'|'low', message }],
 *   keywords: { matched: string[], missing: string[] }
 * }
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = DOM.qs("#resume-form");
    if (!form) return;

    const dropzoneEl = DOM.qs("#resume-dropzone");
    const jdToggle = DOM.qs("#jd-toggle");
    const jdWrap = DOM.qs("#jd-wrap");
    const jdTextarea = DOM.qs("#jd-text");
    const submitBtn = DOM.qs("#analyze-submit");
    const resultsPanel = DOM.qs("#results-panel");

    let selectedFile = null;

    Dropzone.init(dropzoneEl, {
      accept: window.APP_CONFIG.ACCEPTED_RESUME_TYPES.join(","),
      validate: (file) => Validate.resumeFile(file),
      onFile: (file) => {
        selectedFile = file;
        submitBtn.disabled = false;
      },
      onClear: () => {
        selectedFile = null;
        submitBtn.disabled = true;
      },
    });

    jdToggle?.addEventListener("click", () => {
      const isHidden = jdWrap.hasAttribute("hidden");
      if (isHidden) jdWrap.removeAttribute("hidden");
      else jdWrap.setAttribute("hidden", "");
      jdToggle.setAttribute("aria-expanded", String(isHidden));
      jdToggle.querySelector(".jd-toggle__text").textContent = isHidden
        ? "Hide job description"
        : "Paste a job description (optional)";
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!selectedFile) {
        Toast.warning("Upload a resume file first.");
        return;
      }

      const formData = new FormData();
      formData.append("file", selectedFile);
      if (jdTextarea && jdTextarea.value.trim()) {
        formData.append("job_description", jdTextarea.value.trim());
      }

      setLoading(true);
      showLoadingState();
      try {
        const result = await Api.post(
          window.APP_CONFIG.ENDPOINTS.RESUME_ANALYZE,
          formData,
          { timeoutMs: 20000 }
        );
        renderResults(result);
        Toast.success("Your resume has been analyzed.");
      } catch (err) {
        renderError(err);
        Toast.error(err.message || "We couldn't analyze that resume. Please try again.");
      } finally {
        setLoading(false);
      }
    });

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading || !selectedFile;
      submitBtn.innerHTML = isLoading
        ? '<span class="spinner" aria-hidden="true"></span> Analyzing\u2026'
        : "Analyze resume";
    }

    function showLoadingState() {
      resultsPanel.innerHTML = `
        <div class="loading-block">
          <span class="spinner spinner-lg" aria-hidden="true"></span>
          <p>Reading your resume and scoring it against ATS rules\u2026</p>
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
        <div class="score-summary">
          <div id="score-dial"></div>
          <div class="score-summary__text">
            <h3>Overall ATS score</h3>
            <p class="text-muted">Based on formatting, keyword match, completeness, and impact language.</p>
          </div>
        </div>
        <h4>Category breakdown</h4>
        <div id="breakdown-list" class="mb-5"></div>
        <h4>Fix list</h4>
        <div id="fix-list" class="fix-list"></div>
        <div id="keyword-section" hidden>
          <h4 style="margin-top: var(--sp-6);">Keywords vs. job description</h4>
          <div class="keyword-compare">
            <div>
              <h5>Matched</h5>
              <div id="matched-keywords" class="chip-group"></div>
            </div>
            <div>
              <h5>Missing</h5>
              <div id="missing-keywords" class="chip-group"></div>
            </div>
          </div>
        </div>
      `;

      const dialContainer = DOM.qs("#score-dial", resultsPanel);
      Gauge.render(dialContainer, {
        score: data.overall_score ?? 0,
        max: 100,
        label: "ATS Score",
        size: 140,
      });

      const breakdownList = DOM.qs("#breakdown-list", resultsPanel);
      (data.breakdown || []).forEach((item) => {
        const pct = Math.round((item.score / (item.max || 100)) * 100);
        const band = Gauge.bandFor(item.score, item.max || 100).band;
        breakdownList.appendChild(
          DOM.el("div", { class: "breakdown-row" }, [
            DOM.el("span", { class: "breakdown-row__label" }, [item.label]),
            DOM.el("div", { class: "breakdown-row__bar" }, [
              DOM.el("div", { class: "progress" }, [
                DOM.el("div", {
                  class: `progress__fill is-${band}`,
                  style: `width: ${pct}%`,
                }),
              ]),
            ]),
            DOM.el("span", { class: "breakdown-row__score" }, [`${item.score}/${item.max || 100}`]),
          ])
        );
      });

      const fixList = DOM.qs("#fix-list", resultsPanel);
      if (!data.fixes || data.fixes.length === 0) {
        fixList.appendChild(
          DOM.el("p", { class: "text-muted" }, ["No major issues found \u2014 nice work."])
        );
      } else {
        data.fixes.forEach((fix) => {
          const item = DOM.el("div", { class: `fix-item severity-${fix.severity || "low"}` });
          item.innerHTML = `
            <svg class="fix-item__icon" viewBox="0 0 18 18" fill="none" aria-hidden="true"><path d="M9 5.5v4m0 2.5h.01M16 9A7 7 0 1 1 2 9a7 7 0 0 1 14 0Z" stroke="currentColor" stroke-width="1.5"/></svg>
            <span>${DOM.escapeHTML(fix.message)}</span>
          `;
          fixList.appendChild(item);
        });
      }

      if (data.keywords && (data.keywords.matched?.length || data.keywords.missing?.length)) {
        DOM.qs("#keyword-section", resultsPanel).hidden = false;
        Chips.render(DOM.qs("#matched-keywords", resultsPanel), data.keywords.matched, "matched", {
          emptyText: "No keyword matches found.",
        });
        Chips.render(DOM.qs("#missing-keywords", resultsPanel), data.keywords.missing, "missing", {
          emptyText: "No missing keywords \u2014 great coverage.",
        });
      }
    }
  });
})();
