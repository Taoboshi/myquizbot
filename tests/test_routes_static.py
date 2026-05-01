import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tuple_patterns(module_path: str, constant_name: str) -> list[str]:
    tree = ast.parse((ROOT / module_path).read_text(encoding="utf-8"), filename=module_path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if constant_name in names and isinstance(node.value, ast.Tuple):
                patterns: list[str] = []
                for item in node.value.elts:
                    assert isinstance(item, ast.Tuple)
                    assert len(item.elts) == 2
                    pattern = item.elts[1]
                    assert isinstance(pattern, ast.Constant)
                    patterns.append(str(pattern.value))
                return patterns
    raise AssertionError(f"{constant_name} not found in {module_path}")


def test_route_tables_are_present_and_non_empty():
    assert len(_tuple_patterns("quiz_bot/user_routes.py", "USER_CALLBACKS")) >= 40
    assert len(_tuple_patterns("quiz_bot/admin_routes.py", "ADMIN_CALLBACKS")) >= 60


def test_callback_patterns_are_not_duplicated():
    for module_path, constant_name in [
        ("quiz_bot/user_routes.py", "USER_CALLBACKS"),
        ("quiz_bot/admin_routes.py", "ADMIN_CALLBACKS"),
    ]:
        patterns = _tuple_patterns(module_path, constant_name)
        duplicates = {pattern for pattern in patterns if patterns.count(pattern) > 1}
        assert not duplicates


def test_app_uses_route_registrars():
    source = (ROOT / "quiz_bot/app.py").read_text(encoding="utf-8")
    assert "register_admin_handlers(app)" in source
    assert "register_user_handlers(app)" in source
