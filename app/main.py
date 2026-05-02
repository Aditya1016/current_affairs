from fastapi import FastAPI, HTTPException, Query

from .config import settings
from .benchmark import run_model_benchmark
from .schemas import (
    BenchmarkRequest,
    BenchmarkResponse,
    DigestRequest,
    DigestResponse,
    FetchRequest,
    FetchResponse,
    PipelineResponse,
    StorySearchResponse,
    WordPackResponse,
    WordOfDayResponse,
)
from .service import fetch_news_service, generate_digest_service, run_pipeline_service
from .service import get_metrics_summary_service
from .service import get_metrics_trend_service
from .service import search_stories_service
from .service import word_pack_service
from .service import word_of_day_service
from .service import WordNotFoundError

app = FastAPI(title="Current Affairs Backend", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.ollama_model,
        "data_dir": settings.data_dir,
    }


@app.post("/fetch-news", response_model=FetchResponse)
def fetch_news(request: FetchRequest) -> FetchResponse:
    try:
        return fetch_news_service(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/generate-digest", response_model=DigestResponse)
def generate_digest(request: DigestRequest) -> DigestResponse:
    try:
        return generate_digest_service(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/run-pipeline", response_model=PipelineResponse)
def run_pipeline(request: FetchRequest) -> PipelineResponse:
    try:
        return run_pipeline_service(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/benchmark-models", response_model=BenchmarkResponse)
def benchmark_models(request: BenchmarkRequest) -> BenchmarkResponse:
    try:
        report = run_model_benchmark(
            snapshot_id=request.snapshot_id,
            models=request.models,
            max_bullets=request.max_bullets,
        )
        return BenchmarkResponse(**report)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/metrics/summary")
def metrics_summary(snapshot_id: str = "", limit: int = 50) -> dict:
    return get_metrics_summary_service(snapshot_id=snapshot_id, limit=limit)


@app.get("/metrics/trend")
def metrics_trend(phase: str = "", snapshot_id: str = "", limit: int = 30) -> dict:
    return get_metrics_trend_service(phase=phase, snapshot_id=snapshot_id, limit=limit)


@app.get("/word/today", response_model=WordOfDayResponse)
def word_today(
    limit_per_source: int = Query(default=25, ge=5, le=100),
    difficulty: str = "balanced",
    no_repeat_days: int = Query(default=14, ge=0, le=365),
) -> WordOfDayResponse:
    try:
        return word_of_day_service(
            limit_per_source=limit_per_source,
            difficulty=difficulty,
            no_repeat_days=no_repeat_days,
        )
    except WordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/word/pack", response_model=WordPackResponse)
def word_pack(
    limit_per_source: int = Query(default=25, ge=5, le=100),
    difficulty: str = "balanced",
    count: int = Query(default=5, ge=1, le=10),
    no_repeat_days: int = Query(default=14, ge=0, le=365),
) -> WordPackResponse:
    try:
        return word_pack_service(
            limit_per_source=limit_per_source,
            difficulty=difficulty,
            count=count,
            no_repeat_days=no_repeat_days,
        )
    except WordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/stories/search", response_model=StorySearchResponse)
def search_stories(
    q: str = "",
    limit: int = 20,
    category: str = "",
    source: str = "",
    days: int = 0,
) -> StorySearchResponse:
    return search_stories_service(
        query=q,
        limit=limit,
        category=category,
        source=source,
        days=days,
    )
