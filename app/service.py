from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from time import perf_counter
from typing import Dict, List, Optional, Set, Tuple

import requests

from .config import settings
from .ingestion import fetch_all_news
from .pipeline import dedupe_items, rank_items, split_india_world
from .schemas import (
    DigestPoint,
    DigestRequest,
    DigestResponse,
    FetchRequest,
    FetchResponse,
    NewsItem,
    PipelineResponse,
    StorySearchResponse,
    WordPackResponse,
    WordOfDayResponse,
)
from .storage import storage
from .summarizer import summarize_section


IST = timezone(timedelta(hours=5, minutes=30))
_log = logging.getLogger(__name__)
WORD_STOPWORDS = {
    "about",
    "after",
    "against",
    "around",
    "between",
    "cabinet",
    "centre",
    "central",
    "chief",
    "city",
    "could",
    "court",
    "delhi",
    "first",
    "government",
    "india",
    "indian",
    "minister",
    "national",
    "official",
    "state",
    "today",
    "under",
    "union",
    "world",
    "assembly",
    "election",
    "elections",
    "candidate",
    "candidates",
    "campaign",
    "karnataka",
    "kerala",
    "bengal",
    "tamil",
    "nadu",
    "pahalgam",
}

COMMON_CURRENT_AFFAIRS_WORDS = {
    "acquisition",
    "administration",
    "agreement",
    "announcement",
    "committee",
    "consultation",
    "development",
    "expansion",
    "government",
    "implementation",
    "infrastructure",
    "initiative",
    "investment",
    "measures",
    "ministerial",
    "operation",
    "policy",
    "programme",
    "project",
    "rehabilitation",
    "regulation",
    "resolution",
    "security",
    "statement",
    "strategy",
}

WORD_DIFFICULTY_PROFILES: Dict[str, Dict[str, float]] = {
    "easy": {
        "min_len": 5,
        "max_len": 12,
        "max_freq": 3,
    },
    "balanced": {
        "min_len": 5,
        "max_len": 16,
        "max_freq": 2,
    },
    "exam": {
        "min_len": 7,
        "max_len": 18,
        "max_freq": 1,
    },
}


class WordNotFoundError(RuntimeError):
    """Raised when no today India headlines are available for word selection."""


def _normalize_word_difficulty(value: str) -> str:
    normalized = (value or "balanced").strip().lower()
    return normalized if normalized in WORD_DIFFICULTY_PROFILES else "balanced"


def _elapsed_ms(start: float) -> float:
    return (perf_counter() - start) * 1000.0


def _parse_iso_dt(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).astimezone(IST)
    except Exception:
        return None


def _filter_today_india_items(items: List[NewsItem]) -> List[NewsItem]:
    today_ist = datetime.now(IST).date()
    out = []
    for item in items:
        if item.category != "india":
            continue
        dt = _parse_iso_dt(item.published_at or "")
        if dt is None or dt.date() != today_ist:
            continue
        out.append(item)
    return out


def fetch_news_service(request: FetchRequest) -> FetchResponse:
    fetch_total_start = perf_counter()

    feeds = request.rss_feeds or settings.default_rss_feeds
    sources_start = perf_counter()
    items, source_breakdown = fetch_all_news(
        limit_per_source=request.limit_per_source,
        include_newsapi=request.include_newsapi,
        rss_feeds=feeds,
    )
    storage.save_phase_metric(
        phase="fetch.sources",
        duration_ms=_elapsed_ms(sources_start),
        meta={
            "limit_per_source": request.limit_per_source,
            "include_newsapi": request.include_newsapi,
            "rss_feed_count": len(feeds),
        },
    )

    if not items:
        storage.save_phase_metric(
            phase="fetch.total",
            duration_ms=_elapsed_ms(fetch_total_start),
            meta={"total_fetched": 0},
        )
        raise RuntimeError("No news items fetched. Check NEWSAPI key and RSS feed availability.")

    snapshot_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.dict() for item in items],
        "source_breakdown": source_breakdown,
    }
    persist_start = perf_counter()
    snapshot_id = storage.save_raw(snapshot_payload)
    storage.save_phase_metric(
        phase="fetch.persist_snapshot",
        duration_ms=_elapsed_ms(persist_start),
        snapshot_id=snapshot_id,
    )
    storage.save_phase_metric(
        phase="fetch.total",
        duration_ms=_elapsed_ms(fetch_total_start),
        snapshot_id=snapshot_id,
        meta={"total_fetched": len(items), "source_breakdown": source_breakdown},
    )
    return FetchResponse(total_fetched=len(items), snapshot_id=snapshot_id, source_breakdown=source_breakdown)


def generate_digest_service(request: DigestRequest) -> DigestResponse:
    digest_total_start = perf_counter()

    load_start = perf_counter()
    if request.snapshot_id:
        snapshot_data = storage.load_raw(request.snapshot_id)
        snapshot_id = request.snapshot_id
    else:
        snapshot_id, snapshot_data = storage.latest_raw()
    storage.save_phase_metric(
        phase="digest.load_snapshot",
        duration_ms=_elapsed_ms(load_start),
        snapshot_id=snapshot_id,
    )

    prep_start = perf_counter()
    raw_items = [NewsItem(**item) for item in snapshot_data.get("items", [])]
    deduped = dedupe_items(raw_items)
    ranked = rank_items(deduped)
    grouped = split_india_world(ranked)
    storage.save_phase_metric(
        phase="digest.prepare_rank",
        duration_ms=_elapsed_ms(prep_start),
        snapshot_id=snapshot_id,
        meta={"raw_items": len(raw_items), "deduped_items": len(deduped), "ranked_items": len(ranked)},
    )

    model = request.model or settings.ollama_model
    india_candidates = grouped["india"][: settings.summarizer_max_items_per_section]
    world_candidates = grouped["world"][: settings.summarizer_max_items_per_section]

    india_start = perf_counter()
    india_points: List[DigestPoint] = summarize_section(india_candidates, request.max_bullets, model)
    storage.save_phase_metric(
        phase="digest.summarize_india",
        duration_ms=_elapsed_ms(india_start),
        snapshot_id=snapshot_id,
        meta={"input_items": len(india_candidates), "output_points": len(india_points)},
    )

    world_start = perf_counter()
    world_points: List[DigestPoint] = summarize_section(world_candidates, request.max_bullets, model)
    storage.save_phase_metric(
        phase="digest.summarize_world",
        duration_ms=_elapsed_ms(world_start),
        snapshot_id=snapshot_id,
        meta={"input_items": len(world_candidates), "output_points": len(world_points)},
    )

    response = DigestResponse(
        snapshot_id=snapshot_id,
        model=model,
        india_points=india_points,
        world_points=world_points,
        total_input_items=len(raw_items),
        total_ranked_items=len(ranked),
    )

    persist_start = perf_counter()
    storage.save_digest(snapshot_id, response.dict())
    storage.save_phase_metric(
        phase="digest.persist",
        duration_ms=_elapsed_ms(persist_start),
        snapshot_id=snapshot_id,
    )
    storage.save_phase_metric(
        phase="digest.total",
        duration_ms=_elapsed_ms(digest_total_start),
        snapshot_id=snapshot_id,
        meta={"model": model, "max_bullets": request.max_bullets},
    )
    return response


def run_pipeline_service(fetch_request: FetchRequest, digest_request: Optional[DigestRequest] = None) -> PipelineResponse:
    pipeline_start = perf_counter()
    fetch_result = fetch_news_service(fetch_request)
    digest_seed = digest_request or DigestRequest()
    digest_result = generate_digest_service(
        DigestRequest(snapshot_id=fetch_result.snapshot_id, model=digest_seed.model, max_bullets=digest_seed.max_bullets)
    )
    storage.save_phase_metric(
        phase="pipeline.total",
        duration_ms=_elapsed_ms(pipeline_start),
        snapshot_id=fetch_result.snapshot_id,
    )
    return PipelineResponse(fetch=fetch_result, digest=digest_result)


def get_metrics_summary_service(snapshot_id: str = "", limit: int = 200) -> dict:
    return storage.get_phase_metrics_summary(snapshot_id=snapshot_id or None, limit=limit)


def get_metrics_trend_service(phase: str = "", snapshot_id: str = "", limit: int = 30) -> dict:
    return storage.get_phase_metrics_trend(
        phase=phase,
        snapshot_id=snapshot_id or None,
        limit=limit,
    )


def search_stories_service(
    query: str,
    limit: int = 20,
    category: str = "",
    source: str = "",
    days: int = 0,
) -> StorySearchResponse:
    rows = storage.search_stories(
        query=query,
        limit=limit,
        category=category,
        source=source,
        days=days,
    )
    return StorySearchResponse(
        query=query,
        limit=max(1, min(limit, 100)),
        category=category,
        source=source,
        days=max(0, days),
        total=len(rows),
        results=rows,
    )


def _score_word_token(token: str, doc_freq: int, corpus_freq: int, resolved_difficulty: str, min_len: int) -> float:
    if resolved_difficulty == "easy":
        preferred_len_penalty = 0.25 * abs(len(token) - 8)
        familiarity_bonus = 1.2 if corpus_freq in {1, 2} else 0.4
        return (2.0 if doc_freq <= 2 else 0.8) + familiarity_bonus - preferred_len_penalty

    rarity_bonus = 3.4 if doc_freq == 1 else (1.7 if doc_freq == 2 else 0.5)
    corpus_penalty = 0.7 * max(corpus_freq - 2, 0)
    length_score = 0.35 * min(max(len(token) - min_len, 0), 8)
    suffix_penalty = 0.0
    if token.endswith(("tion", "ment", "sion", "ality", "ness")):
        suffix_penalty = 1.0 if resolved_difficulty == "exam" else 0.7
    return rarity_bonus + length_score - corpus_penalty - suffix_penalty


def _collect_word_tokens(
    india_items: List[NewsItem],
    min_len: int,
    max_len: int,
    max_freq: int,
    banned: set,
) -> Tuple[Counter, Counter, Dict[str, List[str]]]:
    token_to_headlines: Dict[str, List[str]] = defaultdict(list)
    token_counts: Counter = Counter()
    token_global_counts: Counter = Counter()

    for item in india_items:
        text = f"{item.title} {item.snippet}".lower()
        token_global_counts.update(re.findall(rf"[a-z]{{{min_len},{max_len}}}", text))

    for item in india_items:
        text = f"{item.title} {item.snippet}".lower()
        unique_tokens = set(re.findall(rf"[a-z]{{{min_len},{max_len}}}", text))
        for token in unique_tokens:
            if token in WORD_STOPWORDS or token in COMMON_CURRENT_AFFAIRS_WORDS:
                continue
            if token in banned or token.isdigit():
                continue
            if len(re.findall(rf"\b{re.escape(token)}\b", text)) > max_freq:
                continue
            token_counts[token] += 1
            token_to_headlines[token].append(item.title)

    return token_counts, token_global_counts, token_to_headlines


def _select_word_candidate(
    india_items: List[NewsItem],
    difficulty: str = "balanced",
    exclude_words: Optional[Set[str]] = None,
) -> Tuple[str, str, str]:
    resolved_difficulty = _normalize_word_difficulty(difficulty)
    profile = WORD_DIFFICULTY_PROFILES[resolved_difficulty]
    min_len = int(profile["min_len"])
    max_len = int(profile["max_len"])
    max_freq = int(profile["max_freq"])
    banned = {w.strip().lower() for w in (exclude_words or set()) if w.strip()}

    token_counts, token_global_counts, token_to_headlines = _collect_word_tokens(
        india_items, min_len, max_len, max_freq, banned
    )

    if not token_counts:
        fallback = india_items[0].title.split()[0] if india_items else "policy"
        headline = india_items[0].title if india_items else "No India headline found"
        return fallback.lower(), headline, "Selected fallback term due to low lexical diversity in source set."

    def _score(kv: Tuple[str, int]) -> Tuple[float, int]:
        token, doc_freq = kv
        corpus_freq = int(token_global_counts.get(token, 0))
        return _score_word_token(token, doc_freq, corpus_freq, resolved_difficulty, min_len), len(token)

    ranked = sorted(token_counts.items(), key=_score, reverse=True)
    word = ranked[0][0]
    headline = token_to_headlines[word][0]
    note = (
        f"Picked from today's India headlines using {resolved_difficulty} difficulty scoring "
        f"(headline_frequency={token_counts[word]}, corpus_frequency={token_global_counts[word]})."
    )
    return word, headline, note


def _is_valid_word_candidate(
    candidate: str,
    india_items: List[NewsItem],
    difficulty: str = "balanced",
    exclude_words: Optional[Set[str]] = None,
) -> bool:
    resolved_difficulty = _normalize_word_difficulty(difficulty)
    profile = WORD_DIFFICULTY_PROFILES[resolved_difficulty]
    min_len = int(profile["min_len"])
    max_len = int(profile["max_len"])
    max_freq = int(profile["max_freq"])
    banned = {w.strip().lower() for w in (exclude_words or set()) if w.strip()}

    if not re.fullmatch(rf"[a-z]{{{min_len},{max_len}}}", candidate):
        return False
    if candidate in WORD_STOPWORDS or candidate in COMMON_CURRENT_AFFAIRS_WORDS:
        return False
    if candidate in banned:
        return False

    text = " ".join(f"{item.title} {item.snippet}".lower() for item in india_items)
    if not re.search(rf"\b{re.escape(candidate)}\b", text):
        return False

    freq = len(re.findall(rf"\b{re.escape(candidate)}\b", text))
    return freq <= max_freq


def _model_pick_word(
    india_items: List[NewsItem],
    difficulty: str = "balanced",
    exclude_words: Optional[Set[str]] = None,
) -> str:
    resolved_difficulty = _normalize_word_difficulty(difficulty)
    banned = {w.strip().lower() for w in (exclude_words or set()) if w.strip()}
    profile_hint = {
        "easy": "Pick a clear but somewhat uncommon word that is still easy to understand.",
        "balanced": "Pick an uncommon but understandable word suitable for daily learning.",
        "exam": "Pick a more advanced and less frequent word useful for exam-oriented vocabulary.",
    }
    lines = []
    for idx, item in enumerate(india_items[:30], start=1):
        lines.append(f"{idx}. {item.title}")
    news_text = "\n".join(lines)
    banned_clause = f"Do not choose any of these words: {', '.join(sorted(banned))}. " if banned else ""

    payload = {
        "model": settings.ollama_model,
        "prompt": (
            "From the following Indian current-affairs headlines, choose ONE uncommon English vocabulary word "
            "that is relevant to the topics. Avoid proper nouns, person names, place names, party names, and acronyms. "
            f"Difficulty: {resolved_difficulty}. {profile_hint[resolved_difficulty]} "
            f"{banned_clause}"
            "Return strict JSON only in this shape: {\"word\":\"lowercaseword\"}.\n\n"
            f"HEADLINES:\n{news_text}"
        ),
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        resp = requests.post(f"{settings.ollama_base_url}/api/generate", json=payload, timeout=45)
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        data = json.loads(raw)
        candidate = str(data.get("word", "")).strip().lower()
        if _is_valid_word_candidate(candidate, india_items, resolved_difficulty, banned):
            return candidate
    except Exception as exc:
        _log.debug(
            "Ollama word-pick failed (url=%s model=%s): %s",
            settings.ollama_base_url,
            settings.ollama_model,
            exc,
        )
    return ""


def _pick_word_entry(
    india_items: List[NewsItem],
    snapshot_id: str,
    difficulty: str,
    exclude_words: Optional[Set[str]] = None,
) -> WordOfDayResponse:
    model_word = _model_pick_word(india_items, difficulty, exclude_words)
    word, headline, note = _select_word_candidate(india_items, difficulty, exclude_words)
    resolved_difficulty = _normalize_word_difficulty(difficulty)
    if model_word:
        word = model_word
        note = (
            "Picked by model from today's India headlines with non-proper-noun constraint "
            f"at {resolved_difficulty} difficulty."
        )
        for item in india_items:
            text = f"{item.title} {item.snippet}".lower()
            if re.search(rf"\b{re.escape(word)}\b", text):
                headline = item.title
                break

    definition = _generate_quick_definition(word, headline)
    return WordOfDayResponse(
        snapshot_id=snapshot_id,
        word=word,
        context_headline=headline,
        relevance_note=note,
        definition=definition,
        difficulty=resolved_difficulty,
    )


def _dictionary_definition(word: str) -> str:
    try:
        resp = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=6)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            return ""
        meanings = payload[0].get("meanings", [])
        for meaning in meanings:
            defs = meaning.get("definitions", [])
            for row in defs:
                text = " ".join(str(row.get("definition", "")).split())
                if text:
                    return text
    except Exception:
        return ""
    return ""


def _heuristic_definition(word: str, headline: str) -> str:
    context = " ".join(headline.split())
    templates = {
        "ity": f"In current-affairs usage, '{word}' refers to the quality or condition highlighted in: {context}.",
        "tion": f"In current-affairs usage, '{word}' refers to an action or policy process highlighted in: {context}.",
        "ment": f"In current-affairs usage, '{word}' refers to an official process or outcome highlighted in: {context}.",
        "ship": f"In current-affairs usage, '{word}' refers to a role or relationship highlighted in: {context}.",
    }
    for suffix, sentence in templates.items():
        if word.endswith(suffix):
            return sentence
    return f"In current-affairs usage, '{word}' is a topic-linked term appearing in: {context}."


def _generate_quick_definition(word: str, headline: str) -> str:
    payload = {
        "model": settings.ollama_model,
        "prompt": (
            f"Define the word '{word}' in plain English in one short line, "
            f"and keep it relevant to this Indian current-affairs headline: {headline}"
        ),
        "stream": False,
        "options": {"temperature": 0.2},
    }
    try:
        resp = requests.post(f"{settings.ollama_base_url}/api/generate", json=payload, timeout=45)
        resp.raise_for_status()
        text = " ".join(resp.json().get("response", "").split())
        if text:
            return text
    except Exception:
        pass

    dictionary_text = _dictionary_definition(word)
    if dictionary_text:
        return dictionary_text

    return _heuristic_definition(word, headline)


def word_of_day_service(
    limit_per_source: int = 25,
    difficulty: str = "balanced",
    no_repeat_days: int = 0,
) -> WordOfDayResponse:
    resolved_difficulty = _normalize_word_difficulty(difficulty)
    bounded_no_repeat_days = max(0, int(no_repeat_days))
    total_start = perf_counter()
    fetch_result = fetch_news_service(
        FetchRequest(
            limit_per_source=limit_per_source,
            include_newsapi=bool(settings.newsapi_key),
        )
    )
    snapshot_data = storage.load_raw(fetch_result.snapshot_id)
    items = [NewsItem(**item) for item in snapshot_data.get("items", [])]
    today_india_items = _filter_today_india_items(items)

    if not today_india_items:
        storage.save_phase_metric(
            phase="word_of_day.total",
            duration_ms=_elapsed_ms(total_start),
            snapshot_id=fetch_result.snapshot_id,
            meta={"today_india_items": 0},
        )
        raise WordNotFoundError("No India headlines from today were found. Try again shortly.")

    recent_words = set(storage.get_recent_vocab_words(days=bounded_no_repeat_days)) if bounded_no_repeat_days > 0 else set()
    result = _pick_word_entry(
        india_items=today_india_items,
        snapshot_id=fetch_result.snapshot_id,
        difficulty=resolved_difficulty,
        exclude_words=recent_words,
    )
    storage.save_vocab_word(
        word=result.word,
        snapshot_id=result.snapshot_id,
        difficulty=result.difficulty,
        context_headline=result.context_headline,
    )

    storage.save_phase_metric(
        phase="word_of_day.total",
        duration_ms=_elapsed_ms(total_start),
        snapshot_id=fetch_result.snapshot_id,
        meta={
            "today_india_items": len(today_india_items),
            "word": result.word,
            "difficulty": resolved_difficulty,
            "no_repeat_days": bounded_no_repeat_days,
        },
    )
    return result


def word_pack_service(
    limit_per_source: int = 25,
    difficulty: str = "balanced",
    count: int = 5,
    no_repeat_days: int = 14,
) -> WordPackResponse:
    resolved_difficulty = _normalize_word_difficulty(difficulty)
    bounded_count = max(1, min(int(count), 10))
    bounded_no_repeat_days = max(0, int(no_repeat_days))

    fetch_result = fetch_news_service(
        FetchRequest(
            limit_per_source=limit_per_source,
            include_newsapi=bool(settings.newsapi_key),
        )
    )
    snapshot_data = storage.load_raw(fetch_result.snapshot_id)
    items = [NewsItem(**item) for item in snapshot_data.get("items", [])]
    today_india_items = _filter_today_india_items(items)
    if not today_india_items:
        raise WordNotFoundError("No India headlines from today were found. Try again shortly.")

    recent_words = set(storage.get_recent_vocab_words(days=bounded_no_repeat_days)) if bounded_no_repeat_days > 0 else set()
    chosen: List[WordOfDayResponse] = []
    used_words: Set[str] = set(recent_words)

    for _ in range(bounded_count):
        pick = _pick_word_entry(
            india_items=today_india_items,
            snapshot_id=fetch_result.snapshot_id,
            difficulty=resolved_difficulty,
            exclude_words=used_words,
        )
        if pick.word.lower() in used_words:
            break
        used_words.add(pick.word.lower())
        storage.save_vocab_word(
            word=pick.word,
            snapshot_id=pick.snapshot_id,
            difficulty=pick.difficulty,
            context_headline=pick.context_headline,
        )
        chosen.append(pick)

    return WordPackResponse(
        snapshot_id=fetch_result.snapshot_id,
        difficulty=resolved_difficulty,
        no_repeat_days=bounded_no_repeat_days,
        count=len(chosen),
        items=chosen,
    )


def generate_today_india_digest_service(limit_per_source: int = 20, model: str = "", max_bullets: int = 12) -> DigestResponse:
    total_start = perf_counter()
    fetch_result = fetch_news_service(
        FetchRequest(
            limit_per_source=limit_per_source,
            include_newsapi=bool(settings.newsapi_key),
        )
    )

    snapshot_data = storage.load_raw(fetch_result.snapshot_id)
    raw_items = [NewsItem(**item) for item in snapshot_data.get("items", [])]
    today_india_items = _filter_today_india_items(raw_items)
    if not today_india_items:
        storage.save_phase_metric(
            phase="digest.today_india.total",
            duration_ms=_elapsed_ms(total_start),
            snapshot_id=fetch_result.snapshot_id,
            meta={"today_india_items": 0},
        )
        raise RuntimeError("No India headlines from today were found. Try again shortly.")

    prep_start = perf_counter()
    deduped = dedupe_items(today_india_items)
    ranked = rank_items(deduped)
    storage.save_phase_metric(
        phase="digest.today_india.prepare_rank",
        duration_ms=_elapsed_ms(prep_start),
        snapshot_id=fetch_result.snapshot_id,
        meta={"raw_items": len(today_india_items), "deduped_items": len(deduped), "ranked_items": len(ranked)},
    )

    chosen_model = model or settings.ollama_model
    candidates = ranked[: settings.summarizer_max_items_per_section]

    summary_start = perf_counter()
    india_points: List[DigestPoint] = summarize_section(candidates, max_bullets, chosen_model)
    storage.save_phase_metric(
        phase="digest.today_india.summarize",
        duration_ms=_elapsed_ms(summary_start),
        snapshot_id=fetch_result.snapshot_id,
        meta={"input_items": len(candidates), "output_points": len(india_points)},
    )

    response = DigestResponse(
        snapshot_id=fetch_result.snapshot_id,
        model=chosen_model,
        india_points=india_points,
        world_points=[],
        total_input_items=len(today_india_items),
        total_ranked_items=len(ranked),
    )
    storage.save_digest(fetch_result.snapshot_id, response.dict())

    storage.save_phase_metric(
        phase="digest.today_india.total",
        duration_ms=_elapsed_ms(total_start),
        snapshot_id=fetch_result.snapshot_id,
        meta={"model": chosen_model, "max_bullets": max_bullets},
    )
    return response


def format_digest_text(response: DigestResponse) -> str:
    lines = []
    lines.append(f"Snapshot: {response.snapshot_id}")
    lines.append(f"Model: {response.model}")
    lines.append(f"Input items: {response.total_input_items} | Ranked items: {response.total_ranked_items}")
    lines.append("")
    lines.append("INDIA")
    lines.append("-----")
    if response.india_points:
        for idx, item in enumerate(response.india_points, start=1):
            src = ", ".join(item.sources[:2]) if item.sources else "unknown"
            lines.append(f"{idx}. {item.point} [{src}]")
    else:
        lines.append("No India items found.")

    lines.append("")
    lines.append("WORLD")
    lines.append("-----")
    if response.world_points:
        for idx, item in enumerate(response.world_points, start=1):
            src = ", ".join(item.sources[:2]) if item.sources else "unknown"
            lines.append(f"{idx}. {item.point} [{src}]")
    else:
        lines.append("No World items found.")

    return "\n".join(lines)


def format_india_digest_text(response: DigestResponse) -> str:
    lines = []
    lines.append(f"Snapshot: {response.snapshot_id}")
    lines.append(f"Model: {response.model}")
    lines.append(f"Input items: {response.total_input_items} | Ranked items: {response.total_ranked_items}")
    lines.append("")
    lines.append("INDIA (TODAY)")
    lines.append("-------------")
    if response.india_points:
        for idx, item in enumerate(response.india_points, start=1):
            src = ", ".join(item.sources[:2]) if item.sources else "unknown"
            lines.append(f"{idx}. {item.point} [{src}]")
    else:
        lines.append("No India items found for today.")
    return "\n".join(lines)


def get_latest_digest_snapshot() -> DigestResponse:
    """
    Load the latest saved digest snapshot from storage.
    Returns an empty DigestResponse if no digest is found.
    """
    try:
        with storage._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM digests
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        
        if row:
            payload = json.loads(row[0])
            return DigestResponse(**payload)
    except Exception as exc:
        _log.debug("Failed to load latest digest: %s", exc)
    
    # Fallback: return empty digest
    return DigestResponse(
        snapshot_id="",
        model="",
        india_points=[],
        world_points=[],
        total_input_items=0,
        total_ranked_items=0,
    )
