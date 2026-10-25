// Dashboard: headline numbers, recent trainees, and who carries the most enrollments.

import { api } from "../api.js";
import { button, el, emptyState, errorPanel, isQuiet, meter, pluralize, skeletonStat, stat, toast } from "../ui.js";
import { openCourseDialog } from "./courses.js";
import { openTraineeDialog, openTraineeDrawer } from "./trainees.js";

const REPORT_MIN_AGE = 21;

function firstName(fullName) {
  return (fullName || "").split(/\s+/)[0] || "there";
}

export async function render(main, { user, signal }) {
  const kpis = el("div", { class: "kpis", "aria-busy": "true" }, Array.from({ length: 4 }, skeletonStat));
  const recent = el("div", { class: "card-body flush" }, el("div", { class: "card-body" }, el("span", { class: "skeleton" })));
  const leaders = el("div", { class: "card-body flush" }, el("div", { class: "card-body" }, el("span", { class: "skeleton" })));

  main.append(
    el(
      "div",
      { class: "stack" },
      el(
        "div",
        { class: "page-intro" },
        el(
          "div",
          { class: "welcome" },
          el("h2", { text: `Welcome back, ${firstName(user.full_name)}` }),
          el("p", { class: "muted", text: "Here's the trainee roster at a glance." }),
        ),
        el(
          "div",
          { class: "actions" },
          button("Add trainee", {
            variant: "primary",
            iconName: "plus",
            onClick: async () => {
              const created = await openTraineeDialog();
              if (created) {
                toast(`Added ${created.name}`);
                load();
              }
            },
          }),
          button("Add course", {
            iconName: "book",
            onClick: async () => {
              try {
                const created = await openCourseDialog();
                if (created) {
                  toast(`Added ${created.course_name}`);
                  load();
                }
              } catch (error) {
                toast(error.message, { type: "error" });
              }
            },
          }),
        ),
      ),
      kpis,
      el(
        "div",
        { class: "grid-2" },
        el(
          "section",
          { class: "card", "aria-labelledby": "recent-title" },
          el("div", { class: "card-header" }, el("h2", { id: "recent-title", text: "Recently added trainees" }), el("a", { href: "#/trainees", text: "View all" })),
          recent,
        ),
        el(
          "section",
          { class: "card", "aria-labelledby": "leaders-title" },
          el(
            "div",
            { class: "card-header" },
            el("div", {}, el("h2", { id: "leaders-title", text: "Most enrolled trainees" }), el("p", { class: "hint", text: "Bar length shows course count." })),
            el("a", { href: "#/courses", text: "View courses" }),
          ),
          leaders,
        ),
      ),
    ),
  );

  async function load() {
    let students, courses, report;
    try {
      [students, courses, report] = await Promise.all([
        api("/students/", { signal }),
        api("/courses/", { signal }),
        api("/students/report", { query: { min_age: REPORT_MIN_AGE }, signal }),
      ]);
    } catch (error) {
      if (isQuiet(error) || signal.aborted) return;
      kpis.replaceChildren(errorPanel(error, load));
      kpis.removeAttribute("aria-busy");
      return;
    }

    const averageAge = students.length ? students.reduce((sum, s) => sum + s.age, 0) / students.length : 0;
    const totalCredits = courses.reduce((sum, c) => sum + c.credits, 0);
    kpis.removeAttribute("aria-busy");
    kpis.replaceChildren(
      stat("Trainees", students.length.toLocaleString(), "On the roster today"),
      stat("Course enrollments", courses.length.toLocaleString(), pluralize(totalCredits, "credit") + " in total"),
      stat("Average age", students.length ? averageAge.toFixed(1) : "–", "Years"),
      stat(`Aged ${REPORT_MIN_AGE} or older`, report.count_meeting_min_age.toLocaleString(), `of ${pluralize(students.length, "trainee")}`),
    );

    const newest = [...students].sort((a, b) => b.id - a.id).slice(0, 5);
    recent.replaceChildren(
      newest.length
        ? el(
            "ul",
            { class: "list" },
            newest.map((student) =>
              el(
                "li",
                {},
                el(
                  "div",
                  { class: "list-primary" },
                  el("button", { class: "link-button", type: "button", text: student.name, onclick: () => openTraineeDrawer(student.id, { onChange: load }) }),
                  el("span", { text: student.email }),
                ),
                el("span", { class: "badge", text: `Age ${student.age}` }),
              ),
            ),
          )
        : emptyState("No trainees yet", "Add your first trainee to get started."),
    );

    const byStudent = new Map();
    for (const course of courses) {
      const entry = byStudent.get(course.student_id) ?? { count: 0, credits: 0 };
      entry.count += 1;
      entry.credits += course.credits;
      byStudent.set(course.student_id, entry);
    }
    const names = new Map(students.map((s) => [s.id, s.name]));
    const ranked = [...byStudent.entries()]
      .map(([id, entry]) => ({ id, name: names.get(id) ?? `Trainee ${id}`, ...entry }))
      .sort((a, b) => b.count - a.count || b.credits - a.credits || a.name.localeCompare(b.name))
      .slice(0, 5);
    const most = ranked[0]?.count ?? 1;
    leaders.replaceChildren(
      ranked.length
        ? el(
            "div",
            {},
            ranked.map((entry) =>
              el(
                "div",
                { class: "bar-row", title: `${entry.name}: ${pluralize(entry.count, "course")}, ${pluralize(entry.credits, "credit")}` },
                el("span", { class: "name", text: entry.name }),
                meter(entry.count / most),
                el("span", { class: "value", text: `${pluralize(entry.count, "course")} · ${entry.credits} cr` }),
              ),
            ),
          )
        : emptyState("No enrollments yet", "Course enrollments will show up here."),
    );
  }

  await load();
}
