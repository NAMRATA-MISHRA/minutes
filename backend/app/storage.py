import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript TEXT NOT NULL,
                notes TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_meeting(db_path: str, transcript: str, notes: dict) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO meetings (transcript, notes, created_at) VALUES (?, ?, ?)",
            (transcript, json.dumps(notes), created_at),
        )
        meeting_id = cursor.lastrowid
        conn.commit()
    return {
        "id": meeting_id,
        "transcript": transcript,
        "notes": notes,
        "created_at": created_at,
    }


def list_meetings(db_path: str, limit: int = 50) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, transcript, notes, created_at FROM meetings ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "transcript": row["transcript"],
            "notes": json.loads(row["notes"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_meeting(db_path: str, meeting_id: int) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, transcript, notes, created_at FROM meetings WHERE id = ?",
            (meeting_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "transcript": row["transcript"],
        "notes": json.loads(row["notes"]),
        "created_at": row["created_at"],
    }
