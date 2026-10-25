// App shell: confirm the session, show the signed-in user, wire the account menu, start routing.

import { api, loginUrl, onWakeChange } from "./api.js";
import { startRouter } from "./router.js";
import { el, hydrateIcons, initials, showError } from "./ui.js";
import { openChangePasswordDialog } from "./views/account.js";

const ROUTES = {
  dashboard: { title: "Dashboard", load: () => import("./views/dashboard.js") },
  trainees: { title: "Trainees", load: () => import("./views/trainees.js") },
  courses: { title: "Courses", load: () => import("./views/courses.js") },
  reports: { title: "Reports", load: () => import("./views/reports.js") },
  assistant: { title: "AI Helper", load: () => import("./views/assistant.js") },
  users: { title: "Users", load: () => import("./views/users.js"), adminOnly: true },
};

const $ = (selector) => document.querySelector(selector);

function showUser(user) {
  $("#user-avatar").textContent = initials(user.full_name);
  $("#user-name").textContent = user.full_name;
  $("#menu-name").textContent = user.full_name;
  $("#menu-email").textContent = user.email;
  document.querySelectorAll("[data-admin-only]").forEach((node) => {
    node.hidden = user.role !== "admin";
  });
}

function setUpUserMenu() {
  const toggle = $("#user-button");
  const menu = $("#user-menu");
  const setOpen = (open) => {
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector("button")?.focus();
  };
  toggle.addEventListener("click", () => setOpen(menu.hidden));
  document.addEventListener("click", (event) => {
    if (!menu.hidden && !event.target.closest(".user-menu")) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      setOpen(false);
      toggle.focus();
    }
  });
  menu.addEventListener("click", async (event) => {
    const action = event.target.closest("button")?.dataset.action;
    if (!action) return;
    setOpen(false);
    if (action === "change-password") {
      await openChangePasswordDialog();
    } else if (action === "sign-out") {
      try {
        await api("/auth/logout", { method: "POST", retry: true, redirectOn401: false });
      } catch (error) {
        showError(error);
        return;
      }
      window.location.replace("login.html?reason=signed-out");
    }
  });
}

function showBootError(error) {
  const message = $("#boot-message");
  message.textContent = error?.message || "StudyTrack couldn't start.";
  message.after(el("button", { class: "btn btn-secondary", type: "button", onclick: () => window.location.reload(), text: "Try again" }));
  $(".boot-screen .spinner")?.remove();
}

async function boot() {
  hydrateIcons(document);
  onWakeChange((waking) => {
    $("#wake-banner").hidden = !waking;
  });

  let user;
  try {
    // Not signed in yet is normal here, so go to sign-in without the "session ended" notice.
    user = await api("/auth/me", { redirectOn401: false });
  } catch (error) {
    if (error?.status === 401) window.location.replace(loginUrl());
    else showBootError(error);
    return;
  }

  showUser(user);
  setUpUserMenu();
  $("#boot-screen").hidden = true;
  $("#shell").hidden = false;
  startRouter({
    routes: ROUTES,
    main: $("#main"),
    titleElement: $("#page-title"),
    navLinks: [...document.querySelectorAll(".nav a")],
    user,
  });
}

boot();
