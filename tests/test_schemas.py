"""Tests for app/schemas.py — Pydantic model validation."""
import pytest
from pydantic import ValidationError

from app.schemas import (
    BenchmarkRequest,
    DigestPoint,
    DigestRequest,
    DigestResponse,
    FetchRequest,
    FetchResponse,
    NewsItem,
)


# ---------------------------------------------------------------------------
# NewsItem
# ---------------------------------------------------------------------------

class TestNewsItem:
    def test_minimal_required_fields(self):
        item = NewsItem(title="Headline", source="BBC", url="https://bbc.com/1")
        assert item.title == "Headline"
        assert item.source == "BBC"
        assert item.url == "https://bbc.com/1"

    def test_defaults(self):
        item = NewsItem(title="T", source="S", url="https://example.com")
        assert item.snippet == ""
        assert item.published_at is None
        assert item.category == "world"

    def test_custom_values(self):
        item = NewsItem(
            title="T",
            source="S",
            url="https://example.com",
            snippet="Some text",
            published_at="2024-01-01T00:00:00Z",
            category="india",
        )
        assert item.snippet == "Some text"
        assert item.category == "india"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            NewsItem(title="T", source="S")  # url missing


# ---------------------------------------------------------------------------
# FetchRequest
# ---------------------------------------------------------------------------

class TestFetchRequest:
    def test_defaults(self):
        req = FetchRequest()
        assert req.limit_per_source == 25
        assert req.include_newsapi is True
        assert req.rss_feeds is None

    def test_custom(self):
        req = FetchRequest(limit_per_source=10, include_newsapi=False)
        assert req.limit_per_source == 10
        assert req.include_newsapi is False

    def test_limit_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            FetchRequest(limit_per_source=4)  # ge=5

    def test_limit_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            FetchRequest(limit_per_source=101)  # le=100


# ---------------------------------------------------------------------------
# FetchResponse
# ---------------------------------------------------------------------------

class TestFetchResponse:
    def test_construction(self):
        resp = FetchResponse(
            total_fetched=42,
            snapshot_id="20240101T120000Z",
            source_breakdown={"BBC": 10, "CNN": 32},
        )
        assert resp.total_fetched == 42
        assert resp.snapshot_id == "20240101T120000Z"
        assert resp.source_breakdown["BBC"] == 10


# ---------------------------------------------------------------------------
# DigestRequest
# ---------------------------------------------------------------------------

class TestDigestRequest:
    def test_defaults(self):
        req = DigestRequest()
        assert req.snapshot_id is None
        assert req.model is None
        assert req.max_bullets == 12

    def test_bullets_bounds(self):
        with pytest.raises(ValidationError):
            DigestRequest(max_bullets=5)  # ge=6
        with pytest.raises(ValidationError):
            DigestRequest(max_bullets=21)  # le=20


# ---------------------------------------------------------------------------
# DigestPoint / DigestResponse
# ---------------------------------------------------------------------------

class TestDigestPoint:
    def test_construction(self):
        pt = DigestPoint(point="Some news point", sources=["BBC", "CNN"])
        assert pt.point == "Some news point"
        assert len(pt.sources) == 2


class TestDigestResponse:
    def _make(self):
        return DigestResponse(
            snapshot_id="20240101T120000Z",
            model="test-model",
            india_points=[DigestPoint(point="India pt", sources=["Hindu"])],
            world_points=[DigestPoint(point="World pt", sources=["BBC"])],
            total_input_items=50,
            total_ranked_items=30,
        )

    def test_construction(self):
        resp = self._make()
        assert resp.snapshot_id == "20240101T120000Z"
        assert len(resp.india_points) == 1
        assert len(resp.world_points) == 1

    def test_counts(self):
        resp = self._make()
        assert resp.total_input_items == 50
        assert resp.total_ranked_items == 30


# ---------------------------------------------------------------------------
# BenchmarkRequest
# ---------------------------------------------------------------------------

class TestBenchmarkRequest:
    def test_defaults(self):
        req = BenchmarkRequest(snapshot_id="snap-1")
        assert req.snapshot_id == "snap-1"
        assert len(req.models) > 0
        assert req.max_bullets == 12

    def test_custom_models(self):
        req = BenchmarkRequest(snapshot_id="snap-1", models=["a", "b"])
        assert req.models == ["a", "b"]
