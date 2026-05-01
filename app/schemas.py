from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    snippet: str = ""
    published_at: Optional[str] = None
    category: str = "world"


class FetchRequest(BaseModel):
    limit_per_source: int = Field(default=25, ge=5, le=100)
    include_newsapi: bool = True
    rss_feeds: Optional[List[str]] = None


class FetchResponse(BaseModel):
    total_fetched: int
    snapshot_id: str
    source_breakdown: Dict[str, int]


class DigestRequest(BaseModel):
    snapshot_id: Optional[str] = None
    model: Optional[str] = None
    max_bullets: int = Field(default=12, ge=6, le=20)


class DigestPoint(BaseModel):
    point: str
    sources: List[str]


class DigestResponse(BaseModel):
    snapshot_id: str
    model: str
    india_points: List[DigestPoint]
    world_points: List[DigestPoint]
    total_input_items: int
    total_ranked_items: int


class PipelineResponse(BaseModel):
    fetch: FetchResponse
    digest: DigestResponse


class StorySearchResult(BaseModel):
    id: int
    url: str
    title: str
    snippet: str = ""
    source: str = ""
    category: str = "world"
    published_at: str = ""
    last_seen_snapshot: str = ""
    rank: float = 0.0


class StorySearchResponse(BaseModel):
    query: str
    limit: int
    category: str = ""
    source: str = ""
    days: int = 0
    total: int
    results: List[StorySearchResult]


class BenchmarkRequest(BaseModel):
    snapshot_id: str
    models: List[str] = Field(
        default_factory=lambda: [
            "qwen3.5:9b",
            "deepseek-r1:7b",
            "qwen2.5-coder:7b",
            "qwen2.5:7b-instruct",
            "mistral:7b-instruct",
        ]
    )
    max_bullets: int = Field(default=12, ge=6, le=20)


class BenchmarkResponse(BaseModel):
    snapshot_id: str
    generated_at: str
    results: List[Dict[str, object]]


class WordOfDayResponse(BaseModel):
    snapshot_id: str
    word: str
    context_headline: str
    relevance_note: str
    definition: str
    difficulty: str = "balanced"


class WordPackResponse(BaseModel):
    snapshot_id: str
    difficulty: str = "balanced"
    no_repeat_days: int = 14
    count: int
    items: List[WordOfDayResponse]
