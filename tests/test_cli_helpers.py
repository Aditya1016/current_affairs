import pytest


def test_get_phase_avg_ms(monkeypatch):
    pytest.importorskip("rich")
    import app.cli as cli

    def fake_metrics(limit=200):
        return {"phases": [{"phase": "digest.total", "avg_ms": 2500}]}

    monkeypatch.setattr(cli, "get_metrics_summary_service", fake_metrics)
    assert cli._get_phase_avg_ms("digest.total") == 2500.0


def test_build_phase_table(monkeypatch):
    pytest.importorskip("rich")
    import app.cli as cli
    from rich.table import Table
    from io import StringIO
    from rich.console import Console

    def fake_metrics(limit=200):
        return {
            "phases": [
                {"phase": "digest.summarize_india", "avg_ms": 2000},
                {"phase": "digest.summarize_world", "avg_ms": 3000},
                {"phase": "other.phase", "avg_ms": 1000},
            ]
        }

    monkeypatch.setattr(cli, "get_metrics_summary_service", fake_metrics)
    table = cli._build_phase_table("digest")
    assert isinstance(table, Table)
    # Render to string and verify only digest.* rows appear (other.phase must be absent)
    buf = StringIO()
    c = Console(file=buf, no_color=True, width=120)
    c.print(table)
    rendered = buf.getvalue()
    assert "digest.summarize_india" in rendered
    assert "digest.summarize_world" in rendered
    assert "other.phase" not in rendered
    # Also confirm exactly 2 data columns
    assert len(table.columns) == 2


def test_parse_pick_indexes_basic():
    pytest.importorskip("rich")
    import app.cli as cli

    assert cli._parse_pick_indexes("2", 12) == [2]
    assert cli._parse_pick_indexes("2,5", 12) == [2, 5]
    assert cli._parse_pick_indexes("2-4", 12) == [2, 3, 4]


def test_parse_pick_indexes_freeform_and_bounds():
    pytest.importorskip("rich")
    import app.cli as cli

    assert cli._parse_pick_indexes("2 from list", 12) == [2]
    assert cli._parse_pick_indexes("99", 12) == []
    assert cli._parse_pick_indexes("4-2", 12) == [2, 3, 4]
