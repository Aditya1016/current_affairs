from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

try:
    import feedparser
except Exception:
    feedparser = None
import requests
from dateutil import parser as date_parser

from .config import settings
from .schemas import NewsItem

import logging


_log = logging.getLogger(__name__)


def _mask_params(params: dict) -> dict:
    if not isinstance(params, dict):
        return params
    out = {}
    for k, v in params.items():
        if str(k).lower() in {"apikey", "api_key", "x-api-key", "x_api_key"}:
            out[k] = "***"
        else:
            out[k] = v
    return out


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
    key = settings.newsapi_key
    if not key:
        return []

    headers = {"X-Api-Key": key, **REQUEST_HEADERS}
    routes = [
        ("top-headlines", {"country": "in", "pageSize": limit_per_source}),
        ("top-headlines", {"language": "en", "pageSize": limit_per_source}),
    ]

    all_items: List[NewsItem] = []
    for route, params in routes:
        try:
            _log.info("fetch_newsapi: requesting %s params=%s", f"{NEWSAPI_BASE}/{route}", _mask_params(params))
            resp = requests.get(f"{NEWSAPI_BASE}/{route}", headers=headers, params=params, timeout=20)
            _log.info("fetch_newsapi: response status=%s", resp.status_code)
            resp.raise_for_status()
            payload = resp.json()
            _log.debug("fetch_newsapi: payload keys=%s", list(payload.keys()) if isinstance(payload, dict) else type(payload))
        except Exception:
            _log.exception("fetch_newsapi failed for route %s", route)
            continue

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


def _resolve_newsdata_key() -> str:
    """Resolve the NewsData.io API key from env settings or as a pub_ fallback from newsapi_key."""
    key = getattr(settings, "newsdata_key", "")
    if not key:
        alt = getattr(settings, "newsapi_key", "")
        if isinstance(alt, str) and alt.strip().startswith("pub_"):
            _log.info("fetch_newsdata: using NEWSAPI_KEY as NewsData key fallback (public key detected)")
            return alt.strip()
    return key


def _is_public_newsdata_key(key: str) -> bool:
    return isinstance(key, str) and key.strip().startswith("pub_")


def fetch_newsdata(limit_per_source: int) -> List[NewsItem]:
    """Fetch articles from NewsData.io (https://newsdata.io).
    Uses NEWSDATA_KEY from env `settings.newsdata_key`. Returns list of NewsItem.
    Public keys may have parameter restrictions, so we use simpler params for them.
    """
    key = _resolve_newsdata_key()
    if not key:
        return []

    is_public_key = _is_public_newsdata_key(key)
    url = "https://newsdata.io/api/1/news"
    # Public keys may have restrictions; use simpler parameters
    if is_public_key:
        params = {"apikey": key, "language": "en"}
        _log.info("fetch_newsdata: public key detected; using minimal params")
    else:
        params = {"apikey": key, "country": "in", "language": "en", "page": 1}

    all_items: List[NewsItem] = []
    try:
        _log.info("fetch_newsdata: requesting %s params=%s", url, _mask_params(params))
        resp = requests.get(url, params=params, timeout=20)
        _log.info("fetch_newsdata: response status=%s", resp.status_code)
        resp.raise_for_status()
        payload = resp.json()
        _log.debug("fetch_newsdata: payload keys=%s", list(payload.keys()) if isinstance(payload, dict) else type(payload))
        # NewsData supports pagination; here we only use first page and trim to limit_per_source
        for article in payload.get("results", [])[:limit_per_source]:
            title = _safe_text(article.get("title", ""))
            if not title:
                continue
            source = _safe_text(article.get("source_id", "NewsData"))
            link = _normalize_url(article.get("link", "") or article.get("url", ""))
            if not link:
                continue
            snippet = _safe_text(article.get("description") or article.get("content") or "")
            published_at = _parse_dt(article.get("pubDate", "") or article.get("pubDateYMD", ""))
            category = _category_from_text(title, source)
            all_items.append(
                NewsItem(
                    title=title,
                    source=source,
                    url=link,
                    snippet=snippet,
                    published_at=published_at,
                    category=category,
                )
            )
    except Exception:
        _log.exception("fetch_newsdata failed")
        return []

    return all_items


def fetch_rss(rss_feeds: List[str], limit_per_source: int) -> List[NewsItem]:
    all_items: List[NewsItem] = []
    if feedparser is None:
        return []
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
            _log.exception("fetch_rss: failed for feed %s", feed_url)
            continue
    return all_items


def _fetch_newsapi_with_fallback(
    limit_per_source: int,
    include_newsdata: bool,
    items: List[NewsItem],
    source_breakdown: Dict[str, int],
) -> None:
    """Fetch from NewsAPI; if it returns nothing and a pub_ key was set, fall back to NewsData."""
    newsapi_items = fetch_newsapi(limit_per_source)
    items.extend(newsapi_items)
    source_breakdown["newsapi"] = len(newsapi_items)
    # Fallback: if NewsAPI returned nothing because a NewsData pub_ key was supplied
    # via NEWSAPI_KEY, try NewsData so the user still gets results.
    if source_breakdown["newsapi"] == 0 and not include_newsdata:
        alt_key = getattr(settings, "newsapi_key", "")
        if isinstance(alt_key, str) and alt_key.strip().startswith("pub_"):
            _log.info("fetch_all_news: detected pub_ key in NEWSAPI_KEY; trying NewsData fallback")
            try:
                newsdata_items = fetch_newsdata(limit_per_source)
                if newsdata_items:
                    items.extend(newsdata_items)
                source_breakdown["newsdata"] = len(newsdata_items)
            except Exception:
                _log.exception("fetch_all_news: newsdata fallback after newsapi returned 0 failed")


def fetch_all_news(
    limit_per_source: int, include_newsapi: bool, rss_feeds: List[str], include_newsdata: bool = False
) -> Tuple[List[NewsItem], Dict[str, int]]:
    items: List[NewsItem] = []
    source_breakdown: Dict[str, int] = {}

    if include_newsapi:
        try:
            _fetch_newsapi_with_fallback(limit_per_source, include_newsdata, items, source_breakdown)
        except Exception:
            _log.exception("fetch_all_news: newsapi fetch failed")
            source_breakdown["newsapi"] = 0

    if include_newsdata:
        try:
            newsdata_items = fetch_newsdata(limit_per_source)
            items.extend(newsdata_items)
            source_breakdown["newsdata"] = len(newsdata_items)
        except Exception:
            _log.exception("fetch_all_news: newsdata fetch failed")
            source_breakdown["newsdata"] = 0

    try:
        rss_items = fetch_rss(rss_feeds, limit_per_source)
        items.extend(rss_items)
        source_breakdown["rss"] = len(rss_items)
    except Exception:
        _log.exception("fetch_all_news: rss fetch failed")
        source_breakdown["rss"] = 0

    _log.info("fetch_all_news: result counts=%s", source_breakdown)
    return items, source_breakdown
