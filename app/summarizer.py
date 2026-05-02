import ast
import json
import re
from typing import List, Set

import requests

from .config import settings
from .schemas import DigestPoint, NewsItem


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercased words, removing stop-words and non-alphanumeric tokens."""
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
        "in", "is", "it", "its", "of", "on", "or", "that", "the", "to", "was", "will",
        "with", "this", "these", "which", "who", "what", "when", "where", "why", "how"
    }
    words = re.findall(r'\b\w+\b', text.lower())
    return {w for w in words if w not in stop_words and len(w) > 2}


def _semantic_similarity(text_a: str, text_b: str, threshold: float = 0.6) -> bool:
    """Check if two texts are semantically similar using Jaccard similarity on tokens.

    Returns True if similarity >= threshold (meaning they are TOO similar / duplicates).
    """
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return False
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    if union == 0:
        return False
    similarity = intersection / union
    return similarity >= threshold


def _validate_extractive(point: str, source_text: str, min_coverage: float = 0.3) -> bool:
    """Validate that a bullet point is grounded in source text.

    Returns True if point is SUPPORTED by source (at least min_coverage% of point tokens appear in source).
    """
    point_tokens = _tokenize(point)
    if not point_tokens:
        return True  # empty or generic points pass (conservative)
    source_tokens = _tokenize(source_text)
    supported = len(point_tokens & source_tokens)
    coverage = supported / len(point_tokens)
    return coverage >= min_coverage


def _normalize_length(point: str, target_max: int = 140) -> str:
    """Truncate point to target length if needed, respecting word boundaries."""
    if len(point) <= target_max:
        return point
    truncated = point[:target_max].rsplit(' ', 1)[0]
    return truncated.rstrip('.,;:') + '.'


def _extract_first_json(text: str) -> str:  # noqa: C901
    """Extract the first balanced JSON array or object from text."""
    if not text:
        return ""
    # find first '[' and balance brackets
    start = text.find("[")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    # fallback: try object
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    # wrap single object in array to normalize
                    return f"[{text[start:i+1]}]"
    return ""


def _normalize_and_dedupe(points: List[DigestPoint], max_bullets: int, source_texts: List[str] = None) -> List[DigestPoint]:
    """Deduplicate and validate points using exact/semantic similarity + extractive grounding.

    Args:
        points: list of candidate bullet points
        max_bullets: maximum number to return
        source_texts: optional list of source texts for extractive validation
    """
    seen_points = []
    out = []
    source_corpus = " ".join(source_texts) if source_texts else ""

    for p in points:
        point_text = p.point.strip()
        if not point_text:
            continue

        # Skip if exact duplicate (normalized)
        normalized_key = re.sub(r"\W+", " ", point_text.lower()).strip()
        if any(normalized_key == re.sub(r"\W+", " ", sp.lower()).strip() for sp in seen_points):
            continue

        # Skip if semantically similar to any existing point (threshold=0.65)
        if any(_semantic_similarity(point_text, sp, threshold=0.65) for sp in seen_points):
            continue

        # Validate against source text if provided (should have 30%+ coverage)
        if source_corpus and not _validate_extractive(point_text, source_corpus, min_coverage=0.3):
            continue

        # Normalize length
        normalized_point = _normalize_length(point_text, target_max=140)

        out.append(DigestPoint(point=normalized_point, sources=p.sources))
        seen_points.append(point_text)

        if len(out) >= max_bullets:
            break

    return out


def parse_model_response(text: str, items: List[NewsItem], max_bullets: int) -> List[DigestPoint]:  # noqa: C901
    """Robustly parse model-generated text into DigestPoint list.

    Attempts several strategies: direct json, extracting balanced JSON, ast.literal_eval for
    python-style literals, and returns fallback on failure.
    """
    text = (text or "").strip()
    if not text:
        return []

    # 1) direct JSON
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    # 2) try extracting first balanced JSON array/object
    if parsed is None:
        snippet = _extract_first_json(text)
        if snippet:
            try:
                parsed = json.loads(snippet)
            except Exception:
                parsed = None

    # 3) try python literal eval (handles single quotes)
    if parsed is None:
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            parsed = None

    # Build DigestPoint list if we got a list-like structure
    if isinstance(parsed, dict):
        parsed = [parsed]

    points: List[DigestPoint] = []
    if isinstance(parsed, list):
        for row in parsed:
            if not isinstance(row, dict):
                continue
            point = str(row.get("point", "")).strip()
            sources = [str(s).strip() for s in row.get("sources", []) if str(s).strip()]
            if point:
                points.append(DigestPoint(point=point, sources=sources[:2]))

    # Combine source texts for extractive validation (include both title and snippet)
    source_texts = [f"{item.title}. {item.snippet or ''}" for item in items]
    points = _normalize_and_dedupe(points, max_bullets, source_texts=source_texts)
    if points:
        return points
    # final fallback
    return []


def _compose_prompt(items: List[NewsItem], max_bullets: int, section: str) -> str:
    lines = []
    for idx, item in enumerate(items, start=1):
        lines.append(
            f"{idx}. Title: {item.title}\nSource: {item.source}\nSnippet: {item.snippet}\nURL: {item.url}\n"
        )

    news_block = "\n".join(lines)
    return (
        "You are creating an English-only current affairs digest. "
        "Use ONLY the provided items and do not invent facts. "
        f"Create up to {max_bullets} concise bullet points for the {section} section. "
        "For each bullet include a short statement and 1-2 supporting source names. "
        "Each bullet should be <=140 characters. "
        "RETURN ONLY a valid JSON ARRAY and nothing else. If you cannot comply, reply EXACTLY: []\n\n"
        f"ITEMS:\n{news_block}"
    )


def _fallback_points(items: List[NewsItem], max_bullets: int) -> List[DigestPoint]:
    picked = items[:max_bullets]
    return [DigestPoint(point=item.title, sources=[item.source]) for item in picked]


def summarize_section(items: List[NewsItem], max_bullets: int, model: str) -> List[DigestPoint]:
    if not items:
        return []
    prompt = _compose_prompt(items, max_bullets=max_bullets, section=items[0].category)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }

    try:
        resp = requests.post(f"{settings.ollama_base_url}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        # Ollama returns JSON with a `response` field containing text
        text = resp.json().get("response", "").strip()
        points = parse_model_response(text, items=items, max_bullets=max_bullets)
        return points if points else _fallback_points(items, max_bullets)
    except Exception:
        return _fallback_points(items, max_bullets)
