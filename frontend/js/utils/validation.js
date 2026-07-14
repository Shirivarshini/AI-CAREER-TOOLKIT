/**
 * validation.js
 * Generic client-side validation helpers — presentation-layer checks only
 * (required fields, formats, file size/type). All authoritative scoring
 * and parsing happens on the backend.
 */
window.Validate = (() => {
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const GITHUB_USERNAME_RE = /^[a-zA-Z\d](?:[a-zA-Z\d]|-(?=[a-zA-Z\d])){0,38}$/;

  function required(value) {
    return value !== null && value !== undefined && String(value).trim().length > 0;
  }

  function email(value) {
    return EMAIL_RE.test(String(value).trim());
  }

  function minLength(value, len) {
    return String(value || "").length >= len;
  }

  function githubUsername(value) {
    return GITHUB_USERNAME_RE.test(String(value).trim());
  }

  /** Parses a GitHub username out of a raw username or a full profile URL. */
  function parseGithubInput(value) {
    const trimmed = String(value || "").trim();
    const match = trimmed.match(/github\.com\/([a-zA-Z\d-]+)/i);
    return match ? match[1] : trimmed.replace(/^@/, "");
  }

  function passwordStrength(value) {
    const v = String(value || "");
    let score = 0;
    if (v.length >= 8) score++;
    if (/[A-Z]/.test(v)) score++;
    if (/[0-9]/.test(v)) score++;
    if (/[^A-Za-z0-9]/.test(v)) score++;
    if (v.length >= 12) score++;
    if (score <= 1) return "weak";
    if (score <= 3) return "fair";
    return "strong";
  }

  function fileType(file, acceptedExtensions) {
    const name = file.name.toLowerCase();
    return acceptedExtensions.some((ext) => name.endsWith(ext));
  }

  function fileSize(file, maxMb) {
    return file.size <= maxMb * 1024 * 1024;
  }

  /**
   * Validates a resume file against config-defined constraints.
   * Returns { valid: boolean, error?: string }
   */
  function resumeFile(file) {
    const cfg = window.APP_CONFIG;
    if (!file) return { valid: false, error: "Choose a file to upload." };
    if (!fileType(file, cfg.ACCEPTED_RESUME_TYPES)) {
      return {
        valid: false,
        error: `Unsupported file type. Upload a ${cfg.ACCEPTED_RESUME_TYPES.join(" or ")} file.`,
      };
    }
    if (!fileSize(file, cfg.MAX_UPLOAD_MB)) {
      return {
        valid: false,
        error: `File is too large. Max size is ${cfg.MAX_UPLOAD_MB}MB.`,
      };
    }
    return { valid: true };
  }

  /** Attaches live validation to a form. Returns true if the whole form is valid. */
  function showFieldError(inputEl, message) {
    inputEl.setAttribute("aria-invalid", "true");
    const errorEl = document.getElementById(`${inputEl.id}-error`);
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.hidden = false;
    }
  }

  function clearFieldError(inputEl) {
    inputEl.removeAttribute("aria-invalid");
    const errorEl = document.getElementById(`${inputEl.id}-error`);
    if (errorEl) {
      errorEl.textContent = "";
      errorEl.hidden = true;
    }
  }

  return {
    required,
    email,
    minLength,
    githubUsername,
    parseGithubInput,
    passwordStrength,
    fileType,
    fileSize,
    resumeFile,
    showFieldError,
    clearFieldError,
  };
})();
