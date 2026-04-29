import sqlite3
from typing import Any

from .config import DB_PATH

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                attempts_started INTEGER NOT NULL DEFAULT 0,
                attempts_finished INTEGER NOT NULL DEFAULT 0,
                total_answered INTEGER NOT NULL DEFAULT 0,
                total_correct INTEGER NOT NULL DEFAULT 0,
                last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            );

            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                duration_seconds INTEGER,
                answered INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                completed_full_test INTEGER NOT NULL DEFAULT 0,
                finished_by_user INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS all_time_errors (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                wrong_count INTEGER NOT NULL DEFAULT 1,
                last_wrong_answer_index INTEGER,
                last_wrong_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id, question_index)
            );

            CREATE TABLE IF NOT EXISTS attempt_wrong_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER,
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                wrong_answer_index INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            );
            """
        )

        for stmt in [
            "ALTER TABLE all_time_errors ADD COLUMN last_wrong_answer_index INTEGER",
            "ALTER TABLE attempts ADD COLUMN finished_by_user INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE active_sessions ADD COLUMN updated_at TEXT",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

        conn.commit()

def upsert_user(user) -> None:
    if not user:
        return

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (user.id, user.username, user.first_name, user.last_name),
        )
        conn.commit()

def ensure_user_stats(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute("INSERT OR IGNORE INTO user_stats (user_id, test_id) VALUES (?, ?)", (user_id, test_id))
        conn.commit()

def record_attempt_start(user_id: int, test_id: str, mode: str) -> int:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET attempts_started = attempts_started + 1,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        )
        cur = conn.execute("INSERT INTO attempts (user_id, test_id, mode) VALUES (?, ?, ?)", (user_id, test_id, mode))
        conn.commit()
        return int(cur.lastrowid)

def record_answer(user_id: int, test_id: str, is_correct: bool) -> None:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET total_answered = total_answered + 1,
                total_correct = total_correct + ?,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ?
            """,
            (1 if is_correct else 0, user_id, test_id),
        )
        conn.commit()

def record_attempt_finish(
    user_id: int,
    test_id: str,
    attempt_id: int | None,
    answered: int,
    correct: int,
    completed_full_test: bool,
    finished_by_user: bool,
) -> None:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET attempts_finished = attempts_finished + 1,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        )
        if attempt_id is not None:
            conn.execute(
                """
                UPDATE attempts
                SET finished_at = CURRENT_TIMESTAMP,
                    duration_seconds = CAST((julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400 AS INTEGER),
                    answered = ?,
                    correct = ?,
                    completed_full_test = ?,
                    finished_by_user = ?
                WHERE attempt_id = ?
                """,
                (answered, correct, 1 if completed_full_test else 0, 1 if finished_by_user else 0, attempt_id),
            )
        conn.commit()

def add_all_time_error(user_id: int, test_id: str, question_index: int, wrong_answer_index: int | None) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO all_time_errors (user_id, test_id, question_index, wrong_count, last_wrong_answer_index, last_wrong_at)
            VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, test_id, question_index)
            DO UPDATE SET
                wrong_count = wrong_count + 1,
                last_wrong_answer_index = excluded.last_wrong_answer_index,
                last_wrong_at = CURRENT_TIMESTAMP
            """,
            (user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()

def remove_all_time_error(user_id: int, test_id: str, question_index: int) -> None:
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM all_time_errors WHERE user_id = ? AND test_id = ? AND question_index = ?",
            (user_id, test_id, question_index),
        )
        conn.commit()

def clear_all_time_errors(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute("DELETE FROM all_time_errors WHERE user_id = ? AND test_id = ?", (user_id, test_id))
        conn.commit()

def get_all_time_error_indices(user_id: int, test_id: str) -> list[int]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            ORDER BY last_wrong_at ASC
            """,
            (user_id, test_id),
        ).fetchall()
    return [int(row["question_index"]) for row in rows]

def record_attempt_wrong_answer(
    attempt_id: int | None,
    user_id: int,
    test_id: str,
    question_index: int,
    wrong_answer_index: int | None,
) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO attempt_wrong_answers (attempt_id, user_id, test_id, question_index, wrong_answer_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (attempt_id, user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()

def get_attempt_wrong_answers(user_id: int, test_id: str, attempt_id: int | None) -> list[dict[str, int | None]]:
    if attempt_id is None:
        return []
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, wrong_answer_index
            FROM attempt_wrong_answers
            WHERE user_id = ? AND test_id = ? AND attempt_id = ?
            ORDER BY id ASC
            """,
            (user_id, test_id, attempt_id),
        ).fetchall()
    return [
        {
            "question_index": int(row["question_index"]),
            "wrong_answer_index": row["wrong_answer_index"],
        }
        for row in rows
    ]
