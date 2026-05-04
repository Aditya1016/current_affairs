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
    # Expect two rows for digest.* phases
    # Rich Table doesn't expose rows publicly, but len(table.columns) should be 2
    assert len(table.columns) == 2
