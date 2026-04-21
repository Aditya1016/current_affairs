from fastapi import FastAPI, HTTPException

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
)
from .service import fetch_news_service, generate_digest_service, run_pipeline_service
from .service import get_metrics_summary_service

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
