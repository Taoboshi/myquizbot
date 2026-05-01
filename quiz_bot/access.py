from .helpers import is_admin
from .loader import test_access, test_allowed_user_ids
from .storage import grant_user_test_access, has_user_test_access, get_test_access_setting


def effective_test_access(test_id: str) -> dict:
    base = dict(test_access(test_id))
    override = get_test_access_setting(test_id)

    if not override:
        return base

    result = dict(base)
    result["type"] = override.get("type") or base.get("type", "public")
    if result["type"] == "code":
        result["code"] = override.get("code") or base.get("code") or ""
    else:
        result["code"] = override.get("code") or base.get("code") or ""
    result["_source"] = "admin"
    result["_base_type"] = base.get("type", "public")
    result["_updated_at"] = override.get("updated_at")
    result["_updated_by"] = override.get("updated_by")
    return result


def effective_access_type(test_id: str) -> str:
    return effective_test_access(test_id).get("type", "public")


def effective_access_code(test_id: str) -> str:
    return str(effective_test_access(test_id).get("code") or "").strip()


def has_explicit_access(user_id: int, test_id: str) -> bool:
    if user_id in test_allowed_user_ids(test_id):
        return True
    return has_user_test_access(user_id, test_id)


def can_view_test(user_id: int, test_id: str) -> bool:
    if is_admin(user_id):
        return True

    access_type = effective_access_type(test_id)
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

    access_type = effective_access_type(test_id)
    if access_type == "public":
        return True
    if access_type in {"private", "code"}:
        return has_explicit_access(user_id, test_id)
    if access_type == "admin_only":
        return False

    return True


def is_code_locked_for_user(user_id: int, test_id: str) -> bool:
    return effective_access_type(test_id) == "code" and not can_open_test(user_id, test_id)


def verify_access_code(user_id: int, test_id: str, code: str) -> bool:
    expected = effective_access_code(test_id)
    if not expected:
        return False

    if str(code or "").strip().casefold() != expected.casefold():
        return False

    grant_user_test_access(user_id, test_id, access_source="code", granted_by=None)
    return True


def access_icon_for_user(user_id: int, test_id: str) -> str:
    access_type = effective_access_type(test_id)
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
    }.get(effective_access_type(test_id), "открытый")


def access_type_label(access_type: str) -> str:
    return {
        "public": "открытый",
        "private": "приватный",
        "code": "по коду",
        "admin_only": "только админ",
    }.get(access_type, "открытый")
