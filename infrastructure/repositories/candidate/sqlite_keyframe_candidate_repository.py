from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.domain.entities.candidate.keyframe_candidate import KeyframeCandidate
from core.domain.ports.candidate.keyframe_candidate_repository_port import KeyframeCandidateRepositoryPort

class SqliteKeyframeCandidateRepository(KeyframeCandidateRepositoryPort):
    def __init__(self, db_path: str = "keyframe_candidates.db") -> None:
        self.db_path = db_path
        self._shared_memory_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._shared_memory_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._init_db(self._shared_memory_conn)
        else:
            with sqlite3.connect(self.db_path) as conn:
                self._init_db(conn)

    def _init_db(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS keyframe_candidates (
                id TEXT PRIMARY KEY,
                shot_contract_id TEXT NOT NULL,
                storage_key TEXT NOT NULL,
                generation_metadata TEXT NOT NULL,
                status TEXT NOT NULL,
                score INTEGER,
                rejection_reason TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_shot ON keyframe_candidates(shot_contract_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_status ON keyframe_candidates(status)"
        )
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_memory_conn is not None:
            return self._shared_memory_conn
        return sqlite3.connect(self.db_path)

    async def save(self, candidate: KeyframeCandidate) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO keyframe_candidates
                (id, shot_contract_id, storage_key, generation_metadata, status, score, rejection_reason, created_at, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.id,
                    candidate.shot_contract_id,
                    candidate.storage_key,
                    json.dumps(candidate.generation_metadata),
                    candidate.status.value,
                    candidate.score,
                    candidate.rejection_reason,
                    candidate.created_at.isoformat(),
                    candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
                ),
            )
            conn.commit()
        finally:
            if self._shared_memory_conn is None:
                conn.close()

    async def get_by_id(self, candidate_id: str) -> KeyframeCandidate | None:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM keyframe_candidates WHERE id = ?", (candidate_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_candidate(row)
        finally:
            if self._shared_memory_conn is None:
                conn.close()

    async def get_by_shot_contract_id(self, shot_contract_id: str) -> list[KeyframeCandidate]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM keyframe_candidates WHERE shot_contract_id = ? ORDER BY created_at DESC",
                (shot_contract_id,),
            )
            return [self._row_to_candidate(row) for row in cursor.fetchall()]
        finally:
            if self._shared_memory_conn is None:
                conn.close()

    async def list_pending(self, limit: int = 100) -> list[KeyframeCandidate]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM keyframe_candidates WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT ?",
                (limit,),
            )
            return [self._row_to_candidate(row) for row in cursor.fetchall()]
        finally:
            if self._shared_memory_conn is None:
                conn.close()

    def _row_to_candidate(self, row: tuple[Any, ...]) -> KeyframeCandidate:
        return KeyframeCandidate.from_dict(
            {
                "id": row[0],
                "shot_contract_id": row[1],
                "storage_key": row[2],
                "generation_metadata": json.loads(row[3]),
                "status": row[4],
                "score": row[5],
                "rejection_reason": row[6],
                "created_at": row[7],
                "reviewed_at": row[8],
            }
        )
