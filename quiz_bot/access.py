from .helpers import is_admin
from .loader import test_access_code, test_access_type, test_allowed_user_ids
from .storage import grant_user_test_access, has_user_test_access


def has_explicit_access(user_id: int, test_id: str) -> bool:
    if user_id in test_allowed_user_ids(test_id):
        return True
    return has_user_test_access(user_id, test_id)


def can_view_test(user_id: int, test_id: str) -> bool:
    if is_admin(user_id):
        return True

    access_type = test_access_type(test_id)
    if access_type == "public":
        return True
    if access_type == "code":
        # Code tests are visible as locked, so users know they can enter a code.
        return True
    if access_type == "private":
        # Private tests are invisible unless access was granted.
        return has_explicit_access(user_id, test_id)
    if access_type == "admin_only":
        return False

    return True


def can_open_test(user_id: int, test_id: str) -> bool:
    if is_admin(user_id):
        return True

    access_type = test_access_type(test_id)
    if access_type == "public":
        return True
    if access_type in {"private", "code"}:
        return has_explicit_access(user_id, test_id)
    if access_type == "admin_only":
        return False

    return True


def is_code_locked_for_user(user_id: int, test_id: str) -> bool:
    return test_access_type(test_id) == "code" and not can_open_test(user_id, test_id)


def verify_access_code(user_id: int, test_id: str, code: str) -> bool:
    expected = test_access_code(test_id)
    if not expected:
        return False

    if str(code or "").strip().casefold() != expected.casefold():
        return False

    grant_user_test_access(user_id, test_id, access_source="code", granted_by=None)
    return True


def access_icon_for_user(user_id: int, test_id: str) -> str:
    access_type = test_access_type(test_id)
    if can_open_test(user_id, test_id):
        return "✅"
    if access_type == "code":
        return "🔒"
    if access_type == "private":
        return "🔐"
    if access_type == "admin_only":
        return "🙈"
    return "📚"


def access_label(test_id: str) -> str:
    return {
        "public": "открытый",
        "private": "приватный",
        "code": "по коду",
        "admin_only": "только админ",
    }.get(test_access_type(test_id), "открытый")
