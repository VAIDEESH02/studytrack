// Reports: the roster report and the minimum-age count from the hand-written algorithms.

import { api } from "../api.js";
import { button, copyText, debounce, el, errorPanel, iconButton, isQuiet, pluralize, stat } from "../ui.js";

export async function render(main, { signal }) {
  let minAge = 21;
  const minAgeInput = el("input", { id: "report-min-age", type: "number", min: 0, max: 150, step: 1, inputmode: "numeric", value: minAge });
  const countSlot = el("div", {}, el("span", { class: "skeleton tall" }));
  const reportOutput = el("pre", { class: "report-output", tabindex: "0", "aria-label": "Roster report" });
  const copyButton = button("Copy", { size: "sm", iconName: "copy", onClick: () => copyText(reportOutput.textContent, "Report copied") });

  const step = (delta) => {
    const value = Math.min(150, Math.max(0, (Number(minAgeInput.value) || 0) + delta));
    minAgeInput.value = String(value);
    minAgeInput.dispatchEvent(new Event("input"));
  };

  main.append(
    el(
      "div",
      { class: "stack" },
      el(
        "div",
        { class: "page-intro" },
        el("div", {}, el("h2", { text: "Roster report" }), el("p", { class: "muted", text: "Built live from the database on every request." })),
      ),
      el(
        "div",
        { class: "grid-2" },
        el(
          "section",
          { class: "card", "aria-labelledby": "age-count-title" },
          el("div", { class: "card-header" }, el("h2", { id: "age-count-title", text: "Minimum age check" })),
          el(
            "div",
            { class: "card-body stack" },
            el(
              "div",
              { class: "field" },
              el("label", { for: "report-min-age", text: "Minimum age" }),
              el(
                "div",
                { class: "stepper" },
                iconButton("minus", "Decrease minimum age", { onClick: () => step(-1) }),
                minAgeInput,
                iconButton("plus", "Increase minimum age", { onClick: () => step(1) }),
              ),
            ),
            countSlot,
          ),
        ),
        el(
          "section",
          { class: "card", "aria-labelledby": "how-title" },
          el("div", { class: "card-header" }, el("h2", { id: "how-title", text: "How the algorithms work" })),
          el(
            "div",
            { class: "card-body explainer" },
            el(
              "div",
              {},
              el("h3", { text: "Counting" }),
              el("p", { text: "A single loop walks the roster and adds one to a running total for each trainee at or above the minimum age." }),
            ),
            el(
              "div",
              {},
              el("h3", { text: "Insertion sort" }),
              el("p", {
                text: "Used by Sort by on the Trainees page. Each trainee is shifted left past larger values. Worst case O(n²), best case O(n) when the roster is already in order.",
              }),
            ),
            el(
              "div",
              {},
              el("h3", { text: "Binary search" }),
              el("p", {
                text: "Used by Exact name lookup. It halves a name-sorted list on each step, which only works because the list is sorted first.",
              }),
            ),
          ),
        ),
      ),
      el(
        "section",
        { class: "card", "aria-labelledby": "report-title" },
        el("div", { class: "card-header" }, el("h2", { id: "report-title", text: "Full roster" }), copyButton),
        el("div", { class: "card-body" }, reportOutput),
      ),
    ),
  );

  async function load() {
    try {
      const report = await api("/students/report", { query: { min_age: minAge }, signal });
      const total = report.report ? report.report.split("\n").length : 0;
      countSlot.replaceChildren(
        stat(
          `Trainees aged ${minAge} or older`,
          report.count_meeting_min_age.toLocaleString(),
          `of ${pluralize(total, "trainee")} on the roster`,
        ),
      );
      reportOutput.textContent = report.report || "The roster is empty.";
      copyButton.disabled = !report.report;
    } catch (error) {
      if (isQuiet(error) || signal.aborted) return;
      countSlot.replaceChildren(errorPanel(error, load));
    }
  }

  minAgeInput.addEventListener(
    "input",
    debounce(() => {
      if (minAgeInput.value === "" || !minAgeInput.checkValidity()) return;
      minAge = Number(minAgeInput.value);
      load();
    }, 300),
  );

  await load();
}
