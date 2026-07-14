/**
 * linkedin-optimizer.js
 * Two input modes per the PRD: paste profile sections manually, or upload
 * a LinkedIn "Save to PDF" export. Both POST to /api/linkedin/analyze.
 * Rule-based scoring happens entirely on the backend.
 *
 * Expected response shape (backend contract):
 * {
 *   score: 0-100,
 *   sections: [{ key, title, status: 'good'|'warn'|'bad', suggestion }]
 * }
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = DOM.qs("#linkedin-form");
    if (!form) return;

    const modeButtons = DOM.qsa(".li-input-mode__btn");
    const pasteFields = DOM.qs("#li-paste-fields");
    const pdfField = DOM.qs("#li-pdf-field");
    const dropzoneEl = DOM.qs("#linkedin-dropzone");
    const submitBtn = DOM.qs("#li-submit");
    const resultsPanel = DOM.qs("#li-results");

    let mode = "paste";
    let selectedFile = null;

    modeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        mode = btn.dataset.mode;
        modeButtons.forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
        pasteFields.hidden = mode !== "paste";
        pdfField.hidden = mode !== "pdf";
      });
    });

    if (dropzoneEl) {
      Dropzone.init(dropzoneEl, {
        accept: ".pdf",
        validate: (file) =>
          file.name.toLowerCase().endsWith(".pdf")
            ? { valid: true }
            : { valid: false, error: "Upload the PDF exported from LinkedIn (Save to PDF)." },
        onFile: (file) => (selectedFile = file),
        onClear: () => (selectedFile = null),
      });
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      let payload;
      let isFormData = false;

      if (mode === "pdf") {
        if (!selectedFile) {
          Toast.warning("Upload your LinkedIn PDF export first.");
          return;
        }
        payload = new FormData();
        payload.append("file", selectedFile);
        isFormData = true;
      } else {
        const headline = DOM.qs("#li-headline").value.trim();
        const about = DOM.qs("#li-about").value.trim();
        const experience = DOM.qs("#li-experience").value.trim();
        const skills = DOM.qs("#li-skills").value.trim();
        if (!headline && !about && !experience) {
          Toast.warning("Fill in at least your headline, about section, or experience.");
          return;
        }
        payload = { headline, about, experience, skills };
      }

      setLoading(true);
      showLoadingState();
      try {
        const data = await Api.post(window.APP_CONFIG.ENDPOINTS.LINKEDIN_ANALYZE, payload, {
          timeoutMs: 20000,
        });
        renderResults(data);
        Toast.success("Your LinkedIn profile has been analyzed.");
      } catch (err) {
        renderError(err);
        Toast.error(err.message || "Couldn't analyze that profile.");
      } finally {
        setLoading(false);
      }
      void isFormData; // FormData vs JSON both handled transparently by Api.post
    });

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      submitBtn.innerHTML = isLoading
        ? '<span class="spinner" aria-hidden="true"></span> Analyzing\u2026'
        : "Analyze profile";
    }

    function showLoadingState() {
      resultsPanel.innerHTML = `
        <div class="loading-block">
          <span class="spinner spinner-lg" aria-hidden="true"></span>
          <p>Reviewing headline, about section, and experience bullets\u2026</p>
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
          <div id="li-score-dial"></div>
          <div class="score-summary__text">
            <h3>Profile strength score</h3>
            <p class="text-muted">Section-by-section, based on keyword richness, length, and calls to action.</p>
          </div>
        </div>
        <div id="li-sections" class="flex flex-col gap-3"></div>
      `;

      Gauge.render(DOM.qs("#li-score-dial", resultsPanel), {
        score: data.score ?? 0,
        max: 100,
        label: "LinkedIn score",
        size: 140,
      });

      const sectionsEl = DOM.qs("#li-sections", resultsPanel);
      (data.sections || []).forEach((section) => {
        const status = section.status || "warn";
        const card = DOM.el("div", { class: `card li-section-card status-${status}` });
        card.innerHTML = `
          <div class="li-section-card__head">
            <span class="li-section-card__title">${DOM.escapeHTML(section.title)}</span>
            <span class="badge badge-${status === "good" ? "good" : status === "bad" ? "bad" : "warn"}">
              ${status === "good" ? "Strong" : status === "bad" ? "Needs work" : "Could improve"}
            </span>
          </div>
          <p class="li-section-card__suggestion">${DOM.escapeHTML(section.suggestion || "")}</p>
        `;
        sectionsEl.appendChild(card);
      });
    }
  });
})();
