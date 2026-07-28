"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
"""

import csv
import inspect
import json
import os
import re
import sys
from dataclasses import dataclass, field
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
from guardrails import validate_input, validate_output
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    MAX_ITERATIONS,
    REACT_SYSTEM_PROMPT,
)
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS, TOOL_SPECS

load_dotenv()

BASELINE_CASE_LIMIT = 5
REACT_MAX_ITERATIONS = max(MAX_ITERATIONS, 6)
REACT_RUNTIME_PROMPT = (
    f"{REACT_SYSTEM_PROMPT}\n\n"
    "# RUNTIME OVERRIDE\n"
    f"Orchestrator cho phép tối đa {REACT_MAX_ITERATIONS} lượt suy luận "
    "để hoàn tất các luồng cần 4 tool calls. Giới hạn runtime này thay cho "
    "con số thấp hơn được mô tả ở trên."
)
SAFE_FALLBACK_ANSWER = (
    "Xin lỗi, tôi chưa thể hoàn tất yêu cầu một cách an toàn. "
    "Vui lòng kiểm tra lại thông tin và thử lại."
)

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


@dataclass
class AgentState:
    """Evidence collected from read-only tools during one ReAct run."""

    action_attempts: dict[str, int] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    orders_by_email: dict[str, Any] = field(default_factory=dict)
    eligibility: dict[tuple[str, str], dict[str, Any]] = field(
        default_factory=dict
    )
    inventory: dict[tuple[str, str, str], dict[str, Any]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ToolExecutionResult:
    observation: Any
    executed: bool
    error_code: Optional[str] = None
    should_stop: bool = False


@dataclass(frozen=True)
class AgentTraceStep:
    iteration: int
    thought: Optional[str] = None
    action: Optional[AgentAction] = None
    observation: Any = None
    final_answer: Optional[str] = None


@dataclass
class AgentRunResult:
    final_answer: str
    trace: list[AgentTraceStep]
    stop_reason: str
    state: AgentState
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


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


def serialize_observation(observation):
    """Serialize a tool observation for the model and Markdown trace."""
    return json.dumps(
        observation,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _error_observation(code, message, **details):
    observation = {"error": code, "message": message}
    observation.update(details)
    return observation


def _action_fingerprint(action):
    return json.dumps(
        [action.tool_name, action.arguments],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _find_order_item(state, order_id, item_id):
    order = state.orders.get(str(order_id))
    if not isinstance(order, dict):
        return None
    for item in order.get("items", []):
        if str(item.get("item_id")) == str(item_id):
            return item
    return None


def _write_precondition_error(action, state):
    args = action.arguments

    if action.tool_name == "initiate_return_request":
        order_id, item_id, _reason, refund_method = args
        evidence = state.eligibility.get(
            (str(order_id), str(item_id))
        )
        if not evidence or evidence.get("eligible") is not True:
            return _error_observation(
                "PRECONDITION_FAILED",
                "Phải xác nhận sản phẩm đủ điều kiện trước khi tạo yêu cầu trả.",
            )
        supported_refund = evidence.get("refund_method")
        if supported_refund and str(refund_method) != str(supported_refund):
            return _error_observation(
                "PRECONDITION_FAILED",
                "Phương thức hoàn tiền không khớp kết quả kiểm tra điều kiện.",
                supported_refund_method=supported_refund,
            )

    if action.tool_name == "initiate_exchange_request":
        order_id, item_id, new_size, new_color = args
        evidence = state.eligibility.get(
            (str(order_id), str(item_id))
        )
        if not evidence or evidence.get("eligible") is not True:
            return _error_observation(
                "PRECONDITION_FAILED",
                "Phải xác nhận sản phẩm đủ điều kiện trước khi tạo yêu cầu đổi.",
            )

        item = _find_order_item(state, order_id, item_id)
        if not item or not item.get("name"):
            return _error_observation(
                "PRECONDITION_FAILED",
                "Phải tra cứu đơn hàng và sản phẩm trước khi tạo yêu cầu đổi.",
            )

        inventory = state.inventory.get(
            (str(item["name"]), str(new_size), str(new_color))
        )
        if not inventory or int(inventory.get("stock", 0)) <= 0:
            return _error_observation(
                "PRECONDITION_FAILED",
                "Biến thể muốn đổi chưa được xác nhận còn hàng.",
            )

    return None


def _record_tool_evidence(action, observation, state):
    if not isinstance(observation, dict) or "error" in observation:
        return

    args = action.arguments
    if action.tool_name == "lookup_order" and args:
        state.orders[str(args[0])] = observation
    elif action.tool_name == "lookup_orders_by_email" and args:
        state.orders_by_email[str(args[0])] = observation
    elif action.tool_name == "check_return_eligibility":
        state.eligibility[(str(args[0]), str(args[1]))] = observation
    elif action.tool_name == "check_inventory":
        state.inventory[
            (str(args[0]), str(args[1]), str(args[2]))
        ] = observation


def execute_tool_action(
    action,
    state,
    *,
    tools=None,
    tool_specs=None,
    confirmation_handler=None,
):
    """Execute one allowlisted action with validation and write guards."""
    tools = AVAILABLE_TOOLS if tools is None else tools
    tool_specs = TOOL_SPECS if tool_specs is None else tool_specs

    fingerprint = _action_fingerprint(action)
    attempt = state.action_attempts.get(fingerprint, 0) + 1
    state.action_attempts[fingerprint] = attempt
    if attempt > 1:
        observation = _error_observation(
            "REPEATED_ACTION",
            "Action giống hệt đã được xử lý; hãy đổi hướng hoặc kết luận.",
            attempt=attempt,
        )
        return ToolExecutionResult(
            observation=observation,
            executed=False,
            error_code="REPEATED_ACTION",
            should_stop=attempt >= 3,
        )

    tool = tools.get(action.tool_name)
    spec = tool_specs.get(action.tool_name)
    if tool is None or spec is None:
        observation = _error_observation(
            "UNKNOWN_TOOL",
            "Tool không nằm trong danh sách cho phép.",
            available_tools=sorted(tools),
        )
        return ToolExecutionResult(
            observation=observation,
            executed=False,
            error_code="UNKNOWN_TOOL",
        )

    try:
        inspect.signature(tool).bind(*action.arguments)
    except TypeError:
        observation = _error_observation(
            "INVALID_ARGUMENTS",
            "Số lượng hoặc cấu trúc tham số của tool không hợp lệ.",
            required_args=spec.get("required_args", []),
        )
        return ToolExecutionResult(
            observation=observation,
            executed=False,
            error_code="INVALID_ARGUMENTS",
        )

    if spec.get("read_only") is not True:
        precondition_error = _write_precondition_error(action, state)
        if precondition_error is not None:
            return ToolExecutionResult(
                observation=precondition_error,
                executed=False,
                error_code="PRECONDITION_FAILED",
            )

        confirmed = False
        if confirmation_handler is not None:
            try:
                confirmed = bool(confirmation_handler(action))
            except Exception:
                confirmed = False
        if not confirmed:
            observation = _error_observation(
                "CONFIRMATION_DENIED",
                "Người dùng chưa xác nhận thao tác làm thay đổi dữ liệu.",
            )
            return ToolExecutionResult(
                observation=observation,
                executed=False,
                error_code="CONFIRMATION_DENIED",
                should_stop=True,
            )

    try:
        observation = tool(*action.arguments)
    except Exception:
        observation = _error_observation(
            "TOOL_EXCEPTION",
            "Tool gặp lỗi ngoài dự kiến; chi tiết nhạy cảm đã được ẩn.",
        )
        return ToolExecutionResult(
            observation=observation,
            executed=False,
            error_code="TOOL_EXCEPTION",
        )

    _record_tool_evidence(action, observation, state)
    error_code = (
        str(observation["error"])
        if isinstance(observation, dict) and observation.get("error")
        else None
    )
    return ToolExecutionResult(
        observation=observation,
        executed=True,
        error_code=error_code,
    )


def _append_observation(transcript, observation):
    transcript.append(
        f"Observation: {serialize_observation(observation)}"
    )


def _agent_result(
    *,
    final_answer,
    trace,
    stop_reason,
    state,
    tool_calls,
):
    return AgentRunResult(
        final_answer=final_answer,
        trace=trace,
        stop_reason=stop_reason,
        state=state,
        tool_calls=tool_calls,
    )


def run_react_agent(
    user_query,
    provider,
    *,
    tools=None,
    tool_specs=None,
    confirmation_handler=None,
    max_iterations=None,
):
    """Run the guarded Thought -> Action -> Observation loop."""
    tools = AVAILABLE_TOOLS if tools is None else tools
    tool_specs = TOOL_SPECS if tool_specs is None else tool_specs
    iteration_limit = (
        REACT_MAX_ITERATIONS
        if max_iterations is None
        else max(1, int(max_iterations))
    )
    state = AgentState()
    trace = []
    tool_calls = []

    input_result = validate_input(user_query)
    if not input_result.allowed:
        observation = _error_observation(
            "INPUT_BLOCKED",
            "Yêu cầu bị chặn bởi lớp bảo vệ đầu vào.",
        )
        trace.append(AgentTraceStep(iteration=0, observation=observation))
        return _agent_result(
            final_answer=SAFE_FALLBACK_ANSWER,
            trace=trace,
            stop_reason="input_blocked",
            state=state,
            tool_calls=tool_calls,
        )

    transcript = [f"User: {input_result.sanitized_text}"]

    for iteration in range(1, iteration_limit + 1):
        prompt = "\n\n".join(transcript)
        try:
            model_output = provider.generate(
                prompt,
                system_prompt=REACT_RUNTIME_PROMPT,
            )
        except Exception:
            observation = _error_observation(
                "PROVIDER_ERROR",
                "Không thể kết nối LLM provider; chi tiết lỗi đã được ẩn.",
            )
            trace.append(
                AgentTraceStep(
                    iteration=iteration,
                    observation=observation,
                )
            )
            return _agent_result(
                final_answer=SAFE_FALLBACK_ANSWER,
                trace=trace,
                stop_reason="provider_error",
                state=state,
                tool_calls=tool_calls,
            )

        parsed = parse_agent_output(model_output)
        if parsed.kind == "error":
            observation = _error_observation(
                parsed.error_code or "INVALID_FORMAT",
                parsed.error_message or "Output của model không hợp lệ.",
            )
            trace.append(
                AgentTraceStep(
                    iteration=iteration,
                    observation=observation,
                )
            )
            _append_observation(transcript, observation)
            continue

        if parsed.kind == "final":
            guard_result = validate_output(
                parsed.raw_output,
                is_final_answer=True,
            )
            if guard_result.allowed:
                final_parsed = parse_agent_output(
                    guard_result.sanitized_text
                )
                final_answer = (
                    final_parsed.final_answer
                    if final_parsed.kind == "final"
                    else parsed.final_answer
                )
                trace.append(
                    AgentTraceStep(
                        iteration=iteration,
                        final_answer=final_answer,
                    )
                )
                return _agent_result(
                    final_answer=final_answer,
                    trace=trace,
                    stop_reason="completed",
                    state=state,
                    tool_calls=tool_calls,
                )

            observation = _error_observation(
                "OUTPUT_BLOCKED",
                "Câu trả lời cuối bị chặn bởi lớp bảo vệ đầu ra.",
            )
            trace.append(
                AgentTraceStep(
                    iteration=iteration,
                    observation=observation,
                )
            )
            _append_observation(transcript, observation)
            continue

        guard_result = validate_output(
            parsed.raw_output,
            is_final_answer=False,
        )
        if not guard_result.allowed:
            observation = _error_observation(
                "OUTPUT_BLOCKED",
                "Action bị chặn bởi lớp bảo vệ đầu ra.",
            )
            trace.append(
                AgentTraceStep(
                    iteration=iteration,
                    thought=parsed.action.thought,
                    observation=observation,
                )
            )
            _append_observation(transcript, observation)
            continue

        execution = execute_tool_action(
            parsed.action,
            state,
            tools=tools,
            tool_specs=tool_specs,
            confirmation_handler=confirmation_handler,
        )
        trace.append(
            AgentTraceStep(
                iteration=iteration,
                thought=parsed.action.thought,
                action=parsed.action,
                observation=execution.observation,
            )
        )
        tool_calls.append(
            {
                "tool_name": parsed.action.tool_name,
                "arguments": list(parsed.action.arguments),
                "executed": execution.executed,
                "observation": execution.observation,
            }
        )
        transcript.append(guard_result.sanitized_text)
        _append_observation(transcript, execution.observation)

        if execution.should_stop:
            reason = (
                execution.error_code.lower()
                if execution.error_code
                else "tool_stop"
            )
            return _agent_result(
                final_answer=SAFE_FALLBACK_ANSWER,
                trace=trace,
                stop_reason=reason,
                state=state,
                tool_calls=tool_calls,
            )

    return _agent_result(
        final_answer=SAFE_FALLBACK_ANSWER,
        trace=trace,
        stop_reason="max_iterations",
        state=state,
        tool_calls=tool_calls,
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
