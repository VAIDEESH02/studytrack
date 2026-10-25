// Sign-in page. Wakes the API while the user types, then posts credentials.

import { api } from "./api.js";
import { setBusy } from "./ui.js";

const $ = (selector) => document.querySelector(selector);
const params = new URLSearchParams(window.location.search);
// Only allow in-app hash routes as the post-login destination (no open redirects).
const next = /^#\/[\w/-]*$/.test(params.get("next") ?? "") ? params.get("next") : "#/dashboard";
const destination = `index.html${next}`;

const NOTICES = {
  expired: "Your session ended. Please sign in again.",
  "signed-out": "You've been signed out.",
};

const form = $("#login-form");
const email = $("#email");
const password = $("#password");
const submit = $("#sign-in-button");
const formError = $("#login-error");
const status = $("#server-status");

function setFieldError(input, message) {
  const error = document.getElementById(`${input.id}-error`);
  if (message) input.setAttribute("aria-invalid", "true");
  else input.removeAttribute("aria-invalid");
  error.textContent = message ?? "";
  error.hidden = !message;
}

function showFormError(message) {
  formError.textContent = message;
  formError.hidden = !message;
}

async function warmUp() {
  status.textContent = "Connecting to the server…";
  const slow = setTimeout(() => {
    status.textContent = "Waking up the server. On the free hosting plan this can take up to a minute…";
  }, 3000);
  try {
    await api("/health", { redirectOn401: false });
    status.textContent = "";
  } catch {
    status.textContent = "Can't reach the server right now. You can still try to sign in.";
    return;
  } finally {
    clearTimeout(slow);
  }
  try {
    await api("/auth/me", { redirectOn401: false });
    window.location.replace(destination); // already signed in
  } catch {
    // Not signed in: stay here.
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showFormError("");
  setFieldError(email, email.checkValidity() ? null : "Enter the email address for your StudyTrack account.");
  setFieldError(password, password.value ? null : "Enter your password.");
  const invalid = form.querySelector('[aria-invalid="true"]');
  if (invalid) {
    invalid.focus();
    return;
  }

  setBusy(submit, true, "Signing in…");
  try {
    await api("/auth/login", {
      method: "POST",
      body: { email: email.value.trim(), password: password.value },
      retry: true,
      redirectOn401: false,
    });
    window.location.replace(destination);
  } catch (error) {
    showFormError(error.status === 422 ? "Enter a valid email address and password." : error.message);
    if (error.status === 401) {
      password.select();
      password.focus();
    }
    setBusy(submit, false);
  }
});

$("#toggle-password").addEventListener("click", (event) => {
  const show = password.type === "password";
  password.type = show ? "text" : "password";
  event.currentTarget.textContent = show ? "Hide" : "Show";
  event.currentTarget.setAttribute("aria-pressed", String(show));
  password.focus();
});

const capsHint = $("#caps-lock-hint");
for (const type of ["keydown", "keyup"]) {
  password.addEventListener(type, (event) => {
    capsHint.hidden = !event.getModifierState?.("CapsLock");
  });
}
password.addEventListener("blur", () => {
  capsHint.hidden = true;
});

const notice = NOTICES[params.get("reason")];
if (notice) {
  $("#auth-notice").textContent = notice;
  $("#auth-notice").hidden = false;
}

warmUp();
