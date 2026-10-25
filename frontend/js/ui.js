// Small DOM helpers shared by every view. User data is only ever inserted as text
// (textContent / text nodes), never as HTML, so names and notes cannot inject markup.

import { ApiError } from "./api.js";

const SVG_NS = "http://www.w3.org/2000/svg";

// 24x24 stroke icons. Each entry is one SVG path "d" attribute.
const ICONS = {
  dashboard: "M3 3h7v9H3z M14 3h7v5h-7z M14 12h7v9h-7z M3 16h7v5H3z",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20 M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
  chart: "M3 3v18h18 M7 16v-4 M12 16V8 M17 16v-7",
  sparkles: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z M19 15l.7 1.8L21.5 17.5l-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  plus: "M12 5v14 M5 12h14",
  edit: "M12 20h9 M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z",
  trash: "M3 6h18 M8 6V4h8v2 M19 6l-1 14H6L5 6 M10 11v6 M14 11v6",
  close: "M18 6L6 18 M6 6l12 12",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9",
  key: "M15.5 7.5L19 4 M21 2l-9.6 9.6 M15.5 7.5l3 3L22 7l-3-3 M7.5 21a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11z",
  copy: "M9 9h11v11H9z M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  "chevron-down": "M6 9l6 6 6-6",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 16v-4 M12 8h.01",
  check: "M20 6L9 17l-5-5",
  alert: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 8v4 M12 16h.01",
  refresh: "M21 12a9 9 0 1 1-2.64-6.36L21 8 M21 3v5h-5",
  minus: "M5 12h14",
};

/** Create an element. attrs: class, text, dataset, on* listeners, booleans, or plain attributes. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICONS[name] ?? ICONS.info);
  svg.append(path);
  return svg;
}

/** Replace every <span data-icon="name"> placeholder in static HTML with its SVG. */
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((placeholder) => placeholder.replaceWith(icon(placeholder.dataset.icon)));
}

export function button(label, { variant = "secondary", size, iconName, onClick, type = "button", ...attrs } = {}) {
  const classes = ["btn", `btn-${variant}`, size ? `btn-${size}` : ""].filter(Boolean).join(" ");
  return el("button", { class: classes, type, onclick: onClick, ...attrs }, iconName ? icon(iconName) : null, label);
}

export function iconButton(iconName, label, { onClick, danger = false, ...attrs } = {}) {
  return el(
    "button",
    {
      class: `btn btn-ghost btn-icon${danger ? " danger" : ""}`,
      type: "button",
      "aria-label": label,
      title: label,
      onclick: onClick,
      ...attrs,
    },
    icon(iconName),
  );
}

/** Show a spinner and disable a button while work is in flight. */
export function setBusy(target, busy, busyLabel) {
  if (busy) {
    if (!target.originalChildren) target.originalChildren = [...target.childNodes];
    target.disabled = true;
    target.setAttribute("aria-busy", "true");
    target.replaceChildren(el("span", { class: "spinner", "aria-hidden": "true" }), busyLabel ?? target.textContent);
  } else {
    target.disabled = false;
    target.removeAttribute("aria-busy");
    if (target.originalChildren) target.replaceChildren(...target.originalChildren);
    target.originalChildren = null;
  }
}

export function toast(message, { type = "success", timeout } = {}) {
  const region = document.getElementById("toasts");
  if (!region) return;
  const iconName = type === "error" ? "alert" : type === "info" ? "info" : "check";
  const item = el("div", { class: `toast toast-${type}` }, icon(iconName), el("p", { text: message }));
  const dismiss = () => item.remove();
  item.append(iconButton("close", "Dismiss notification", { onClick: dismiss }));
  region.append(item);
  setTimeout(dismiss, timeout ?? (type === "error" ? 8000 : 4500));
}

/** Toast an error unless it is an aborted request or a redirect to sign-in already in progress. */
export function showError(error, fallback = "Something went wrong.") {
  if (isQuiet(error)) return;
  toast(error?.message || fallback, { type: "error" });
}

export function isQuiet(error) {
  return error?.name === "AbortError" || Boolean(error?.redirecting);
}

export function debounce(fn, wait = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function pluralize(count, singular, plural = `${singular}s`) {
  return `${count.toLocaleString()} ${count === 1 ? singular : plural}`;
}

export function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

const dateTimeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(value) {
  return value ? dateTimeFormat.format(new Date(value)) : "Never";
}

export function skeletonRows(columns, rows = 5) {
  return Array.from({ length: rows }, () =>
    el(
      "tr",
      { "aria-hidden": "true" },
      Array.from({ length: columns }, (_, index) =>
        el("td", {}, el("span", { class: `skeleton${index > 0 ? " short" : ""}` })),
      ),
    ),
  );
}

export function messageRow(columns, ...content) {
  return el("tr", { class: "table-message" }, el("td", { colspan: columns }, ...content));
}

export function emptyState(title, message, action) {
  return el("div", { class: "empty" }, el("strong", { text: title }), message ? el("p", { text: message }) : null, action);
}

/** A panel shown when a view's data failed to load, with a retry button. */
export function errorPanel(error, onRetry) {
  return el(
    "div",
    { class: "error-panel", role: "alert" },
    el("div", { class: "notice error" }, icon("alert"), el("p", { text: error?.message || "Something went wrong." })),
    onRetry ? button("Try again", { iconName: "refresh", onClick: onRetry }) : null,
  );
}

export function stat(label, value, note) {
  return el(
    "div",
    { class: "stat" },
    el("p", { class: "stat-label", text: label }),
    el("p", { class: "stat-value", text: value }),
    note ? el("p", { class: "stat-note", text: note }) : null,
  );
}

export function skeletonStat() {
  return el(
    "div",
    { class: "stat", "aria-hidden": "true" },
    el("span", { class: "skeleton short" }),
    el("span", { class: "skeleton tall" }),
  );
}

/** Horizontal meter. value is 0..1. The number itself should be shown as text next to it. */
export function meter(value) {
  const clamped = Math.max(0, Math.min(1, Number(value) || 0));
  const fill = el("span");
  fill.style.setProperty("--value", String(clamped));
  return el("div", { class: `meter${clamped === 0 ? " zero" : ""}`, "aria-hidden": "true" }, fill);
}

export async function copyText(text, successMessage = "Copied to clipboard") {
  try {
    await navigator.clipboard.writeText(text);
    toast(successMessage, { type: "info" });
  } catch {
    toast("Couldn't copy automatically. Select the text and copy it instead.", { type: "error" });
  }
}

/** A strong random password from an unambiguous alphabet, using the browser's CSPRNG. */
export function generatePassword(length = 16) {
  const alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_!@#%";
  const bytes = crypto.getRandomValues(new Uint32Array(length));
  return Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join("");
}

let dialogCounter = 0;

function modalShell({ title, description, size }) {
  dialogCounter += 1;
  const titleId = `dialog-title-${dialogCounter}`;
  const descriptionId = description ? `dialog-description-${dialogCounter}` : undefined;
  const dialog = el("dialog", {
    class: `modal${size ? ` modal-${size}` : ""}`,
    "aria-labelledby": titleId,
    "aria-describedby": descriptionId,
  });
  const header = el(
    "div",
    { class: "modal-header" },
    el(
      "div",
      {},
      el("h2", { id: titleId, text: title }),
      description ? el("p", { id: descriptionId, class: "muted", text: description }) : null,
    ),
    iconButton("close", "Close dialog", { onClick: () => dialog.close() }),
  );
  dialog.addEventListener("close", () => dialog.remove());
  return { dialog, header };
}

function buildControl(field, value, idBase) {
  const id = `${idBase}-${field.name}`;
  const errorId = `${id}-error`;
  const hintId = field.hint ? `${id}-hint` : null;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ");
  const common = { id, name: field.name, "aria-describedby": describedBy, required: field.required };
  let control;

  if (field.type === "select") {
    control = el(
      "select",
      common,
      field.options.map((option) => el("option", { value: option.value, text: option.label })),
    );
    if (value !== undefined && value !== null) control.value = String(value);
    if (field.disabled) control.disabled = true;
  } else if (field.type === "checkbox") {
    control = el("input", { ...common, type: "checkbox" });
    control.checked = Boolean(value);
    if (field.disabled) control.disabled = true;
    const wrapper = el(
      "div",
      { class: "field" },
      el("label", { class: "checkbox", for: id }, control, field.label),
      field.hint ? el("p", { id: hintId, class: "hint", text: field.hint }) : null,
      el("p", { id: errorId, class: "field-error", hidden: true }),
    );
    return { wrapper, control };
  } else if (field.type === "textarea") {
    control = el("textarea", { ...common, rows: field.rows ?? 5, maxlength: field.maxlength, placeholder: field.placeholder });
    control.value = value ?? "";
  } else {
    control = el("input", {
      ...common,
      type: field.type ?? "text",
      min: field.min,
      max: field.max,
      step: field.step,
      minlength: field.minlength,
      maxlength: field.maxlength,
      autocomplete: field.autocomplete ?? "off",
      inputmode: field.inputmode,
      placeholder: field.placeholder,
      spellcheck: field.type === "password" || field.type === "email" ? "false" : undefined,
    });
    control.value = value ?? "";
  }

  let input = control;
  if (field.action) {
    const actionButton = button(field.action.label, {
      size: "sm",
      onClick: () => field.action.onClick(control),
    });
    input = el("div", { class: "input-row" }, control, actionButton);
  }

  const wrapper = el(
    "div",
    { class: "field" },
    el("label", { for: id, text: field.label }),
    input,
    field.hint ? el("p", { id: hintId, class: "hint", text: field.hint }) : null,
    el("p", { id: errorId, class: "field-error", hidden: true }),
  );
  return { wrapper, control };
}

function readValue(field, control) {
  if (field.type === "checkbox") return control.checked;
  if (field.type === "number" || field.valueType === "number") return control.value === "" ? null : Number(control.value);
  if (field.type === "password") return control.value;
  return control.value.trim();
}

/**
 * A modal form. Resolves with whatever onSubmit returns, or null if cancelled.
 * onSubmit may throw an ApiError; its fieldErrors are shown next to the matching inputs.
 *
 * field: {name, label, type?, required?, min?, max?, step?, minlength?, maxlength?, hint?,
 *         options? (select), valueType? ("number"), autocomplete?, disabled?, action? {label, onClick(input)}}
 */
export function openFormDialog({ title, description, fields, values = {}, submitLabel = "Save", onSubmit }) {
  return new Promise((resolve) => {
    const { dialog, header } = modalShell({ title, description });
    const idBase = `field-${dialogCounter}`;
    const controls = new Map();
    const body = el("div", { class: "modal-body" });
    for (const field of fields) {
      const { wrapper, control } = buildControl(field, values[field.name], idBase);
      controls.set(field.name, { field, control, error: wrapper.querySelector(".field-error") });
      body.append(wrapper);
    }
    const formError = el("p", { class: "form-error", role: "alert", hidden: true });
    body.append(formError);

    const submit = el("button", { class: "btn btn-primary", type: "submit", text: submitLabel });
    const footer = el(
      "div",
      { class: "modal-footer" },
      button("Cancel", { onClick: () => dialog.close() }),
      submit,
    );
    const form = el("form", { novalidate: true }, header, body, footer);
    dialog.append(form);

    const clearErrors = () => {
      formError.hidden = true;
      for (const { control, error } of controls.values()) {
        control.removeAttribute("aria-invalid");
        error.hidden = true;
        error.textContent = "";
      }
    };

    const showFieldError = (name, message) => {
      const entry = controls.get(name);
      if (!entry) return false;
      entry.control.setAttribute("aria-invalid", "true");
      entry.error.textContent = message;
      entry.error.hidden = false;
      return true;
    };

    const focusFirstInvalid = () => form.querySelector('[aria-invalid="true"]')?.focus();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearErrors();
      let valid = true;
      for (const [name, { control }] of controls) {
        if (!control.checkValidity()) {
          valid = false;
          showFieldError(name, control.validationMessage);
        }
      }
      if (!valid) {
        focusFirstInvalid();
        return;
      }
      const data = Object.fromEntries([...controls].map(([name, { field, control }]) => [name, readValue(field, control)]));
      setBusy(submit, true, "Saving…");
      try {
        const result = await onSubmit(data);
        resolve(result ?? true);
        dialog.close();
      } catch (error) {
        if (isQuiet(error)) return;
        const shown = Object.entries(error instanceof ApiError ? error.fieldErrors : {}).filter(([name, message]) =>
          showFieldError(name, message),
        );
        if (!shown.length) {
          formError.textContent = error?.message || "Something went wrong.";
          formError.hidden = false;
        }
        focusFirstInvalid();
      } finally {
        setBusy(submit, false);
      }
    });

    dialog.addEventListener("close", () => resolve(null));
    document.body.append(dialog);
    dialog.showModal();
    form.querySelector("input:not([type=checkbox]), select, textarea")?.focus();
  });
}

/** Ask a yes/no question. Resolves true when confirmed. Focus starts on Cancel. */
export function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const { dialog, header } = modalShell({ title });
    let confirmed = false;
    const cancel = button("Cancel", { onClick: () => dialog.close() });
    const confirm = button(confirmLabel, {
      variant: danger ? "danger" : "primary",
      onClick: () => {
        confirmed = true;
        dialog.close();
      },
    });
    dialog.append(
      el("div", { class: "modal-content" }, header, el("div", { class: "modal-body" }, el("p", { text: message })), el("div", { class: "modal-footer" }, cancel, confirm)),
    );
    dialog.addEventListener("close", () => resolve(confirmed));
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}

/** Show information (for example, a temporary password) with a single dismiss button. */
export function infoDialog({ title, description, content, closeLabel = "Done" }) {
  return new Promise((resolve) => {
    const { dialog, header } = modalShell({ title, description });
    const done = button(closeLabel, { variant: "primary", onClick: () => dialog.close() });
    dialog.append(
      el("div", { class: "modal-content" }, header, el("div", { class: "modal-body" }, content), el("div", { class: "modal-footer" }, done)),
    );
    dialog.addEventListener("close", () => resolve());
    document.body.append(dialog);
    dialog.showModal();
    done.focus();
  });
}

/** A right-hand side panel. Returns {body, setTitle, close}. */
export function openDrawer({ title, onClose }) {
  dialogCounter += 1;
  const titleId = `drawer-title-${dialogCounter}`;
  const heading = el("h2", { id: titleId, text: title });
  const dialog = el("dialog", { class: "drawer", "aria-labelledby": titleId });
  const body = el("div", { class: "drawer-body" });
  dialog.append(
    el("div", { class: "drawer-header" }, heading, iconButton("close", "Close panel", { onClick: () => dialog.close() })),
    body,
  );
  dialog.addEventListener("close", () => {
    dialog.remove();
    onClose?.();
  });
  // Clicking the backdrop (outside the panel) closes it.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  document.body.append(dialog);
  dialog.showModal();
  return {
    body,
    setTitle: (text) => {
      heading.textContent = text;
    },
    close: () => dialog.close(),
  };
}

/** Only the fields whose value differs from the original record (for PATCH bodies). */
export function changedFields(original, values) {
  return Object.fromEntries(Object.entries(values).filter(([key, value]) => original[key] !== value));
}
