import ast
import json
import re
from typing import List

import requests

from .config import settings
from .schemas import DigestPoint, NewsItem


def _extract_first_json(text: str) -> str:
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
                    return text[start : i + 1]
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


def _normalize_and_dedupe(points: List[DigestPoint], max_bullets: int) -> List[DigestPoint]:
    seen = set()
    out = []
    for p in points:
        key = re.sub(r"\W+", " ", p.point.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= max_bullets:
            break
    return out


def parse_model_response(text: str, items: List[NewsItem], max_bullets: int) -> List[DigestPoint]:
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

    points = _normalize_and_dedupe(points, max_bullets)
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
