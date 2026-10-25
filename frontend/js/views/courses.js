// Courses: every enrollment with its trainee, filterable, with add/edit/delete.

import { api } from "../api.js";
import {
  button,
  changedFields,
  confirmDialog,
  el,
  errorPanel,
  iconButton,
  isQuiet,
  messageRow,
  openFormDialog,
  pluralize,
  showError,
  skeletonRows,
  toast,
} from "../ui.js";
import { openTraineeDrawer } from "./trainees.js";

/**
 * Add or edit a course enrollment. Editing re-reads the course first (GET /courses/{id}) so the
 * form never starts from stale data. Resolves with the saved course, or null if cancelled.
 */
export async function openCourseDialog({ course = null, defaultStudentId = null } = {}) {
  const [current, students] = await Promise.all([course ? api(`/courses/${course.id}`) : null, api("/students/")]);
  if (!students.length) {
    toast("Add a trainee before adding course enrollments.", { type: "info" });
    return null;
  }
  const values = current ?? { course_name: "", credits: 3, student_id: defaultStudentId ?? students[0].id };
  return openFormDialog({
    title: current ? `Edit ${current.course_name}` : "Add a course enrollment",
    submitLabel: current ? "Save changes" : "Add course",
    values,
    fields: [
      { name: "course_name", label: "Course name", required: true, maxlength: 160 },
      {
        name: "credits",
        label: "Credits",
        type: "number",
        required: true,
        min: 1,
        max: 6,
        step: 1,
        inputmode: "numeric",
        hint: "Between 1 and 6.",
      },
      {
        name: "student_id",
        label: "Trainee",
        type: "select",
        valueType: "number",
        required: true,
        options: students.map((student) => ({ value: student.id, label: `${student.name} (${student.email})` })),
      },
    ],
    onSubmit: (data) => {
      if (!current) return api("/courses/", { method: "POST", body: data });
      const changes = changedFields(current, data);
      if (!Object.keys(changes).length) return current;
      return api(`/courses/${current.id}`, { method: "PATCH", body: changes });
    },
  });
}

export async function confirmDeleteCourse(course, traineeName) {
  const confirmed = await confirmDialog({
    title: `Remove ${course.course_name}?`,
    message: traineeName
      ? `${traineeName} will no longer be enrolled in ${course.course_name}.`
      : `This removes the ${course.course_name} enrollment.`,
    confirmLabel: "Remove course",
    danger: true,
  });
  if (!confirmed) return false;
  try {
    await api(`/courses/${course.id}`, { method: "DELETE" });
  } catch (error) {
    showError(error);
    return false;
  }
  toast(`Removed ${course.course_name}`);
  return true;
}

export async function render(main, { signal }) {
  const state = { courses: [], students: new Map(), filter: "", studentId: "" };

  const filterInput = el("input", { id: "course-filter", type: "search", placeholder: "Course name", autocomplete: "off" });
  const traineeSelect = el("select", { id: "course-trainee" }, el("option", { value: "", text: "All trainees" }));
  const summary = el("p", { class: "muted", "aria-live": "polite" });
  const tbody = el("tbody");

  const addButton = button("Add course", {
    variant: "primary",
    iconName: "plus",
    onClick: async () => {
      try {
        const created = await openCourseDialog({ defaultStudentId: state.studentId ? Number(state.studentId) : null });
        if (created) {
          toast(`Added ${created.course_name}`);
          load();
        }
      } catch (error) {
        showError(error);
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
        el("div", {}, el("h2", { text: "Course enrollments" }), el("p", { class: "muted", text: "Each row is one trainee enrolled in one course." })),
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
            el("div", { class: "field grow" }, el("label", { for: "course-filter", text: "Filter" }), filterInput),
            el("div", { class: "field" }, el("label", { for: "course-trainee", text: "Trainee" }), traineeSelect),
          ),
        ),
        el("div", { class: "toolbar-meta" }, summary),
        el(
          "div",
          { class: "table-wrap" },
          el(
            "table",
            { class: "data-table" },
            el("caption", { class: "sr-only", text: "Course enrollments" }),
            el(
              "thead",
              {},
              el(
                "tr",
                {},
                el("th", { scope: "col", text: "Course" }),
                el("th", { scope: "col", text: "Trainee" }),
                el("th", { scope: "col", class: "num", text: "Credits" }),
                el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })),
              ),
            ),
            tbody,
          ),
        ),
      ),
    ),
  );

  function row(course) {
    const student = state.students.get(course.student_id);
    const traineeName = student?.name ?? `Trainee ${course.student_id}`;
    return el(
      "tr",
      {},
      el("td", { "data-label": "Course" }, el("strong", { text: course.course_name })),
      el(
        "td",
        { "data-label": "Trainee" },
        el("button", {
          class: "link-button",
          type: "button",
          text: traineeName,
          onclick: () => openTraineeDrawer(course.student_id, { onChange: load }),
        }),
      ),
      el("td", { "data-label": "Credits", class: "num", text: String(course.credits) }),
      el(
        "td",
        { class: "row-actions" },
        iconButton("edit", `Edit ${course.course_name} for ${traineeName}`, {
          onClick: async () => {
            try {
              const saved = await openCourseDialog({ course });
              if (saved) {
                toast(`Saved ${saved.course_name}`);
                load();
              }
            } catch (error) {
              showError(error);
            }
          },
        }),
        iconButton("trash", `Remove ${course.course_name} for ${traineeName}`, {
          danger: true,
          onClick: async () => {
            if (await confirmDeleteCourse(course, traineeName)) load();
          },
        }),
      ),
    );
  }

  function draw() {
    const term = state.filter.trim().toLowerCase();
    const visible = state.courses.filter(
      (course) =>
        (!term || course.course_name.toLowerCase().includes(term)) &&
        (!state.studentId || course.student_id === Number(state.studentId)),
    );
    const credits = visible.reduce((sum, course) => sum + course.credits, 0);
    summary.textContent = `${pluralize(visible.length, "enrollment")} · ${pluralize(credits, "credit")}`;
    if (!visible.length) {
      tbody.replaceChildren(
        messageRow(4, state.courses.length ? "No enrollments match these filters." : "No course enrollments yet."),
      );
      return;
    }
    tbody.replaceChildren(...visible.map(row));
  }

  async function load() {
    tbody.replaceChildren(...skeletonRows(4, 4));
    try {
      const [courses, students] = await Promise.all([api("/courses/", { signal }), api("/students/", { signal })]);
      state.courses = courses;
      state.students = new Map(students.map((student) => [student.id, student]));
      const selected = state.studentId;
      traineeSelect.replaceChildren(
        el("option", { value: "", text: "All trainees" }),
        students.map((student) => el("option", { value: student.id, text: student.name })),
      );
      traineeSelect.value = state.students.has(Number(selected)) ? selected : "";
      state.studentId = traineeSelect.value;
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
  traineeSelect.addEventListener("change", () => {
    state.studentId = traineeSelect.value;
    draw();
  });

  await load();
}
