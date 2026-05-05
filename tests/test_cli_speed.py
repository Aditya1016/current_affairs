from app import ui_config as uic_mod


def _set_temp_ui_dir(monkeypatch, tmp_path):
    class _FakeCfg:
        data_dir = str(tmp_path)

    monkeypatch.setattr(uic_mod, "settings", _FakeCfg())


def test_speed_mode_defaults_and_toggle(tmp_path):
    import pytest

    monkeypatch = pytest.MonkeyPatch()
    _set_temp_ui_dir(monkeypatch, tmp_path)
    try:
        load_ui_config = uic_mod.load_ui_config
        save_ui_config = uic_mod.save_ui_config

        # Ensure defaults contain speed_mode key and default is False
        ui = load_ui_config()
        assert "speed_mode" in ui
        assert ui.get("speed_mode") is False

        # Toggle on and persist
        ui["speed_mode"] = True
        ui["use_fast_model"] = True
        ui["fast_model_name"] = ui.get("fast_model_name", "test-model")
        save_ui_config(ui)

        reloaded = load_ui_config()
        assert reloaded.get("speed_mode") is True
        assert reloaded.get("use_fast_model") is True
    finally:
        monkeypatch.undo()
