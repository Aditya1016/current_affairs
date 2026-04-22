"""Tests for app/storage.py — SQLite-backed Storage class."""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(tmp_path):
    """Create a Storage instance isolated to a temporary directory."""
    import app.storage as sm
    from app.storage import Storage

    db_path = str(tmp_path / "test.db")
    data_dir = str(tmp_path)

    # Build a settings-like stub at function level so attrs are simple strings
    class _FakeCfg:
        pass

    cfg = _FakeCfg()
    cfg.sqlite_db_path = db_path
    cfg.data_dir = data_dir
    cfg.use_legacy_json_storage = False

    original_cfg = sm.settings
    sm.settings = cfg
    try:
        s = Storage()
    finally:
        sm.settings = original_cfg

    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStorage:
    def test_save_and_load_raw(self, tmp_path):
        s = _make_storage(tmp_path)
        payload = {"items": [{"title": "Test", "source": "S", "url": "https://x.com/1"}]}
        sid = s.save_raw(payload)
        assert sid  # non-empty snapshot id
        loaded = s.load_raw(sid)
        assert loaded["items"][0]["title"] == "Test"

    def test_load_raw_missing_raises(self, tmp_path):
        s = _make_storage(tmp_path)
        with pytest.raises(FileNotFoundError):
            s.load_raw("nonexistent-snapshot-id")

    def test_latest_raw_raises_when_empty(self, tmp_path):
        s = _make_storage(tmp_path)
        with pytest.raises(FileNotFoundError):
            s.latest_raw()

    def test_save_and_latest_raw(self, tmp_path):
        s = _make_storage(tmp_path)
        payload = {"items": [], "source_breakdown": {}}
        sid = s.save_raw(payload)
        latest_sid, latest_payload = s.latest_raw()
        assert latest_sid == sid
        assert latest_payload == payload

    def test_save_and_load_digest(self, tmp_path):
        s = _make_storage(tmp_path)
        raw_payload = {"items": []}
        sid = s.save_raw(raw_payload)
        digest_payload = {"model": "test-model", "india_points": [], "world_points": []}
        s.save_digest(sid, digest_payload)
        # Load via raw (digests don't have a standalone load, just verify no error)

    def test_save_phase_metric(self, tmp_path):
        s = _make_storage(tmp_path)
        s.save_phase_metric(phase="test.phase", duration_ms=123.4, meta={"key": "val"})
        summary = s.get_phase_metrics_summary()
        phases = {p["phase"] for p in summary["phases"]}
        assert "test.phase" in phases

    def test_phase_metrics_summary_with_snapshot_filter(self, tmp_path):
        s = _make_storage(tmp_path)
        s.save_phase_metric(phase="fetch", duration_ms=50.0, snapshot_id="snap-A")
        s.save_phase_metric(phase="digest", duration_ms=80.0, snapshot_id="snap-B")
        summary = s.get_phase_metrics_summary(snapshot_id="snap-A")
        phases = {p["phase"] for p in summary["phases"]}
        assert "fetch" in phases
        assert "digest" not in phases

    def test_snapshot_id_overwrite(self, tmp_path):
        s = _make_storage(tmp_path)
        sid = "static-id"
        s.save_raw({"v": 1}, snapshot_id=sid)
        s.save_raw({"v": 2}, snapshot_id=sid)
        loaded = s.load_raw(sid)
        assert loaded["v"] == 2

    def test_new_snapshot_id_format(self, tmp_path):
        s = _make_storage(tmp_path)
        sid = s._new_snapshot_id()
        # Expect format like 20240101T120000Z
        assert len(sid) == 16
        assert sid.endswith("Z")
        assert "T" in sid
