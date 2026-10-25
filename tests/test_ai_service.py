from types import SimpleNamespace

import google.genai as genai
import pytest

from backend import ai_service


def words(count: int) -> str:
    return " ".join(["word"] * count)


def test_empty_notes_return_untitled_easy_summary():
    assert ai_service.summarize_notes("   \n ") == {"topic": "untitled", "key_points": [], "difficulty": "easy"}


def test_topic_is_first_line_and_key_points_are_first_three_sentences():
    summary = ai_service.summarize_notes("\nBinary Search\nIt halves. It needs order! Is it fast? Yes.")
    assert summary["topic"] == "Binary Search"
    assert summary["key_points"] == ["Binary Search\nIt halves", "It needs order", "Is it fast"]


@pytest.mark.parametrize(("count", "difficulty"), [(39, "easy"), (40, "medium"), (100, "medium"), (101, "hard")])
def test_difficulty_thresholds(count, difficulty):
    assert ai_service.summarize_notes(words(count))["difficulty"] == difficulty


def test_search_ranks_matching_note_first():
    results = ai_service.search_notes("binary search")
    assert results[0]["id"] == 1
    assert results[0]["score"] > results[1]["score"]


def test_empty_or_unknown_query_returns_all_notes_with_zero_scores_in_id_order():
    for query in ("", "zebra"):
        results = ai_service.search_notes(query)
        assert [r["id"] for r in results] == [1, 2, 3, 4, 5]
        assert all(r["score"] == 0.0 for r in results)


def test_cosine_similarity_handles_zero_vectors():
    assert ai_service.cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert ai_service.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


class FakeGemini:
    """Stands in for google.genai.Client so real mode can be tested offline."""

    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def client(self, api_key):
        self.api_key = api_key
        return SimpleNamespace(models=self)

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "real")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    def install(fake):
        monkeypatch.setattr(genai, "Client", fake.client)
        return fake

    return install


def test_real_mode_requires_api_key(monkeypatch):
    monkeypatch.setenv("AI_MODE", "real")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ai_service.AIServiceError, match="GOOGLE_API_KEY"):
        ai_service.summarize_notes("notes")


def test_real_mode_returns_validated_summary_and_uses_default_model(real_mode):
    fake = real_mode(FakeGemini(text='{"topic": "SQL", "key_points": ["a", "b", "c", "d"], "difficulty": "hard"}'))
    summary = ai_service.summarize_notes("Joins combine rows.")
    assert summary == {"topic": "SQL", "key_points": ["a", "b", "c"], "difficulty": "hard"}
    assert fake.api_key == "test-key"
    assert fake.calls[0]["model"] == ai_service.DEFAULT_GEMINI_MODEL
    assert fake.calls[0]["contents"].endswith("NOTES:\nJoins combine rows.")
    assert fake.calls[0]["config"].response_schema is ai_service.GeminiSummary


def test_real_mode_honours_gemini_model_override(real_mode, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    fake = real_mode(FakeGemini(text='{"topic": "T", "key_points": [], "difficulty": "easy"}'))
    ai_service.summarize_notes("x")
    assert fake.calls[0]["model"] == "gemini-custom"


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        (FakeGemini(text=None), "no summary text"),
        (FakeGemini(text="[1, 2]"), "unexpected format"),
        (FakeGemini(text='{"topic": "T", "key_points": "x", "difficulty": "easy"}'), "required summary fields"),
        (FakeGemini(text='{"topic": "T", "key_points": [], "difficulty": "extreme"}'), "required summary fields"),
        (FakeGemini(text="not json"), "could not generate"),
        (FakeGemini(error=RuntimeError("network down")), "could not generate"),
    ],
)
def test_real_mode_failures_raise_ai_service_error(real_mode, fake, message):
    real_mode(fake)
    with pytest.raises(ai_service.AIServiceError, match=message):
        ai_service.summarize_notes("notes")


def test_summarize_route_returns_mock_summary(client):
    response = client.post("/assistant/summarize", json={"text": "Binary Search\nBinary Search is fast."})
    assert response.status_code == 200
    assert response.json() == {
        "topic": "Binary Search",
        "key_points": ["Binary Search\nBinary Search is fast"],
        "difficulty": "easy",
    }


def test_summarize_route_reports_503_when_real_mode_is_misconfigured(client, monkeypatch):
    monkeypatch.setenv("AI_MODE", "real")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    response = client.post("/assistant/summarize", json={"text": "notes"})
    assert response.status_code == 503
    assert "GOOGLE_API_KEY" in response.json()["detail"]


def test_summarize_route_rejects_oversized_notes(client):
    response = client.post("/assistant/summarize", json={"text": "x" * 20_001})
    assert response.status_code == 422


def test_search_route_ranks_notes(client):
    response = client.get("/assistant/search", params={"query": "binary"})
    assert response.status_code == 200
    assert response.json()[0]["id"] == 1
    # Note 1 says "search" twice and "binary" once, so the score is 1 / sqrt(5).
    assert response.json()[0]["score"] == pytest.approx(0.4472135954999579)
