# Role 4 Milestone 2 Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tích hợp Chatbot Baseline vào `src/app.py`, đọc đúng schema 20 test case mới và chạy đúng 5 case đầu mà không gọi tool.

**Architecture:** `app.py` giữ ba ranh giới rõ ràng: loader xác thực contract JSON, hàm baseline thực hiện đúng một LLM call, và suite runner chọn/điều phối 5 case. Luồng `main()` chỉ chạy baseline ở Mốc 2; ReAct cũ về thời tiết bị gỡ để không phụ thuộc tool đã bị Role 2 xóa.

**Tech Stack:** Python 3.14, standard-library `unittest`, `json`, `subprocess`, existing multi-provider adapter và `python-dotenv`.

---

## File map

- Create: `tests/__init__.py` — đánh dấu thư mục test để `unittest discover` hoạt động ổn định.
- Create: `tests/test_app.py` — kiểm tra import, loader, một baseline call, giới hạn 5 case và smoke test.
- Modify: `src/app.py` — tích hợp schema mới, baseline suite và luồng `main()`.
- Do not modify: `src/tools.py`, `src/prompts.py`, `src/guardrails.py`, `config/test_cases.json`, `src/providers.py`.

### Task 1: Loại bỏ phụ thuộc tool thời tiết đã bị xóa

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_app.py`
- Modify: `src/app.py:21-24`
- Modify: `src/app.py:53-78`

- [ ] **Step 1: Tạo package test**

Tạo file rỗng:

```python
# tests/__init__.py
```

- [ ] **Step 2: Viết test tái hiện ImportError hiện tại**

Tạo `tests/test_app.py`:

```python
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
```

- [ ] **Step 3: Chạy test để xác nhận RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.AppImportTests -v
```

Expected: FAIL; stderr chứa `ImportError: cannot import name 'get_weather' from 'tools'`.

- [ ] **Step 4: Sửa import và bỏ ReAct weather khỏi Mốc 2**

Trong `src/app.py`, thay import:

```python
from tools import AVAILABLE_TOOLS, get_weather, search_flights
from prompts import CHATBOT_BASELINE_PROMPT, REACT_SYSTEM_PROMPT, MAX_ITERATIONS
```

bằng:

```python
from prompts import CHATBOT_BASELINE_PROMPT
```

Xóa toàn bộ `run_react_agent()` cũ ở dòng 53–78. Không thêm ReAct placeholder vì Mốc 2 không gọi Agent.

- [ ] **Step 5: Chạy test để xác nhận GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.AppImportTests -v
```

Expected: `Ran 1 test` và `OK`.

- [ ] **Step 6: Commit thay đổi độc lập**

```powershell
git add tests/__init__.py tests/test_app.py src/app.py
git commit -m "fix: remove obsolete weather tool imports"
```

### Task 2: Chuẩn hóa loader theo schema mới

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/app.py:28-38`

- [ ] **Step 1: Thêm helper import app và test loader**

Thêm sau `PROJECT_ROOT` trong `tests/test_app.py`:

```python
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app
```

Thêm imports:

```python
import json
import tempfile
```

Thêm test class:

```python
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
                json.dumps({"test_cases": [{"id": "BROKEN", "user_input": ""}]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "BROKEN.*non-empty 'user_input'",
            ):
                app.load_test_cases(config_path)
```

- [ ] **Step 2: Chạy test loader để xác nhận RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.LoadTestCasesTests -v
```

Expected: FAIL vì loader hiện trả object top-level và chưa nhận `config_path`.

- [ ] **Step 3: Viết implementation tối thiểu**

Thay `load_test_cases()` trong `src/app.py` bằng:

```python
def load_test_cases(config_path=None):
    """Đọc và xác thực bộ test case do Role 1 cung cấp."""
    if config_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config", "test_cases.json")

    with open(config_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    test_cases = data.get("test_cases") if isinstance(data, dict) else None
    if not isinstance(test_cases, list):
        raise ValueError(
            "config/test_cases.json must contain a 'test_cases' list"
        )

    for index, case in enumerate(test_cases, start=1):
        case_id = case.get("id", f"case #{index}") if isinstance(case, dict) else f"case #{index}"
        user_input = case.get("user_input") if isinstance(case, dict) else None
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError(
                f"{case_id} must contain a non-empty 'user_input'"
            )

    return test_cases
```

- [ ] **Step 4: Chạy test loader để xác nhận GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.LoadTestCasesTests -v
```

Expected: `Ran 3 tests` và `OK`.

- [ ] **Step 5: Chạy toàn bộ test hiện có**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Expected: `Ran 4 tests` và `OK`.

- [ ] **Step 6: Commit loader**

```powershell
git add tests/test_app.py src/app.py
git commit -m "feat: load role 1 test case schema"
```

### Task 3: Làm baseline call có thể kiểm thử

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/app.py:41-50`

- [ ] **Step 1: Viết Fake Provider và failing test**

Thêm vào `tests/test_app.py`:

```python
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

        response = app.run_baseline_chatbot("Đơn ORD-2001 đâu rồi?", provider)

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
```

- [ ] **Step 2: Chạy test để xác nhận RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.BaselineChatbotTests -v
```

Expected: FAIL vì `run_baseline_chatbot()` hiện trả `None`.

- [ ] **Step 3: Trả response từ baseline**

Thêm cuối `run_baseline_chatbot()`:

```python
    return response
```

Không thêm bất kỳ import hoặc lời gọi tool nào.

- [ ] **Step 4: Chạy test để xác nhận GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.BaselineChatbotTests -v
```

Expected: `Ran 1 test` và `OK`.

- [ ] **Step 5: Commit baseline contract**

```powershell
git add tests/test_app.py src/app.py
git commit -m "test: make baseline response observable"
```

### Task 4: Chạy đúng 5 test case đầu

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/app.py`

- [ ] **Step 1: Viết failing test cho suite limit**

Thêm vào `tests/test_app.py`:

```python
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
```

- [ ] **Step 2: Chạy test để xác nhận RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.BaselineSuiteTests -v
```

Expected: ERROR với `AttributeError: module 'app' has no attribute 'run_baseline_suite'`.

- [ ] **Step 3: Viết suite runner tối thiểu**

Thêm sau `run_baseline_chatbot()` trong `src/app.py`:

```python
def run_baseline_suite(test_cases, provider, limit=5):
    """Chạy Chatbot Baseline trên một số test case đầu tiên."""
    selected_cases = test_cases[:limit]
    results = []

    for index, case in enumerate(selected_cases, start=1):
        case_id = case.get("id", f"case-{index}")
        title = case.get("title", "Không có tiêu đề")
        user_query = case["user_input"]

        print(f"\n{'=' * 60}")
        print(f"🧪 BASELINE CASE {index}/{len(selected_cases)}: {case_id} — {title}")
        print(f"{'=' * 60}")

        response = run_baseline_chatbot(user_query, provider)
        results.append(
            {
                "id": case_id,
                "title": title,
                "response": response,
            }
        )

    return results
```

- [ ] **Step 4: Chạy test để xác nhận GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.BaselineSuiteTests -v
```

Expected: `Ran 1 test` và `OK`.

- [ ] **Step 5: Commit suite runner**

```powershell
git add tests/test_app.py src/app.py
git commit -m "feat: run first five baseline cases"
```

### Task 5: Nối suite vào `main()` và smoke test

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/app.py:81-101`

- [ ] **Step 1: Viết failing subprocess smoke test**

Thêm vào `tests/test_app.py`:

```python
import os
```

Thêm test class:

```python
class AppSmokeTests(unittest.TestCase):
    def test_main_runs_five_baseline_cases_with_mock_provider(self):
        environment = os.environ.copy()
        environment["LLM_PROVIDER"] = "mock"
        environment["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [sys.executable, "src/app.py"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Đã tải 20 test cases", result.stdout)
        self.assertEqual(5, result.stdout.count("🧪 BASELINE CASE"))
        self.assertNotIn("[REACT AGENT]", result.stdout)
```

- [ ] **Step 2: Chạy smoke test để xác nhận RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.AppSmokeTests -v
```

Expected: FAIL vì main hiện vẫn truy cập schema cũ và gọi ReAct.

- [ ] **Step 3: Tách và viết `main()`**

Thay block `if __name__ == "__main__":` trong `src/app.py` bằng:

```python
BASELINE_CASE_LIMIT = 5


def main():
    print("=" * 60)
    print("🏫 ĐẠI HỌC VINUNI - MỐC 2: CHATBOT BASELINE")
    print("=" * 60)

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(
        "🔌 LLM Provider đang hoạt động: "
        f"{provider.__class__.__name__} (Model: {model_name})"
    )

    test_cases = load_test_cases()
    print(
        f"✅ Đã tải {len(test_cases)} test cases; "
        f"chạy {BASELINE_CASE_LIMIT} case đầu bằng Chatbot Baseline."
    )

    run_baseline_suite(
        test_cases,
        provider,
        limit=BASELINE_CASE_LIMIT,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Chạy smoke test để xác nhận GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_app.AppSmokeTests -v
```

Expected: `Ran 1 test` và `OK`.

- [ ] **Step 5: Chạy toàn bộ unit test**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Expected: `Ran 7 tests` và `OK`.

- [ ] **Step 6: Commit luồng main**

```powershell
git add tests/test_app.py src/app.py
git commit -m "feat: integrate milestone 2 baseline runner"
```

### Task 6: Verification và chạy thử OpenAI

**Files:**
- Verify only; do not modify `.env`.

- [ ] **Step 1: Kiểm tra compile**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Expected: exit code `0`, không có output lỗi.

- [ ] **Step 2: Kiểm tra dependencies**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Expected: `No broken requirements found.`

- [ ] **Step 3: Chạy smoke test Mock Provider**

Run:

```powershell
$env:LLM_PROVIDER = "mock"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe src\app.py
```

Expected:

- Exit code `0`.
- Hiển thị `Đã tải 20 test cases`.
- Có đúng 5 dòng `🧪 BASELINE CASE`.
- Không có `[REACT AGENT]`.

- [ ] **Step 4: Chạy 5 case bằng OpenAI**

Run:

```powershell
$env:LLM_PROVIDER = "openai"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe src\app.py
```

Expected:

- Provider là `OpenAIProvider`.
- Có đúng 5 phản hồi baseline.
- Không xuất API key.
- Nếu provider trả lỗi, lỗi phải xuất hiện dưới dạng phản hồi có nhãn thay vì làm lộ secret.

- [ ] **Step 5: Kiểm tra Git**

Run:

```powershell
git diff --check
git status --short
git diff --name-only main...HEAD
git ls-files .env
```

Expected:

- `git diff --check` không có output.
- `.env` không xuất hiện từ `git ls-files`.
- Chỉ có spec, plan, `src/app.py` và `tests/` khác `main`.
