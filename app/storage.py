import json
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

        if settings.use_legacy_json_storage:
            path = self.raw_dir / f"{sid}.json"
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return sid

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


storage = Storage()
