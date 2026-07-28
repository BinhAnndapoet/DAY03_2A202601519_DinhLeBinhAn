import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
