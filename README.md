# StudyTrack

StudyTrack is a two-process FastAPI + SQLite dashboard for Myntra's Trainee Enablement team. The plain JavaScript dashboard always calls this repository's FastAPI server at `http://localhost:8000`; it never uses a third-party roster API.

## Run locally

From the `studytrack` directory, create the virtual environment and install the committed, pinned requirements:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
python -m backend.seed_data --reset
uvicorn backend.main:app --reload --port 8000
```

In a second terminal (also from `studytrack`), serve the frontend on the CORS-approved local origin:

```bash
python3 -m http.server 5500 --directory frontend
```

Open `http://localhost:5500`. FastAPI seeds the roster at startup as well, but `python -m backend.seed_data --reset` is the repeatable demo-seeding command. API documentation is at `http://localhost:8000/docs`.

For a deployed frontend, change `API_BASE_URL` in `frontend/app.js` to the deployed Render API URL and set `ALLOWED_ORIGINS` on the backend to include the exact Netlify origin. CORS deliberately names origins and never permits `*`.

## API endpoints

All JSON responses use these shapes:

```json
// Student
{"id": 1, "name": "Aditi Rao", "email": "aditi.rao@example.com", "age": 22}

// Course enrollment
{"id": 1, "course_name": "Retail Foundations", "credits": 3, "student_id": 1}
```

| Method | Path | Request body | Success response |
| --- | --- | --- | --- |
| POST | `/students/` | `{"name":"…","email":"…@…","age":22}` | 201, Student |
| GET | `/students/` | —; optional `?min_age=20` | 200, Student[] |
| GET | `/students/sorted?by=age` | —; `by` is `age` or `name` | 200, insertion-sorted Student[] |
| GET | `/students/search?name=Priya%20Iyer` | —; exact name required | 200, Student; 404 when absent |
| GET | `/students/report?min_age=21` | —; optional minimum age | 200, `{"report":"…","count_meeting_min_age":5}` |
| GET | `/students/{student_id}` | — | 200, Student |
| PATCH | `/students/{student_id}` | Any subset of `name`, `email`, `age` | 200, Student |
| DELETE | `/students/{student_id}` | — | 204, no body |
| GET | `/students/{student_id}/course-count` | — | 200, `{"student_id":1,"course_count":2}` |
| POST | `/courses/` | `{"course_name":"…","credits":3,"student_id":1}` | 201, Course |
| GET | `/courses/` | — | 200, Course[] |
| GET | `/courses/{course_id}` | — | 200, Course |
| PATCH | `/courses/{course_id}` | Any subset of `course_name`, `credits`, `student_id` | 200, Course |
| DELETE | `/courses/{course_id}` | — | 204, no body |
| POST | `/assistant/summarize` | `{"text":"<raw notes>"}` | 200, `{"topic":"…","key_points":["…"],"difficulty":"easy"}` |
| GET | `/assistant/search?query=binary%20search` | — | 200, ranked `[{"id":1,"text":"…","score":1.0}]` |

Missing student or course IDs return 404. Duplicate student emails return 409; invalid input returns FastAPI/Pydantic 422. The email validator requires `@`, ages must be positive, and credits must be 1–6.

`GET /students/{student_id}/course-count` uses `select(func.count(Course.id)).where(Course.student_id == student_id)` in `backend/crud.py`, so SQL performs the aggregate; it never counts a Python list. The seeded Aditi record has two enrollments for a ready-made walkthrough.

## Algorithms engine

`GET /students/sorted?by=age` loads the live database roster and applies the project’s in-place Insertion Sort; it returns Farhan, Rohan, Meera, Priya, Aditi, Devansh, Sameer, then Kavya by age. Insertion Sort is O(n²) in the worst case because a reverse-ordered list shifts nearly every prior item for each new item. Its best case is O(n) for an already sorted roster, because each outer-loop pass performs one comparison and no shifts. `GET /students/search?name=Priya%20Iyer` first builds a name-sorted copy, then runs the hand-written iterative Binary Search and returns Priya’s record. Binary Search requires the list to be sorted by the search field because its left-or-right decision discards half only when all smaller and larger values are predictably arranged. `GET /students/report?min_age=21` returns the multi-line roster and the visible-accumulator count, which is 5 for the seed data.

## AI Helper

The grading demonstration uses the default **mock** mode: it is fully offline and makes no LLM or embedding API calls. The mock summarizer chooses the first non-empty note line as its title-like topic, takes up to three sentences split on `.`, `!`, or `?`, and rates difficulty as easy below 40 words, medium at 40–100 words, and hard above 100. `GET /assistant/search` uses fixed 12-word count vectors and a hand-written cosine calculation; an empty or out-of-vocabulary query returns all five notes at score `0.0` in id order. An optional real summarizer uses Google Gemini's `generate_content` endpoint through the `google-genai` Python SDK when `AI_MODE=real` and `GOOGLE_API_KEY` is set as a private environment variable; no API key is committed anywhere in this repository.

To enable Gemini locally without adding a secret to a file, set `AI_MODE=real` and `GOOGLE_API_KEY` in the terminal environment before starting Uvicorn. `GEMINI_MODEL` is optional and defaults to `gemini-2.0-flash`.

If a real mode were enabled later, this is the exact structured prompt it would send to the LLM:

```text
Task: Summarize the study notes below.
Context: The notes are supplied verbatim after NOTES.
Constraints: Return exactly three fields. Use a concise title-like topic, give at most three key points, and set difficulty to exactly easy, medium, or hard. Do not include commentary, markdown, or extra fields.
Format instructions: Return valid JSON only, matching this schema exactly:
{"topic":"string","key_points":["string"],"difficulty":"easy|medium|hard"}
NOTES:
{{raw_text}}
```

## Dashboard walkthrough

1. Open `http://localhost:5500`; the initial `GET http://localhost:8000/students/` renders the seeded trainee cards.
2. Change a card's inline age, click **Save Age**, and observe `PATCH /students/{id}` with `{"age": …}`. The card updates without a reload. The backend logs `Updated student id=…`.
3. Submit the Add a trainee form. The `POST /students/` response is appended immediately as a new card; the backend logs `Created student id=…`.
4. Click **Delete**. `DELETE /students/{id}` returns 204 and the card is removed; the backend logs `Deleted student id=…`.
5. Stop the API or use browser offline mode. The dashboard shows the visible message “Could not reach the StudyTrack backend…” instead of relying on an alert or console output.

The roster container and each card have explicit margin, padding, and borders. Its two-column layout switches to one column at widths below 600px.

### Example API activity

```text
GET /students/                         200 OK
GET /students/sorted?by=age            200 OK  Farhan Sheikh (18) … Kavya Nair (25)
GET /students/search?name=Priya%20Iyer 200 OK  {"id":5,"name":"Priya Iyer","email":"priya.iyer@example.com","age":21}
GET /students/report?min_age=21        200 OK  {"count_meeting_min_age":5,"report":"[Age 22] Aditi Rao <aditi.rao@example.com>…"}
POST /assistant/summarize               200 OK  {"topic":"Binary Search","key_points":["Binary Search is fast"],"difficulty":"easy"}
GET /assistant/search?query=binary      200 OK  [{"id":1,"score":0.7071067811865475,"text":"Binary search requires…"}, …]
PATCH /students/1  {"age": 23}          200 OK  {"id":1,"name":"Aditi Rao","email":"aditi.rao@example.com","age":23}
POST /students/  {"name":"Nila","email":"nila@myntra.com","age":21}
                                        201 Created  {"id":6,"name":"Nila","email":"nila@myntra.com","age":21}
DELETE /students/6                     204 No Content

INFO Updated student id=1
INFO Created student id=6
INFO Deleted student id=6
```
