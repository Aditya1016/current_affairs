import os
from dataclasses import dataclass, field
from typing import List
from pathlib import Path

try:
    from dotenv import load_dotenv, find_dotenv

    # Load .env from repository root (if present) to ensure settings pick it up when CLI is started
    try:
        load_dotenv(find_dotenv())
    except Exception:
        # ignore errors from dotenv loading
        pass
except Exception:
    # If python-dotenv isn't installed, continue without loading .env (CLI can still run)
    def load_dotenv(*args, **kwargs):
        return None

    def find_dotenv(*args, **kwargs):
        return None

# If dotenv didn't run (missing package), try a simple .env loader from repo root.
try:
    repo_root = Path(__file__).resolve().parents[1]
    env_path = repo_root / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"')
            if k and v and os.environ.get(k, "") == "":
                os.environ[k] = v
except Exception:
    pass


def _parse_csv_env(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    newsapi_key: str = os.getenv("NEWSAPI_KEY", "")
    newsdata_key: str = os.getenv("NEWSDATA_KEY", "")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    fast_ollama_model: str = os.getenv("FAST_OLLAMA_MODEL", "qwen2.5:7b")
    data_dir: str = os.getenv("DATA_DIR", "./data")
    sqlite_db_path: str = os.getenv("SQLITE_DB_PATH", "./data/friday.db")
    use_legacy_json_storage: bool = os.getenv("USE_LEGACY_JSON_STORAGE", "false").lower() in {"1", "true", "yes", "on"}
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.82"))
    summarizer_max_items_per_section: int = int(os.getenv("SUMMARIZER_MAX_ITEMS_PER_SECTION", "24"))
    summarizer_concurrency: int = int(os.getenv("SUMMARIZER_CONCURRENCY", "2"))
    default_rss_feeds: List[str] = field(
        default_factory=lambda: _parse_csv_env(
            "RSS_FEEDS",
            [
                "https://www.thehindu.com/news/national/feeder/default.rss",
                "https://indianexpress.com/section/india/feed/",
                "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://www.aljazeera.com/xml/rss/all.xml",
            ],
        )
    )


settings = Settings()
