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
        parsed = date_parser.parse(value)
        if parsed.tzinfo is None or parsed.tzinfo.utcoffset(None) is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _category_from_text(title: str, source: str) -> str:
    text = f"{title} {source}".lower()
    india_signals = ["india", "delhi", "mumbai", "bjp", "parliament", "supreme court", "rupee"]
    return "india" if any(token in text for token in india_signals) else "world"


def _resolve_newsdata_key() -> str:
    """Resolve the NewsData.io API key from env settings or as a pub_ fallback from NEWSAPI_KEY."""
    key = getattr(settings, "newsdata_key", "") or ""
    key = str(key).strip()
    if not key:
        alt = getattr(settings, "newsapi_key", "") or ""
        if isinstance(alt, str) and alt.strip().startswith("pub_"):
            _log.info("fetch_newsdata: using NEWSAPI_KEY as NewsData key fallback (public key detected)")
            return alt.strip()
    return key


def _is_public_newsdata_key(key: str) -> bool:
    return isinstance(key, str) and key.strip().startswith("pub_")


def fetch_newsdata(limit_per_source: int) -> List[NewsItem]:
    """Fetch articles from NewsData.io (https://newsdata.io).
    Uses NEWSDATA_KEY from env or UI config.
    For private keys, query India headlines (`country=in`) in English.
    For public keys, fallback to language-only query due to parameter restrictions.
    Pagination is used when `nextPage` is provided so fetches can exceed one page.
    """
    key = _resolve_newsdata_key()
    if not key:
        return []

    is_public_key = _is_public_newsdata_key(key)
    url = "https://newsdata.io/api/1/news"
    base_params = {"apikey": key, "language": "en"}
    if not is_public_key:
        base_params["country"] = "in"

    all_items: List[NewsItem] = []
    seen_urls = set()
    next_page = None
    max_pages = 10

    try:
        for _ in range(max_pages):
            if len(all_items) >= limit_per_source:
                break

            params = dict(base_params)
            if next_page:
                params["page"] = next_page

            _log.info("fetch_newsdata: requesting %s params=%s", url, _mask_params(params))
            resp = requests.get(url, params=params, timeout=20)
            _log.info("fetch_newsdata: response status=%s", resp.status_code)
            resp.raise_for_status()
            payload = resp.json()
            _log.debug("fetch_newsdata: payload keys=%s", list(payload.keys()) if isinstance(payload, dict) else type(payload))

            results = payload.get("results", [])
            if not isinstance(results, list) or not results:
                break

            for article in results:
                if len(all_items) >= limit_per_source:
                    break
                title = _safe_text(article.get("title", ""))
                if not title:
                    continue
                source = _safe_text(article.get("source_id", "NewsData"))
                link = _normalize_url(article.get("link", "") or article.get("url", ""))
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)
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

            next_page = payload.get("nextPage")
            if not next_page:
                break
    except Exception:
        _log.exception("fetch_newsdata failed")
        return []

    return all_items


def fetch_rss(rss_feeds: List[str], limit_per_source: int) -> List[NewsItem]:
    """Fetch articles from a list of RSS feed URLs (sequential).

    This implementation is intentionally sequential and robust: individual
    feed failures are logged and ignored so other feeds can still contribute.
    """
    all_items: List[NewsItem] = []
    if not rss_feeds or feedparser is None:
        return all_items

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
            _log.exception("fetch_rss: failed for feed %s", feed_url)
            continue

    return all_items


def fetch_all_news(limit_per_source: int, rss_feeds: List[str], include_newsdata: bool = True) -> Tuple[List[NewsItem], Dict[str, int]]:
    """Fetch news from NewsData (optional) and RSS feeds.

    Returns (items, source_breakdown).
    """
    items: List[NewsItem] = []
    source_breakdown: Dict[str, int] = {}

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
