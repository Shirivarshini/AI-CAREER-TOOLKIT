/**
 * dropzone.js
 * Accessible drag-and-drop file upload. Keyboard users can Tab to the
 * zone and press Enter/Space to open the native file picker. Validation
 * is delegated to a caller-supplied function (see validation.js) so this
 * component stays purely presentational.
 *
 * Usage:
 *   Dropzone.init(document.getElementById('resume-dropzone'), {
 *     accept: '.pdf,.docx',
 *     validate: (file) => Validate.resumeFile(file),
 *     onFile: (file) => { ... },
 *     onClear: () => { ... },
 *   });
 */
window.Dropzone = (() => {
  function init(rootEl, { accept, validate, onFile, onClear } = {}) {
    if (!rootEl) return;

    const input = DOM.el("input", {
      type: "file",
      accept,
      id: rootEl.id ? `${rootEl.id}-input` : undefined,
      "aria-label": rootEl.dataset.label || "Choose a file to upload",
    });
    rootEl.appendChild(input);
    rootEl.setAttribute("tabindex", "0");
    rootEl.setAttribute("role", "button");
    rootEl.setAttribute(
      "aria-label",
      rootEl.dataset.label || "Drag and drop a file here, or activate to browse"
    );

    let previewEl = null;

    function showError(message) {
      rootEl.classList.add("has-error");
      Toast.error(message, { title: "Upload failed" });
    }

    function clearError() {
      rootEl.classList.remove("has-error");
    }

    function handleFile(file) {
      clearError();
      const result = validate ? validate(file) : { valid: true };
      if (!result.valid) {
        showError(result.error);
        return;
      }
      renderPreview(file);
      onFile && onFile(file);
    }

    function renderPreview(file) {
      previewEl?.remove();
      previewEl = DOM.el("div", { class: "file-preview" });
      previewEl.innerHTML = `
        <span class="file-preview__icon" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M4 1.5h6.5L14 5v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
        </span>
        <div class="file-preview__meta">
          <div class="file-preview__name">${DOM.escapeHTML(file.name)}</div>
          <div class="file-preview__size">${DOM.formatBytes(file.size)}</div>
        </div>
      `;
      const removeBtn = DOM.el(
        "button",
        {
          type: "button",
          class: "btn btn-ghost btn-icon",
          "aria-label": "Remove file",
          onClick: (e) => {
            e.stopPropagation();
            input.value = "";
            previewEl.remove();
            previewEl = null;
            onClear && onClear();
          },
        },
        []
      );
      removeBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1 1 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
      previewEl.appendChild(removeBtn);
      rootEl.insertAdjacentElement("afterend", previewEl);
    }

    rootEl.addEventListener("click", () => input.click());
    rootEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });

    input.addEventListener("change", () => {
      if (input.files && input.files[0]) handleFile(input.files[0]);
    });

    ["dragenter", "dragover"].forEach((evt) =>
      rootEl.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        rootEl.classList.add("is-dragover");
      })
    );
    ["dragleave", "dragend"].forEach((evt) =>
      rootEl.addEventListener(evt, (e) => {
        e.preventDefault();
        rootEl.classList.remove("is-dragover");
      })
    );
    rootEl.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      rootEl.classList.remove("is-dragover");
      const file = e.dataTransfer?.files?.[0];
      if (file) handleFile(file);
    });

    return { clear: () => { input.value = ""; previewEl?.remove(); previewEl = null; } };
  }

  return { init };
})();
