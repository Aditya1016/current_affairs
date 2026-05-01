"""Tests for word-of-day helper behavior in app/service.py."""

from app.schemas import NewsItem
from app.service import _generate_quick_definition, _normalize_word_difficulty, _select_word_candidate


def _item(title: str, snippet: str = "") -> NewsItem:
    return NewsItem(
        title=title,
        source="Test",
        url=f"https://example.com/{abs(hash(title))}",
        snippet=snippet,
        category="india",
        published_at="2026-05-01T08:00:00+00:00",
    )


class TestWordCandidateSelection:
    def test_prefers_rarer_non_generic_term(self):
        items = [
            _item(
                "High Court upholds land acquisition and rehabilitation package",
                "Rehabilitation norms and acquisition measures continue in policy debate",
            ),
            _item(
                "Cabinet discusses maritime interdiction framework",
                "Interdiction strategy proposed in coastal security review",
            ),
        ]

        word, headline, note = _select_word_candidate(items)
        assert word != "rehabilitation"
        assert headline
        assert "frequency" in note

    def test_exam_difficulty_selection(self):
        items = [
            _item(
                "Government discusses rehabilitation and acquisition package",
                "Policy measures and implementation details continue",
            ),
            _item(
                "Navy expands maritime interdiction posture in littoral zones",
                "Interdiction doctrine updated after security review",
            ),
        ]
        word, _headline, note = _select_word_candidate(items, difficulty="exam")
        assert len(word) >= 7
        assert "difficulty" in note

    def test_excludes_recent_words(self):
        items = [
            _item(
                "Navy expands maritime interdiction posture",
                "Interdiction doctrine revised for coastal patrols",
            ),
            _item(
                "Parliament committee debates tariff recalibration",
                "Recalibration strategy discussed in economic review",
            ),
        ]
        word, _headline, _note = _select_word_candidate(items, difficulty="balanced", exclude_words={"interdiction"})
        assert word != "interdiction"


class TestDifficultyNormalization:
    def test_invalid_difficulty_falls_back_to_balanced(self):
        assert _normalize_word_difficulty("hardcore") == "balanced"


class TestDefinitionFallback:
    def test_definition_never_returns_unavailable_message(self, monkeypatch):
        import app.service as svc

        def _raise_post(*args, **kwargs):
            raise RuntimeError("model unavailable")

        def _raise_get(*args, **kwargs):
            raise RuntimeError("dictionary unavailable")

        monkeypatch.setattr(svc.requests, "post", _raise_post)
        monkeypatch.setattr(svc.requests, "get", _raise_get)

        text = _generate_quick_definition(
            "interdiction",
            "Navy expands coastal interdiction operations after threat inputs",
        )
        assert text
        assert "unavailable" not in text.lower()
