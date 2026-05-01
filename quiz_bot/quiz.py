import html
import sqlite3
from typing import Any

from .config import FULL_TEST_MODES, LETTERS, RESUMABLE_MODES, SOLUTION_MODES, TESTS
from .helpers import attempt_percent, mode_title, seconds_to_text, sep, user_display_name
from .loader import get_questions
from .state import delete_active_session, delete_runtime_session
from .storage import db_connect, get_attempt, record_attempt_finish, stats_summary

def add_session_wrong_answer(state: dict[str, Any], question_index: int, wrong_answer_index: int | None) -> None:
    state.setdefault("wrong_answers", []).append({
        "question_index": question_index,
        "wrong_answer_index": wrong_answer_index,
    })

def wrong_index_for_question(state: dict[str, Any], question_index: int) -> int | None:
    for item in reversed(state.get("wrong_answers", [])):
        if item.get("question_index") == question_index:
            return item.get("wrong_answer_index")
    return None

def finish_attempt_if_needed(user_id: int, state: dict[str, Any], finished_by_user: bool = False) -> None:
    if state.get("finish_recorded"):
        return

    test_id = state.get("test_id")
    if not test_id:
        return

    completed_full = state.get("mode") in FULL_TEST_MODES and state.get("total", 0) == len(get_questions(test_id))

    record_attempt_finish(
        user_id=user_id,
        test_id=test_id,
        attempt_id=state.get("attempt_id"),
        answered=state.get("total", 0),
        correct=state.get("correct", 0),
        completed_full_test=completed_full,
        finished_by_user=finished_by_user,
    )

    attempt = get_attempt(state.get("attempt_id"))
    if attempt:
        state["duration_seconds"] = attempt.get("duration_seconds")

    state["finish_recorded"] = True

    delete_runtime_session(user_id, test_id, state.get("mode"))

    if state.get("mode") in RESUMABLE_MODES:
        delete_active_session(user_id, test_id)

def build_question_text(
    index: int,
    state: dict[str, Any],
    selected_index: int | None = None,
    show_correct: bool = False,
) -> str:
    test_id = state["test_id"]
    q = get_questions(test_id)[index]
    title = html.escape(TESTS[test_id]["title"])
    mode = html.escape(mode_title(state.get("mode")))
    correct_index = int(q["correct_index"])

    current_in_attempt = int(state.get("pos", 0)) + 1
    total_in_attempt = len(state.get("order", [])) or 1
    real_question_number = index + 1
    progress = f"{current_in_attempt}/{total_in_attempt} (вопрос {real_question_number})"

    lines = [
        title,
        f"{mode} · {progress}",
        "",
        f"<b>{html.escape(q['question'])}</b>",
        "",
        "···",
    ]

    for i, option in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""
        if show_correct and i == correct_index:
            prefix = "✅ "
        elif selected_index is not None and i == selected_index and i != correct_index:
            prefix = "❌ "
        lines.append(f"{prefix}{letter}) {html.escape(option)}")

    if show_correct and selected_index is None:
        lines.append("")
        lines.append("👁 Показан ответ")

    return "\n".join(lines)

def format_session_error_card(test_id: str, pos: int, items: list[dict[str, int | None]]) -> str:
    title = html.escape(TESTS[test_id]["title"])
    if not items:
        return f"Ошибок в этом решении по тесту «{title}» нет."

    item = items[pos]
    index = int(item["question_index"])
    wrong_index = item.get("wrong_answer_index")
    q = get_questions(test_id)[index]
    correct_index = int(q["correct_index"])

    lines = [
        "Ошибки этого решения",
        title,
        f"{pos + 1}/{len(items)} (вопрос {index + 1})",
        "",
        f"<b>{html.escape(q['question'])}</b>",
        "",
        "···",
    ]

    for i, option in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""
        if i == correct_index:
            prefix = "✅ "
        elif wrong_index is not None and i == wrong_index and i != correct_index:
            prefix = "❌ "
        lines.append(f"{prefix}{letter}) {html.escape(option)}")

    if wrong_index is None:
        lines.append("")
        lines.append("👁 Показан ответ")

    return "\n".join(lines)

def result_text(state: dict[str, Any], user_id: int, finished_by_user: bool = False) -> str:
    total = int(state.get("total", 0))
    correct = int(state.get("correct", 0))
    percent = round(correct / total * 100) if total else 0
    wrong_count = len(state.get("wrong_answers", []))
    test_id = state.get("test_id")

    if test_id:
        title = TESTS[test_id]["title"]
        total_questions = len(state.get("order", [])) or total
    else:
        title = "тест не выбран"
        total_questions = total

    duration = state.get("duration_seconds")
    if duration is None and state.get("attempt_id") is not None:
        attempt = get_attempt(state.get("attempt_id"))
        if attempt:
            duration = attempt.get("duration_seconds")

    header = "⏹ Решение завершено" if finished_by_user else "🎉 Тест завершён"
    mode = mode_title(state.get("mode"))
    return (
        f"{header}\n\n"
        f"📚 {title}\n"
        f"🎮 {mode}\n"
        f"⏱ Время: {seconds_to_text(duration)}\n\n"
        f"📊 Результат\n"
        f"🏆 {percent}%\n"
        f"✅ Правильно: {correct}\n"
        f"❌ Ошибок: {wrong_count}\n"
        f"📝 Решено: {total}/{total_questions}"
    )

def format_solution_attempt(attempt: sqlite3.Row | None) -> str:
    if not attempt or not attempt["answered"]:
        return "Пока нет завершённых решений"

    percent = round(attempt["correct"] / attempt["answered"] * 100, 1)
    return (
        f"{attempt['correct']}/{attempt['answered']} — {percent}%\n"
        f"Время: {seconds_to_text(attempt['duration_seconds'])}"
    )

def format_training_attempt(attempt: sqlite3.Row | None) -> str:
    if not attempt or not attempt["answered"]:
        return "Пока нет тренировок"

    percent = round(attempt["correct"] / attempt["answered"] * 100, 1)
    return f"{attempt['correct']}/{attempt['answered']} — {percent}%"

def _round_percent(value) -> int:
    try:
        return round(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _attempt_percent_line(attempt: dict[str, Any] | None) -> str:
    if not attempt or not int(attempt.get("answered") or 0):
        return "пока нет"
    return f"{_round_percent(int(attempt.get('correct') or 0) / int(attempt.get('answered') or 1) * 100)}%"


def _mode_stats_line(title: str, data: dict[str, Any]) -> list[str]:
    attempts = int(data.get("attempts") or 0)
    if attempts <= 0:
        return [title, "Попыток: 0"]
    return [
        title,
        f"Попыток: {attempts}",
        f"Лучший результат: {_round_percent(data.get('best_percent'))}%",
        f"Средний результат: {_round_percent(data.get('avg_percent'))}%",
    ]


def my_stats_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    total_questions = len(get_questions(test_id))
    summary = stats_summary(user_id, test_id)

    answered_questions = int(summary.get("answered_questions") or 0)
    progress = round(answered_questions / total_questions * 100) if total_questions else 0
    errors = summary.get("errors") or {}
    overall = summary.get("overall") or {}

    lines = [
        "📊 Статистика",
        f"📚 {title}",
        "",
        "📌 Прогресс",
        f"Решено вопросов: {answered_questions} из {total_questions}",
        f"Пройдено: {progress}%",
        "",
    ]

    for block in [
        _mode_stats_line("📝 Основной тест", summary.get("solution") or {}),
        _mode_stats_line("⚡ Тренировка", summary.get("training") or {}),
        _mode_stats_line("🧠 Разбор ошибок", summary.get("errors_mode") or {}),
    ]:
        lines.extend(block)
        lines.append("")

    lines.extend([
        "🧠 Ошибки",
        f"Актуальных ошибок: {int(errors.get('unresolved') or 0)}",
        f"Исправлено: {int(errors.get('resolved') or 0)}",
        f"Всего за историю: {int(errors.get('total') or 0)}",
        "",
        "⭐ Избранное",
        f"Избранных вопросов: {int(summary.get('favorites') or 0)}",
    ])

    return "\n".join(lines)


def public_rating_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        rows = conn.execute(
            """
            WITH ranked_attempts AS (
                SELECT
                    a.*,
                    (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) AS percent_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.user_id
                        ORDER BY
                            a.answered DESC,
                            (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) DESC,
                            a.duration_seconds ASC,
                            a.finished_at DESC
                    ) AS user_rank
                FROM attempts a
                WHERE a.test_id = ?
                  AND a.mode IN ('normal', 'random', 'reverse', 'from_number')
                  AND a.finished_at IS NOT NULL
                  AND a.answered > 0
            )
            SELECT r.*, u.user_id, u.username, u.first_name, u.last_name
            FROM ranked_attempts r
            LEFT JOIN users u ON u.user_id = r.user_id
            WHERE r.user_rank = 1
            ORDER BY
                r.answered DESC,
                r.percent_value DESC,
                r.duration_seconds ASC,
                r.finished_at DESC
            LIMIT 10
            """,
            (test_id,),
        ).fetchall()

    lines = [
        "🏆 Рейтинг топ-10",
        title,
        "",
    ]

    if not rows:
        lines.append("Пока нет завершённых решений.")
        return "\n".join(lines)

    seen_users: set[int] = set()
    place = 1

    for row in rows:
        user_id = int(row["user_id"])
        if user_id in seen_users:
            continue

        seen_users.add(user_id)
        percent = round((row["correct"] / row["answered"]) * 100, 1) if row["answered"] else 0
        lines.append(
            f"{place}. {user_display_name(row)} — "
            f"{row['correct']}/{row['answered']} — {percent}% · {seconds_to_text(row['duration_seconds'])}"
        )
        place += 1

    return "\n".join(lines)
