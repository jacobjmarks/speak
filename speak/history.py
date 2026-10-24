"""SQLite transcript history (opt-in)."""
import sqlite3
from contextlib import closing
from datetime import datetime

from .config import HISTORY_FILE


def _connect():
    db = sqlite3.connect(HISTORY_FILE)
    db.execute("CREATE TABLE IF NOT EXISTS transcripts (created TEXT, text TEXT)")
    return db


def add(text: str) -> None:
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(_connect()) as db, db:
        db.execute("INSERT INTO transcripts VALUES (?, ?)", (created, text))


def recent(limit: int = 500) -> list:
    if not HISTORY_FILE.exists():
        return []
    with closing(_connect()) as db, db:
        return db.execute("SELECT created, text FROM transcripts ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()


def clear() -> None:
    if HISTORY_FILE.exists():
        with closing(_connect()) as db, db:
            db.execute("DELETE FROM transcripts")
