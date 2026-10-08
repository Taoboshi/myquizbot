import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from quiz_bot.webapp import create_webapp


def _make_init_data(user_id: int, bot_token: str = "test_bot_token") -> str:
    user = {"id": user_id, "first_name": "TestUser", "username": "test_user"}
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(fields)


class AdminApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "quiz.sqlite3"
        os.environ["DB_PATH"] = str(self.db_path)
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token"
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        import quiz_bot.config as config
        import quiz_bot.storage as storage

        config.DB_PATH = self.db_path
        config.BOT_TOKEN = "test_bot_token"
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

    def _auth_header(self, user_id: int) -> dict[str, str]:
        return {"X-Telegram-Init-Data": _make_init_data(user_id)}

    def test_subject_icons_can_be_assigned_and_changed(self):
        from quiz_bot.storage import get_subject_setting

        headers = self._auth_header(12345)
        for icon_key in ("stethoscope", "histology", "gynecology", "informatics"):
            with self.subTest(icon_key=icon_key):
                subject_id = f"icon_test_{icon_key}"
                created = self.client.post("/api/admin/add_subject", headers=headers, json={
                    "user_id": 12345, "id": subject_id,
                    "title": "Test subject", "icon_key": icon_key,
                })
                self.assertEqual(created.status_code, 200)
                self.assertEqual(get_subject_setting(subject_id)["icon_key"], icon_key)

                edited = self.client.post("/api/admin/edit_subject", headers=headers, json={
                    "user_id": 12345, "id": subject_id,
                    "title": "Renamed subject", "icon_key": "oncology",
                })
                self.assertEqual(edited.status_code, 200)
                self.assertEqual(get_subject_setting(subject_id)["icon_key"], "oncology")

        invalid = self.client.post("/api/admin/edit_subject", headers=headers, json={
            "user_id": 12345, "id": "icon_test_histology",
            "title": "Test subject", "icon_key": "unknown_icon",
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(get_subject_setting("icon_test_histology")["icon_key"], "oncology")

    def test_admin_users_api(self):
        # Unauthorized access
        res = self.client.get(
            "/api/admin/users?user_id=99999",
            headers=self._auth_header(99999),
        )
        self.assertEqual(res.status_code, 403)

        # Authorized access
        res = self.client.get(
            "/api/admin/users?user_id=12345",
            headers=self._auth_header(12345),
        )
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
        res = self.client.get(
            "/api/admin/user/detail?user_id=12345&target_user_id=99999",
            headers=self._auth_header(12345),
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["user_id"], 99999)
        self.assertEqual(len(data["attempts"]), 1)
        self.assertGreaterEqual(len(data["errors"]), 1)

    def test_user_state_returns_database_profile_data(self):
        import quiz_bot.storage as storage

        storage.set_favorite(99999, "oziz_1_200", 2, True)
        response = self.client.get("/api/user/state", headers=self._auth_header(99999))
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["tests"]["oziz_1_200"]["errors"], [2])
        self.assertEqual(data["tests"]["oziz_1_200"]["favorites"], [3])
        self.assertEqual(len(data["attempts"]), 1)
        self.assertEqual(data["attempts"][0]["correct"], 1)

    def test_custom_profile_is_saved_and_returned_by_bootstrap(self):
        headers = self._auth_header(99999)
        saved = self.client.post(
            "/api/user/profile",
            headers=headers,
            json={"display_name": "Моё имя", "avatar": "🧬"},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["profile"], {"display_name": "Моё имя", "avatar": "🧬"})

        bootstrap = self.client.get("/api/bootstrap?user_id=99999", headers=headers)
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(
            bootstrap.get_json()["user_profile"],
            {"display_name": "Моё имя", "avatar": "🧬"},
        )

    def test_custom_profile_rejects_untrusted_avatar_markup(self):
        response = self.client.post(
            "/api/user/profile",
            headers=self._auth_header(99999),
            json={"display_name": "Моё имя", "avatar": "<img src=x onerror=alert(1)>"},
        )
        self.assertEqual(response.status_code, 400)

    def test_web_favorite_can_be_saved_and_removed(self):
        headers = self._auth_header(99999)
        response = self.client.post("/api/user/favorite", headers=headers, json={
            "test_id": "oziz_1_200", "question_id": 3, "is_favorite": True,
        })
        self.assertEqual(response.status_code, 200)
        state_response = self.client.get("/api/user/state?test_id=oziz_1_200", headers=headers)
        self.assertEqual(state_response.get_json()["favorites"], [3])

        removed = self.client.post("/api/user/favorite", headers=headers, json={
            "test_id": "oziz_1_200", "question_id": 3, "is_favorite": False,
        })
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self.client.get("/api/user/state?test_id=oziz_1_200", headers=headers).get_json()["favorites"], [])

    def test_admin_block_and_unblock_api(self):
        # Block user
        res = self.client.post(
            "/api/admin/user/block",
            headers=self._auth_header(12345),
            json={"user_id": 12345, "target_user_id": 99999, "reason": "Test block"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Check detail shows blocked
        res_det = self.client.get(
            "/api/admin/user/detail?user_id=12345&target_user_id=99999",
            headers=self._auth_header(12345),
        )
        self.assertTrue(res_det.get_json()["user"]["is_blocked"])

        # Unblock user
        res_unblock = self.client.post(
            "/api/admin/user/unblock",
            headers=self._auth_header(12345),
            json={"user_id": 12345, "target_user_id": 99999},
        )
        self.assertEqual(res_unblock.status_code, 200)
        self.assertTrue(res_unblock.get_json()["success"])

        res_det2 = self.client.get(
            "/api/admin/user/detail?user_id=12345&target_user_id=99999",
            headers=self._auth_header(12345),
        )
        self.assertFalse(res_det2.get_json()["user"]["is_blocked"])

    def test_admin_unlink_and_assign_api(self):
        # Unlink test
        res_unlink = self.client.post(
            "/api/admin/unlink_test",
            headers=self._auth_header(12345),
            json={"user_id": 12345, "test_id": "oziz_1_200"},
        )
        self.assertEqual(res_unlink.status_code, 200)
        self.assertTrue(res_unlink.get_json()["success"])

        # Assign test
        res_assign = self.client.post(
            "/api/admin/assign_test",
            headers=self._auth_header(12345),
            json={"user_id": 12345, "test_id": "oziz_1_200", "subject_id": "oziz"},
        )
        self.assertEqual(res_assign.status_code, 200)
        self.assertTrue(res_assign.get_json()["success"])

    def test_admin_unassigned_api_returns_tests_for_linking(self):
        with (
            patch("quiz_bot.webapp.get_unassigned_tests", return_value=[
                ("sample_unassigned", {"file": "sample_unassigned.json"}),
            ]),
            patch("quiz_bot.webapp.effective_test_info", return_value={"title": "Новый тест"}),
            patch("quiz_bot.access.effective_test_access", return_value={"type": "public", "code": ""}),
        ):
            response = self.client.get(
                "/api/admin/unassigned?user_id=12345",
                headers=self._auth_header(12345),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], [{
            "id": "sample_unassigned",
            "title": "Новый тест",
            "questions_count": 0,
            "file": "sample_unassigned.json",
            "study_mode": "test",
            "access_type": "public",
            "access_code": "",
        }])

    def test_subject_test_order_persists_in_catalog_and_preserves_metadata(self):
        from quiz_bot.loader import LOADED_TESTS, TESTS, effective_test_info, get_tests_for_subject
        from quiz_bot import storage

        fixtures = {
            "order_a": {"title": "A", "subject_id": "ordering", "subject_title": "Ordering"},
            "order_b": {"title": "B", "subject_id": "ordering", "subject_title": "Ordering"},
        }
        with patch.dict(TESTS, fixtures, clear=True), patch.dict(LOADED_TESTS, {key: [] for key in fixtures}, clear=True):
            storage.set_test_metadata_setting("order_b", title="B renamed", subject_id="ordering", study_mode="quizlet")
            self.assertEqual([key for key, _ in get_tests_for_subject("ordering")], ["order_a", "order_b"])
            response = self.client.post("/api/admin/reorder_tests", headers=self._auth_header(12345), json={
                "subject_id": "ordering", "test_ids": ["order_b", "order_a"],
            })
            self.assertEqual(response.status_code, 200)
            storage.clear_cache()
            self.assertEqual([key for key, _ in get_tests_for_subject("ordering")], ["order_b", "order_a"])
            self.assertEqual(effective_test_info("order_b")["study_mode"], "quizlet")
            self.assertEqual(effective_test_info("order_b")["title"], "B renamed")
            catalog = self.client.get("/api/bootstrap", headers=self._auth_header(99999)).get_json()
            subject = next(subject for subject in catalog["subjects"] if subject["id"] == "ordering")
            self.assertEqual([test["id"] for test in subject["tests"]], ["order_b", "order_a"])
            self.assertEqual([test["sort_order"] for test in subject["tests"]], [0, 1])
            admin_items = self.client.get("/api/admin/tests", headers=self._auth_header(12345)).get_json()["items"]
            self.assertEqual({test["id"]: test["sort_order"] for test in admin_items}, {"order_a": 1, "order_b": 0})
            storage.set_test_metadata_setting("order_b", title="Z renamed")
            self.assertEqual([key for key, _ in get_tests_for_subject("ordering")], ["order_b", "order_a"])
            TESTS["order_new"] = {"title": "0 New", "subject_id": "ordering"}
            self.assertEqual([key for key, _ in get_tests_for_subject("ordering")], ["order_b", "order_a", "order_new"])
            storage.set_test_metadata_setting("order_b", subject_id="other")
            self.assertIsNone(storage.get_test_metadata_setting("order_b")["sort_order"])

    def test_reorder_requires_admin_and_complete_subject_membership(self):
        from quiz_bot.loader import TESTS
        from quiz_bot import storage

        fixtures = {
            "order_a": {"title": "A", "subject_id": "ordering"},
            "order_b": {"title": "B", "subject_id": "ordering"},
            "outside": {"title": "Outside", "subject_id": "other"},
        }
        with patch.dict(TESTS, fixtures, clear=True):
            response = self.client.post("/api/admin/reorder_tests", headers=self._auth_header(99999), json={
                "user_id": 12345, "subject_id": "ordering", "test_ids": ["order_b", "order_a"],
            })
            self.assertEqual(response.status_code, 403)
            for payload, status in [
                ({"subject_id": "ordering", "test_ids": ["order_a"]}, 409),
                ({"subject_id": "ordering", "test_ids": ["outside", "order_a"]}, 409),
                ({"subject_id": "ordering", "test_ids": ["order_a", "order_a"]}, 400),
                ({"subject_id": "ordering", "test_ids": [{}]}, 400),
                ({"subject_id": "missing", "test_ids": ["order_a"]}, 404),
                (["invalid"], 400),
            ]:
                with self.subTest(payload=payload):
                    response = self.client.post("/api/admin/reorder_tests", headers=self._auth_header(12345), json=payload)
                    self.assertEqual(response.status_code, status)
            self.assertIsNone(storage.get_test_metadata_setting("order_a"))
            self.assertIsNone(storage.get_test_metadata_setting("order_b"))

    def test_subject_tests_load_current_order_and_filter_restricted_tests(self):
        from quiz_bot.loader import LOADED_TESTS, TESTS
        from quiz_bot import storage

        fixtures = {key: {"title": key, "subject_id": "loading"} for key in ["load_public", "load_code", "load_private", "load_admin"]}
        with patch.dict(TESTS, fixtures, clear=True), patch.dict(LOADED_TESTS, {key: [] for key in fixtures}, clear=True):
            storage.set_test_access_setting("load_code", "code", code="secret")
            storage.set_test_access_setting("load_private", "private")
            storage.set_test_access_setting("load_admin", "admin_only")
            order = ["load_admin", "load_private", "load_public", "load_code"]
            storage.set_subject_test_order("loading", order, 12345)

            student = self.client.get("/api/subjects/loading/tests", headers=self._auth_header(99999))
            self.assertEqual(student.status_code, 200)
            self.assertEqual([test["id"] for test in student.get_json()["items"]], ["load_public", "load_code"])
            self.assertTrue(all(test["access_code"] == "" for test in student.get_json()["items"]))
            admin = self.client.get("/api/subjects/loading/tests", headers=self._auth_header(12345))
            self.assertEqual([test["id"] for test in admin.get_json()["items"]], order)
            self.assertEqual(admin.get_json()["items"][-1]["access_code"], "secret")
            storage.grant_user_test_access(99999, "load_private")
            granted = self.client.get("/api/subjects/loading/tests", headers=self._auth_header(99999))
            self.assertEqual([test["id"] for test in granted.get_json()["items"]], ["load_private", "load_public", "load_code"])

    def test_subject_tests_require_identity_and_section_access(self):
        from quiz_bot.loader import TESTS
        from quiz_bot import storage

        with patch.dict(TESTS, {"load_public": {"title": "Public", "subject_id": "locked"}}, clear=True):
            storage.set_subject_setting("locked", title="Locked", access_type="code", code="section-secret")
            unauthenticated = self.client.get("/api/subjects/locked/tests")
            self.assertEqual(unauthenticated.status_code, 401)
            denied = self.client.get("/api/subjects/locked/tests", headers=self._auth_header(99999))
            self.assertEqual(denied.status_code, 403)
            self.assertNotIn("items", denied.get_json())
            verified = self.client.post("/api/subjects/verify_code", headers=self._auth_header(99999), json={
                "subject_id": "locked", "code": "section-secret",
            })
            self.assertEqual(verified.status_code, 200)
            allowed = self.client.get("/api/subjects/locked/tests", headers=self._auth_header(99999))
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual([test["id"] for test in allowed.get_json()["items"]], ["load_public"])
            missing = self.client.get("/api/subjects/missing/tests", headers=self._auth_header(99999))
            self.assertEqual(missing.status_code, 404)

    def test_admin_delete_subject_api(self):
        res = self.client.post(
            "/api/admin/delete_subject",
            headers=self._auth_header(12345),
            json={"user_id": 12345, "id": "oziz"},
        )
        self.assertEqual(res.status_code, 200)

    def test_revealed_answer_is_not_double_counted_at_attempt_finish(self):
        error_response = self.client.post(
            "/api/errors/record",
            headers=self._auth_header(99999),
            json={
                "user_id": 99999,
                "test_id": "oziz_1_200",
                "question_id": 1,
                "user_answer": None,
            },
        )
        self.assertEqual(error_response.status_code, 200)

        attempt_response = self.client.post(
            "/api/attempts/record",
            headers=self._auth_header(99999),
            json={
                "user_id": 99999,
                "test_id": "oziz_1_200",
                "correct": 0,
                "answered": 1,
                "duration": 10,
                "mode": "normal",
                # Older clients sent this list; errors are already recorded immediately.
                "wrong_questions": [1],
            },
        )
        self.assertEqual(attempt_response.status_code, 200)

        import quiz_bot.storage as storage

        with storage.db_connect() as conn:
            row = conn.execute(
                "SELECT wrong_count FROM all_time_errors WHERE user_id = ? AND test_id = ? AND question_index = ?",
                (99999, "oziz_1_200", 0),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["wrong_count"], 1)

    def test_user_rating_visibility_and_reset_api(self):
        # Initial rating shows student 99999
        res_r1 = self.client.get(
            "/api/rating?test_id=oziz_1_200",
            headers=self._auth_header(99999),
        )
        self.assertEqual(res_r1.status_code, 200)
        items1 = res_r1.get_json()["items"]
        self.assertTrue(any(it["user_id"] == 99999 for it in items1))

        # Bootstrap shows not hidden
        res_b1 = self.client.get(
            "/api/bootstrap?user_id=99999",
            headers=self._auth_header(99999),
        )
        self.assertEqual(res_b1.status_code, 200)
        self.assertFalse(res_b1.get_json()["is_hidden_in_rating"])

        # Hide user 99999
        res_tog = self.client.post(
            "/api/user/toggle_rating_visibility",
            headers=self._auth_header(99999),
            json={"user_id": 99999, "is_hidden": True},
        )
        self.assertEqual(res_tog.status_code, 200)
        self.assertTrue(res_tog.get_json()["is_hidden"])

        # Bootstrap now shows hidden
        res_b2 = self.client.get(
            "/api/bootstrap?user_id=99999",
            headers=self._auth_header(99999),
        )
        self.assertTrue(res_b2.get_json()["is_hidden_in_rating"])

        # Rating query no longer includes user 99999
        res_r2 = self.client.get(
            "/api/rating?test_id=oziz_1_200",
            headers=self._auth_header(99999),
        )
        items2 = res_r2.get_json()["items"]
        self.assertFalse(any(it["user_id"] == 99999 for it in items2))

        # Reset rating for user 99999
        res_reset = self.client.post(
            "/api/user/reset_rating",
            headers=self._auth_header(99999),
            json={"user_id": 99999},
        )
        self.assertEqual(res_reset.status_code, 200)
        self.assertTrue(res_reset.get_json()["success"])
        self.assertGreaterEqual(res_reset.get_json()["deleted_attempts"], 1)

        # Unhide user, rating should still have no attempts because they were reset
        self.client.post(
            "/api/user/toggle_rating_visibility",
            headers=self._auth_header(99999),
            json={"user_id": 99999, "is_hidden": False},
        )
        res_r3 = self.client.get(
            "/api/rating?test_id=oziz_1_200",
            headers=self._auth_header(99999),
        )
        items3 = res_r3.get_json()["items"]
        self.assertFalse(any(it["user_id"] == 99999 for it in items3))


if __name__ == "__main__":
    unittest.main()
