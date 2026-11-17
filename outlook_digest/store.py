from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Analysis, Mail

SCHEMA = """
CREATE TABLE IF NOT EXISTS mails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_key TEXT NOT NULL UNIQUE,
    internet_message_id TEXT,
    entry_id TEXT,
    folder TEXT,
    sender_name TEXT,
    sender_email TEXT,
    to_list TEXT,
    cc_list TEXT,
    subject TEXT,
    received_at TEXT NOT NULL,
    unread INTEGER,
    class_id INTEGER,
    category TEXT,
    priority INTEGER,
    lang TEXT,
    summary TEXT,
    translation TEXT,
    todos TEXT,
    attachments TEXT,
    body_text TEXT,
    md_path TEXT,
    engine TEXT,
    title_norm TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mails_received ON mails(received_at);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    scanned INTEGER DEFAULT 0,
    inserted INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    note TEXT
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(mails)")}
        if "title_norm" not in columns:
            self._conn.execute("ALTER TABLE mails ADD COLUMN title_norm TEXT")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def has(self, msg_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM mails WHERE msg_key = ?", (msg_key,)
        ).fetchone()
        return row is not None

    def insert(self, mail: Mail, analysis: Analysis, md_path: str | None) -> None:
        self._conn.execute(
            """
            INSERT INTO mails (
                msg_key, internet_message_id, entry_id, folder, sender_name, sender_email,
                to_list, cc_list, subject, received_at, unread, class_id, category,
                priority, lang, summary, translation, todos, attachments, body_text,
                md_path, engine, title_norm, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mail.msg_key,
                mail.internet_message_id,
                mail.entry_id,
                mail.folder,
                mail.sender_name,
                mail.sender_email,
                mail.to_list,
                mail.cc_list,
                mail.subject,
                mail.received_at.isoformat(timespec="seconds"),
                int(mail.unread),
                mail.class_id,
                analysis.category,
                analysis.priority,
                analysis.lang,
                analysis.summary,
                analysis.translation,
                json.dumps(analysis.todos, ensure_ascii=False),
                json.dumps(mail.attachments, ensure_ascii=False),
                mail.body_text[:50000],
                md_path,
                analysis.engine,
                mail.title_norm,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self._conn.commit()

    def rows_for_day(self, day: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM mails WHERE substr(received_at, 1, 10) = ? "
                "ORDER BY received_at",
                (day,),
            )
        )

    def rows_for_month(self, month: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM mails WHERE substr(received_at, 1, 7) = ? "
                "ORDER BY received_at",
                (month,),
            )
        )

    def days_with_mails(self, since_days: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT substr(received_at, 1, 10) AS d FROM mails "
            "WHERE substr(received_at, 1, 10) >= date('now', ?) ORDER BY d",
            (f"-{since_days} day",),
        )
        return [row[0] for row in rows]

    def start_run(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        scanned: int = 0,
        inserted: int = 0,
        skipped: int = 0,
        errors: int = 0,
        note: str = "",
    ) -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at=?, scanned=?, inserted=?, skipped=?, errors=?, note=? "
            "WHERE id=?",
            (
                datetime.now().isoformat(timespec="seconds"),
                scanned,
                inserted,
                skipped,
                errors,
                note[:500],
                run_id,
            ),
        )
        self._conn.commit()

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = self._conn.execute(
            "SELECT COUNT(*) FROM mails WHERE substr(received_at, 1, 10) = ?", (today,)
        ).fetchone()[0]
        run = self._conn.execute(
            "SELECT * FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "total": total,
            "today": today_count,
            "last_run": dict(run) if run else None,
        }
