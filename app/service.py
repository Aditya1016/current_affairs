from datetime import datetime, timezone
from time import perf_counter
from typing import List, Optional

from .config import settings
from .ingestion import fetch_all_news
from .pipeline import dedupe_items, rank_items, split_india_world
from .schemas import DigestPoint, DigestRequest, DigestResponse, FetchRequest, FetchResponse, NewsItem, PipelineResponse
from .storage import storage
from .summarizer import summarize_section


def _elapsed_ms(start: float) -> float:
    return (perf_counter() - start) * 1000.0


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
