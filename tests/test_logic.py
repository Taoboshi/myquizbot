import unittest
from quiz_bot.loader import _slug, normalize_question
from quiz_bot.helpers import _percent

class TestQuizBotLogic(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(_slug("Hello World"), "hello_world")
        self.assertEqual(_slug("Привет Мир"), "привет_мир")
        self.assertEqual(_slug("  Test  Data  "), "test_data")
        self.assertEqual(_slug("!@#$%^&*()"), "default")

    def test_percent(self):
        self.assertEqual(_percent(5, 10), 50.0)
        self.assertEqual(_percent(1, 3), 33.3)
        self.assertEqual(_percent(0, 10), 0.0)
        self.assertEqual(_percent(10, 0), 0.0)
        self.assertEqual(_percent(None, 10), 0.0)

    def test_normalize_question(self):
        raw = {
            "question": "Test Q",
            "options": ["A", "B", "C"],
            "correct_index": 1
        }
        normalized = normalize_question(raw, 0)
        self.assertEqual(normalized["question"], "Test Q")
        self.assertEqual(normalized["correct_index"], 1)

        raw_alt = {
            "q": "Another Q",
            "answers": ["X", "Y"],
            "correct": "X"
        }
        normalized_alt = normalize_question(raw_alt, 1)
        self.assertEqual(normalized_alt["question"], "Another Q")
        self.assertEqual(normalized_alt["correct_index"], 0)

if __name__ == "__main__":
    unittest.main()
