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


class FakeProvider:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, system_prompt=""):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt}
        )
        return f"fake response: {prompt}"


class BaselineChatbotTests(unittest.TestCase):
    def test_calls_provider_once_without_tools_and_returns_response(self):
        provider = FakeProvider()

        response = app.run_baseline_chatbot(
            "Đơn ORD-2001 đâu rồi?",
            provider,
        )

        self.assertEqual(
            "fake response: Đơn ORD-2001 đâu rồi?",
            response,
        )
        self.assertEqual(
            [
                {
                    "prompt": "Đơn ORD-2001 đâu rồi?",
                    "system_prompt": app.CHATBOT_BASELINE_PROMPT,
                }
            ],
            provider.calls,
        )


class BaselineSuiteTests(unittest.TestCase):
    def test_runs_only_first_five_cases_in_order(self):
        provider = FakeProvider()
        cases = [
            {
                "id": f"TC{index:02d}",
                "title": f"Case {index}",
                "user_input": f"question {index}",
            }
            for index in range(1, 7)
        ]

        results = app.run_baseline_suite(cases, provider, limit=5)

        self.assertEqual(5, len(results))
        self.assertEqual(
            [f"question {index}" for index in range(1, 6)],
            [call["prompt"] for call in provider.calls],
        )
        self.assertEqual(
            [f"TC{index:02d}" for index in range(1, 6)],
            [result["id"] for result in results],
        )


if __name__ == "__main__":
    unittest.main()
