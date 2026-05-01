import os

# Set environment variables BEFORE importing quiz_bot modules
os.environ["TELEGRAM_BOT_TOKEN"] = "dummy"
os.environ["DB_PATH"] = "test_integrity.sqlite3"

import sqlite3
import unittest
from quiz_bot.loader import LOADED_TESTS
from quiz_bot.storage import init_db

class TestBotIntegrity(unittest.TestCase):
    def tearDown(self):
        if os.path.exists("test_integrity.sqlite3"):
            os.remove("test_integrity.sqlite3")

    def test_test_loading(self):
        """Verify that the default test is loaded correctly."""
        test_id = "oziz_module_2"
        self.assertIn(test_id, LOADED_TESTS)
        self.assertEqual(len(LOADED_TESTS[test_id]), 203)

    def test_db_initialization(self):
        """Verify that the database schema is correctly initialized."""
        init_db()
        self.assertTrue(os.path.exists("test_integrity.sqlite3"))

        conn = sqlite3.connect("test_integrity.sqlite3")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected_tables = [
            "users", "user_stats", "user_answered_questions", "attempts",
            "all_time_errors", "attempt_wrong_answers", "active_sessions",
            "favorites", "user_test_access", "test_access_settings",
            "test_metadata_settings", "subject_settings"
        ]

        for table in expected_tables:
            with self.subTest(table=table):
                self.assertIn(table, tables)

if __name__ == "__main__":
    unittest.main()
