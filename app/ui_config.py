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
    "use_fast_model": False,
    "fast_model_name": "",
    "summarizer_concurrency": 2,
    "confirmation_threshold_s": 0,
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
        # Only accept known keys from defaults; ignore unknown keys on disk.
        for k in DEFAULT_UI_CONFIG.keys():
            if k in data:
                merged[k] = data[k]
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_UI_CONFIG)


def save_ui_config(config: Dict[str, object]) -> None:
    path = _config_path()
    # Persist only known/default keys to avoid saving unexpected fields.
    payload = {k: config.get(k, DEFAULT_UI_CONFIG[k]) for k in DEFAULT_UI_CONFIG.keys()}
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
