import sqlite3
import json

class SQLiteVideoRepository:
    """SQLite implementation for video repository port handling concurrency."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize tables and set WAL mode for high concurrency."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT,
                    current_step TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT,
                    step_name TEXT,
                    step_status TEXT,
                    payload JSON,
                    error_message TEXT,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                )
            ''')
            conn.commit()

    def save_video(self, video_data: dict):
        """Save a new video record to the database."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO videos (id, title, status, current_step) VALUES (?, ?, ?, ?)",
                (video_data.get('id'), video_data.get('title'), video_data.get('status'), video_data.get('current_step'))
            )
            conn.commit()

    def get_video(self, video_id: str) -> dict:
        """Retrieve a video record by its ID."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, status, current_step FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'title': row[1],
                    'status': row[2],
                    'current_step': row[3]
                }
            return None

    def update_video_status(self, video_id: str, status: str, current_step: str):
        """Update the status and current step of a video."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE videos SET status = ?, current_step = ? WHERE id = ?",
                (status, current_step, video_id)
            )
            conn.commit()

    def save_checkpoint(self, video_id: str, step_name: str, step_status: str, payload: dict, error_message: str = None):
        """Save a saga checkpoint for a specific video and step."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            payload_json = json.dumps(payload)
            cursor.execute(
                "INSERT INTO checkpoints (video_id, step_name, step_status, payload, error_message) VALUES (?, ?, ?, ?, ?)",
                (video_id, step_name, step_status, payload_json, error_message)
            )
            conn.commit()

    def get_latest_checkpoint(self, video_id: str) -> dict:
        """Retrieve the most recent checkpoint for a given video."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, video_id, step_name, step_status, payload, error_message FROM checkpoints WHERE video_id = ? ORDER BY id DESC LIMIT 1",
                (video_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'video_id': row[1],
                    'step_name': row[2],
                    'step_status': row[3],
                    'payload': json.loads(row[4]) if row[4] else None,
                    'error_message': row[5]
                }
            return None
