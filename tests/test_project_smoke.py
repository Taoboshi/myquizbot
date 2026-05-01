import ast
import os
from pathlib import Path


def test_python_files_parse():
    root = Path(__file__).resolve().parents[1]
    for path in sorted((root / "quiz_bot").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_loader_loads_json_tests():
    from quiz_bot.loader import LOADED_TESTS

    assert LOADED_TESTS
    assert sum(len(items) for items in LOADED_TESTS.values()) > 0


def test_config_import_does_not_require_bot_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    from quiz_bot.config import get_bot_token

    assert get_bot_token(required=False) == ""
