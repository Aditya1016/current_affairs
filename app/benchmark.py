import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .config import settings
from .pipeline import dedupe_items, rank_items, split_india_world
from .schemas import DigestPoint, NewsItem
from .storage import storage
from .summarizer import summarize_section


def _score_points(points: List[DigestPoint]) -> Dict[str, float]:
    if not points:
        return {"coverage": 0.0, "conciseness": 0.0}

    with_sources = sum(1 for p in points if p.sources)
    avg_len = sum(len(p.point.split()) for p in points) / len(points)
    coverage = with_sources / len(points)
    conciseness = max(0.0, min(1.0, 1.0 - (max(avg_len - 22, 0) / 30)))
    return {"coverage": round(coverage, 3), "conciseness": round(conciseness, 3)}


def run_model_benchmark(snapshot_id: str, models: List[str], max_bullets: int = 12) -> Dict[str, object]:
    raw = storage.load_raw(snapshot_id)
    raw_items = [NewsItem(**item) for item in raw.get("items", [])]
    ranked = rank_items(dedupe_items(raw_items))
    grouped = split_india_world(ranked)

    results = []
    for model in models:
        started = time.perf_counter()
        india_points = summarize_section(grouped["india"], max_bullets=max_bullets, model=model)
        world_points = summarize_section(grouped["world"], max_bullets=max_bullets, model=model)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        india_score = _score_points(india_points)
        world_score = _score_points(world_points)
        aggregate = round(
            (india_score["coverage"] + world_score["coverage"] + india_score["conciseness"] + world_score["conciseness"])
            / 4,
            3,
        )

        results.append(
            {
                "model": model,
                "latency_ms": elapsed_ms,
                "india_points": len(india_points),
                "world_points": len(world_points),
                "india_score": india_score,
                "world_score": world_score,
                "aggregate_score": aggregate,
            }
        )

    report = {
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": sorted(results, key=lambda row: row["aggregate_score"], reverse=True),
    }

    benchmark_dir = Path(settings.data_dir) / "benchmarks"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    out_path = benchmark_dir / f"{snapshot_id}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report
