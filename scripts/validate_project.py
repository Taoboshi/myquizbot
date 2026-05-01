#!/usr/bin/env python3
"""Fast local validation for the quiz bot project.

Checks:
- Python syntax for project files;
- JSON quiz loading/normalization;
- duplicate question text hints;
- SQLite schema creation;
- a minimal attempt/statistics write flow.
"""

from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check_python_syntax() -> None:
    for path in sorted((ROOT / "quiz_bot").glob("*.py")) + sorted((ROOT / "scripts").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def check_tests_loaded() -> None:
    from quiz_bot.loader import LOADED_TESTS, TESTS

    if not LOADED_TESTS:
        raise AssertionError("No quiz tests were loaded")

    total = sum(len(items) for items in LOADED_TESTS.values())
    print(f"Loaded tests: {len(LOADED_TESTS)} files, {total} questions")

    duplicates: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for test_id, questions in LOADED_TESTS.items():
        if test_id not in TESTS:
            raise AssertionError(f"Loaded test without metadata: {test_id}")
        seen = Counter(" ".join(q["question"].split()).casefold() for q in questions)
        for question_text, count in seen.items():
            if count > 1:
                duplicates[test_id].append((question_text, count))

    if duplicates:
        print("Duplicate question texts to review:")
        for test_id, items in sorted(duplicates.items()):
            preview = "; ".join(f"{count}× {text[:70]}" for text, count in items[:5])
            print(f"- {test_id}: {preview}")


def check_storage_smoke() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "smoke.sqlite3"
        os.environ["DB_PATH"] = str(db_path)

        import quiz_bot.config as config
        import quiz_bot.storage as storage

        config.DB_PATH = db_path
        storage.DB_PATH = db_path
        storage.DATABASE_URL = None

        storage.init_db()
        attempt_id = storage.record_attempt_start(123, "smoke_test", "normal")
        storage.record_attempt_order(attempt_id, [0, 1, 2])
        storage.record_answer(123, "smoke_test", True, question_index=0)
        storage.record_answer(123, "smoke_test", False, question_index=1)
        storage.add_all_time_error(123, "smoke_test", question_index=1, wrong_answer_index=0)
        storage.record_attempt_wrong_answer(attempt_id, 123, "smoke_test", 1, 0)
        storage.record_attempt_finish(
            user_id=123,
            test_id="smoke_test",
            attempt_id=attempt_id,
            answered=2,
            correct=1,
            completed_full_test=False,
            finished_by_user=True,
        )
        summary = storage.stats_summary(123, "smoke_test")
        if int(summary.get("total_answered") or 0) != 2:
            raise AssertionError(f"Unexpected stats summary: {summary}")

        with sqlite3.connect(db_path) as conn:
            indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
            if not indexes:
                raise AssertionError("SQLite indexes were not created")


def main() -> None:
    check_python_syntax()
    check_tests_loaded()
    check_storage_smoke()
    print("Validation passed")


if __name__ == "__main__":
    main()
