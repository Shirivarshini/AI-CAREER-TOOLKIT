/**
 * api.js
 * Thin fetch() wrapper around the FastAPI backend. This file intentionally
 * contains NO business logic (no scoring, no parsing, no scraping) — it
 * only sends requests and normalizes responses/errors for the UI layer.
 */
window.Api = (() => {
  const BASE = () => window.APP_CONFIG.API_BASE_URL;

  class ApiError extends Error {
    constructor(message, { status, details } = {}) {
      super(message);
      this.name = "ApiError";
      this.status = status || 0;
      this.details = details || null;
    }
  }

  /**
   * Core request helper.
   * @param {string} path - endpoint path, e.g. '/resume/analyze'
   * @param {object} options
   *   method, body (object -> JSON, or FormData as-is), headers, signal, timeoutMs
   */
  async function request(path, options = {}) {
    const {
      method = "GET",
      body,
      headers = {},
      timeoutMs = 30000,
      signal,
    } = options;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    // Allow an externally-supplied signal (e.g. cancel on navigation) to also abort.
    if (signal) signal.addEventListener("abort", () => controller.abort());

    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    const fetchOptions = {
      method,
      credentials: "include", // session cookie set by the backend on login
      headers: isFormData
        ? { ...headers }
        : { "Content-Type": "application/json", ...headers },
      body: body ? (isFormData ? body : JSON.stringify(body)) : undefined,
      signal: controller.signal,
    };

    let response;
    try {
      response = await fetch(`${BASE()}${path}`, fetchOptions);
    } catch (err) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        throw new ApiError("The request took too long. Please try again.", {
          status: 0,
        });
      }
      throw new ApiError(
        "Couldn't reach the server. Check your connection and try again.",
        { status: 0 }
      );
    }
    clearTimeout(timeout);

    let payload = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      payload = await response.json().catch(() => null);
    }

    if (!response.ok) {
      const message =
        (payload && (payload.detail || payload.message)) ||
        `Request failed (${response.status}).`;
      throw new ApiError(message, { status: response.status, details: payload });
    }

    return payload;
  }

  return {
    ApiError,
    get: (path, options) => request(path, { ...options, method: "GET" }),
    post: (path, body, options) => request(path, { ...options, method: "POST", body }),
    put: (path, body, options) => request(path, { ...options, method: "PUT", body }),
    del: (path, options) => request(path, { ...options, method: "DELETE" }),
    /** Returns a downloadable blob response (for PDF report export). */
    async getBlob(path, options = {}) {
      const response = await fetch(`${BASE()}${path}`, {
        credentials: "include",
        ...options,
      });
      if (!response.ok) {
        throw new ApiError(`Couldn't download the report (${response.status}).`, {
          status: response.status,
        });
      }
      return response.blob();
    },
  };
})();
