// AI Helper: summarize pasted notes, and search the sample notes by similarity.

import { api } from "../api.js";
import { button, el, emptyState, icon, isQuiet, meter, setBusy } from "../ui.js";

const MAX_CHARACTERS = 20_000;
const SAMPLE_NOTES = `Binary Search
Binary search finds an item in a sorted list by checking the middle element. If the target is smaller it continues in the left half, otherwise in the right half. Each step halves the remaining range, so it needs about log2(n) comparisons.`;
const SUGGESTIONS = ["binary search", "insertion sort", "sql join", "fastapi pydantic", "prompt llm"];
const DIFFICULTY_BADGES = { easy: "badge-success", medium: "badge-warning", hard: "badge-danger" };

function placeholder(text) {
  return el("p", { class: "muted", text });
}

export async function render(main, { signal }) {
  // ---- Summarize ----
  const notes = el("textarea", { id: "notes-input", rows: 9, maxlength: MAX_CHARACTERS, placeholder: "Paste study notes here. The first line becomes the topic." });
  const counter = el("p", { class: "char-count", "aria-live": "off" });
  const summarizeButton = button("Summarize", { type: "submit", variant: "primary", iconName: "sparkles" });
  const summaryResult = el("div", { class: "summary-result", "aria-live": "polite" }, placeholder("Your summary will appear here."));

  const updateCounter = () => {
    counter.textContent = `${notes.value.length.toLocaleString()} / ${MAX_CHARACTERS.toLocaleString()} characters`;
  };
  notes.addEventListener("input", updateCounter);
  updateCounter();

  const summaryForm = el(
    "form",
    { class: "stack" },
    el("div", { class: "field" }, el("label", { for: "notes-input", text: "Study notes" }), notes, counter),
    el(
      "div",
      { class: "actions" },
      summarizeButton,
      button("Use sample notes", {
        onClick: () => {
          notes.value = SAMPLE_NOTES;
          updateCounter();
          notes.focus();
        },
      }),
      button("Clear", {
        variant: "ghost",
        onClick: () => {
          notes.value = "";
          updateCounter();
          summaryResult.replaceChildren(placeholder("Your summary will appear here."));
          notes.focus();
        },
      }),
    ),
  );

  summaryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!notes.value.trim()) {
      summaryResult.replaceChildren(placeholder("Paste some notes first, or use the sample."));
      notes.focus();
      return;
    }
    setBusy(summarizeButton, true, "Summarizing…");
    try {
      const summary = await api("/assistant/summarize", { method: "POST", body: { text: notes.value }, signal });
      summaryResult.replaceChildren(
        el(
          "div",
          { class: "section-header" },
          el("h3", { text: summary.topic }),
          el("span", { class: `badge ${DIFFICULTY_BADGES[summary.difficulty] ?? ""}`, text: `Difficulty: ${summary.difficulty}` }),
        ),
        el("p", { class: "field-label", text: "Key points" }),
        summary.key_points.length
          ? el("ul", {}, summary.key_points.map((point) => el("li", { text: point })))
          : placeholder("No sentences were found in these notes."),
      );
    } catch (error) {
      if (isQuiet(error)) return;
      summaryResult.replaceChildren(el("div", { class: "notice error", role: "alert" }, icon("alert"), el("p", { text: error.message })));
    } finally {
      setBusy(summarizeButton, false);
    }
  });

  // ---- Search ----
  const queryInput = el("input", { id: "note-query", type: "search", placeholder: "e.g. binary search", autocomplete: "off" });
  const searchButton = button("Search", { type: "submit", iconName: "search" });
  const results = el("div", { "aria-live": "polite" }, placeholder("Results will appear here, best match first."));

  async function search() {
    setBusy(searchButton, true, "Searching…");
    try {
      const ranked = await api("/assistant/search", { query: { query: queryInput.value.trim() }, signal });
      const anyMatch = ranked.some((note) => note.score > 0);
      const content = [
        anyMatch
          ? null
          : el(
              "div",
              { class: "notice" },
              icon("info"),
              el("p", { text: "None of the search vocabulary matched, so every note scores 0. Try words like sort, search, sql, join, fastapi, or prompt." }),
            ),
        ranked.length
          ? el(
              "ol",
              { class: "results" },
              ranked.map((note) =>
                el(
                  "li",
                  { class: "result" },
                  el(
                    "div",
                    { class: "result-meta" },
                    el("strong", { text: `Note ${note.id}` }),
                    meter(note.score),
                    el("span", { class: "score", text: `Similarity ${note.score.toFixed(2)}` }),
                  ),
                  el("p", { text: note.text }),
                ),
              ),
            )
          : emptyState("No notes to search"),
      ];
      // replaceChildren() would turn a null into the text "null", so drop empty slots first.
      results.replaceChildren(...content.filter(Boolean));
    } catch (error) {
      if (isQuiet(error)) return;
      results.replaceChildren(el("div", { class: "notice error", role: "alert" }, icon("alert"), el("p", { text: error.message })));
    } finally {
      setBusy(searchButton, false);
    }
  }

  const searchForm = el(
    "form",
    { class: "stack" },
    el("div", { class: "field" }, el("label", { for: "note-query", text: "Search the study notes" }), el("div", { class: "input-row" }, queryInput, searchButton)),
    el(
      "div",
      { class: "chips", role: "group", "aria-label": "Suggested searches" },
      SUGGESTIONS.map((suggestion) =>
        el("button", {
          class: "chip",
          type: "button",
          text: suggestion,
          onclick: () => {
            queryInput.value = suggestion;
            search();
          },
        }),
      ),
    ),
  );
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    search();
  });

  main.append(
    el(
      "div",
      { class: "stack" },
      el(
        "div",
        { class: "page-intro" },
        el(
          "div",
          {},
          el("h2", { text: "AI Helper" }),
          el("p", { class: "muted", text: "Summaries run offline by default. Search ranks five sample notes by word-vector similarity." }),
        ),
      ),
      el(
        "div",
        { class: "grid-2" },
        el(
          "section",
          { class: "card", "aria-labelledby": "summarize-title" },
          el("div", { class: "card-header" }, el("h2", { id: "summarize-title", text: "Summarize notes" })),
          el("div", { class: "card-body stack" }, summaryForm, summaryResult),
        ),
        el(
          "section",
          { class: "card", "aria-labelledby": "search-title" },
          el("div", { class: "card-header" }, el("h2", { id: "search-title", text: "Search notes" })),
          el("div", { class: "card-body stack" }, searchForm, results),
        ),
      ),
    ),
  );
}
