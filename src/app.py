"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
"""

import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Optional
from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import prompt của Role 3 và Multi-Provider Adapter
from prompts import CHATBOT_BASELINE_PROMPT
from providers import get_llm_provider

load_dotenv()

BASELINE_CASE_LIMIT = 5

REACT_ACTION_RE = re.compile(
    (
        r"^\s*Thought:\s*(?P<thought>.+?)\s*\n"
        r"Action:\s*(?P<tool>[A-Za-z_]\w*)"
        r"\[(?P<arguments>.*)\]\s*$"
    ),
    re.DOTALL,
)
REACT_FINAL_RE = re.compile(
    r"^\s*Final Answer:\s*(?P<answer>.+?)\s*$",
    re.DOTALL,
)


@dataclass(frozen=True)
class AgentAction:
    thought: str
    tool_name: str
    arguments: list[Any]
    raw_output: str


@dataclass(frozen=True)
class ParsedAgentOutput:
    kind: str
    raw_output: str
    action: Optional[AgentAction] = None
    final_answer: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def _parse_error(raw_output, code, message):
    return ParsedAgentOutput(
        kind="error",
        raw_output=raw_output,
        error_code=code,
        error_message=message,
    )


def _parse_action_arguments(arguments_text):
    if not arguments_text.strip():
        return []

    try:
        return json.loads(f"[{arguments_text}]")
    except json.JSONDecodeError:
        try:
            return [
                value.strip()
                for value in next(
                    csv.reader(
                        [arguments_text],
                        skipinitialspace=True,
                        strict=True,
                    )
                )
            ]
        except (csv.Error, StopIteration):
            raise ValueError("malformed action arguments") from None


def parse_agent_output(model_output):
    """Parse output ReAct mà không thực thi code từ arguments."""
    text = (model_output or "").strip()

    if "Action:" in text and "Final Answer:" in text:
        return _parse_error(
            text,
            "MIXED_OUTPUT",
            "Không được trộn Action và Final Answer.",
        )

    final_match = REACT_FINAL_RE.fullmatch(text)
    if final_match:
        return ParsedAgentOutput(
            kind="final",
            raw_output=text,
            final_answer=final_match.group("answer").strip(),
        )

    action_match = REACT_ACTION_RE.fullmatch(text)
    if not action_match:
        return _parse_error(
            text,
            "INVALID_FORMAT",
            (
                "Output phải là Thought + Action hoặc "
                "một Final Answer."
            ),
        )

    thought = action_match.group("thought").strip()
    if not thought:
        return _parse_error(
            text,
            "INVALID_FORMAT",
            "Thought công khai không được rỗng.",
        )

    try:
        arguments = _parse_action_arguments(
            action_match.group("arguments")
        )
    except ValueError:
        return _parse_error(
            text,
            "MALFORMED_ARGUMENTS",
            (
                "Arguments phải là chuỗi phân tách bằng dấu phẩy "
                "hoặc JSON values hợp lệ."
            ),
        )

    return ParsedAgentOutput(
        kind="action",
        raw_output=text,
        action=AgentAction(
            thought=thought,
            tool_name=action_match.group("tool"),
            arguments=arguments,
            raw_output=text,
        ),
    )


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
        if isinstance(case, dict):
            case_id = case.get("id", f"case #{index}")
            user_input = case.get("user_input")
        else:
            case_id = f"case #{index}"
            user_input = None

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError(
                f"{case_id} must contain a non-empty 'user_input'"
            )

    return test_cases


def run_baseline_chatbot(user_query: str, provider):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    """
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    print(f"⚙️ System Prompt: {CHATBOT_BASELINE_PROMPT.strip()}")
    
    # Gọi LLM Provider thực hiện sinh câu trả lời
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")
    return response


def run_baseline_suite(test_cases, provider, limit=5):
    """Chạy Chatbot Baseline trên một số test case đầu tiên."""
    selected_cases = test_cases[:limit]
    results = []

    for index, case in enumerate(selected_cases, start=1):
        case_id = case.get("id", f"case-{index}")
        title = case.get("title", "Không có tiêu đề")
        user_query = case["user_input"]

        print(f"\n{'=' * 60}")
        print(
            f"🧪 BASELINE CASE {index}/{len(selected_cases)}: "
            f"{case_id} — {title}"
        )
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


def main():
    """Khởi chạy mốc 2 của Role 4 với Chatbot Baseline."""
    print("=" * 60)
    print("🏫 ĐẠI HỌC VINUNI - MỐC 2: CHATBOT BASELINE")
    print("=" * 60)

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(
        f"🔌 LLM Provider đang hoạt động: "
        f"{provider.__class__.__name__} (Model: {model_name})"
    )

    test_cases = load_test_cases()
    print(
        f"✅ Đã tải {len(test_cases)} test cases; "
        f"chạy {BASELINE_CASE_LIMIT} case đầu bằng Chatbot Baseline."
    )
    return run_baseline_suite(
        test_cases,
        provider,
        limit=BASELINE_CASE_LIMIT,
    )


if __name__ == "__main__":
    main()
