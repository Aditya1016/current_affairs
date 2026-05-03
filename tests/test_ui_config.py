"""Tests for app/ui_config.py — load/save UI config."""
import json

from app.ui_config import DEFAULT_UI_CONFIG, load_ui_config, save_ui_config


class TestDefaultUiConfig:
    def test_has_required_keys(self):
        assert "assistant_name" in DEFAULT_UI_CONFIG
        assert "accent_color" in DEFAULT_UI_CONFIG
        assert "panel_color" in DEFAULT_UI_CONFIG
        assert "show_tips" in DEFAULT_UI_CONFIG
        assert "show_timers" in DEFAULT_UI_CONFIG

    def test_assistant_name_default(self):
        assert DEFAULT_UI_CONFIG["assistant_name"] == "friday"

    def test_show_tips_is_bool(self):
        assert isinstance(DEFAULT_UI_CONFIG["show_tips"], bool)
        assert isinstance(DEFAULT_UI_CONFIG["show_timers"], bool)


class TestLoadSaveUiConfig:
    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        import app.ui_config as uic_mod

        # Point settings.data_dir to tmp_path
        class _FakeCfg:
            data_dir = str(tmp_path)
            sqlite_db_path = str(tmp_path / "test.db")
            use_legacy_json_storage = False
            newsapi_key = ""
            ollama_base_url = ""
            ollama_model = ""
            similarity_threshold = 0.82
            summarizer_max_items_per_section = 24
            default_rss_feeds = []

        monkeypatch.setattr(uic_mod, "settings", _FakeCfg())

        config = load_ui_config()
        assert config["assistant_name"] == DEFAULT_UI_CONFIG["assistant_name"]
        assert config["accent_color"] == DEFAULT_UI_CONFIG["accent_color"]

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        import app.ui_config as uic_mod

        class _FakeCfg:
            data_dir = str(tmp_path)

        monkeypatch.setattr(uic_mod, "settings", _FakeCfg())

        custom = {
            "assistant_name": "jarvis",
            "accent_color": "red",
            "panel_color": "blue",
            "show_tips": False,
            "show_timers": False,
        }
        save_ui_config(custom)
        loaded = load_ui_config()
        assert loaded["assistant_name"] == "jarvis"
        assert loaded["accent_color"] == "red"
        assert loaded["show_tips"] is False
        assert loaded["show_timers"] is False

    def test_load_ignores_unknown_keys(self, tmp_path, monkeypatch):
        import app.ui_config as uic_mod

        class _FakeCfg:
            data_dir = str(tmp_path)

        monkeypatch.setattr(uic_mod, "settings", _FakeCfg())

        # Write a config file with extra keys
        cfg_path = tmp_path / "ui_config.json"
        cfg_path.write_text(
            json.dumps({"unknown_key": "ignored", "assistant_name": "friday"}),
            encoding="utf-8",
        )
        loaded = load_ui_config()
        assert "unknown_key" not in loaded
        assert loaded["assistant_name"] == "friday"

    def test_load_returns_defaults_on_invalid_json(self, tmp_path, monkeypatch):
        import app.ui_config as uic_mod

        class _FakeCfg:
            data_dir = str(tmp_path)

        monkeypatch.setattr(uic_mod, "settings", _FakeCfg())

        cfg_path = tmp_path / "ui_config.json"
        cfg_path.write_text("NOT VALID JSON!!!", encoding="utf-8")
        loaded = load_ui_config()
        assert loaded["assistant_name"] == DEFAULT_UI_CONFIG["assistant_name"]

    def test_load_returns_defaults_on_non_utf8_file(self, tmp_path, monkeypatch):
        import app.ui_config as uic_mod

        class _FakeCfg:
            data_dir = str(tmp_path)

        monkeypatch.setattr(uic_mod, "settings", _FakeCfg())

        # Write raw bytes that are not valid UTF-8
        cfg_path = tmp_path / "ui_config.json"
        cfg_path.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
        loaded = load_ui_config()
        assert loaded["assistant_name"] == DEFAULT_UI_CONFIG["assistant_name"]
