import hashlib
import json
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


_POLLING_LOCK_CONN = None
_USER_UPSERT_CACHE: dict[int, float] = {}
USER_UPSERT_CACHE_TTL_SECONDS = int(os.getenv("USER_UPSERT_CACHE_TTL_SECONDS", "600"))


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
        _POLLING_LOCK_CONN.close()
    finally:
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


def _row_get(row, key, default=None):
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return default


def _table_exists(conn, table_name: str) -> bool:
    try:
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
            return bool(_row_get(row, "exists", False))

        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    try:
        if DATABASE_URL:
            row = conn.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
                ) AS exists
                """,
                (table_name, column_name),
            ).fetchone()
            return bool(_row_get(row, "exists", False))

        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(_row_get(row, "name") == column_name for row in rows)
    except Exception:
        return False


def _add_column_if_missing(conn, table_name: str, column_sql: str) -> None:
    column_name = column_sql.split()[0]
    if _column_exists(conn, table_name, column_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


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
            CREATE TABLE IF NOT EXISTS user_answered_questions (
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                first_answered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_answered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                answer_count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, test_id, question_index)
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id, question_index)
            )
            """
        )

        for stmt in [
            "ALTER TABLE all_time_errors ADD COLUMN IF NOT EXISTS last_wrong_answer_index INTEGER",
            "ALTER TABLE attempts ADD COLUMN IF NOT EXISTS finished_by_user INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE active_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
            "ALTER TABLE all_time_errors ADD COLUMN IF NOT EXISTS first_wrong_at TIMESTAMP",
            "ALTER TABLE all_time_errors ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP",
            "ALTER TABLE all_time_errors ADD COLUMN IF NOT EXISTS is_resolved INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE attempts ADD COLUMN IF NOT EXISTS question_order_json TEXT",
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

            CREATE TABLE IF NOT EXISTS user_answered_questions (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                first_answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                answer_count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, test_id, question_index)
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

            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id, question_index)
            );
            """
        )

        for stmt in [
            "ALTER TABLE all_time_errors ADD COLUMN last_wrong_answer_index INTEGER",
            "ALTER TABLE attempts ADD COLUMN finished_by_user INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE active_sessions ADD COLUMN updated_at TEXT",
            "ALTER TABLE all_time_errors ADD COLUMN first_wrong_at TEXT",
            "ALTER TABLE all_time_errors ADD COLUMN resolved_at TEXT",
            "ALTER TABLE all_time_errors ADD COLUMN is_resolved INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE attempts ADD COLUMN question_order_json TEXT",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

        conn.commit()


def init_db() -> None:
    if DATABASE_URL:
        _init_postgres_db()
    else:
        _init_sqlite_db()


def upsert_user(user) -> None:
    if not user:
        return

    now = time.time()
    last_seen = _USER_UPSERT_CACHE.get(user.id)
    if last_seen is not None and now - last_seen < USER_UPSERT_CACHE_TTL_SECONDS:
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


def _answered_indices_from_session_json(state_json: str | None) -> set[int]:
    if not state_json:
        return set()
    try:
        data = json.loads(state_json)
    except (TypeError, json.JSONDecodeError):
        return set()

    order = data.get("order") or []
    try:
        pos = int(data.get("pos") or 0)
    except (TypeError, ValueError):
        pos = 0

    pos = max(0, min(pos, len(order)))
    indices: set[int] = set()

    for raw_index in order[:pos]:
        try:
            indices.add(int(raw_index))
        except (TypeError, ValueError):
            pass

    if data.get("awaiting_next") and pos < len(order):
        try:
            indices.add(int(order[pos]))
        except (TypeError, ValueError):
            pass

    return indices


def get_answered_question_count(user_id: int, test_id: str) -> int:
    """Return count of different questions the user has answered in this test.

    Old builds only stored total answer clicks. The session fallback lets the profile
    show current in-progress progress even if the detailed table was added later.
    """
    indices: set[int] = set()

    with db_connect() as conn:
        if _table_exists(conn, "user_answered_questions"):
            rows = conn.execute(
                """
                SELECT question_index
                FROM user_answered_questions
                WHERE user_id = ? AND test_id = ?
                """,
                (user_id, test_id),
            ).fetchall()
            for row in rows:
                try:
                    indices.add(int(row["question_index"]))
                except (TypeError, ValueError):
                    pass

        session_rows = conn.execute(
            """
            SELECT state_json
            FROM active_sessions
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchall()
        for row in session_rows:
            indices.update(_answered_indices_from_session_json(row["state_json"]))

        if _table_exists(conn, "runtime_sessions"):
            runtime_rows = conn.execute(
                """
                SELECT state_json
                FROM runtime_sessions
                WHERE user_id = ? AND test_id = ?
                """,
                (user_id, test_id),
            ).fetchall()
            for row in runtime_rows:
                indices.update(_answered_indices_from_session_json(row["state_json"]))

    return len(indices)


def record_answer(user_id: int, test_id: str, is_correct: bool, question_index: int | None = None) -> None:
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
        if question_index is not None:
            conn.execute(
                """
                INSERT INTO user_answered_questions (
                    user_id, test_id, question_index, first_answered_at, last_answered_at, answer_count
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(user_id, test_id, question_index)
                DO UPDATE SET
                    last_answered_at = CURRENT_TIMESTAMP,
                    answer_count = user_answered_questions.answer_count + 1
                """,
                (user_id, test_id, question_index),
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
            INSERT INTO all_time_errors (user_id, test_id, question_index, wrong_count, last_wrong_answer_index, first_wrong_at, last_wrong_at, is_resolved, resolved_at)
            VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, NULL)
            ON CONFLICT(user_id, test_id, question_index)
            DO UPDATE SET
                wrong_count = all_time_errors.wrong_count + 1,
                last_wrong_answer_index = excluded.last_wrong_answer_index,
                last_wrong_at = CURRENT_TIMESTAMP,
                is_resolved = 0,
                resolved_at = NULL
            """,
            (user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()


def remove_all_time_error(user_id: int, test_id: str, question_index: int) -> None:
    # Ошибка остаётся в истории профиля, но больше не попадает в «Разобрать ошибки».
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE all_time_errors
            SET is_resolved = 1,
                resolved_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ? AND question_index = ?
            """,
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
            WHERE user_id = ? AND test_id = ? AND COALESCE(is_resolved, 0) = 0
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


PAGE_SIZE = 10


def _dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        return {k: row[k] for k in row.keys()}


def record_attempt_order(attempt_id: int | None, order: list[int]) -> None:
    if attempt_id is None:
        return
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE attempts
            SET question_order_json = ?
            WHERE attempt_id = ?
            """,
            (json.dumps([int(x) for x in order], ensure_ascii=False), attempt_id),
        )
        conn.commit()


def get_attempt(attempt_id: int | None) -> dict[str, Any] | None:
    if attempt_id is None:
        return None
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
    return _dict(row)


def get_attempt_order(attempt_id: int | None) -> list[int]:
    row = get_attempt(attempt_id)
    if not row:
        return []
    raw = row.get("question_order_json")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    order = []
    for item in data:
        try:
            order.append(int(item))
        except (TypeError, ValueError):
            pass
    return order


def list_attempts(user_id: int, test_id: str, page: int = 0, page_size: int = PAGE_SIZE) -> tuple[list[dict[str, Any]], int]:
    page = max(0, int(page or 0))
    offset = page * page_size
    with db_connect() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL AND answered > 0
            """,
            (user_id, test_id),
        ).fetchone()["c"] or 0
        rows = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL AND answered > 0
            ORDER BY finished_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, test_id, page_size, offset),
        ).fetchall()
    return [_dict(row) for row in rows], int(total)


def get_attempt_wrong_answers(user_id: int, test_id: str, attempt_id: int | None) -> list[dict[str, Any]]:
    if attempt_id is None:
        return []
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, wrong_answer_index, created_at
            FROM attempt_wrong_answers
            WHERE user_id = ? AND test_id = ? AND attempt_id = ?
            ORDER BY id ASC
            """,
            (user_id, test_id, attempt_id),
        ).fetchall()
    return [_dict(row) for row in rows]


def favorite_count(user_id: int, test_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM favorites WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        ).fetchone()
    return int(row["c"] or 0)


def is_favorite(user_id: int, test_id: str, question_index: int) -> bool:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM favorites
            WHERE user_id = ? AND test_id = ? AND question_index = ?
            LIMIT 1
            """,
            (user_id, test_id, question_index),
        ).fetchone()
    return row is not None


def set_favorite(user_id: int, test_id: str, question_index: int, value: bool) -> bool:
    with db_connect() as conn:
        if value:
            conn.execute(
                """
                INSERT INTO favorites (user_id, test_id, question_index, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, test_id, question_index) DO NOTHING
                """,
                (user_id, test_id, question_index),
            )
        else:
            conn.execute(
                "DELETE FROM favorites WHERE user_id = ? AND test_id = ? AND question_index = ?",
                (user_id, test_id, question_index),
            )
        conn.commit()
    return value


def toggle_favorite(user_id: int, test_id: str, question_index: int) -> bool:
    new_value = not is_favorite(user_id, test_id, question_index)
    return set_favorite(user_id, test_id, question_index, new_value)


def list_favorites(user_id: int, test_id: str, page: int = 0, page_size: int = PAGE_SIZE) -> tuple[list[int], int]:
    page = max(0, int(page or 0))
    offset = page * page_size
    with db_connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM favorites WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        ).fetchone()["c"] or 0
        rows = conn.execute(
            """
            SELECT question_index
            FROM favorites
            WHERE user_id = ? AND test_id = ?
            ORDER BY created_at DESC, question_index ASC
            LIMIT ? OFFSET ?
            """,
            (user_id, test_id, page_size, offset),
        ).fetchall()
    return [int(row["question_index"]) for row in rows], int(total)


def error_counts(user_id: int, test_id: str) -> dict[str, int]:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN COALESCE(is_resolved, 0) = 0 THEN 1 ELSE 0 END), 0) AS unresolved,
                COALESCE(SUM(CASE WHEN COALESCE(is_resolved, 0) = 1 THEN 1 ELSE 0 END), 0) AS resolved
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "unresolved": int(row["unresolved"] or 0),
        "resolved": int(row["resolved"] or 0),
    }


def list_profile_errors(user_id: int, test_id: str, page: int = 0, page_size: int = PAGE_SIZE) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    page = max(0, int(page or 0))
    offset = page * page_size
    counts = error_counts(user_id, test_id)
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, wrong_count, last_wrong_answer_index, first_wrong_at, last_wrong_at, resolved_at, COALESCE(is_resolved, 0) AS is_resolved
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            ORDER BY COALESCE(is_resolved, 0) ASC, last_wrong_at DESC, question_index ASC
            LIMIT ? OFFSET ?
            """,
            (user_id, test_id, page_size, offset),
        ).fetchall()
    return [_dict(row) for row in rows], counts["total"], counts


def get_profile_error_items(user_id: int, test_id: str) -> list[dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, wrong_count, last_wrong_answer_index, first_wrong_at, last_wrong_at, resolved_at, COALESCE(is_resolved, 0) AS is_resolved
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            ORDER BY COALESCE(is_resolved, 0) ASC, last_wrong_at DESC, question_index ASC
            """,
            (user_id, test_id),
        ).fetchall()
    return [_dict(row) for row in rows]


def _avg_percent_row(conn, user_id: int, test_id: str, modes: tuple[str, ...]) -> dict[str, Any]:
    placeholders = ",".join(["?"] * len(modes))
    params = (user_id, test_id, *modes)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS attempts,
            COALESCE(AVG(CASE WHEN answered > 0 THEN CAST(correct AS REAL) / answered * 100 ELSE 0 END), 0) AS avg_percent,
            COALESCE(MAX(CASE WHEN answered > 0 THEN CAST(correct AS REAL) / answered * 100 ELSE 0 END), 0) AS best_percent
        FROM attempts
        WHERE user_id = ? AND test_id = ? AND mode IN ({placeholders}) AND finished_at IS NOT NULL AND answered > 0
        """,
        params,
    ).fetchone()
    return _dict(row) or {"attempts": 0, "avg_percent": 0, "best_percent": 0}


def latest_attempt(user_id: int, test_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ?
              AND test_id = ?
              AND finished_at IS NOT NULL
              AND answered > 0
              AND mode != 'repeat_attempt'
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()
    return _dict(row)


def best_attempt(user_id: int, test_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ?
              AND test_id = ?
              AND finished_at IS NOT NULL
              AND answered > 0
              AND mode != 'repeat_attempt'
            ORDER BY (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC, correct DESC, finished_at DESC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()
    return _dict(row)


def stats_summary(user_id: int, test_id: str) -> dict[str, Any]:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        stats = conn.execute(
            "SELECT attempts_started, attempts_finished, total_answered, total_correct FROM user_stats WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        ).fetchone()
        overall = _avg_percent_row(conn, user_id, test_id, ("normal", "random", "reverse", "from_number", "mini", "errors"))
        solution = _avg_percent_row(conn, user_id, test_id, ("normal", "random", "reverse", "from_number"))
        training = _avg_percent_row(conn, user_id, test_id, ("mini",))
        errors_mode = _avg_percent_row(conn, user_id, test_id, ("errors",))
    stats = _dict(stats) or {}
    return {
        "attempts_started": int(stats.get("attempts_started") or 0),
        "attempts_finished": int(stats.get("attempts_finished") or 0),
        "total_answered": int(stats.get("total_answered") or 0),
        "total_correct": int(stats.get("total_correct") or 0),
        "overall": overall,
        "solution": solution,
        "training": training,
        "errors_mode": errors_mode,
        "latest": latest_attempt(user_id, test_id),
        "best": best_attempt(user_id, test_id),
        "errors": error_counts(user_id, test_id),
        "favorites": favorite_count(user_id, test_id),
        "answered_questions": get_answered_question_count(user_id, test_id),
    }
