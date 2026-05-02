import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import settings


class Storage:
    def __init__(self) -> None:
        self.base_dir = Path(settings.data_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = Path(settings.sqlite_db_path)
        if not self.db_path.is_absolute():
            self.db_path = Path(".") / self.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.raw_dir = self.base_dir / "raw"
        self.digest_dir = self.base_dir / "digests"
        if settings.use_legacy_json_storage:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            self.digest_dir.mkdir(parents=True, exist_ok=True)

        self._fts_enabled = False
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS digests (
                    snapshot_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS phase_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    snapshot_id TEXT,
                    phase TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    meta_json TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phase_metrics_phase ON phase_metrics(phase)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phase_metrics_snapshot ON phase_metrics(snapshot_id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    snippet TEXT,
                    source TEXT,
                    category TEXT,
                    published_at TEXT,
                    first_seen_snapshot TEXT,
                    last_seen_snapshot TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_published_at ON stories(published_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_source ON stories(source)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vocab_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    snapshot_id TEXT,
                    difficulty TEXT,
                    context_headline TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vocab_history_word ON vocab_history(word)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vocab_history_created_at ON vocab_history(created_at)")
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS story_fts USING fts5(
                        url UNINDEXED,
                        title,
                        snippet,
                        source,
                        category,
                        tokenize='unicode61 porter'
                    )
                    """
                )
                self._fts_enabled = True
            except sqlite3.OperationalError:
                self._fts_enabled = False

    @staticmethod
    def _new_snapshot_id() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def save_raw(self, payload: Dict[str, Any], snapshot_id: Optional[str] = None) -> str:
        sid = snapshot_id or self._new_snapshot_id()
        payload_json = json.dumps(payload, ensure_ascii=True)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO snapshots(snapshot_id, created_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    created_at=excluded.created_at,
                    payload_json=excluded.payload_json
                """,
                (sid, created_at, payload_json),
            )
            self._index_snapshot_items(snapshot_id=sid, payload=payload, conn=conn)

        if settings.use_legacy_json_storage:
            path = self.raw_dir / f"{sid}.json"
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return sid

    def _index_snapshot_items(
        self,
        snapshot_id: str,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        items = payload.get("items", [])
        if not isinstance(items, list) or not items:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        close_conn = False
        active_conn = conn
        if active_conn is None:
            active_conn = self._connect()
            close_conn = True

        try:
            for row in items:
                if not isinstance(row, dict):
                    continue
                url = str(row.get("url", "")).strip()
                title = str(row.get("title", "")).strip()
                if not url or not title:
                    continue
                snippet = str(row.get("snippet", "") or "")
                source = str(row.get("source", "") or "")
                category = str(row.get("category", "world") or "world")
                published_at = str(row.get("published_at", "") or "")

                active_conn.execute(
                    """
                    INSERT INTO stories(
                        url, title, snippet, source, category, published_at,
                        first_seen_snapshot, last_seen_snapshot, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title=excluded.title,
                        snippet=excluded.snippet,
                        source=excluded.source,
                        category=excluded.category,
                        published_at=excluded.published_at,
                        last_seen_snapshot=excluded.last_seen_snapshot,
                        updated_at=excluded.updated_at
                    """,
                    (
                        url,
                        title,
                        snippet,
                        source,
                        category,
                        published_at,
                        snapshot_id,
                        snapshot_id,
                        now_iso,
                        now_iso,
                    ),
                )

                if self._fts_enabled:
                    story_row = active_conn.execute("SELECT id FROM stories WHERE url = ?", (url,)).fetchone()
                    if story_row:
                        story_id = int(story_row["id"])
                        active_conn.execute("DELETE FROM story_fts WHERE rowid = ?", (story_id,))
                        active_conn.execute(
                            """
                            INSERT INTO story_fts(rowid, url, title, snippet, source, category)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (story_id, url, title, snippet, source, category),
                        )
        finally:
            if close_conn and active_conn is not None:
                active_conn.close()

    @staticmethod
    def _fts_query(value: str) -> str:
        tokens = [token for token in re.findall(r"[A-Za-z0-9]+", value) if token]
        if not tokens:
            return ""
        return " ".join(tokens)

    def search_stories(
        self,
        query: str,
        limit: int = 20,
        category: str = "",
        source: str = "",
        days: int = 0,
    ) -> List[Dict[str, Any]]:
        bounded_limit = max(1, min(limit, 100))
        fts_query = self._fts_query(query)
        category_val = category.strip().lower()
        source_val = source.strip().lower()

        where_clauses: List[str] = []
        params: List[Any] = []
        if category_val:
            where_clauses.append("LOWER(s.category) = ?")
            params.append(category_val)
        if source_val:
            where_clauses.append("LOWER(s.source) = ?")
            params.append(source_val)
        if days > 0:
            where_clauses.append("datetime(s.published_at) >= datetime('now', ?)")
            params.append(f"-{days} days")
        where_sql = f" AND {' AND '.join(where_clauses)}" if where_clauses else ""

        with self._connect() as conn:
            if self._fts_enabled and fts_query:
                sql = f"""
                    SELECT
                        s.id,
                        s.url,
                        s.title,
                        s.snippet,
                        s.source,
                        s.category,
                        s.published_at,
                        s.last_seen_snapshot,
                        bm25(story_fts) AS rank
                    FROM story_fts
                    JOIN stories s ON s.id = story_fts.rowid
                    WHERE story_fts MATCH ?
                    {where_sql}
                    ORDER BY rank ASC, datetime(s.published_at) DESC
                    LIMIT ?
                """
                rows = conn.execute(sql, [fts_query, *params, bounded_limit]).fetchall()
                return [dict(row) for row in rows]

            like_sql = ""
            like_params: List[Any] = []
            if query.strip():
                like_sql = " AND (LOWER(s.title) LIKE ? OR LOWER(s.snippet) LIKE ?)"
                like_pattern = f"%{query.strip().lower()}%"
                like_params = [like_pattern, like_pattern]

            sql = f"""
                SELECT
                    s.id,
                    s.url,
                    s.title,
                    s.snippet,
                    s.source,
                    s.category,
                    s.published_at,
                    s.last_seen_snapshot,
                    0.0 AS rank
                FROM stories s
                WHERE 1=1
                {where_sql}
                {like_sql}
                ORDER BY datetime(s.published_at) DESC, s.id DESC
                LIMIT ?
            """
            rows = conn.execute(sql, [*params, *like_params, bounded_limit]).fetchall()
            return [dict(row) for row in rows]

    def save_vocab_word(
        self,
        word: str,
        snapshot_id: str,
        difficulty: str,
        context_headline: str,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO vocab_history(word, snapshot_id, difficulty, context_headline, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (word.lower().strip(), snapshot_id, difficulty.strip().lower(), context_headline.strip(), created_at),
            )

    def get_recent_vocab_words(self, days: int = 14, limit: int = 500) -> List[str]:
        bounded_limit = max(1, min(limit, 2000))
        bounded_days = max(0, days)
        with self._connect() as conn:
            if bounded_days > 0:
                rows = conn.execute(
                    """
                    SELECT DISTINCT word
                    FROM vocab_history
                    WHERE datetime(created_at) >= datetime('now', ?)
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (f"-{bounded_days} days", bounded_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT word
                    FROM vocab_history
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
        return [str(row["word"]).lower().strip() for row in rows if str(row["word"]).strip()]

    def load_raw(self, snapshot_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()

        if row:
            return json.loads(row["payload_json"])

        legacy_path = self.raw_dir / f"{snapshot_id}.json"
        if legacy_path.exists():
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            self.save_raw(payload, snapshot_id=snapshot_id)
            return payload

        raise FileNotFoundError(f"Snapshot {snapshot_id} not found.")

    def latest_raw(self) -> Tuple[str, Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT snapshot_id, payload_json FROM snapshots ORDER BY snapshot_id DESC LIMIT 1"
            ).fetchone()

        if row:
            return row["snapshot_id"], json.loads(row["payload_json"])

        files = sorted(self.raw_dir.glob("*.json"))
        if files:
            path = files[-1]
            snapshot_id = path.stem
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.save_raw(payload, snapshot_id=snapshot_id)
            return snapshot_id, payload

        raise FileNotFoundError("No raw snapshots found. Run /fetch-news first.")

    def save_digest(self, snapshot_id: str, payload: Dict[str, Any]) -> None:
        payload_json = json.dumps(payload, ensure_ascii=True)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO digests(snapshot_id, created_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    created_at=excluded.created_at,
                    payload_json=excluded.payload_json
                """,
                (snapshot_id, created_at, payload_json),
            )

        if settings.use_legacy_json_storage:
            path = self.digest_dir / f"{snapshot_id}.json"
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def save_phase_metric(
        self,
        phase: str,
        duration_ms: float,
        snapshot_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(meta or {}, ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO phase_metrics(created_at, snapshot_id, phase, duration_ms, meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (created_at, snapshot_id, phase, float(duration_ms), meta_json),
            )

    def get_phase_metrics_summary(self, snapshot_id: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        params: List[Any] = []
        where = ""
        if snapshot_id:
            where = "WHERE snapshot_id = ?"
            params.append(snapshot_id)

        query = f"""
            SELECT phase,
                   COUNT(*) AS samples,
                   ROUND(AVG(duration_ms), 2) AS avg_ms,
                   ROUND(MAX(duration_ms), 2) AS max_ms,
                   ROUND(SUM(duration_ms), 2) AS total_ms
            FROM phase_metrics
            {where}
            GROUP BY phase
            ORDER BY total_ms DESC
            LIMIT ?
        """
        params.append(max(1, min(limit, 1000)))

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return {
            "snapshot_id": snapshot_id,
            "phases": [
                {
                    "phase": row["phase"],
                    "samples": row["samples"],
                    "avg_ms": row["avg_ms"],
                    "max_ms": row["max_ms"],
                    "total_ms": row["total_ms"],
                }
                for row in rows
            ],
        }

    def get_phase_metrics_trend(
        self,
        phase: str = "",
        snapshot_id: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        bounded_limit = max(1, min(limit, 500))
        params: List[Any] = []
        where_parts: List[str] = []

        if phase:
            where_parts.append("phase = ?")
            params.append(phase)
        if snapshot_id:
            where_parts.append("snapshot_id = ?")
            params.append(snapshot_id)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"""
            SELECT created_at, snapshot_id, phase, duration_ms
            FROM phase_metrics
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(bounded_limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        rows_list = [dict(row) for row in rows]
        rows_list.reverse()
        durations = [float(row["duration_ms"]) for row in rows_list]

        return {
            "phase": phase,
            "snapshot_id": snapshot_id,
            "limit": bounded_limit,
            "count": len(rows_list),
            "min_ms": round(min(durations), 2) if durations else 0.0,
            "max_ms": round(max(durations), 2) if durations else 0.0,
            "avg_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "points": rows_list,
        }


storage = Storage()
