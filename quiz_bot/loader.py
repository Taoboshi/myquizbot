import json
from typing import Any

from .config import BASE_DIR, LETTERS, TESTS

def normalize_question(raw: dict[str, Any], index: int) -> dict[str, Any]:
    question = raw.get("question") or raw.get("text") or raw.get("q") or raw.get("title")
    options = raw.get("options") or raw.get("answers") or raw.get("variants")

    if not question:
        raise ValueError(f"Вопрос #{index + 1}: нет текста вопроса")
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError(f"Вопрос #{index + 1}: options должен быть списком минимум из 2 вариантов")

    correct = raw.get("correct_index")
    if correct is None:
        correct = raw.get("answer_index")
    if correct is None:
        correct = raw.get("correct")
    if correct is None:
        correct = raw.get("answer")

    if isinstance(correct, str):
        value = correct.strip()
        upper = value.upper()
        if upper in LETTERS:
            correct = LETTERS.index(upper)
        elif value.isdigit():
            correct = int(value)
            if correct >= 1:
                correct -= 1
        else:
            try:
                correct = options.index(value)
            except ValueError:
                found = None
                for i, option in enumerate(options):
                    option_text = str(option).strip()
                    if value == option_text or value in option_text:
                        found = i
                        break
                if found is None:
                    raise ValueError(f"Вопрос #{index + 1}: не удалось определить правильный ответ")
                correct = found

    if not isinstance(correct, int):
        raise ValueError(f"Вопрос #{index + 1}: correct_index должен быть числом, буквой или текстом ответа")
    if correct < 0 or correct >= len(options):
        raise ValueError(f"Вопрос #{index + 1}: correct_index вне диапазона")

    return {
        "question": str(question).strip(),
        "options": [str(option).strip() for option in options],
        "correct_index": correct,
    }

def load_tests() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = {}

    for test_id, info in list(TESTS.items()):
        path = BASE_DIR / info["file"]
        if not path.exists():
            raise FileNotFoundError(f"Не найден файл с вопросами: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        questions = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(questions, list):
            raise ValueError(f"{path}: нужен список вопросов или объект с questions")

        loaded[test_id] = [normalize_question(item, i) for i, item in enumerate(questions)]

    tests_dir = BASE_DIR / "tests"
    known_paths = {str((BASE_DIR / info["file"]).resolve()) for info in TESTS.values()}

    if tests_dir.exists():
        for path in sorted(tests_dir.glob("*.json")):
            if str(path.resolve()) in known_paths:
                continue

            test_id = path.stem
            if test_id in loaded:
                continue

            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                questions = data.get("questions") if isinstance(data, dict) else data
                if not isinstance(questions, list):
                    continue

                TESTS[test_id] = {
                    "title": path.stem.replace("_", " "),
                    "file": str(path.relative_to(BASE_DIR)),
                }
                loaded[test_id] = [normalize_question(item, i) for i, item in enumerate(questions)]
            except Exception:
                pass

    return loaded

LOADED_TESTS = load_tests()

def get_questions(test_id: str) -> list[dict[str, Any]]:
    return LOADED_TESTS[test_id]
