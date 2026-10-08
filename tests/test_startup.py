import json
from pathlib import Path
import subprocess
import sys
import unittest


class ProductionStartupTests(unittest.TestCase):
    def test_bot_import_order_keeps_mini_app_assets_and_routes(self):
        root = Path(__file__).resolve().parents[1]
        for module in ('quiz_bot.app', 'quiz_bot.admin_users'):
            with self.subTest(module=module):
                # A fresh process catches circular imports hidden by earlier tests.
                code = (
                    f'import {module}; '
                    'from quiz_bot.runtime import WEB_APP; import json; '
                    'client=WEB_APP.test_client(); '
                    'print(json.dumps({'
                    '"app":client.get("/app").status_code,'
                    '"core":client.get("/app-assets/app-core.js").status_code,'
                    '"navigation":client.get("/app-assets/app-settings.js").status_code,'
                    '"admin":client.get("/app-assets/app-admin-people.js").status_code,'
                    '"api":client.get("/api/admin/people").status_code}))'
                )
                result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code],
                                        cwd=root, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 {'app': 200, 'core': 200, 'navigation': 200, 'admin': 200, 'api': 401})
