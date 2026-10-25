// Hash routes (#/trainees) so the back button, refresh, and deep links work on static hosting.

import { el, errorPanel, icon } from "./ui.js";

function routeName() {
  const match = window.location.hash.match(/^#\/([\w-]+)/);
  return match ? match[1] : "";
}

function forbiddenPanel() {
  return el(
    "div",
    { class: "card" },
    el(
      "div",
      { class: "error-panel" },
      el("div", { class: "notice warning" }, icon("shield"), el("p", { text: "Only administrators can open this page." })),
      el("a", { class: "btn btn-secondary", href: "#/dashboard", text: "Back to dashboard" }),
    ),
  );
}

/**
 * Render the view for the current hash into `main`.
 * routes: {name: {title, load: () => import(...), adminOnly?}}; each view module exports
 * render(main, {user, signal}). The signal aborts when the user navigates away.
 */
export function startRouter({ routes, main, titleElement, navLinks, user, fallback = "dashboard" }) {
  let controller = null;
  let firstRender = true;

  async function render() {
    const name = routeName();
    const route = routes[name];
    if (!route) {
      window.location.replace(`#/${fallback}`);
      return;
    }
    controller?.abort();
    controller = new AbortController();
    const { signal } = controller;

    titleElement.textContent = route.title;
    document.title = `${route.title} · StudyTrack`;
    navLinks.forEach((link) => {
      if (link.dataset.route === name) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    main.replaceChildren();
    if (!firstRender) {
      main.focus({ preventScroll: true });
      window.scrollTo({ top: 0 });
    }
    firstRender = false;

    if (route.adminOnly && user.role !== "admin") {
      main.append(forbiddenPanel());
      return;
    }
    try {
      const view = await route.load();
      if (signal.aborted) return;
      await view.render(main, { user, signal });
    } catch (error) {
      if (signal.aborted || error?.name === "AbortError" || error?.redirecting) return;
      main.replaceChildren(errorPanel(error, render));
    }
  }

  window.addEventListener("hashchange", render);
  render();
}
