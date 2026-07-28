import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app


class AppImportTests(unittest.TestCase):
    def test_app_imports_without_legacy_weather_tools(self):
        command = [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'src'); import app",
        ]
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, result.returncode, result.stderr)


class LoadTestCasesTests(unittest.TestCase):
    def test_loads_current_twenty_case_contract(self):
        cases = app.load_test_cases()

        self.assertEqual(20, len(cases))
        self.assertEqual("TC01", cases[0]["id"])
        self.assertIn("user_input", cases[0])

    def test_rejects_missing_test_cases_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_cases.json"
            config_path.write_text(
                json.dumps({"meta": {}}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "must contain a 'test_cases' list",
            ):
                app.load_test_cases(config_path)

    def test_rejects_case_without_non_empty_user_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_cases.json"
            config_path.write_text(
                json.dumps(
                    {"test_cases": [{"id": "BROKEN", "user_input": ""}]}
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "BROKEN.*non-empty 'user_input'",
            ):
                app.load_test_cases(config_path)


if __name__ == "__main__":
    unittest.main()
