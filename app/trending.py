"""Trending topics detection and ranking from story snapshots."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from .schemas import NewsItem
from .storage import storage

IST = timezone(timedelta(hours=5, minutes=30))


def _extract_entities(text: str) -> List[str]:
    """Extract capitalized multi-word phrases as potential entities/topics.

    Simple heuristic: uppercase words at start of phrases (capitalized proper nouns).
    """
    import re
    # Find capitalized words and phrases (2-4 words)
    phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', text)
    return [p for p in phrases if len(p.split()) <= 3 and len(p) > 3]


def detect_trending_topics(  # noqa: C901
    days: int = 7, min_occurrences: int = 3, limit: int = 10
) -> List[Dict[str, object]]:
    """Detect trending topics from recent snapshots.

    Args:
        days: look back this many days
        min_occurrences: topic must appear in at least this many stories
        limit: return top N topics

    Returns:
        List of trending topics sorted by frequency, with sample stories.
    """
    since = datetime.now(IST) - timedelta(days=days)
    snapshots = storage.get_recent_snapshots(limit=100)

    topic_counter: Counter = Counter()
    topic_stories: Dict[str, List[NewsItem]] = defaultdict(list)
    # Track how many snapshots each topic appears in (for accurate percentage)
    topic_snapshot_count: Counter = Counter()

    filtered_count = 0
    for snapshot_data in snapshots:
        if not snapshot_data.get("items"):
            continue
        # Try multiple known timestamp keys for backward compatibility
        snap_time = (
            snapshot_data.get("generated_at")
            or snapshot_data.get("created_at")
            or snapshot_data.get("timestamp")
        )
        if not snap_time:
            # No usable timestamp — skip to avoid including out-of-window data
            continue
        try:
            snap_dt = datetime.fromisoformat(snap_time.replace('Z', '+00:00')).astimezone(IST)
            if snap_dt < since:
                continue
        except Exception:
            continue

        filtered_count += 1
        snapshot_topics: set = set()
        for item_data in snapshot_data["items"]:
            # Extract topics from title and snippet
            title_entities = _extract_entities(item_data.get("title", ""))
            snippet_entities = _extract_entities(item_data.get("snippet", ""))
            all_entities = set(title_entities + snippet_entities)

            for entity in all_entities:
                topic_counter[entity] += 1
                snapshot_topics.add(entity)
                if len(topic_stories[entity]) < 5:  # keep up to 5 samples
                    topic_stories[entity].append(
                        NewsItem(
                            title=item_data.get("title", ""),
                            source=item_data.get("source", ""),
                            url=item_data.get("url", ""),
                            snippet=item_data.get("snippet", ""),
                            published_at=item_data.get("published_at"),
                            category=item_data.get("category", "world"),
                        )
                    )

        for topic in snapshot_topics:
            topic_snapshot_count[topic] += 1

    # Filter and rank — percentage = fraction of snapshots containing the topic
    trending = [
        {
            "topic": topic,
            "frequency": count,
            "percentage": round(100 * topic_snapshot_count[topic] / max(filtered_count, 1), 1),
            "sample_stories": [
                {
                    "title": s.title,
                    "source": s.source,
                    "url": s.url,
                    "category": s.category,
                }
                for s in topic_stories[topic][:3]
            ],
        }
        for topic, count in topic_counter.most_common()
        if count >= min_occurrences
    ]

    return trending[:limit]


def get_trending_by_category(  # noqa: C901
    category: str = "india", days: int = 7, limit: int = 5, min_occurrences: int = 1
) -> List[Dict[str, object]]:
    """Get trending topics for a specific category."""
    since = datetime.now(IST) - timedelta(days=days)
    snapshots = storage.get_recent_snapshots(limit=100)

    topic_counter: Counter = Counter()
    topic_stories: Dict[str, List[NewsItem]] = defaultdict(list)
    topic_snapshot_count: Counter = Counter()

    filtered_count = 0
    for snapshot_data in snapshots:
        if not snapshot_data.get("items"):
            continue
        snap_time = (
            snapshot_data.get("generated_at")
            or snapshot_data.get("created_at")
            or snapshot_data.get("timestamp")
        )
        if not snap_time:
            continue
        try:
            snap_dt = datetime.fromisoformat(snap_time.replace('Z', '+00:00')).astimezone(IST)
            if snap_dt < since:
                continue
        except Exception:
            continue

        filtered_count += 1
        snapshot_topics: set = set()
        for item_data in snapshot_data["items"]:
            if item_data.get("category", "world").lower() != category.lower():
                continue

            title_entities = _extract_entities(item_data.get("title", ""))
            snippet_entities = _extract_entities(item_data.get("snippet", ""))
            all_entities = set(title_entities + snippet_entities)

            for entity in all_entities:
                topic_counter[entity] += 1
                snapshot_topics.add(entity)
                if len(topic_stories[entity]) < 3:
                    topic_stories[entity].append(
                        NewsItem(
                            title=item_data.get("title", ""),
                            source=item_data.get("source", ""),
                            url=item_data.get("url", ""),
                            snippet=item_data.get("snippet", ""),
                            published_at=item_data.get("published_at"),
                            category=item_data.get("category", "world"),
                        )
                    )

        for topic in snapshot_topics:
            topic_snapshot_count[topic] += 1

    trending = [
        {
            "topic": topic,
            "frequency": count,
            "percentage": min(100.0, round(100 * topic_snapshot_count[topic] / max(filtered_count, 1), 1)),
            "category": category,
            "sample_stories": [
                {
                    "title": s.title,
                    "source": s.source,
                    "url": s.url,
                }
                for s in topic_stories[topic][:2]
            ],
        }
        for topic, count in topic_counter.most_common()
        if count >= min_occurrences
    ]

    return trending[:limit]
