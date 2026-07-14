/**
 * login.js
 * Validates the login form client-side, then POSTs credentials to the
 * FastAPI backend. All authentication logic (password checks, token
 * issuance) lives on the backend; this only renders the result.
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = DOM.qs("#login-form");
    if (!form) return;

    const emailInput = DOM.qs("#email", form);
    const passwordInput = DOM.qs("#password", form);
    const submitBtn = DOM.qs("#login-submit", form);

    function validate() {
      let valid = true;
      if (!Validate.required(emailInput.value) || !Validate.email(emailInput.value)) {
        Validate.showFieldError(emailInput, "Enter a valid email address.");
        valid = false;
      } else {
        Validate.clearFieldError(emailInput);
      }
      if (!Validate.required(passwordInput.value)) {
        Validate.showFieldError(passwordInput, "Enter your password.");
        valid = false;
      } else {
        Validate.clearFieldError(passwordInput);
      }
      return valid;
    }

    [emailInput, passwordInput].forEach((input) => {
      input.addEventListener("blur", validate);
      input.addEventListener("input", () => Validate.clearFieldError(input));
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!validate()) return;

      setLoading(true);
      try {
        await Api.post(window.APP_CONFIG.ENDPOINTS.AUTH_LOGIN, {
          email: emailInput.value.trim(),
          password: passwordInput.value,
        });
        Toast.success("You're logged in. Redirecting to your dashboard\u2026");
        window.setTimeout(() => {
          window.location.href = "dashboard.html";
        }, 700);
      } catch (err) {
        if (err instanceof Api.ApiError && err.status === 401) {
          Toast.error("That email and password don't match our records.");
        } else {
          Toast.error(err.message || "Couldn't log you in. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    });

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      submitBtn.innerHTML = isLoading
        ? '<span class="spinner" aria-hidden="true"></span> Logging in\u2026'
        : "Log in";
    }

    // Guest mode: users can skip auth entirely per PRD (guest usage of core tools).
    const guestBtn = DOM.qs("#continue-as-guest");
    guestBtn?.addEventListener("click", () => {
      window.location.href = "resume-analyzer.html";
    });
  });
})();
