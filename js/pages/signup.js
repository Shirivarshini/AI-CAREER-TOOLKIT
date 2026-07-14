/**
 * signup.js
 * Client-side validation + POST to /auth/signup. No password hashing or
 * account logic happens here — that's entirely the backend's job.
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = DOM.qs("#signup-form");
    if (!form) return;

    const nameInput = DOM.qs("#name", form);
    const emailInput = DOM.qs("#email", form);
    const passwordInput = DOM.qs("#password", form);
    const confirmInput = DOM.qs("#confirm-password", form);
    const termsInput = DOM.qs("#terms", form);
    const submitBtn = DOM.qs("#signup-submit", form);
    const strengthEl = DOM.qs("#password-strength");

    passwordInput.addEventListener("input", () => {
      const strength = Validate.passwordStrength(passwordInput.value);
      const segs = DOM.qsa(".pw-strength__seg", strengthEl);
      segs.forEach((seg, i) => {
        seg.className = "pw-strength__seg";
        const threshold = { weak: 1, fair: 2, strong: 3 }[strength];
        if (i < threshold) seg.classList.add(`is-${strength}`);
      });
      strengthEl.setAttribute(
        "data-label",
        passwordInput.value ? `Password strength: ${strength}` : ""
      );
    });

    function validate() {
      let valid = true;

      if (!Validate.required(nameInput.value)) {
        Validate.showFieldError(nameInput, "Enter your name.");
        valid = false;
      } else Validate.clearFieldError(nameInput);

      if (!Validate.required(emailInput.value) || !Validate.email(emailInput.value)) {
        Validate.showFieldError(emailInput, "Enter a valid email address.");
        valid = false;
      } else Validate.clearFieldError(emailInput);

      if (!Validate.minLength(passwordInput.value, 8)) {
        Validate.showFieldError(passwordInput, "Use at least 8 characters.");
        valid = false;
      } else Validate.clearFieldError(passwordInput);

      if (confirmInput.value !== passwordInput.value || !confirmInput.value) {
        Validate.showFieldError(confirmInput, "Passwords don't match.");
        valid = false;
      } else Validate.clearFieldError(confirmInput);

      if (!termsInput.checked) {
        Toast.warning("Please accept the terms to continue.");
        valid = false;
      }

      return valid;
    }

    [nameInput, emailInput, passwordInput, confirmInput].forEach((input) => {
      input.addEventListener("blur", validate);
      input.addEventListener("input", () => Validate.clearFieldError(input));
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!validate()) return;

      setLoading(true);
      try {
        await Api.post(window.APP_CONFIG.ENDPOINTS.AUTH_SIGNUP, {
          name: nameInput.value.trim(),
          email: emailInput.value.trim(),
          password: passwordInput.value,
        });
        Toast.success("Account created. Taking you to your dashboard\u2026");
        window.setTimeout(() => {
          window.location.href = "dashboard.html";
        }, 700);
      } catch (err) {
        if (err instanceof Api.ApiError && err.status === 409) {
          Toast.error("An account with that email already exists.");
        } else {
          Toast.error(err.message || "Couldn't create your account. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    });

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      submitBtn.innerHTML = isLoading
        ? '<span class="spinner" aria-hidden="true"></span> Creating account\u2026'
        : "Create account";
    }
  });
})();
