from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List

from .config import settings
from .schemas import NewsItem


def _hours_since(iso_dt: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    return max((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 0.0)


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def dedupe_items(items: List[NewsItem]) -> List[NewsItem]:
    unique: List[NewsItem] = []
    seen_urls = set()

    for item in items:
        if item.url in seen_urls:
            continue

        is_duplicate = False
        for prev in unique:
            if _title_similarity(item.title, prev.title) >= settings.similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            unique.append(item)
            seen_urls.add(item.url)

    return unique


def _score_item(item: NewsItem, corroboration_count: int) -> float:
    recency_weight = max(0.0, 1.0 - (_hours_since(item.published_at or "") / 24.0))
    india_boost = 0.2 if item.category == "india" else 0.0
    corroboration_boost = min(corroboration_count, 4) * 0.1
    return recency_weight + india_boost + corroboration_boost


def rank_items(items: List[NewsItem]) -> List[NewsItem]:
    # Corroboration is approximated via similarity overlap in titles.
    scores: Dict[str, float] = {}
    for i, item in enumerate(items):
        corroboration = 0
        for j, other in enumerate(items):
            if i == j:
                continue
            if _title_similarity(item.title, other.title) >= 0.55:
                corroboration += 1
        scores[item.url] = _score_item(item, corroboration)

    return sorted(items, key=lambda x: scores.get(x.url, 0.0), reverse=True)


def split_india_world(items: List[NewsItem]) -> Dict[str, List[NewsItem]]:
    india = [item for item in items if item.category == "india"]
    world = [item for item in items if item.category != "india"]
    return {"india": india, "world": world}
