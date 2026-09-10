import json
import sqlite3
from typing import List, Optional
from core.domain.entities.script_candidate import ScriptCandidate, CandidateGroup, CandidateStatus
from core.domain.ports.candidate_repository_port import CandidateRepositoryPort

class SqliteCandidateRepository(CandidateRepositoryPort):
    def __init__(self, db_path: str = "candidates.sqlite"):
        self.db_path = db_path
        self._shared_memory_conn = None
        if self.db_path == ":memory:":
            # Memory DBs die when the connection closes. Keep one open.
            self._shared_memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_db()

    def _init_db(self):
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS script_candidates (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    language TEXT,
                    target_duration_seconds INTEGER,
                    target_audience TEXT,
                    raw_sources TEXT,
                    verified_claims TEXT,
                    model_info TEXT,
                    prompt_version TEXT,
                    initial_script TEXT NOT NULL,
                    revised_script TEXT,
                    status TEXT NOT NULL,
                    reasoning TEXT,
                    scores TEXT,
                    content_hash TEXT,
                    group_name TEXT NOT NULL,
                    retention_score REAL,
                    view_count INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_group ON script_candidates(group_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON script_candidates(status)")
        finally:
            if not self._shared_memory_conn:
                conn.close()

    def _get_connection(self):
        if self._shared_memory_conn:
            return self._shared_memory_conn
        return sqlite3.connect(self.db_path)

    def save(self, candidate: ScriptCandidate) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO script_candidates (
                        id, topic, language, target_duration_seconds, target_audience,
                        raw_sources, verified_claims, model_info, prompt_version,
                        initial_script, revised_script, status, reasoning, scores,
                        content_hash, group_name, retention_score, view_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        topic=excluded.topic,
                        language=excluded.language,
                        target_duration_seconds=excluded.target_duration_seconds,
                        target_audience=excluded.target_audience,
                        raw_sources=excluded.raw_sources,
                        verified_claims=excluded.verified_claims,
                        model_info=excluded.model_info,
                        prompt_version=excluded.prompt_version,
                        initial_script=excluded.initial_script,
                        revised_script=excluded.revised_script,
                        status=excluded.status,
                        reasoning=excluded.reasoning,
                        scores=excluded.scores,
                        content_hash=excluded.content_hash,
                        group_name=excluded.group_name,
                        retention_score=excluded.retention_score,
                        view_count=excluded.view_count
                    """,
                    (
                        candidate.id,
                        candidate.topic,
                        candidate.language,
                        candidate.target_duration_seconds,
                        candidate.target_audience,
                        candidate.raw_sources,
                        candidate.verified_claims,
                        candidate.model_info,
                        candidate.prompt_version,
                        candidate.initial_script,
                        candidate.revised_script,
                        candidate.status.value,
                        candidate.reasoning,
                        json.dumps(candidate.scores.to_dict()),
                        candidate.content_hash,
                        candidate.group.value,
                        candidate.retention_score,
                        candidate.view_count,
                        candidate.created_at,
                    )
                )
        finally:
            if not self._shared_memory_conn:
                conn.close()

    def _row_to_candidate(self, row: sqlite3.Row) -> ScriptCandidate:
        data = dict(row)
        data["scores"] = json.loads(data["scores"]) if data["scores"] else {}
        data["group"] = data.pop("group_name")
        return ScriptCandidate.from_dict(data)

    def get_by_id(self, candidate_id: str) -> Optional[ScriptCandidate]:
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM script_candidates WHERE id = ?", (candidate_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_candidate(row)
            return None
        finally:
            if not self._shared_memory_conn:
                conn.close()

    def list_by_status(self, status: CandidateStatus, limit: int = 100, offset: int = 0) -> List[ScriptCandidate]:
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM script_candidates WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status.value, limit, offset)
            )
            return [self._row_to_candidate(row) for row in cursor.fetchall()]
        finally:
            if not self._shared_memory_conn:
                conn.close()

    def get_exportable_training_data(self) -> List[ScriptCandidate]:
        """
        Retrieves candidates suitable for training.
        Strictly excludes the HOLDOUT group to prevent data leakage.
        """
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM script_candidates WHERE group_name != ? AND status IN (?, ?)",
                (CandidateGroup.HOLDOUT.value, CandidateStatus.ACCEPTED.value, CandidateStatus.PUBLISHED.value)
            )
            return [self._row_to_candidate(row) for row in cursor.fetchall()]
        finally:
            if not self._shared_memory_conn:
                conn.close()

    def assign_group(self, candidate_id: str, group: CandidateGroup) -> None:
        """
        Helper method to strictly assign a candidate to a specific group.
        Real split logic should occur at creation or via a dedicated service that checks
        for topic overlap before assigning TRAIN/VALIDATION vs HOLDOUT.
        """
        candidate = self.get_by_id(candidate_id)
        if candidate:
            candidate.group = group
            self.save(candidate)
