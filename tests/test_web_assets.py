import unittest

from quiz_bot.webapp import create_webapp


class MiniAppAssetTestCase(unittest.TestCase):
    def setUp(self):
        self.client = create_webapp().test_client()

    def test_app_page_loads_each_javascript_module(self):
        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        modules = (
            "app-data.js",
            "app-core.js",
            "app-quiz.js",
            "app-profile.js",
            "app-admin.js",
            "app-settings.js",
        )
        positions = []
        for module in modules:
            self.assertIn(f'/app-assets/{module}', html)
            positions.append(html.index(f'/app-assets/{module}'))
            self.assertIn(f'/app-assets/{module}" defer', html)
        self.assertEqual(positions, sorted(positions))

    def test_javascript_modules_are_served_without_telegram_auth(self):
        for module in (
            "app-data.js",
            "app-core.js",
            "app-quiz.js",
            "app-profile.js",
            "app-admin.js",
            "app-settings.js",
        ):
            with self.subTest(module=module):
                response = self.client.get(f"/app-assets/{module}")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_data())
                self.assertIn("javascript", response.mimetype)
                self.assertIn("no-store", response.headers["Cache-Control"])
                response.close()

    def test_asset_route_does_not_expose_paths_outside_web_directory(self):
        response = self.client.get("/app-assets/%2e%2e/webapp.py")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
