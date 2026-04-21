import json
from typing import List

import requests

from .config import settings
from .schemas import DigestPoint, NewsItem


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
        "Return valid JSON array where each element has: point (string), sources (array of strings).\n\n"
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
        text = resp.json().get("response", "[]").strip()
        parsed = json.loads(text)
        points = []
        for row in parsed:
            point = str(row.get("point", "")).strip()
            sources = [str(s).strip() for s in row.get("sources", []) if str(s).strip()]
            if point:
                points.append(DigestPoint(point=point, sources=sources[:2]))
        return points[:max_bullets] if points else _fallback_points(items, max_bullets)
    except Exception:
        return _fallback_points(items, max_bullets)
