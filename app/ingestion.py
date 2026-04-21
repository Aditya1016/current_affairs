from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

import feedparser
import requests
from dateutil import parser as date_parser

from .config import settings
from .schemas import NewsItem

NEWSAPI_BASE = "https://newsapi.org/v2"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    clean = parsed._replace(query="", fragment="")
    return urlunparse(clean)


def _safe_text(value: str) -> str:
    return " ".join((value or "").split())


def _parse_dt(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        return date_parser.parse(value).astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _category_from_text(title: str, source: str) -> str:
    text = f"{title} {source}".lower()
    india_signals = ["india", "delhi", "mumbai", "bjp", "parliament", "supreme court", "rupee"]
    return "india" if any(token in text for token in india_signals) else "world"


def fetch_newsapi(limit_per_source: int) -> List[NewsItem]:
    if not settings.newsapi_key:
        return []

    headers = {"X-Api-Key": settings.newsapi_key, **REQUEST_HEADERS}
    routes = [
        ("top-headlines", {"country": "in", "pageSize": limit_per_source}),
        ("top-headlines", {"language": "en", "pageSize": limit_per_source}),
    ]

    all_items: List[NewsItem] = []
    for route, params in routes:
        resp = requests.get(f"{NEWSAPI_BASE}/{route}", headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        for article in payload.get("articles", []):
            title = _safe_text(article.get("title", ""))
            if not title:
                continue
            source = _safe_text(article.get("source", {}).get("name", "NewsAPI"))
            url = _normalize_url(article.get("url", ""))
            if not url:
                continue
            snippet = _safe_text(article.get("description") or article.get("content") or "")
            published_at = _parse_dt(article.get("publishedAt", ""))
            category = _category_from_text(title, source)
            all_items.append(
                NewsItem(
                    title=title,
                    source=source,
                    url=url,
                    snippet=snippet,
                    published_at=published_at,
                    category=category,
                )
            )
    return all_items


def fetch_rss(rss_feeds: List[str], limit_per_source: int) -> List[NewsItem]:
    all_items: List[NewsItem] = []
    for feed_url in rss_feeds:
        try:
            resp = requests.get(feed_url, timeout=20, headers=REQUEST_HEADERS)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)

            if not parsed.entries:
                continue

            default_source = urlparse(feed_url).netloc or "RSS"
            source_name = _safe_text(parsed.feed.get("title", "")) if parsed.feed else ""
            source_name = source_name or default_source

            entries = parsed.entries[:limit_per_source]
            for entry in entries:
                title = _safe_text(getattr(entry, "title", ""))
                if not title:
                    continue
                link = _normalize_url(getattr(entry, "link", ""))
                if not link:
                    continue
                snippet = _safe_text(getattr(entry, "summary", ""))
                published_raw = getattr(entry, "published", "") or getattr(entry, "updated", "")
                category = _category_from_text(title, source_name)
                all_items.append(
                    NewsItem(
                        title=title,
                        source=source_name,
                        url=link,
                        snippet=snippet,
                        published_at=_parse_dt(published_raw),
                        category=category,
                    )
                )
        except Exception:
            # Ignore per-feed failures so remaining feeds can still contribute.
            continue
    return all_items


def fetch_all_news(limit_per_source: int, include_newsapi: bool, rss_feeds: List[str]) -> Tuple[List[NewsItem], Dict[str, int]]:
    items: List[NewsItem] = []
    source_breakdown: Dict[str, int] = {}

    if include_newsapi:
        try:
            newsapi_items = fetch_newsapi(limit_per_source)
            items.extend(newsapi_items)
            source_breakdown["newsapi"] = len(newsapi_items)
        except Exception:
            source_breakdown["newsapi"] = 0

    try:
        rss_items = fetch_rss(rss_feeds, limit_per_source)
        items.extend(rss_items)
        source_breakdown["rss"] = len(rss_items)
    except Exception:
        source_breakdown["rss"] = 0

    return items, source_breakdown
