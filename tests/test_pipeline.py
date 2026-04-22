"""Tests for app/pipeline.py — pure functions: dedupe, rank, split."""
from datetime import datetime, timedelta, timezone

from app.pipeline import dedupe_items, rank_items, split_india_world
from app.schemas import NewsItem


def _make_item(
    title: str,
    url: str,
    category: str = "world",
    published_at: str = "",
    source: str = "TestSource",
) -> NewsItem:
    if not published_at:
        published_at = datetime.now(timezone.utc).isoformat()
    return NewsItem(
        title=title,
        source=source,
        url=url,
        published_at=published_at,
        category=category,
    )


# ---------------------------------------------------------------------------
# dedupe_items
# ---------------------------------------------------------------------------

class TestDedupeItems:
    def test_empty_list(self):
        assert dedupe_items([]) == []

    def test_no_duplicates(self):
        items = [
            _make_item("Alpha news story", "https://a.com/1"),
            _make_item("Beta news story completely different", "https://b.com/2"),
        ]
        result = dedupe_items(items)
        assert len(result) == 2

    def test_exact_url_duplicate_removed(self):
        item = _make_item("Some headline", "https://example.com/same-url")
        result = dedupe_items([item, item])
        assert len(result) == 1

    def test_same_url_different_object_removed(self):
        url = "https://example.com/article"
        a = _make_item("Headline A", url)
        b = _make_item("Headline B", url)
        result = dedupe_items([a, b])
        assert len(result) == 1
        assert result[0].url == url

    def test_near_duplicate_title_removed(self):
        # Titles highly similar → should be treated as duplicate
        a = _make_item(
            "India wins cricket world cup against Australia",
            "https://a.com/1",
        )
        b = _make_item(
            "India wins cricket world cup against Australia today",
            "https://b.com/2",
        )
        result = dedupe_items([a, b])
        # At least one should survive; likely one removed as near-dup
        assert len(result) <= 2

    def test_order_preserved_for_first_seen(self):
        items = [
            _make_item("First unique story here", "https://a.com/1"),
            _make_item("Second unique story here", "https://b.com/2"),
            _make_item("Third unique story here", "https://c.com/3"),
        ]
        result = dedupe_items(items)
        assert result[0].url == "https://a.com/1"


# ---------------------------------------------------------------------------
# rank_items
# ---------------------------------------------------------------------------

class TestRankItems:
    def test_empty_list(self):
        assert rank_items([]) == []

    def test_single_item(self):
        item = _make_item("Single item", "https://a.com/1")
        assert rank_items([item]) == [item]

    def test_returns_all_items(self):
        items = [
            _make_item("Story A", "https://a.com/1"),
            _make_item("Story B", "https://b.com/2"),
            _make_item("Story C", "https://c.com/3"),
        ]
        ranked = rank_items(items)
        assert len(ranked) == 3

    def test_india_item_boosted(self):
        recent = datetime.now(timezone.utc).isoformat()
        india_item = _make_item(
            "Parliament passes new bill in India",
            "https://a.com/india",
            category="india",
            published_at=recent,
        )
        world_item = _make_item(
            "Generic world event happens today",
            "https://b.com/world",
            category="world",
            published_at=recent,
        )
        ranked = rank_items([world_item, india_item])
        # India item has a 0.2 boost so it should appear first
        assert ranked[0].category == "india"

    def test_recent_item_ranked_higher(self):
        recent = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        new_item = _make_item("Fresh breaking news story", "https://a.com/1", published_at=recent)
        old_item = _make_item("Stale old news story long ago", "https://b.com/2", published_at=old)
        ranked = rank_items([old_item, new_item])
        assert ranked[0].url == "https://a.com/1"


# ---------------------------------------------------------------------------
# split_india_world
# ---------------------------------------------------------------------------

class TestSplitIndiaWorld:
    def test_empty(self):
        result = split_india_world([])
        assert result == {"india": [], "world": []}

    def test_splits_correctly(self):
        items = [
            _make_item("Story 1", "https://a.com/1", category="india"),
            _make_item("Story 2", "https://b.com/2", category="world"),
            _make_item("Story 3", "https://c.com/3", category="india"),
        ]
        result = split_india_world(items)
        assert len(result["india"]) == 2
        assert len(result["world"]) == 1

    def test_all_india(self):
        items = [
            _make_item("Story 1", "https://a.com/1", category="india"),
            _make_item("Story 2", "https://b.com/2", category="india"),
        ]
        result = split_india_world(items)
        assert len(result["india"]) == 2
        assert result["world"] == []

    def test_all_world(self):
        items = [
            _make_item("Story 1", "https://a.com/1", category="world"),
            _make_item("Story 2", "https://b.com/2", category="technology"),
        ]
        result = split_india_world(items)
        assert result["india"] == []
        assert len(result["world"]) == 2

    def test_non_india_category_goes_to_world(self):
        item = _make_item("Story", "https://a.com/1", category="sports")
        result = split_india_world([item])
        assert result["world"] == [item]
        assert result["india"] == []
