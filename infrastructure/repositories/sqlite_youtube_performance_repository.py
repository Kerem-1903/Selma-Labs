import sqlite3
import json
from pathlib import Path
from core.domain.ports.youtube_performance_repository_port import YoutubePerformanceRepositoryPort
from core.domain.value_objects.youtube_performance import YoutubePerformanceRecord

class SQLiteYoutubePerformanceRepository(YoutubePerformanceRepositoryPort):
    """SQLite implementation for YouTube performance records handling concurrency."""

    _mem_locks = {}
    _mem_conns = {}

    def __init__(self, db_path: str | Path):
        self._is_memory = str(db_path) == ":memory:" or str(db_path).startswith("file:memdb_")
        if str(db_path) == ":memory:":
            import uuid
            self.db_path = f"file:memdb_{uuid.uuid4().hex}?mode=memory&cache=shared"
        else:
            self.db_path = str(db_path)

        if self._is_memory and self.db_path not in SQLiteYoutubePerformanceRepository._mem_locks:
            import asyncio
            SQLiteYoutubePerformanceRepository._mem_locks[self.db_path] = asyncio.Lock()
            # Keep one connection open to prevent the shared memory db from being destroyed
            SQLiteYoutubePerformanceRepository._mem_conns[self.db_path] = sqlite3.connect(self.db_path, uri=True, check_same_thread=False)

        self._init_db()
    def _get_connection(self):
        return sqlite3.connect(self.db_path, timeout=10.0, uri=self._is_memory, check_same_thread=False)

    def _init_db(self):
        """Initialize table and set WAL mode for high concurrency."""
        from contextlib import closing
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                if not self._is_memory:
                    cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS youtube_performance_records (
                        video_id TEXT PRIMARY KEY,
                        data JSON
                    )
                ''')
            conn.commit()

    async def list_records(self) -> tuple[YoutubePerformanceRecord, ...]:
        import asyncio
        if self._is_memory:
            async with SQLiteYoutubePerformanceRepository._mem_locks[self.db_path]:
                return await asyncio.to_thread(self._list_records_sync)
        return await asyncio.to_thread(self._list_records_sync)

    def _list_records_sync(self) -> tuple[YoutubePerformanceRecord, ...]:
        from contextlib import closing
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM youtube_performance_records")
                rows = cursor.fetchall()
                records = []
                for row in rows:
                    data = json.loads(row[0])
                    records.append(YoutubePerformanceRecord.from_dict(data))
                records.sort(key=lambda item: item.published_at)
                return tuple(records)

    async def save(self, record: YoutubePerformanceRecord) -> None:
        import asyncio
        if self._is_memory:
            async with SQLiteYoutubePerformanceRepository._mem_locks[self.db_path]:
                await asyncio.to_thread(self._save_sync, record)
        else:
            await asyncio.to_thread(self._save_sync, record)
    def _save_sync(self, record: YoutubePerformanceRecord) -> None:
        data_json = json.dumps(record.to_dict())
        from contextlib import closing
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO youtube_performance_records (video_id, data)
                    VALUES (?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET data=excluded.data
                    """,
                    (record.video_id, data_json)
                )
            conn.commit()
