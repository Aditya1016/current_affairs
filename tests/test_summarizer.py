from app.summarizer import parse_model_response
from app.schemas import NewsItem


def sample_items():
    return [
        NewsItem(title="Alpha event", source="SourceA", url="http://a", snippet="s1", category="world"),
        NewsItem(title="Beta update", source="SourceB", url="http://b", snippet="s2", category="world"),
        NewsItem(title="Gamma news", source="SourceC", url="http://c", snippet="s3", category="world"),
    ]


def test_parse_valid_json():
    text = '[{"point": "Alpha happened.", "sources": ["SourceA"]}, {"point": "Beta updated.", "sources": ["SourceB"]}]'
    pts = parse_model_response(text, items=sample_items(), max_bullets=3)
    assert len(pts) == 2
    assert pts[0].point.startswith("Alpha")


def test_parse_with_trailing_text():
    text = '[{"point": "Alpha happened.", "sources": ["SourceA"]}]\nSome commentary by model.'
    pts = parse_model_response(text, items=sample_items(), max_bullets=3)
    assert len(pts) == 1
    assert pts[0].point.startswith("Alpha")


def test_parse_python_literal_single_quotes():
    text = "[{'point': 'Gamma news surfaced.', 'sources': ['SourceC']}]"
    pts = parse_model_response(text, items=sample_items(), max_bullets=3)
    assert len(pts) == 1
    assert pts[0].point.startswith("Gamma")


def test_malformed_fallback():
    text = 'not a json at all... <html>'
    pts = parse_model_response(text, items=sample_items(), max_bullets=2)
    # parse_model_response returns [] on failure; caller should fallback
    assert pts == []
