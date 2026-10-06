import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class StorageSmokeTestCase(unittest.TestCase):
    def test_sqlite_init_and_attempt_flow(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            db_path = Path(tmp_dir) / "quiz.sqlite3"
            os.environ["DB_PATH"] = str(db_path)
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

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
            self.assertEqual(summary["total_answered"], 2)
            self.assertEqual(summary["total_correct"], 1)
            self.assertEqual(storage.get_attempt_wrong_answers(777, "sample", attempt_id)[0]["question_index"], 1)

            with sqlite3.connect(db_path) as conn:
                index_count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'").fetchone()[0]
            self.assertGreater(index_count, 0)

            # Test feedback storage
            fb_id = storage.save_support_feedback(
                user_id=777,
                contact="@issdm",
                fb_type="bug",
                message="Вопрос 14 требует уточнения",
                test_id="sample"
            )
            self.assertIsNotNone(fb_id)
            feedbacks = storage.list_support_feedback(limit=10)
            self.assertGreaterEqual(len(feedbacks), 1)
            self.assertEqual(feedbacks[0]["message"], "Вопрос 14 требует уточнения")
            self.assertEqual(feedbacks[0]["contact"], "@issdm")

            # Test test_access storage
            storage.set_test_access_setting("sample", "code", code="secret123", updated_by=777)
            setting = storage.get_test_access_setting("sample")
            self.assertIsNotNone(setting)
            self.assertEqual(setting["type"], "code")
            self.assertEqual(setting["code"], "secret123")

            storage.set_test_access_setting("sample", "public")
            setting2 = storage.get_test_access_setting("sample")
            self.assertIsNotNone(setting2)
            self.assertEqual(setting2["type"], "public")

            # Test deleted subjects storage
            self.assertFalse(storage.is_subject_deleted("test_subj"))
            storage.delete_subject_setting("test_subj", updated_by=777)
            self.assertTrue(storage.is_subject_deleted("test_subj"))
            self.assertIn("test_subj", storage.get_deleted_subject_ids())

            # Re-creating subject clears deleted mark
            storage.set_subject_setting("test_subj", "Test Subj", "📚", updated_by=777)
            self.assertFalse(storage.is_subject_deleted("test_subj"))

            # Test unlinking metadata
            storage.set_test_metadata_setting("sample", subject_id="test_subj", subject_title="Test Subj", subject_emoji="📚")
            meta = storage.get_test_metadata_setting("sample")
            self.assertEqual(meta["subject_id"], "test_subj")

            storage.set_test_metadata_setting("sample", subject_id="default", subject_title="", subject_emoji="")
            meta_unlinked = storage.get_test_metadata_setting("sample")
            # Test rating privacy toggle
            self.assertFalse(storage.is_user_rating_hidden(777))
            storage.set_user_rating_hidden(777, True)
            self.assertTrue(storage.is_user_rating_hidden(777))
            storage.set_user_rating_hidden(777, False)
            self.assertFalse(storage.is_user_rating_hidden(777))

            # Test reset user rating
            reset_res = storage.reset_user_rating(777)
            self.assertGreaterEqual(reset_res["attempts"], 1)
            summary_after = storage.stats_summary(777, "sample")
            self.assertEqual(summary_after["total_answered"], 0)


if __name__ == "__main__":
    unittest.main()



