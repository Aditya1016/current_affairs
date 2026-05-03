import json
from pathlib import Path
from typing import Dict

from .config import settings


DEFAULT_UI_CONFIG = {
    "assistant_name": "friday",
    "accent_color": "bright_cyan",
    "panel_color": "cyan",
    "show_tips": True,
    "show_timers": True,
}


def _config_path() -> Path:
    base = Path(settings.data_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / "ui_config.json"


def load_ui_config() -> Dict[str, object]:
    path = _config_path()
    if not path.exists():
        save_ui_config(DEFAULT_UI_CONFIG)
        return dict(DEFAULT_UI_CONFIG)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_UI_CONFIG)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_UI_CONFIG})
        return merged
    except Exception:
        return dict(DEFAULT_UI_CONFIG)


def save_ui_config(config: Dict[str, object]) -> None:
    path = _config_path()
    payload = dict(DEFAULT_UI_CONFIG)
    payload.update(config)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
