import unittest
from quiz_bot.runtime import safe_callback, unpack_callback
from quiz_bot.loader import _slug, load_tests as bot_load_tests
from quiz_bot.admin_core import (
    admin_add_test_to_subject_keyboard,
    admin_subject_keyboard,
    admin_subject_access_keyboard,
    admin_subject_settings_keyboard,
    admin_delete_subject_confirm_keyboard,
    admin_tests_keyboard,
)
from quiz_bot.admin_tools import admin_move_test_subject_keyboard


class TestCallbackSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bot_load_tests()

    def test_safe_callback_short_untouched(self):
        short = "admin:menu"
        self.assertEqual(safe_callback(short), short)

    def test_safe_callback_long_packed_and_unpacked(self):
        long_data = "admin:assign_test_subject:ochen_dlinnyi_razdel_s_bolshim_nazvaniem:luchevaya_test_blank_super_long_identifier"
        self.assertGreater(len(long_data.encode("utf-8")), 64)

        packed = safe_callback(long_data)
        self.assertTrue(packed.startswith("cbe:"))
        self.assertLessEqual(len(packed.encode("utf-8")), 64)

        unpacked = unpack_callback(packed)
        self.assertEqual(unpacked, long_data)

    def test_unpack_normal_callback(self):
        self.assertEqual(unpack_callback("admin:tests"), "admin:tests")

    def test_slug_transliteration(self):
        self.assertEqual(_slug("Лучевая диагностика"), "luchevaya_diagnostika")
        self.assertEqual(_slug("Основы лучевой диагностики"), "osnovy_luchevoy_diagnostiki")
        self.assertEqual(_slug("Фармакология"), "farmakologiya")

    def test_slug_ascii_only(self):
        slug_res = _slug("Общественное здоровье и здравоохранение для студентов")
        # Must be ASCII only
        slug_res.encode("ascii")
        self.assertLessEqual(len(slug_res), 32)

    def _assert_all_buttons_under_64_bytes(self, markup):
        for row in markup.inline_keyboard:
            for btn in row:
                cb = btn.callback_data
                self.assertIsNotNone(cb)
                byte_len = len(cb.encode("utf-8"))
                self.assertLessEqual(
                    byte_len,
                    64,
                    f"Button '{btn.text}' has callback_data > 64 bytes: '{cb}' ({byte_len} bytes)"
                )

    def test_admin_add_test_to_subject_keyboard_normal(self):
        kb = admin_add_test_to_subject_keyboard("luchevaya_diagnostika")
        self._assert_all_buttons_under_64_bytes(kb)

    def test_admin_add_test_to_subject_keyboard_cyrillic_long(self):
        kb = admin_add_test_to_subject_keyboard("очень_длинный_раздел_на_русском_языке_12345")
        self._assert_all_buttons_under_64_bytes(kb)

    def test_admin_subject_keyboard(self):
        kb = admin_subject_keyboard("очень_длинный_раздел_на_русском_языке_12345")
        self._assert_all_buttons_under_64_bytes(kb)

    def test_admin_subject_access_keyboard(self):
        kb = admin_subject_access_keyboard("очень_длинный_раздел_на_русском_языке_12345")
        self._assert_all_buttons_under_64_bytes(kb)

    def test_admin_subject_settings_keyboard(self):
        kb = admin_subject_settings_keyboard("очень_длинный_раздел_на_русском_языке_12345")
        self._assert_all_buttons_under_64_bytes(kb)

    def test_admin_delete_subject_confirm_keyboard(self):
        kb = admin_delete_subject_confirm_keyboard("очень_длинный_раздел_на_русском_языке_12345")
        self._assert_all_buttons_under_64_bytes(kb)

    def test_admin_move_test_subject_keyboard(self):
        kb = admin_move_test_subject_keyboard("luchevaya_test_blank")
        self._assert_all_buttons_under_64_bytes(kb)


if __name__ == "__main__":
    unittest.main()
