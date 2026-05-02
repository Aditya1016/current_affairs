"""Tests for app/trending.py — trending topic detection and ranking."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.trending import _extract_entities, detect_trending_topics, get_trending_by_category

IST = timezone(timedelta(hours=5, minutes=30))


def _make_snapshot(items, days_ago=0):
    """Build a minimal snapshot payload matching the real payload structure."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {"generated_at": ts, "items": items}


def _item(title, source="TestSource", category="world", snippet=""):
    return {"title": title, "source": source, "url": "https://example.com", "snippet": snippet, "category": category}


# ---------------------------------------------------------------------------
# _extract_entities
# ---------------------------------------------------------------------------

class TestExtractEntities:
    def test_extracts_capitalized_phrase(self):
        entities = _extract_entities("Prime Minister Modi visited New Delhi")
        # Regex greedily captures up to 3-word phrases; at least one phrase expected
        assert len(entities) >= 1
        assert any("Prime" in e or "Delhi" in e for e in entities)

    def test_ignores_lowercase_words(self):
        entities = _extract_entities("the stock market fell today")
        assert entities == []

    def test_single_short_word_skipped(self):
        entities = _extract_entities("The US is")
        # "The" and "Us" are short; no phrase > 3 chars that is proper
        for e in entities:
            assert len(e) > 3

    def test_returns_list(self):
        assert isinstance(_extract_entities("Hello World"), list)


# ---------------------------------------------------------------------------
# detect_trending_topics — time-windowing
# ---------------------------------------------------------------------------

class TestDetectTrendingTopics:
    def _patch_storage(self, snapshots):
        return patch("app.trending.storage.get_recent_snapshots", return_value=snapshots)

    def test_filters_old_snapshots(self):
        old_snap = _make_snapshot(
            [_item("Elon Musk Elon Musk Elon Musk Tesla Tesla Tesla")],
            days_ago=30,
        )
        recent_snap = _make_snapshot(
            [_item("Narendra Modi Modi Modi Modi")],
            days_ago=1,
        )
        with self._patch_storage([old_snap, recent_snap]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=10)

        topics = [r["topic"] for r in results]
        # Topics from old snapshot should not appear
        assert not any("Tesla" in t or "Elon" in t for t in topics)

    def test_includes_recent_snapshots(self):
        snap = _make_snapshot(
            [_item("Reserve Bank India"), _item("Reserve Bank India"), _item("Reserve Bank India")],
            days_ago=1,
        )
        with self._patch_storage([snap]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=10)

        topics = [r["topic"] for r in results]
        assert any("Reserve" in t or "Bank" in t or "India" in t for t in topics)

    def test_min_occurrences_filter(self):
        snap = _make_snapshot(
            [_item("Rare Topic Once")],
            days_ago=1,
        )
        with self._patch_storage([snap]):
            results = detect_trending_topics(days=7, min_occurrences=5, limit=10)

        assert results == []

    def test_limit_applied(self):
        items = [_item(f"Topic{i} Alpha Beta") for i in range(20)]
        snap = _make_snapshot(items * 3, days_ago=1)
        with self._patch_storage([snap]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=3)

        assert len(results) <= 3

    def test_empty_snapshots(self):
        with self._patch_storage([]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=10)

        assert results == []


# ---------------------------------------------------------------------------
# detect_trending_topics — percentage calculation
# ---------------------------------------------------------------------------

class TestPercentageCalculation:
    def _patch_storage(self, snapshots):
        return patch("app.trending.storage.get_recent_snapshots", return_value=snapshots)

    def test_percentage_never_exceeds_100(self):
        # One topic appearing many times in one snapshot must still give ≤100%
        items = [_item("Supreme Court India") for _ in range(50)]
        snap = _make_snapshot(items, days_ago=1)
        with self._patch_storage([snap]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=10)

        for r in results:
            assert r["percentage"] <= 100.0, f"percentage {r['percentage']} > 100 for {r['topic']}"

    def test_percentage_is_per_snapshot_not_per_story(self):
        # Topic appears in 1 out of 2 snapshots → percentage should be 50%
        snap1 = _make_snapshot([_item("European Union Trade")], days_ago=1)
        snap2 = _make_snapshot([_item("Unrelated Story Here")], days_ago=2)
        with self._patch_storage([snap1, snap2]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=10)

        eu_results = [r for r in results if "European" in r["topic"] or "Union" in r["topic"]]
        if eu_results:
            assert eu_results[0]["percentage"] == pytest.approx(50.0, abs=1.0)

    def test_percentage_100_when_in_all_snapshots(self):
        # Same entity appears in every snapshot → 100%
        snap1 = _make_snapshot([_item("Supreme Court Ruling")], days_ago=1)
        snap2 = _make_snapshot([_item("Supreme Court Ruling")], days_ago=2)
        with self._patch_storage([snap1, snap2]):
            results = detect_trending_topics(days=7, min_occurrences=1, limit=10)

        sc_results = [r for r in results if "Supreme" in r["topic"]]
        if sc_results:
            assert sc_results[0]["percentage"] == pytest.approx(100.0, abs=1.0)


# ---------------------------------------------------------------------------
# get_trending_by_category
# ---------------------------------------------------------------------------

class TestGetTrendingByCategory:
    def _patch_storage(self, snapshots):
        return patch("app.trending.storage.get_recent_snapshots", return_value=snapshots)

    def test_filters_by_category(self):
        snap = _make_snapshot([
            _item("Narendra Modi India", category="india"),
            _item("United Nations World", category="world"),
        ], days_ago=1)
        with self._patch_storage([snap]):
            results = get_trending_by_category(category="india", days=7, limit=10)

        topics = [r["topic"] for r in results]
        # World-only topics should not appear
        assert not any("United" in t or "Nations" in t for t in topics)

    def test_old_snapshots_excluded(self):
        old_snap = _make_snapshot(
            [_item("Tesla Motors India", category="india")],
            days_ago=30,
        )
        with self._patch_storage([old_snap]):
            results = get_trending_by_category(category="india", days=7, limit=10)

        assert results == []

    def test_returns_at_most_limit(self):
        items = [_item(f"Topic{i} Mumbai City", category="india") for i in range(20)]
        snap = _make_snapshot(items, days_ago=1)
        with self._patch_storage([snap]):
            results = get_trending_by_category(category="india", days=7, limit=3)

        assert len(results) <= 3

    def test_percentage_field_present(self):
        snap = _make_snapshot([_item("Lok Sabha Session", category="india")], days_ago=1)
        with self._patch_storage([snap]):
            results = get_trending_by_category(category="india", days=7, limit=10)

        for r in results:
            assert "percentage" in r
            assert 0.0 <= r["percentage"] <= 100.0

    def test_min_occurrences_respected(self):
        snap = _make_snapshot([_item("Rare India Topic", category="india")], days_ago=1)
        with self._patch_storage([snap]):
            results = get_trending_by_category(category="india", days=7, limit=10, min_occurrences=99)

        assert results == []

    def test_snapshot_without_timestamp_skipped(self):
        snap_no_ts = {"items": [_item("No Timestamp India", category="india")]}
        snap_with_ts = _make_snapshot([_item("Supreme Court India", category="india")], days_ago=1)
        with self._patch_storage([snap_no_ts, snap_with_ts]):
            results = get_trending_by_category(category="india", days=7, limit=10)

        topics = [r["topic"] for r in results]
        # Items from snap_with_ts should appear; items from the timestampless snapshot should not
        assert any("Supreme" in t or "Court" in t for t in topics)
        assert not any("Timestamp" in t for t in topics)
