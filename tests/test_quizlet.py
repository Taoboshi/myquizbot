import sqlite3
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from quiz_bot import loader, storage
from quiz_bot.webapp import create_webapp


class QuizletTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        # Exercise migration of an existing database, not just a fresh schema.
        self.connection.execute("""CREATE TABLE test_metadata_settings (
            test_id TEXT PRIMARY KEY, title TEXT, subject_id TEXT, subject_title TEXT,
            subject_emoji TEXT, updated_at TEXT, updated_by INTEGER)""")
        patches = (
            patch.object(storage, "DATABASE_URL", None),
            patch.object(storage, "db_connect", return_value=self.connection),
            patch("quiz_bot.webapp._verified_telegram_data", return_value={"id": 12345}),
            patch("quiz_bot.webapp.is_admin_user", return_value=True),
            patch.dict(loader.TESTS, {"sample_cards": {"title": "Sample", "subject_id": "default"}}),
            patch.dict(loader.LOADED_TESTS, {"sample_cards": [
                {"question": "Question", "options": ["Correct", "Wrong"], "correct_index": 0}
            ]}),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(storage.clear_cache)
        storage.clear_cache()
        storage.init_db()
        storage.init_db()
        self.client = create_webapp().test_client()

    def tearDown(self):
        self.connection.close()

    def test_format_persists_through_rename_and_assignment(self):
        storage.set_test_metadata_setting("sample_cards", study_mode="quizlet")
        storage.set_test_metadata_setting("sample_cards", title="New title")
        storage.set_test_metadata_setting("sample_cards", subject_id="anatomy", subject_title="Anatomy")
        self.assertEqual(loader.get_test_study_mode("sample_cards"), "quizlet")
        self.assertEqual(loader.effective_test_info("sample_cards")["title"], "New title")
        storage.set_test_metadata_setting("sample_cards", study_mode="test")
        self.assertEqual(loader.get_test_study_mode("sample_cards"), "test")

    def test_question_answer_cards_reuse_existing_normalized_shape(self):
        question = loader.normalize_question({"question": "Term", "answer": "Definition"}, 0, "quizlet")
        self.assertEqual(question["options"], ["Definition"])
        self.assertEqual(question["correct_index"], 0)
        data = {"study_mode": "quizlet", "questions": [{"question": "Term", "answer": "Definition"}]}
        self.assertEqual(loader._questions_from_data(data, Path("cards.json")), [question])
        self.assertEqual(loader.normalize_question({"question": "Term", "answer": "Definition"}, 0), question)
        with self.assertRaises(ValueError):
            loader.normalize_question({"question": "Term", "answer": " "}, 0, "quizlet")

    def test_preview_supports_quizlet_and_preserves_standard_tests(self):
        response = self.client.post("/api/admin/preview_test", json={
            "filename": "cards.json", "data": {
                "study_mode": "quizlet", "questions": [{"question": "Term", "answer": "Definition"}]
            }
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["study_mode"], "quizlet")
        self.assertEqual(response.json["questions"][0]["options"], ["Definition"])
        response = self.client.post("/api/admin/preview_test", json={
            "filename": "test.json", "data": {"questions": loader.LOADED_TESTS["sample_cards"]}
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["study_mode"], "test")
        response = self.client.post("/api/admin/preview_test", json={
            "filename": "mixed.json", "data": {
                "study_mode": "test", "questions": [{"question": "Term", "answer": "Definition"}]
            }
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["questions"][0]["options"], ["Definition"])
        self.assertEqual(response.json["study_mode"], "test")

    def test_format_api_updates_catalog_and_detail(self):
        response = self.client.post("/api/admin/set_test_study_mode", json={
            "test_id": "sample_cards", "study_mode": "quizlet"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["study_mode"], "quizlet")
        self.assertEqual(self.client.get("/api/tests/sample_cards").json["study_mode"], "quizlet")
        items = self.client.get("/api/admin/tests").json["items"]
        self.assertEqual(next(item for item in items if item["id"] == "sample_cards")["study_mode"], "quizlet")

    def test_format_api_rejects_non_admin_invalid_modes_and_missing_tests(self):
        with patch("quiz_bot.webapp.is_admin_user", return_value=False):
            response = self.client.post("/api/admin/set_test_study_mode", json={
                "test_id": "sample_cards", "study_mode": "quizlet"
            })
            self.assertEqual(response.status_code, 403)
        for mode in ("bad", None, [], {}):
            response = self.client.post("/api/admin/set_test_study_mode", json={
                "test_id": "sample_cards", "study_mode": mode
            })
            self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/admin/set_test_study_mode", json={
            "test_id": "missing", "study_mode": "quizlet"
        })
        self.assertEqual(response.status_code, 404)

    def test_single_answer_material_can_be_switched_to_test_and_quizlet(self):
        with patch.dict(loader.LOADED_TESTS, {"sample_cards": [
            {"question": "Term", "options": ["Definition"], "correct_index": 0}
        ]}):
            self.assertEqual(loader.get_test_study_mode("sample_cards"), "quizlet")
            response = self.client.post("/api/admin/set_test_study_mode", json={
                "test_id": "sample_cards", "study_mode": "test"
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["study_mode"], "test")

    def test_upload_refreshes_live_questions_without_restart(self):
        question = {"question": "Term", "options": ["Definition"], "correct_index": 0}
        with (
            patch("pathlib.Path.open", mock_open()),
            patch("quiz_bot.webapp.load_tests", return_value={"sample_cards": [question]}),
        ):
            response = self.client.post("/api/admin/upload_test", json={
                "filename": "sample_cards.json", "data": {
                    "study_mode": "quizlet", "questions": [{"question": "Term", "answer": "Definition"}]
                }
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["study_mode"], "quizlet")
        detail = self.client.get("/api/tests/sample_cards").json
        self.assertEqual(detail["questions"][0]["options"], ["Definition"])
        self.assertEqual(detail["study_mode"], "quizlet")


if __name__ == "__main__":
    unittest.main()
