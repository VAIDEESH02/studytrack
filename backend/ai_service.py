"""Offline, deterministic AI-helper functions for StudyTrack."""

from __future__ import annotations

import json
import math
import os
import re
from typing import TypedDict
from google import genai
from google.genai import types

class StudyNote(TypedDict):
    id: int
    text: str


class RankedNote(StudyNote):
    score: float


# This exact in-memory dataset is intentionally separate from the roster database.
notes: list[StudyNote] = [
    {"id": 1, "text": "Binary search requires a sorted array and repeatedly halves the search range using a midpoint comparison."},
    {"id": 2, "text": "Insertion sort builds a sorted list one element at a time by shifting larger elements to the right."},
    {"id": 3, "text": "FastAPI uses Pydantic models to validate request bodies and automatically generates Swagger documentation."},
    {"id": 4, "text": "SQL joins combine rows from two tables using a matching column, such as inner join, left join, and full join."},
    {"id": 5, "text": "Prompt engineering structures a task, context, constraints, and desired output format to guide an LLM's response."},
]

VOCABULARY = [
    "sort",
    "search",
    "binary",
    "insertion",
    "sql",
    "join",
    "fastapi",
    "pydantic",
    "prompt",
    "llm",
    "database",
    "validate",
]

REAL_SUMMARY_PROMPT = """Task: Summarize the study notes below.
Context: The notes are supplied verbatim after NOTES.
Constraints: Return exactly three fields. Use a concise title-like topic, give at
most three key points, and set difficulty to exactly easy, medium, or hard. Do
not include commentary, markdown, or extra fields.
Format instructions: Return valid JSON only, matching this schema exactly:
{"topic":"string","key_points":["string"],"difficulty":"easy|medium|hard"}
NOTES:
"""


class AIServiceError(RuntimeError):
    """Raised when explicitly requested real-mode generation cannot run."""


def _validate_real_summary(payload: object) -> dict[str, object]:
    """Make the optional provider response use the same fixed summary shape."""
    if not isinstance(payload, dict):
        raise AIServiceError("Gemini returned a summary in an unexpected format")
    topic = payload.get("topic")
    key_points = payload.get("key_points")
    difficulty = payload.get("difficulty")
    if (
        not isinstance(topic, str)
        or not isinstance(key_points, list)
        or not all(isinstance(point, str) for point in key_points)
        or difficulty not in {"easy", "medium", "hard"}
    ):
        raise AIServiceError("Gemini did not return the required summary fields")
    return {"topic": topic, "key_points": key_points[:3], "difficulty": difficulty}


def _summarize_with_gemini(raw_text: str) -> dict[str, object]:
    """Optional Google Gemini implementation; never runs in default mock mode."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise AIServiceError("AI_MODE=real requires GOOGLE_API_KEY to be configured")
    try:

        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction="You are a helpful assistant.",
            response_mime_type="application/json")
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=f"{REAL_SUMMARY_PROMPT}{raw_text}",
            config=config,
        )
        response_text = response.text
        if response_text is None:
            raise AIServiceError("Gemini returned no summary text")
        return _validate_real_summary(json.loads(response_text))
    except AIServiceError:
        raise
    except Exception as error:
        raise AIServiceError("Gemini could not generate a summary") from error


def summarize_notes(raw_text: str) -> dict[str, object]:
    """Return the fixed mock-summary shape without any network call.

    The topic rule takes the first non-empty line as a title-like label. Difficulty
    is easy for fewer than 40 words, medium for 40–100, and hard above 100.
    """
    if os.getenv("AI_MODE", "mock").lower() == "real":
        return _summarize_with_gemini(raw_text)

    stripped_text = raw_text.strip()
    if not stripped_text:
        return {"topic": "untitled", "key_points": [], "difficulty": "easy"}

    non_empty_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    topic = non_empty_lines[0] if non_empty_lines else "untitled"
    key_points = [sentence.strip() for sentence in re.split(r"[.!?]+", raw_text) if sentence.strip()][:3]
    word_count = len(re.findall(r"[A-Za-z0-9]+", raw_text))

    if word_count < 40:
        difficulty = "easy"
    elif word_count <= 100:
        difficulty = "medium"
    else:
        difficulty = "hard"

    return {"topic": topic, "key_points": key_points, "difficulty": difficulty}


def mock_embed(text: str) -> list[float]:
    """Build the required fixed-vocabulary word-count vector, entirely offline."""
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    token_counts = {word: 0 for word in VOCABULARY}
    for token in tokens:
        if token in token_counts:
            token_counts[token] += 1
    return [float(token_counts[word]) for word in VOCABULARY]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity from the dot product and vector magnitudes."""
    dot_product = 0.0
    magnitude_a_squared = 0.0
    magnitude_b_squared = 0.0

    for value_a, value_b in zip(vec_a, vec_b):
        dot_product += value_a * value_b
        magnitude_a_squared += value_a * value_a
        magnitude_b_squared += value_b * value_b

    magnitude_a = math.sqrt(magnitude_a_squared)
    magnitude_b = math.sqrt(magnitude_b_squared)
    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0
    return dot_product / (magnitude_a * magnitude_b)


def search_notes(query: str) -> list[RankedNote]:
    """Rank the sample notes by mock-embedding similarity, highest score first."""
    query_embedding = mock_embed(query)
    ranked_notes: list[RankedNote] = []
    for note in notes:
        score = cosine_similarity(query_embedding, mock_embed(note["text"]))
        ranked_notes.append({"id": note["id"], "text": note["text"], "score": score})

    # Python's stable sort retains original id order when zero-score ties occur.
    return sorted(ranked_notes, key=lambda note: note["score"], reverse=True)
