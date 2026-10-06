import os
import tempfile
import unittest
from pathlib import Path

from quiz_bot.webapp import create_webapp


class AdminApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "quiz.sqlite3"
        os.environ["DB_PATH"] = str(self.db_path)
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        import quiz_bot.config as config
        import quiz_bot.storage as storage

        config.DB_PATH = self.db_path
        storage.DB_PATH = self.db_path
        storage.DATABASE_URL = None
        storage.init_db()

        with storage.db_connect() as conn:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (12345, "admin_user", "Admin", "Test"),
            )
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (99999, "student_user", "Student", "Test"),
            )
            conn.commit()
        os.environ["ADMIN_IDS"] = "12345"
        config.ADMIN_IDS = frozenset([12345])

        # Record an attempt for student
        att_id = storage.record_attempt_start(99999, "oziz_1_200", "normal")
        storage.record_answer(99999, "oziz_1_200", True, question_index=0)
        storage.record_answer(99999, "oziz_1_200", False, question_index=1)
        storage.add_all_time_error(99999, "oziz_1_200", 1, 0)
        storage.record_attempt_finish(99999, "oziz_1_200", att_id, answered=2, correct=1, completed_full_test=True, finished_by_user=True)

        self.app = create_webapp()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_admin_users_api(self):
        # Unauthorized access
        res = self.client.get("/api/admin/users?user_id=99999")
        self.assertEqual(res.status_code, 403)

        # Authorized access
        res = self.client.get("/api/admin/users?user_id=12345")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(len(data["users"]), 2)

        student = next((u for u in data["users"] if u["user_id"] == 99999), None)
        self.assertIsNotNone(student)
        self.assertEqual(student["attempts_count"], 1)
        self.assertEqual(student["correct_count"], 1)
        self.assertEqual(student["answered_count"], 2)
        self.assertEqual(student["accuracy"], 50)

    def test_admin_user_detail_api(self):
        res = self.client.get("/api/admin/user/detail?user_id=12345&target_user_id=99999")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["user_id"], 99999)
        self.assertEqual(len(data["attempts"]), 1)
        self.assertGreaterEqual(len(data["errors"]), 1)

    def test_admin_block_and_unblock_api(self):
        # Block user
        res = self.client.post(
            "/api/admin/user/block",
            json={"user_id": 12345, "target_user_id": 99999, "reason": "Test block"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Check detail shows blocked
        res_det = self.client.get("/api/admin/user/detail?user_id=12345&target_user_id=99999")
        self.assertTrue(res_det.get_json()["user"]["is_blocked"])

        # Unblock user
        res_unblock = self.client.post(
            "/api/admin/user/unblock",
            json={"user_id": 12345, "target_user_id": 99999},
        )
        self.assertEqual(res_unblock.status_code, 200)
        self.assertTrue(res_unblock.get_json()["success"])

        res_det2 = self.client.get("/api/admin/user/detail?user_id=12345&target_user_id=99999")
        self.assertFalse(res_det2.get_json()["user"]["is_blocked"])

    def test_admin_unlink_and_assign_api(self):
        # Unlink test
        res_unlink = self.client.post(
            "/api/admin/unlink_test",
            json={"user_id": 12345, "test_id": "oziz_1_200"},
        )
        self.assertEqual(res_unlink.status_code, 200)
        self.assertTrue(res_unlink.get_json()["success"])

        # Assign test
        res_assign = self.client.post(
            "/api/admin/assign_test",
            json={"user_id": 12345, "test_id": "oziz_1_200", "subject_id": "oziz"},
        )
        self.assertEqual(res_assign.status_code, 200)
        self.assertTrue(res_assign.get_json()["success"])

    def test_admin_delete_subject_api(self):
        res = self.client.post(
            "/api/admin/delete_subject",
            json={"user_id": 12345, "id": "oziz"},
        )
        self.assertEqual(res.status_code, 200)
    def test_user_rating_visibility_and_reset_api(self):
        # Initial rating shows student 99999
        res_r1 = self.client.get("/api/rating?test_id=oziz_1_200")
        self.assertEqual(res_r1.status_code, 200)
        items1 = res_r1.get_json()["items"]
        self.assertTrue(any(it["user_id"] == 99999 for it in items1))

        # Bootstrap shows not hidden
        res_b1 = self.client.get("/api/bootstrap?user_id=99999")
        self.assertEqual(res_b1.status_code, 200)
        self.assertFalse(res_b1.get_json()["is_hidden_in_rating"])

        # Hide user 99999
        res_tog = self.client.post(
            "/api/user/toggle_rating_visibility",
            json={"user_id": 99999, "is_hidden": True},
        )
        self.assertEqual(res_tog.status_code, 200)
        self.assertTrue(res_tog.get_json()["is_hidden"])

        # Bootstrap now shows hidden
        res_b2 = self.client.get("/api/bootstrap?user_id=99999")
        self.assertTrue(res_b2.get_json()["is_hidden_in_rating"])

        # Rating query no longer includes user 99999
        res_r2 = self.client.get("/api/rating?test_id=oziz_1_200")
        items2 = res_r2.get_json()["items"]
        self.assertFalse(any(it["user_id"] == 99999 for it in items2))

        # Reset rating for user 99999
        res_reset = self.client.post(
            "/api/user/reset_rating",
            json={"user_id": 99999},
        )
        self.assertEqual(res_reset.status_code, 200)
        self.assertTrue(res_reset.get_json()["success"])
        self.assertGreaterEqual(res_reset.get_json()["deleted_attempts"], 1)

        # Unhide user, rating should still have no attempts because they were reset
        self.client.post("/api/user/toggle_rating_visibility", json={"user_id": 99999, "is_hidden": False})
        res_r3 = self.client.get("/api/rating?test_id=oziz_1_200")
        items3 = res_r3.get_json()["items"]
        self.assertFalse(any(it["user_id"] == 99999 for it in items3))


if __name__ == "__main__":
    unittest.main()
