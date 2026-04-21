import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


load_dotenv()


def _parse_csv_env(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    newsapi_key: str = os.getenv("NEWSAPI_KEY", "")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    data_dir: str = os.getenv("DATA_DIR", "./data")
    sqlite_db_path: str = os.getenv("SQLITE_DB_PATH", "./data/friday.db")
    use_legacy_json_storage: bool = os.getenv("USE_LEGACY_JSON_STORAGE", "false").lower() in {"1", "true", "yes", "on"}
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.82"))
    summarizer_max_items_per_section: int = int(os.getenv("SUMMARIZER_MAX_ITEMS_PER_SECTION", "24"))
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
