import sqlite3


def test_sqlite_init_and_attempt_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "quiz.sqlite3"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import quiz_bot.config as config
    import quiz_bot.storage as storage

    config.DB_PATH = db_path
    storage.DB_PATH = db_path
    storage.DATABASE_URL = None

    storage.init_db()
    attempt_id = storage.record_attempt_start(777, "sample", "normal")
    storage.record_attempt_order(attempt_id, [0, 2, 1])
    storage.record_answer(777, "sample", True, question_index=0)
    storage.record_answer(777, "sample", False, question_index=1)
    storage.add_all_time_error(777, "sample", 1, 0)
    storage.record_attempt_wrong_answer(attempt_id, 777, "sample", 1, 0)
    storage.record_attempt_finish(777, "sample", attempt_id, 2, 1, False, True)

    summary = storage.stats_summary(777, "sample")
    assert summary["total_answered"] == 2
    assert summary["total_correct"] == 1
    assert storage.get_attempt_wrong_answers(777, "sample", attempt_id)[0]["question_index"] == 1

    with sqlite3.connect(db_path) as conn:
        index_count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'").fetchone()[0]
    assert index_count > 0
