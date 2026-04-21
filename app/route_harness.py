import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .config import settings


SPECIALISTS = {
    "Friday Dev Cycle": ["full dev cycle", "implement", "verify", "ship", "repo hygiene", "ci", "build"],
    "Friday Hook Guardian": ["pre-commit", "hooks", "lint", "format", "quality gates", "husky", "lefthook"],
    "Friday PR Reviewer": ["pr", "pull request", "review", "risk", "release notes", "changelog"],
    "Friday Graph Intelligence": ["graph", "cluster", "similarity", "threshold", "mermaid", "edges", "nodes"],
    "Friday CLI UX Designer": ["ux", "ui", "prompt", "dashboard", "theme", "discoverability", "commands"],
}


def route_prompt(prompt: str) -> List[str]:
    p = prompt.lower()
    scores: Dict[str, int] = {}
    for specialist, keywords in SPECIALISTS.items():
        score = 0
        for kw in keywords:
            if kw in p:
                score += 1
        if score > 0:
            scores[specialist] = score

    if not scores:
        return ["Friday Dev Cycle"]

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_score = ranked[0][1]
    selected = [name for name, score in ranked if score == top_score]

    # For multi-intent prompts, include second specialist if close enough.
    if len(ranked) > 1 and ranked[1][1] >= max(1, top_score - 1):
        if ranked[1][0] not in selected:
            selected.append(ranked[1][0])

    return selected


def run_route_harness(prompts: List[str]) -> Dict[str, object]:
    routed = []
    specialist_counts: Dict[str, int] = {name: 0 for name in SPECIALISTS}

    for prompt in prompts:
        chosen = route_prompt(prompt)
        for specialist in chosen:
            if specialist in specialist_counts:
                specialist_counts[specialist] += 1
        routed.append({"prompt": prompt, "selected_specialists": chosen})

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(settings.data_dir) / "routing"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"routing_harness_{timestamp}.json"

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_count": len(prompts),
        "specialist_counts": specialist_counts,
        "routed": routed,
        "output_file": str(out_path),
    }

    out_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    return result
