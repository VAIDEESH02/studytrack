const API_BASE_URL = "http://localhost:8000";

const rosterList = document.querySelector("#roster-list");
const studentForm = document.querySelector("#student-form");
const errorBanner = document.querySelector("#error-banner");
const summaryForm = document.querySelector("#summary-form");
const notesInput = document.querySelector("#notes-input");
const summaryResult = document.querySelector("#summary-result");
const noteSearchForm = document.querySelector("#note-search-form");
const noteQuery = document.querySelector("#note-query");
const noteSearchResults = document.querySelector("#note-search-results");

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  errorBanner.textContent = "";
  errorBanner.hidden = true;
}

async function request(path, options = {}) {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    if (!response.ok) {
      let detail = "The StudyTrack backend could not complete that request.";
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) {
        // The server may return an empty error response.
      }
      throw new Error(detail);
    }
    return response;
  } catch (error) {
    showError(
      error instanceof TypeError
        ? "Could not reach the StudyTrack backend. Make sure it is running on port 8000."
        : error.message
    );
    throw error;
  }
}

function studentCard(student) {
  const card = document.createElement("article");
  card.className = "student-card";
  card.dataset.studentId = String(student.id);

  const name = document.createElement("p");
  name.className = "student-name";
  name.textContent = student.name;

  const email = document.createElement("p");
  email.textContent = student.email;

  const ageText = document.createElement("p");
  ageText.className = "student-age";
  ageText.textContent = `Age: ${student.age}`;

  const ageControl = document.createElement("div");
  ageControl.className = "age-control";
  const ageInput = document.createElement("input");
  ageInput.className = "age-input";
  ageInput.type = "number";
  ageInput.min = "1";
  ageInput.value = String(student.age);
  ageInput.setAttribute("aria-label", `New age for ${student.name}`);
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "save-age-button";
  saveButton.textContent = "Save Age";
  ageControl.appendChild(ageInput);
  ageControl.appendChild(saveButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "delete-button";
  deleteButton.textContent = "Delete";

  card.appendChild(name);
  card.appendChild(email);
  card.appendChild(ageText);
  card.appendChild(ageControl);
  card.appendChild(deleteButton);
  return card;
}

async function loadRoster() {
  try {
    const response = await request("/students/");
    const students = await response.json();
    rosterList.replaceChildren();
    students.forEach((student) => rosterList.appendChild(studentCard(student)));
    clearError();
  } catch (_) {
    // request() already displays the visible, plain-language error.
  }
}

// One delegated listener handles all current and future card controls.
rosterList.addEventListener("click", async (event) => {
  const card = event.target.closest(".student-card");
  if (!card) return;

  const studentId = card.dataset.studentId;
  if (event.target.matches(".save-age-button")) {
    const ageInput = card.querySelector(".age-input");
    const age = Number(ageInput.value);
    if (!Number.isInteger(age) || age <= 0) {
      showError("Age must be a whole number greater than zero.");
      return;
    }
    try {
      const response = await request(`/students/${studentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ age }),
      });
      const updated = await response.json();
      card.querySelector(".student-age").textContent = `Age: ${updated.age}`;
      ageInput.value = String(updated.age);
      clearError();
    } catch (_) {
      // request() has shown the error.
    }
  }

  if (event.target.matches(".delete-button")) {
    try {
      await request(`/students/${studentId}`, { method: "DELETE" });
      card.remove();
      clearError();
    } catch (_) {
      // request() has shown the error.
    }
  }
});

studentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(studentForm);
  const payload = {
    name: String(formData.get("name")).trim(),
    email: String(formData.get("email")).trim(),
    age: Number(formData.get("age")),
  };
  try {
    const response = await request("/students/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const student = await response.json();
    rosterList.appendChild(studentCard(student));
    studentForm.reset();
    clearError();
  } catch (_) {
    // request() has shown the error.
  }
});

function renderSummary(summary) {
  summaryResult.replaceChildren();

  const topic = document.createElement("p");
  topic.textContent = `Topic: ${summary.topic}`;
  const difficulty = document.createElement("p");
  difficulty.textContent = `Difficulty: ${summary.difficulty}`;
  const pointsLabel = document.createElement("p");
  pointsLabel.textContent = "Key points:";
  const points = document.createElement("ul");
  summary.key_points.forEach((point) => {
    const item = document.createElement("li");
    item.textContent = point;
    points.appendChild(item);
  });
  if (summary.key_points.length === 0) {
    const item = document.createElement("li");
    item.textContent = "No note sentences were provided.";
    points.appendChild(item);
  }

  summaryResult.appendChild(topic);
  summaryResult.appendChild(difficulty);
  summaryResult.appendChild(pointsLabel);
  summaryResult.appendChild(points);
}

summaryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await request("/assistant/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: notesInput.value }),
    });
    renderSummary(await response.json());
    clearError();
  } catch (_) {
    // request() has shown the error.
  }
});

function renderNoteSearchResults(results) {
  noteSearchResults.replaceChildren();
  results.forEach((result) => {
    const note = document.createElement("article");
    note.className = "note-result";
    const score = document.createElement("p");
    score.textContent = `Note ${result.id} · similarity ${result.score.toFixed(3)}`;
    const text = document.createElement("p");
    text.textContent = result.text;
    note.appendChild(score);
    note.appendChild(text);
    noteSearchResults.appendChild(note);
  });
}

noteSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await request(`/assistant/search?query=${encodeURIComponent(noteQuery.value)}`);
    renderNoteSearchResults(await response.json());
    clearError();
  } catch (_) {
    // request() has shown the error.
  }
});

loadRoster();
