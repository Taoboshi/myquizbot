import hashlib
import os
import sqlite3
import time
from typing import Any

from .config import DB_PATH

DATABASE_URL = os.getenv("DATABASE_URL")

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # локальный запуск без PostgreSQL всё ещё сможет работать на SQLite
    psycopg = None
    dict_row = None


USER_UPSERT_CACHE_TTL_SECONDS = int(os.getenv("USER_UPSERT_CACHE_TTL_SECONDS", "600"))
RUNTIME_SESSION_TTL_DAYS = int(os.getenv("RUNTIME_SESSION_TTL_DAYS", "7"))
ACTIVE_SESSION_TTL_DAYS = int(os.getenv("ACTIVE_SESSION_TTL_DAYS", "90"))
MAX_FINISHED_ATTEMPTS_PER_USER_TEST = int(os.getenv("MAX_FINISHED_ATTEMPTS_PER_USER_TEST", "300"))
ORPHAN_WRONG_ANSWER_TTL_DAYS = int(os.getenv("ORPHAN_WRONG_ANSWER_TTL_DAYS", "30"))

_USER_UPSERT_CACHE: dict[int, float] = {}


_POLLING_LOCK_CONN = None


def _polling_lock_key() -> int:
    raw_key = os.getenv("BOT_POLLING_LOCK_KEY", "telegram_quiz_bot_polling_lock")
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False) & ((1 << 63) - 1)


def acquire_polling_lock() -> None:
    """Allow only one Render process to run Telegram polling at a time."""
    global _POLLING_LOCK_CONN

    if not DATABASE_URL:
        return
    if psycopg is None:
        raise RuntimeError("Для PostgreSQL установи зависимость: psycopg[binary]")
    if _POLLING_LOCK_CONN is not None:
        return

    print("Waiting for Telegram polling lock...")
    _POLLING_LOCK_CONN = psycopg.connect(DATABASE_URL, autocommit=True)
    _POLLING_LOCK_CONN.execute("SELECT pg_advisory_lock(%s)", (_polling_lock_key(),))
    print("Telegram polling lock acquired.")


def release_polling_lock() -> None:
    global _POLLING_LOCK_CONN

    if _POLLING_LOCK_CONN is None:
        return

    try:
        _POLLING_LOCK_CONN.execute("SELECT pg_advisory_unlock(%s)", (_polling_lock_key(),))
    finally:
        _POLLING_LOCK_CONN.close()
        _POLLING_LOCK_CONN = None


def _pg_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class PgCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)


class PgConnectionWrapper:
    def __init__(self):
        if psycopg is None:
            raise RuntimeError("Для PostgreSQL установи зависимость: psycopg[binary]")
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.conn.__exit__(exc_type, exc, tb)

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None):
        cur = self.conn.execute(_pg_sql(sql), params)
        return PgCursorWrapper(cur)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.conn.execute(_pg_sql(statement))

    def commit(self) -> None:
        self.conn.commit()


def db_connect():
    if DATABASE_URL:
        return PgConnectionWrapper()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_postgres_db() -> None:
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                attempts_started INTEGER NOT NULL DEFAULT 0,
                attempts_finished INTEGER NOT NULL DEFAULT 0,
                total_answered INTEGER NOT NULL DEFAULT 0,
                total_correct INTEGER NOT NULL DEFAULT 0,
                last_activity_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                duration_seconds INTEGER,
                answered INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                completed_full_test INTEGER NOT NULL DEFAULT 0,
                finished_by_user INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS all_time_errors (
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                wrong_count INTEGER NOT NULL DEFAULT 1,
                last_wrong_answer_index INTEGER,
                last_wrong_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id, question_index)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attempt_wrong_answers (
                id SERIAL PRIMARY KEY,
                attempt_id INTEGER,
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                wrong_answer_index INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            )
            """
        )

        for stmt in [
            "ALTER TABLE all_time_errors ADD COLUMN IF NOT EXISTS last_wrong_answer_index INTEGER",
            "ALTER TABLE attempts ADD COLUMN IF NOT EXISTS finished_by_user INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE active_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
        ]:
            conn.execute(stmt)

        conn.commit()


def _init_sqlite_db() -> None:
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

def _table_exists(conn, table_name: str) -> bool:
    if DATABASE_URL:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ?
            ) AS exists
            """,
            (table_name,),
        ).fetchone()
        return bool(row and row["exists"])

    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _timestamp_cutoff_sql(days: int) -> tuple[str, tuple[int]]:
    if DATABASE_URL:
        return "CURRENT_TIMESTAMP - (? * INTERVAL '1 day')", (days,)
    return "datetime('now', '-' || ? || ' days')", (days,)


def _chunked(items: list[int], size: int = 500):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def cleanup_old_data() -> None:
    """Keep Neon/SQLite storage compact without touching current progress.

    Defaults can be changed from Render Environment Variables:
    - MAX_FINISHED_ATTEMPTS_PER_USER_TEST=300
    - RUNTIME_SESSION_TTL_DAYS=7
    - ACTIVE_SESSION_TTL_DAYS=90
    - ORPHAN_WRONG_ANSWER_TTL_DAYS=30
    """
    with db_connect() as conn:
        # Runtime sessions are only used to survive restarts/deploys. Old rows are safe to remove.
        if RUNTIME_SESSION_TTL_DAYS > 0 and _table_exists(conn, "runtime_sessions"):
            cutoff_sql, params = _timestamp_cutoff_sql(RUNTIME_SESSION_TTL_DAYS)
            conn.execute(f"DELETE FROM runtime_sessions WHERE updated_at < {cutoff_sql}", params)

        # Active sessions are paused main-test sessions. Keep them much longer.
        if ACTIVE_SESSION_TTL_DAYS > 0:
            cutoff_sql, params = _timestamp_cutoff_sql(ACTIVE_SESSION_TTL_DAYS)
            conn.execute(f"DELETE FROM active_sessions WHERE updated_at < {cutoff_sql}", params)

        # Keep only the latest N finished attempts per user/test.
        if MAX_FINISHED_ATTEMPTS_PER_USER_TEST > 0:
            old_rows = conn.execute(
                """
                SELECT attempt_id
                FROM (
                    SELECT
                        attempt_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY user_id, test_id
                            ORDER BY COALESCE(finished_at, started_at) DESC, attempt_id DESC
                        ) AS rn
                    FROM attempts
                    WHERE finished_at IS NOT NULL
                ) ranked
                WHERE rn > ?
                """,
                (MAX_FINISHED_ATTEMPTS_PER_USER_TEST,),
            ).fetchall()
            old_attempt_ids = [int(row["attempt_id"]) for row in old_rows]

            for batch in _chunked(old_attempt_ids):
                placeholders = ",".join(["?"] * len(batch))
                conn.execute(
                    f"DELETE FROM attempt_wrong_answers WHERE attempt_id IN ({placeholders})",
                    tuple(batch),
                )
                conn.execute(
                    f"DELETE FROM attempts WHERE attempt_id IN ({placeholders})",
                    tuple(batch),
                )

        # Remove very old wrong-answer rows that are not attached to an attempt.
        if ORPHAN_WRONG_ANSWER_TTL_DAYS > 0:
            cutoff_sql, params = _timestamp_cutoff_sql(ORPHAN_WRONG_ANSWER_TTL_DAYS)
            conn.execute(
                f"""
                DELETE FROM attempt_wrong_answers
                WHERE attempt_id IS NULL AND created_at < {cutoff_sql}
                """,
                params,
            )

        conn.commit()


def storage_debug_stats() -> dict[str, int | str | None]:
    """Small storage report for admin/debug screens."""
    with db_connect() as conn:
        data: dict[str, int | str | None] = {
            "backend": "PostgreSQL / Neon" if DATABASE_URL else "SQLite",
            "users": int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] or 0),
            "attempts": int(conn.execute("SELECT COUNT(*) AS c FROM attempts").fetchone()["c"] or 0),
            "finished_attempts": int(conn.execute("SELECT COUNT(*) AS c FROM attempts WHERE finished_at IS NOT NULL").fetchone()["c"] or 0),
            "active_sessions": int(conn.execute("SELECT COUNT(*) AS c FROM active_sessions").fetchone()["c"] or 0),
            "attempt_wrong_answers": int(conn.execute("SELECT COUNT(*) AS c FROM attempt_wrong_answers").fetchone()["c"] or 0),
            "all_time_errors": int(conn.execute("SELECT COUNT(*) AS c FROM all_time_errors").fetchone()["c"] or 0),
            "database_size_bytes": None,
        }
        if _table_exists(conn, "runtime_sessions"):
            data["runtime_sessions"] = int(conn.execute("SELECT COUNT(*) AS c FROM runtime_sessions").fetchone()["c"] or 0)
        else:
            data["runtime_sessions"] = 0

        if DATABASE_URL:
            row = conn.execute("SELECT pg_database_size(current_database()) AS size_bytes").fetchone()
            data["database_size_bytes"] = int(row["size_bytes"] or 0)
        return data


def init_db() -> None:
    if DATABASE_URL:
        _init_postgres_db()
    else:
        _init_sqlite_db()
    cleanup_old_data()


def upsert_user(user) -> None:
    if not user:
        return

    now = time.time()
    last_updated = _USER_UPSERT_CACHE.get(user.id)
    if last_updated is not None and now - last_updated < USER_UPSERT_CACHE_TTL_SECONDS:
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

    _USER_UPSERT_CACHE[user.id] = now

def ensure_user_stats(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO user_stats (user_id, test_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, test_id) DO NOTHING
            """,
            (user_id, test_id),
        )
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

        if DATABASE_URL:
            row = conn.execute(
                """
                INSERT INTO attempts (user_id, test_id, mode)
                VALUES (?, ?, ?)
                RETURNING attempt_id
                """,
                (user_id, test_id, mode),
            ).fetchone()
            attempt_id = int(row["attempt_id"])
        else:
            cur = conn.execute("INSERT INTO attempts (user_id, test_id, mode) VALUES (?, ?, ?)", (user_id, test_id, mode))
            attempt_id = int(cur.lastrowid)

        conn.commit()
        return attempt_id


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
            if DATABASE_URL:
                duration_expr = "EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at))::INTEGER"
            else:
                duration_expr = "CAST((julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400 AS INTEGER)"

            conn.execute(
                f"""
                UPDATE attempts
                SET finished_at = CURRENT_TIMESTAMP,
                    duration_seconds = {duration_expr},
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
                wrong_count = all_time_errors.wrong_count + 1,
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
