// The one place the frontend talks to the backend.
//
// - Sends the HttpOnly session cookie with every request (credentials: "include").
// - A 401 sends the user to the sign-in page, remembering where they were.
// - FastAPI's 422 validation lists become per-field messages forms can show inline.
// - GETs retry 502/503/504 and network failures for up to 90 seconds. That covers a free
//   Render instance waking up, which takes longer than Netlify's 26-second proxy timeout.

import { API_BASE_URL } from "./config.js";

const RETRYABLE_STATUSES = new Set([502, 503, 504]);
const RETRY_WINDOW_MS = 90_000;

const FALLBACK_MESSAGES = {
  400: "The server couldn't accept that request.",
  403: "You don't have permission to do that.",
  404: "That item no longer exists. It may have been deleted.",
  409: "That conflicts with an existing record.",
  429: "Too many attempts. Please wait and try again.",
  500: "Something went wrong on the server. Please try again.",
};

const FIELD_HINTS = [
  [/email/i, "email"],
  [/^student_id/i, "student_id"],
  [/^credits/i, "credits"],
  [/^role/i, "role"],
  [/current password/i, "current_password"],
  [/new password/i, "new_password"],
];

export class ApiError extends Error {
  constructor(status, message, { fieldErrors = {}, retryAfter = null, redirecting = false } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.retryAfter = retryAfter;
    this.redirecting = redirecting;
  }
}

const wakeListeners = new Set();
let requestsWaiting = 0;

/** Subscribe to "the server is waking up" changes. Returns an unsubscribe function. */
export function onWakeChange(listener) {
  wakeListeners.add(listener);
  return () => wakeListeners.delete(listener);
}

function changeWaiting(delta) {
  const before = requestsWaiting > 0;
  requestsWaiting = Math.max(0, requestsWaiting + delta);
  const after = requestsWaiting > 0;
  if (before !== after) wakeListeners.forEach((listener) => listener(after));
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Request aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

function buildUrl(path, query) {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.href);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return url;
}

/** The sign-in URL, carrying the current in-app route so the user lands back where they were. */
export function loginUrl(reason) {
  const params = new URLSearchParams();
  if (window.location.hash.startsWith("#/")) params.set("next", window.location.hash);
  if (reason) params.set("reason", reason);
  const query = params.toString();
  return `login.html${query ? `?${query}` : ""}`;
}

function humanizeField(field) {
  const text = field.replace(/_id$/, "").replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

async function toApiError(response) {
  let detail = null;
  try {
    detail = (await response.json()).detail;
  } catch {
    // Empty or non-JSON body; fall back to a status-based message.
  }
  const retryAfter = Number(response.headers.get("Retry-After")) || null;

  if (Array.isArray(detail)) {
    const fieldErrors = {};
    for (const item of detail) {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
      const message = String(item.msg ?? "Invalid value").replace(/^Value error, /, "");
      if (typeof field === "string" && !(field in fieldErrors)) fieldErrors[field] = message;
    }
    const [first] = Object.entries(fieldErrors);
    const message = first ? `${humanizeField(first[0])}: ${first[1]}` : "Some values were not valid.";
    return new ApiError(response.status, message, { fieldErrors });
  }

  if (typeof detail === "string" && detail) {
    const fieldErrors = {};
    if (response.status === 409 || response.status === 422 || response.status === 400) {
      const hint = FIELD_HINTS.find(([pattern]) => pattern.test(detail));
      if (hint) fieldErrors[hint[1]] = detail;
    }
    return new ApiError(response.status, detail, { fieldErrors, retryAfter });
  }

  const fallback = FALLBACK_MESSAGES[response.status] ?? `The server couldn't complete the request (${response.status}).`;
  return new ApiError(response.status, fallback, { retryAfter });
}

/**
 * Call the StudyTrack API and return parsed JSON (or null for 204).
 *
 * @param {string} path e.g. "/students/"
 * @param {{method?: string, body?: unknown, query?: Record<string, unknown>, signal?: AbortSignal,
 *          retry?: boolean, redirectOn401?: boolean}} [options]
 */
export async function api(path, options = {}) {
  const { method = "GET", body, query, signal, retry = method === "GET", redirectOn401 = true } = options;
  const init = { method, credentials: "include", cache: "no-store", headers: { Accept: "application/json" }, signal };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const url = buildUrl(path, query);
  const deadline = Date.now() + RETRY_WINDOW_MS;
  let waiting = false;

  try {
    for (let attempt = 0; ; attempt += 1) {
      let response;
      try {
        response = await fetch(url, init);
      } catch (error) {
        if (error.name === "AbortError") throw error;
        if (!retry || Date.now() >= deadline) {
          throw new ApiError(0, "Can't reach the StudyTrack server. Check your connection and try again.");
        }
      }

      if (response && !(retry && RETRYABLE_STATUSES.has(response.status) && Date.now() < deadline)) {
        if (response.status === 401 && redirectOn401) {
          window.location.assign(loginUrl("expired"));
          throw new ApiError(401, "Your session has ended. Please sign in again.", { redirecting: true });
        }
        if (!response.ok) throw await toApiError(response);
        return response.status === 204 ? null : await response.json();
      }

      if (!waiting) {
        waiting = true;
        changeWaiting(1);
      }
      await sleep(Math.min(1000 * 2 ** attempt, 5000), signal);
    }
  } finally {
    if (waiting) changeWaiting(-1);
  }
}
