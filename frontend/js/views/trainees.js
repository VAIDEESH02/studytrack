// Trainees: list with filter, minimum age, server-side insertion sort, exact-name binary search,
// add/edit/delete, and a detail panel with course enrollments.

import { api } from "../api.js";
import {
  button,
  changedFields,
  confirmDialog,
  debounce,
  el,
  emptyState,
  errorPanel,
  iconButton,
  isQuiet,
  messageRow,
  openDrawer,
  openFormDialog,
  pluralize,
  setBusy,
  showError,
  skeletonRows,
  toast,
} from "../ui.js";
import { confirmDeleteCourse, openCourseDialog } from "./courses.js";

const SORTS = [
  { value: "id", label: "Date added" },
  { value: "name", label: "Name, A to Z" },
  { value: "age", label: "Age, youngest first" },
];

/** Add or edit a trainee. Resolves with the saved trainee, or null if cancelled. */
export function openTraineeDialog({ student } = {}) {
  const editing = Boolean(student);
  return openFormDialog({
    title: editing ? `Edit ${student.name}` : "Add a trainee",
    submitLabel: editing ? "Save changes" : "Add trainee",
    values: student ?? {},
    fields: [
      { name: "name", label: "Full name", required: true, maxlength: 120 },
      { name: "email", label: "Email", type: "email", required: true, maxlength: 255 },
      { name: "age", label: "Age", type: "number", required: true, min: 1, max: 150, step: 1, inputmode: "numeric" },
    ],
    onSubmit: (values) => {
      if (!editing) return api("/students/", { method: "POST", body: values });
      const changes = changedFields(student, values);
      if (!Object.keys(changes).length) return student;
      return api(`/students/${student.id}`, { method: "PATCH", body: changes });
    },
  });
}

/** Confirm, then delete. Warns how many course enrollments go with the trainee. */
export async function confirmDeleteTrainee(student) {
  let courseCount = 0;
  try {
    ({ course_count: courseCount } = await api(`/students/${student.id}/course-count`));
  } catch (error) {
    showError(error);
    return false;
  }
  const consequence = courseCount
    ? `This also removes ${pluralize(courseCount, "course enrollment")}. This can't be undone.`
    : "This can't be undone.";
  const confirmed = await confirmDialog({
    title: `Delete ${student.name}?`,
    message: consequence,
    confirmLabel: "Delete trainee",
    danger: true,
  });
  if (!confirmed) return false;
  try {
    await api(`/students/${student.id}`, { method: "DELETE" });
  } catch (error) {
    showError(error);
    return false;
  }
  toast(`Deleted ${student.name}`);
  return true;
}

/** Side panel with one trainee's details and course enrollments. onChange runs after any edit. */
export function openTraineeDrawer(studentId, { onChange } = {}) {
  const drawer = openDrawer({ title: "Trainee" });

  async function load() {
    drawer.body.replaceChildren(el("span", { class: "skeleton tall" }), el("span", { class: "skeleton" }));
    let student, courseCount, courses;
    try {
      [student, { course_count: courseCount }, courses] = await Promise.all([
        api(`/students/${studentId}`),
        api(`/students/${studentId}/course-count`),
        api("/courses/"),
      ]);
    } catch (error) {
      if (isQuiet(error)) return;
      drawer.body.replaceChildren(errorPanel(error, error.status === 404 ? null : load));
      return;
    }
    const enrolled = courses.filter((course) => course.student_id === student.id);
    const credits = enrolled.reduce((sum, course) => sum + course.credits, 0);
    drawer.setTitle(student.name);

    const courseList = enrolled.length
      ? el(
          "ul",
          { class: "list bordered" },
          enrolled.map((course) =>
            el(
              "li",
              {},
              el("div", { class: "list-primary" }, el("strong", { text: course.course_name }), el("span", { text: pluralize(course.credits, "credit") })),
              el(
                "div",
                {},
                iconButton("edit", `Edit ${course.course_name}`, {
                  onClick: async () => {
                    try {
                      if (await openCourseDialog({ course })) {
                        toast(`Saved ${course.course_name}`);
                        changed();
                      }
                    } catch (error) {
                      showError(error);
                    }
                  },
                }),
                iconButton("trash", `Remove ${course.course_name}`, {
                  danger: true,
                  onClick: async () => {
                    if (await confirmDeleteCourse(course, student.name)) changed();
                  },
                }),
              ),
            ),
          ),
        )
      : emptyState("No course enrollments yet", "Add a course to start tracking credits.");

    drawer.body.replaceChildren(
      el(
        "dl",
        { class: "details" },
        el("dt", { text: "Email" }),
        el("dd", { text: student.email }),
        el("dt", { text: "Age" }),
        el("dd", { text: String(student.age) }),
        el("dt", { text: "Enrollments" }),
        el("dd", {}, el("span", { class: "badge badge-accent", text: pluralize(courseCount, "course") })),
        el("dt", { text: "Total credits" }),
        el("dd", { text: String(credits) }),
      ),
      el(
        "div",
        { class: "actions" },
        button("Edit trainee", {
          iconName: "edit",
          onClick: async () => {
            const saved = await openTraineeDialog({ student });
            if (saved) {
              toast(`Saved ${saved.name}`);
              changed();
            }
          },
        }),
        button("Delete", {
          iconName: "trash",
          variant: "ghost",
          class: "btn btn-ghost danger",
          onClick: async () => {
            if (await confirmDeleteTrainee(student)) {
              drawer.close();
              onChange?.();
            }
          },
        }),
      ),
      el(
        "section",
        { "aria-label": "Course enrollments" },
        el(
          "div",
          { class: "section-header" },
          el("h3", { text: "Course enrollments" }),
          button("Add course", {
            size: "sm",
            iconName: "plus",
            onClick: async () => {
              try {
                const created = await openCourseDialog({ defaultStudentId: student.id });
                if (created) {
                  toast(`Added ${created.course_name}`);
                  changed();
                }
              } catch (error) {
                showError(error);
              }
            },
          }),
        ),
        courseList,
      ),
    );
  }

  function changed() {
    load();
    onChange?.();
  }

  load();
  return drawer;
}

export async function render(main, { signal }) {
  const state = { sort: "id", minAge: "", filter: "", students: [] };

  const filterInput = el("input", { id: "trainee-filter", type: "search", placeholder: "Name or email", autocomplete: "off" });
  const minAgeInput = el("input", { id: "trainee-min-age", type: "number", min: 0, max: 150, inputmode: "numeric", placeholder: "Any" });
  const sortSelect = el("select", { id: "trainee-sort" }, SORTS.map((sort) => el("option", { value: sort.value, text: sort.label })));
  const addButton = button("Add trainee", {
    variant: "primary",
    iconName: "plus",
    onClick: async () => {
      const created = await openTraineeDialog();
      if (created) {
        toast(`Added ${created.name}`);
        load();
      }
    },
  });

  const lookupInput = el("input", { id: "exact-name", type: "search", placeholder: "e.g. Priya Iyer", required: true, autocomplete: "off" });
  const lookupButton = button("Find", { type: "submit", iconName: "search" });
  const lookupResult = el("p", { class: "lookup-result", role: "status" });
  const lookupForm = el(
    "form",
    { class: "lookup" },
    el("label", { class: "field-label", for: "exact-name", text: "Exact name lookup" }),
    el("div", { class: "input-row" }, lookupInput, lookupButton),
    el("p", { class: "hint", text: "Binary search over the name-sorted roster. Matches the full name exactly, including capitals." }),
    lookupResult,
  );
  lookupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = lookupInput.value.trim();
    if (!name) {
      lookupResult.textContent = "Type a full name to look up.";
      return;
    }
    setBusy(lookupButton, true, "Finding…");
    try {
      const found = await api("/students/search", { query: { name }, signal });
      lookupResult.textContent = `Found ${found.name}.`;
      openTraineeDrawer(found.id, { onChange: load });
    } catch (error) {
      if (isQuiet(error)) return;
      lookupResult.textContent = error.status === 404 ? `No trainee is named exactly "${name}".` : error.message;
    } finally {
      setBusy(lookupButton, false);
    }
  });

  const summary = el("p", { class: "muted", "aria-live": "polite" });
  const sortNote = el("p", { class: "hint" });
  const tbody = el("tbody");
  const table = el(
    "table",
    { class: "data-table" },
    el("caption", { class: "sr-only", text: "Trainees" }),
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        el("th", { scope: "col", text: "Name" }),
        el("th", { scope: "col", text: "Email" }),
        el("th", { scope: "col", class: "num", text: "Age" }),
        el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })),
      ),
    ),
    tbody,
  );

  main.append(
    el(
      "div",
      { class: "stack" },
      el(
        "div",
        { class: "page-intro" },
        el("div", {}, el("h2", { text: "Trainee roster" }), el("p", { class: "muted", text: "Everyone currently in the enablement program." })),
        addButton,
      ),
      el(
        "div",
        { class: "card" },
        el(
          "div",
          { class: "card-body" },
          el(
            "div",
            { class: "toolbar" },
            el("div", { class: "field grow" }, el("label", { for: "trainee-filter", text: "Filter" }), filterInput),
            el("div", { class: "field narrow" }, el("label", { for: "trainee-min-age", text: "Minimum age" }), minAgeInput),
            el("div", { class: "field" }, el("label", { for: "trainee-sort", text: "Sort by" }), sortSelect),
          ),
        ),
        el("div", { class: "toolbar-meta" }, summary, sortNote),
        el("div", { class: "table-wrap" }, table),
      ),
      el("div", { class: "card" }, el("div", { class: "card-body" }, lookupForm)),
    ),
  );

  function row(student) {
    return el(
      "tr",
      {},
      el(
        "td",
        { "data-label": "Name" },
        el("button", { class: "link-button", type: "button", text: student.name, onclick: () => openTraineeDrawer(student.id, { onChange: load }) }),
      ),
      el("td", { "data-label": "Email", class: "secondary", text: student.email }),
      el("td", { "data-label": "Age", class: "num", text: String(student.age) }),
      el(
        "td",
        { class: "row-actions" },
        iconButton("edit", `Edit ${student.name}`, {
          onClick: async () => {
            const saved = await openTraineeDialog({ student });
            if (saved) {
              toast(`Saved ${saved.name}`);
              load();
            }
          },
        }),
        iconButton("trash", `Delete ${student.name}`, {
          danger: true,
          onClick: async () => {
            if (await confirmDeleteTrainee(student)) load();
          },
        }),
      ),
    );
  }

  function draw() {
    const term = state.filter.trim().toLowerCase();
    const visible = term
      ? state.students.filter((s) => s.name.toLowerCase().includes(term) || s.email.toLowerCase().includes(term))
      : state.students;
    summary.textContent =
      visible.length === state.students.length
        ? pluralize(state.students.length, "trainee")
        : `${visible.length} of ${pluralize(state.students.length, "trainee")}`;
    sortNote.textContent = state.sort === "id" ? "" : "Sorted by the server with insertion sort.";
    if (!visible.length) {
      const message = state.students.length ? "No trainees match these filters." : "No trainees yet. Add the first one.";
      tbody.replaceChildren(messageRow(4, message));
      return;
    }
    tbody.replaceChildren(...visible.map(row));
  }

  async function load() {
    tbody.replaceChildren(...skeletonRows(4, 6));
    const minAge = state.minAge === "" ? null : Number(state.minAge);
    try {
      let students;
      if (state.sort === "id") {
        students = await api("/students/", { query: { min_age: minAge }, signal });
      } else {
        students = await api("/students/sorted", { query: { by: state.sort }, signal });
        if (minAge !== null) students = students.filter((student) => student.age >= minAge);
      }
      state.students = students;
      draw();
    } catch (error) {
      if (isQuiet(error) || signal.aborted) return;
      tbody.replaceChildren(messageRow(4, errorPanel(error, load)));
    }
  }

  filterInput.addEventListener("input", () => {
    state.filter = filterInput.value;
    draw();
  });
  minAgeInput.addEventListener(
    "input",
    debounce(() => {
      if (!minAgeInput.checkValidity()) return;
      state.minAge = minAgeInput.value;
      load();
    }, 350),
  );
  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    load();
  });

  await load();
}
