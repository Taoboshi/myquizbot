from .helpers import is_admin
from .loader import effective_test_info, test_access, test_allowed_user_ids
from .storage import grant_user_test_access, has_user_test_access, get_subject_setting, get_test_access_setting


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



def subject_access(subject_id: str | None) -> dict:
    if not subject_id:
        return {"type": "public", "code": ""}

    setting = get_subject_setting(subject_id)
    if not setting:
        return {"type": "public", "code": ""}

    return {
        "type": setting.get("access_type") or "public",
        "code": setting.get("code") or "",
        "title": setting.get("title") or subject_id,
    }


def subject_access_type(subject_id: str | None) -> str:
    return subject_access(subject_id).get("type", "public")


def subject_access_code(subject_id: str | None) -> str:
    return str(subject_access(subject_id).get("code") or "").strip()


def subject_access_label(subject_id: str | None) -> str:
    return access_type_label(subject_access_type(subject_id))


def has_subject_access(user_id: int, subject_id: str | None) -> bool:
    if not subject_id:
        return True
    return has_user_test_access(user_id, f"subject:{subject_id}")


def grant_user_subject_access(user_id: int, subject_id: str, access_source: str = "admin", granted_by: int | None = None) -> None:
    grant_user_test_access(user_id, f"subject:{subject_id}", access_source=access_source, granted_by=granted_by)


def can_view_subject(user_id: int, subject_id: str | None) -> bool:
    if is_admin(user_id):
        return True

    access_type = subject_access_type(subject_id)
    if access_type == "public":
        return True
    if access_type == "code":
        return True
    if access_type == "private":
        return has_subject_access(user_id, subject_id)
    if access_type == "admin_only":
        return False

    return True


def can_open_subject(user_id: int, subject_id: str | None) -> bool:
    if is_admin(user_id):
        return True

    access_type = subject_access_type(subject_id)
    if access_type == "public":
        return True
    if access_type in {"private", "code"}:
        return has_subject_access(user_id, subject_id)
    if access_type == "admin_only":
        return False

    return True


def is_subject_code_locked_for_user(user_id: int, subject_id: str | None) -> bool:
    return subject_access_type(subject_id) == "code" and not can_open_subject(user_id, subject_id)


def verify_subject_access_code(user_id: int, subject_id: str, code: str) -> bool:
    expected = subject_access_code(subject_id)
    if not expected:
        return False

    if str(code or "").strip().casefold() != expected.casefold():
        return False

    grant_user_subject_access(user_id, subject_id, access_source="code", granted_by=None)
    return True


def has_explicit_access(user_id: int, test_id: str) -> bool:
    if user_id in test_allowed_user_ids(test_id):
        return True
    return has_user_test_access(user_id, test_id)


def can_view_test(user_id: int, test_id: str) -> bool:
    if is_admin(user_id):
        return True

    subject_id = effective_test_info(test_id).get("subject_id")
    if not can_view_subject(user_id, subject_id):
        return False
    if not can_open_subject(user_id, subject_id):
        return False

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

    subject_id = effective_test_info(test_id).get("subject_id")
    if not can_open_subject(user_id, subject_id):
        return False

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
