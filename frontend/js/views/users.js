// Users (administrators only): invite people, change roles, reset passwords, deactivate access.

import { api } from "../api.js";
import {
  button,
  changedFields,
  confirmDialog,
  copyText,
  el,
  errorPanel,
  formatDateTime,
  generatePassword,
  iconButton,
  infoDialog,
  isQuiet,
  messageRow,
  openFormDialog,
  pluralize,
  showError,
  skeletonRows,
  toast,
} from "../ui.js";

const ROLE_OPTIONS = [
  { value: "member", label: "Member: can manage trainees and courses" },
  { value: "admin", label: "Administrator: can also manage users" },
];

function passwordField(label, hint) {
  return {
    name: "password",
    label,
    type: "text",
    required: true,
    minlength: 12,
    maxlength: 128,
    autocomplete: "new-password",
    hint,
    action: {
      label: "Generate",
      onClick: (input) => {
        input.value = generatePassword();
        input.focus();
        input.select();
      },
    },
  };
}

function showCredentials(email, password, intro) {
  return infoDialog({
    title: "Share these sign-in details",
    description: `${intro} Send them privately. The password won't be shown again.`,
    content: el(
      "div",
      { class: "stack" },
      el("div", { class: "credential-box" }, el("span", { text: `Email: ${email}` }), el("span", { text: `Password: ${password}` })),
      button("Copy details", {
        iconName: "copy",
        onClick: () => copyText(`StudyTrack sign-in\nEmail: ${email}\nPassword: ${password}`, "Sign-in details copied"),
      }),
    ),
  });
}

export async function render(main, { user: me, signal }) {
  const tbody = el("tbody");
  const summary = el("p", { class: "muted", "aria-live": "polite" });

  const inviteButton = button("Add user", {
    variant: "primary",
    iconName: "plus",
    onClick: async () => {
      let password = "";
      const created = await openFormDialog({
        title: "Add a user",
        description: "They can sign in as soon as you share the details. There is no public sign-up.",
        submitLabel: "Add user",
        values: { role: "member", password: generatePassword() },
        fields: [
          { name: "full_name", label: "Full name", required: true, maxlength: 120 },
          { name: "email", label: "Email", type: "email", required: true, maxlength: 255 },
          { name: "role", label: "Role", type: "select", options: ROLE_OPTIONS, required: true },
          passwordField("Temporary password", "At least 12 characters. Ask them to change it after signing in."),
        ],
        onSubmit: (data) => {
          password = data.password;
          return api("/users/", { method: "POST", body: data });
        },
      });
      if (created) {
        load();
        await showCredentials(created.email, password, `${created.full_name} has been added.`);
      }
    },
  });

  main.append(
    el(
      "div",
      { class: "stack" },
      el(
        "div",
        { class: "page-intro" },
        el("div", {}, el("h2", { text: "People with access" }), el("p", { class: "muted", text: "Only these accounts can sign in to StudyTrack." })),
        inviteButton,
      ),
      el(
        "div",
        { class: "card" },
        el("div", { class: "toolbar-meta" }, summary),
        el(
          "div",
          { class: "table-wrap" },
          el(
            "table",
            { class: "data-table" },
            el("caption", { class: "sr-only", text: "Users" }),
            el(
              "thead",
              {},
              el(
                "tr",
                {},
                el("th", { scope: "col", text: "Name" }),
                el("th", { scope: "col", text: "Email" }),
                el("th", { scope: "col", text: "Role" }),
                el("th", { scope: "col", text: "Status" }),
                el("th", { scope: "col", text: "Last sign-in" }),
                el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })),
              ),
            ),
            tbody,
          ),
        ),
      ),
    ),
  );

  async function edit(user) {
    const isSelf = user.id === me.id;
    const fields = [{ name: "full_name", label: "Full name", required: true, maxlength: 120 }];
    if (!isSelf) fields.push({ name: "role", label: "Role", type: "select", options: ROLE_OPTIONS, required: true });
    const saved = await openFormDialog({
      title: `Edit ${user.full_name}`,
      description: isSelf ? "You can't change your own role." : "Changing the role signs them out so the new access applies.",
      submitLabel: "Save changes",
      values: user,
      fields,
      onSubmit: (data) => {
        const changes = changedFields(user, data);
        if (!Object.keys(changes).length) return user;
        return api(`/users/${user.id}`, { method: "PATCH", body: changes });
      },
    });
    if (saved) {
      toast(`Saved ${saved.full_name}`);
      load();
    }
  }

  async function resetPassword(user) {
    let password = "";
    const saved = await openFormDialog({
      title: `Reset password for ${user.full_name}`,
      description: user.id === me.id ? "You'll stay signed in here." : "They'll be signed out everywhere.",
      submitLabel: "Reset password",
      values: { password: generatePassword() },
      fields: [passwordField("New password", "At least 12 characters.")],
      onSubmit: (data) => {
        password = data.password;
        return api(`/users/${user.id}`, { method: "PATCH", body: { password } });
      },
    });
    if (saved) await showCredentials(saved.email, password, `The password for ${saved.full_name} was reset.`);
  }

  async function toggleActive(user) {
    const activating = !user.is_active;
    const confirmed = await confirmDialog({
      title: activating ? `Reactivate ${user.full_name}?` : `Deactivate ${user.full_name}?`,
      message: activating
        ? "They'll be able to sign in again with their existing password."
        : "They'll be signed out right away and won't be able to sign in until reactivated.",
      confirmLabel: activating ? "Reactivate" : "Deactivate",
      danger: !activating,
    });
    if (!confirmed) return;
    try {
      await api(`/users/${user.id}`, { method: "PATCH", body: { is_active: activating } });
      toast(activating ? `Reactivated ${user.full_name}` : `Deactivated ${user.full_name}`);
      load();
    } catch (error) {
      showError(error);
    }
  }

  function row(user) {
    const isSelf = user.id === me.id;
    return el(
      "tr",
      {},
      el("td", { "data-label": "Name" }, el("strong", { text: user.full_name }), isSelf ? el("span", { class: "badge badge-inline", text: "You" }) : null),
      el("td", { "data-label": "Email", class: "secondary", text: user.email }),
      el(
        "td",
        { "data-label": "Role" },
        el("span", { class: `badge${user.role === "admin" ? " badge-accent" : ""}`, text: user.role === "admin" ? "Administrator" : "Member" }),
      ),
      el(
        "td",
        { "data-label": "Status" },
        el("span", { class: `badge ${user.is_active ? "badge-success" : "badge-danger"}`, text: user.is_active ? "Active" : "Deactivated" }),
      ),
      el("td", { "data-label": "Last sign-in", class: "secondary", text: formatDateTime(user.last_login_at) }),
      el(
        "td",
        { class: "row-actions" },
        iconButton("edit", `Edit ${user.full_name}`, { onClick: () => edit(user) }),
        iconButton("key", `Reset password for ${user.full_name}`, { onClick: () => resetPassword(user) }),
        isSelf
          ? null
          : iconButton(user.is_active ? "close" : "check", `${user.is_active ? "Deactivate" : "Reactivate"} ${user.full_name}`, {
              danger: user.is_active,
              onClick: () => toggleActive(user),
            }),
      ),
    );
  }

  async function load() {
    tbody.replaceChildren(...skeletonRows(6, 3));
    try {
      const users = await api("/users/", { signal });
      const active = users.filter((user) => user.is_active).length;
      summary.textContent = `${pluralize(users.length, "account")} · ${active} active`;
      tbody.replaceChildren(...users.map(row));
    } catch (error) {
      if (isQuiet(error) || signal.aborted) return;
      tbody.replaceChildren(messageRow(6, errorPanel(error, load)));
    }
  }

  await load();
}
