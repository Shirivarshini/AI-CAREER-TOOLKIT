/**
 * config.js
 * Single source of truth for frontend-wide configuration.
 * The FastAPI backend base URL is the only thing that should ever need to
 * change between environments (local dev / staging / production).
 */
window.APP_CONFIG = Object.freeze({
  // Point this at the FastAPI backend. Override by setting
  // localStorage.setItem('act_api_base', 'https://api.example.com') during dev.
  API_BASE_URL:
    window.localStorage.getItem("act_api_base") || "http://localhost:8000/api",

  ENDPOINTS: {
    RESUME_ANALYZE: "/resume/analyze",
    RESUME_MATCH_JD: "/resume/match-jd",
    GITHUB_ANALYZE: "/github/analyze",
    LINKEDIN_ANALYZE: "/linkedin/analyze",
    SKILLS_GAP: "/skills/gap",
    REPORT: "/report", // GET /report/{analysis_id}
    AUTH_SIGNUP: "/auth/signup",
    AUTH_LOGIN: "/auth/login",
    HISTORY: "/history",
  },

  // Client-side validation limits only — never trusted as security boundaries.
  MAX_UPLOAD_MB: 5,
  ACCEPTED_RESUME_TYPES: [".pdf", ".docx"],
  ACCEPTED_RESUME_MIME: [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ],

  TOAST_DURATION_MS: 5000,
});
