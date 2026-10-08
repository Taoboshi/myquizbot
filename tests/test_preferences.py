import sqlite3
import unittest
from unittest.mock import patch

from quiz_bot import storage
from quiz_bot.webapp import create_webapp


class PreferencesTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        for item in (
            patch.object(storage, "DATABASE_URL", None),
            patch.object(storage, "db_connect", return_value=self.connection),
            patch("quiz_bot.webapp._verified_telegram_data", return_value={"id": 123}),
        ):
            item.start()
            self.addCleanup(item.stop)
        storage.init_db()
        storage.init_db()
        self.client = create_webapp().test_client()

    def tearDown(self):
        self.connection.close()

    def test_partial_updates_preserve_other_preferences(self):
        self.assertEqual(self.client.post("/api/user/preferences", json={"autoNext": True}).status_code, 200)
        response = self.client.post("/api/user/preferences", json={"trainingCount": 25, "fcSwipes": False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["preferences"], {"autoNext": True, "trainingCount": 25, "fcSwipes": False})
        self.assertEqual(storage.get_user_preferences(123), response.json["preferences"])

    def test_preferences_are_bound_to_verified_identity(self):
        self.client.post("/api/user/preferences", json={"showTimer": False})
        with patch("quiz_bot.webapp._verified_telegram_data", return_value={"id": 456}):
            self.client.post("/api/user/preferences", json={"showTimer": True})
        self.assertEqual(storage.get_user_preferences(123), {"showTimer": False})
        self.assertEqual(storage.get_user_preferences(456), {"showTimer": True})
        with patch("quiz_bot.webapp._verified_telegram_data", return_value=None):
            self.assertEqual(self.client.post("/api/user/preferences", json={"autoNext": True}).status_code, 401)

    def test_validation_rejects_device_settings_and_invalid_values(self):
        for data in ({}, [], {"theme": "light"}, {"autoNext": 1}, {"fcRemember": "yes"},
                     {"trainingCount": True}, {"trainingCount": 0}, {"trainingCount": 501}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post("/api/user/preferences", json=data).status_code, 400)
        self.assertEqual(storage.get_user_preferences(123), {})


if __name__ == "__main__":
    unittest.main()
