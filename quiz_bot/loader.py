import json
import re
from pathlib import Path
from typing import Any

from .config import BASE_DIR, LETTERS, SUBJECTS, TESTS

try:
    from .storage import get_test_metadata_setting, list_subject_settings
except Exception:
    get_test_metadata_setting = None
    list_subject_settings = None


def _slug(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-zа-яё0-9]+", "_", value, flags=re.IGNORECASE)
    value = value.strip("_")
    return value or "default"


def _clean_title(value: str) -> str:
    return str(value or "").replace("_", " ").strip().title() or "Тесты"


def _normalize_subject(subject: Any, path: Path | None = None) -> dict[str, Any]:
    if isinstance(subject, dict):
        subject_id = _slug(subject.get("id") or subject.get("slug") or subject.get("title") or "default")
        title = str(subject.get("title") or _clean_title(subject_id)).strip()
        emoji = str(subject.get("emoji") or "📚").strip()
        order = int(subject.get("order") or 100)
    else:
        subject_id = _slug(subject or "")
        if not subject_id and path is not None:
            subject_id = _slug(path.parent.name)
        title = _clean_title(subject or subject_id)
        emoji = "📚"
        order = 100

    if path is not None and (not subject_id or subject_id == "default"):
        tests_root = BASE_DIR / "tests"
        try:
            relative = path.relative_to(tests_root)
            if len(relative.parts) > 1:
                subject_id = _slug(relative.parts[0])
                title = _clean_title(relative.parts[0])
        except ValueError:
            pass

    if not subject_id:
        subject_id = "default"

    return {
        "id": subject_id,
        "title": title,
        "emoji": emoji,
        "order": order,
    }


def _register_subject(subject: dict[str, Any]) -> None:
    subject_id = subject["id"]
    existing = SUBJECTS.get(subject_id, {})
    SUBJECTS[subject_id] = {
        "title": existing.get("title") or subject.get("title") or _clean_title(subject_id),
        "emoji": existing.get("emoji") or subject.get("emoji") or "📚",
        "order": existing.get("order", subject.get("order", 100)),
    }


def _normalize_access(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"type": "public"}
    if isinstance(raw, str):
        return {"type": raw.strip().lower() or "public"}
    if not isinstance(raw, dict):
        return {"type": "public"}

    access_type = str(raw.get("type") or "public").strip().lower()
    if access_type not in {"public", "private", "code", "admin_only"}:
        access_type = "public"

    result = dict(raw)
    result["type"] = access_type

    if access_type == "code":
        result["code"] = str(raw.get("code") or "").strip()

    users = raw.get("users") or raw.get("user_ids") or raw.get("allowed_user_ids") or []
    if isinstance(users, (str, int)):
        users = [users]

    allowed_user_ids: list[int] = []
    for item in users:
        try:
            allowed_user_ids.append(int(item))
        except (TypeError, ValueError):
            pass

    if allowed_user_ids:
        result["users"] = sorted(set(allowed_user_ids))

    return result


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


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _questions_from_data(data: Any, path: Path) -> list[dict[str, Any]]:
    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list):
        raise ValueError(f"{path}: нужен список вопросов или объект с questions")
    return [normalize_question(item, i) for i, item in enumerate(questions)]


def _metadata_from_data(path: Path, data: Any, explicit_test_id: str | None = None, explicit_info: dict[str, Any] | None = None) -> dict[str, Any]:
    explicit_info = explicit_info or {}

    if isinstance(data, dict):
        test_id = explicit_test_id or data.get("id") or data.get("test_id") or path.stem
        title = data.get("title") or data.get("name") or explicit_info.get("title") or _clean_title(path.stem)
        subject = data.get("subject") or {
            "id": explicit_info.get("subject_id") or explicit_info.get("subject") or None,
            "title": explicit_info.get("subject_title"),
            "emoji": explicit_info.get("subject_emoji"),
            "order": explicit_info.get("subject_order", 100),
        }
        access = data.get("access", explicit_info.get("access"))
        description = data.get("description") or explicit_info.get("description")
    else:
        test_id = explicit_test_id or explicit_info.get("id") or path.stem
        title = explicit_info.get("title") or _clean_title(path.stem)
        subject = {
            "id": explicit_info.get("subject_id") or explicit_info.get("subject") or None,
            "title": explicit_info.get("subject_title"),
            "emoji": explicit_info.get("subject_emoji"),
            "order": explicit_info.get("subject_order", 100),
        }
        access = explicit_info.get("access")
        description = explicit_info.get("description")

    subject_info = _normalize_subject(subject, path)
    _register_subject(subject_info)

    test_id = _slug(test_id)
    return {
        "id": test_id,
        "title": str(title).strip(),
        "file": str(path.relative_to(BASE_DIR)),
        "subject_id": subject_info["id"],
        "subject_title": subject_info["title"],
        "subject_emoji": subject_info["emoji"],
        "access": _normalize_access(access),
        "description": description or "",
    }


def _load_explicit_tests(loaded: dict[str, list[dict[str, Any]]]) -> set[str]:
    known_paths: set[str] = set()

    for test_id, info in list(TESTS.items()):
        path = BASE_DIR / info["file"]
        known_paths.add(str(path.resolve()))

        if not path.exists():
            tests_dir = BASE_DIR / "tests"
            fallback = tests_dir / Path(info["file"]).name
            if fallback.exists():
                path = fallback
            else:
                matches = sorted(tests_dir.rglob(Path(info["file"]).name)) if tests_dir.exists() else []
                if matches:
                    path = matches[0]
                else:
                    raise FileNotFoundError(f"Не найден файл с вопросами: {path}")

        data = _read_json(path)
        meta = _metadata_from_data(path, data, explicit_test_id=test_id, explicit_info=info)
        meta["id"] = test_id
        TESTS[test_id].update(meta)
        loaded[test_id] = _questions_from_data(data, path)

    return known_paths


def _load_auto_tests(loaded: dict[str, list[dict[str, Any]]], known_paths: set[str]) -> None:
    tests_dir = BASE_DIR / "tests"
    if not tests_dir.exists():
        return

    for path in sorted(tests_dir.rglob("*.json")):
        if str(path.resolve()) in known_paths:
            continue

        try:
            data = _read_json(path)
            questions = _questions_from_data(data, path)
            meta = _metadata_from_data(path, data)
        except Exception:
            # Broken files should not break the bot startup. The admin validation
            # screen can still be used for configured tests. Auto-bad files are skipped.
            continue

        test_id = meta["id"]
        if test_id in loaded or test_id in TESTS:
            continue

        TESTS[test_id] = meta
        loaded[test_id] = questions


def load_tests() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = {}
    known_paths = _load_explicit_tests(loaded)
    _load_auto_tests(loaded, known_paths)
    return loaded


LOADED_TESTS = load_tests()


def get_questions(test_id: str) -> list[dict[str, Any]]:
    return LOADED_TESTS[test_id]


def effective_test_info(test_id: str) -> dict[str, Any]:
    info = dict(TESTS[test_id])

    setting = None
    if get_test_metadata_setting is not None:
        try:
            setting = get_test_metadata_setting(test_id)
        except Exception:
            setting = None

    if not setting:
        return info

    if setting.get("title"):
        info["title"] = setting["title"]
    if setting.get("subject_id"):
        info["subject_id"] = setting["subject_id"]
    if setting.get("subject_title"):
        info["subject_title"] = setting["subject_title"]
    if setting.get("subject_emoji"):
        info["subject_emoji"] = setting["subject_emoji"]

    return info


def apply_test_metadata_override(
    test_id: str,
    title: str | None = None,
    subject_id: str | None = None,
    subject_title: str | None = None,
    subject_emoji: str | None = None,
) -> None:
    if test_id not in TESTS:
        return

    if title is not None:
        TESTS[test_id]["title"] = title
    if subject_id is not None:
        TESTS[test_id]["subject_id"] = subject_id
    if subject_title is not None:
        TESTS[test_id]["subject_title"] = subject_title
    if subject_emoji is not None:
        TESTS[test_id]["subject_emoji"] = subject_emoji


def apply_all_test_metadata_overrides() -> None:
    if get_test_metadata_setting is None:
        return

    for test_id in list(TESTS.keys()):
        try:
            setting = get_test_metadata_setting(test_id)
        except Exception:
            continue
        if not setting:
            continue

        apply_test_metadata_override(
            test_id,
            title=setting.get("title") or None,
            subject_id=setting.get("subject_id") or None,
            subject_title=setting.get("subject_title") or None,
            subject_emoji=setting.get("subject_emoji") or None,
        )


UNASSIGNED_SUBJECT_IDS = {"", "default", "unassigned", "none", "no_subject"}


def is_unassigned_subject_id(subject_id: str | None) -> bool:
    return str(subject_id or "").strip().lower() in UNASSIGNED_SUBJECT_IDS


def add_subject_override(subject_id: str, title: str, emoji: str = "📚") -> None:
    subject_id = _slug(subject_id)
    SUBJECTS[subject_id] = {
        "title": str(title or _clean_title(subject_id)).strip(),
        "emoji": str(emoji or "📚").strip() or "📚",
        "order": 100,
    }


def get_subjects() -> list[tuple[str, dict[str, Any]]]:
    subjects: dict[str, dict[str, Any]] = {}

    for test_id in TESTS:
        info = effective_test_info(test_id)
        subject_id = info.get("subject_id") or "default"
        if is_unassigned_subject_id(subject_id):
            continue
        subjects[subject_id] = {
            "title": info.get("subject_title") or SUBJECTS.get(subject_id, {}).get("title") or _clean_title(subject_id),
            "emoji": info.get("subject_emoji") or SUBJECTS.get(subject_id, {}).get("emoji") or "📚",
            "order": SUBJECTS.get(subject_id, {}).get("order", 100),
        }

    for subject_id, info in SUBJECTS.items():
        if is_unassigned_subject_id(subject_id):
            continue
        subjects.setdefault(subject_id, info)

    if list_subject_settings is not None:
        try:
            for subject in list_subject_settings():
                subjects[subject["id"]] = {
                    "title": subject.get("title") or _clean_title(subject["id"]),
                    "emoji": subject.get("emoji") or "📚",
                    "order": 100,
                }
        except Exception:
            pass

    return sorted(
        subjects.items(),
        key=lambda item: str(item[1].get("title", item[0])).casefold(),
    )


def get_subject_info(subject_id: str) -> dict[str, Any]:
    for current_id, info in get_subjects():
        if current_id == subject_id:
            return info
    return SUBJECTS.get(subject_id, {"title": _clean_title(subject_id), "emoji": "📚", "order": 100})


def get_tests_for_subject(subject_id: str) -> list[tuple[str, dict[str, Any]]]:
    rows = []
    for test_id in TESTS:
        info = effective_test_info(test_id)
        if info.get("subject_id") == subject_id:
            rows.append((test_id, info))
    return sorted(rows, key=lambda item: str(item[1].get("title", item[0])).casefold())


def get_unassigned_tests() -> list[tuple[str, dict[str, Any]]]:
    rows = []
    for test_id in TESTS:
        info = effective_test_info(test_id)
        if is_unassigned_subject_id(info.get("subject_id")):
            rows.append((test_id, info))
    return sorted(rows, key=lambda item: str(item[1].get("title", item[0])).casefold())


def test_subject_id(test_id: str) -> str:
    return effective_test_info(test_id).get("subject_id", "default")


def test_access(test_id: str) -> dict[str, Any]:
    return _normalize_access(TESTS[test_id].get("access"))


def test_access_type(test_id: str) -> str:
    return test_access(test_id).get("type", "public")


def test_access_code(test_id: str) -> str:
    return str(test_access(test_id).get("code") or "").strip()


def test_allowed_user_ids(test_id: str) -> set[int]:
    raw = test_access(test_id).get("users") or []
    result: set[int] = set()
    for item in raw:
        try:
            result.add(int(item))
        except (TypeError, ValueError):
            pass
    return result
