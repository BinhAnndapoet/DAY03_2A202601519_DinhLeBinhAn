import inspect
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardrails import validate_output
from prompts import REACT_SYSTEM_PROMPT
from tools import AVAILABLE_TOOLS, TOOL_SPECS

import app


CANONICAL_TOOL_NAMES = {
    "lookup_order",
    "lookup_orders_by_email",
    "check_return_eligibility",
    "check_inventory",
    "initiate_return_request",
    "initiate_exchange_request",
    "get_return_policy",
}


class ReactContractTests(unittest.TestCase):
    def test_registry_and_specs_use_the_same_canonical_names(self):
        self.assertEqual(CANONICAL_TOOL_NAMES, set(AVAILABLE_TOOLS))
        self.assertEqual(CANONICAL_TOOL_NAMES, set(TOOL_SPECS))

    def test_registered_tools_no_longer_contain_a_pass_statement(self):
        for tool_name, tool in AVAILABLE_TOOLS.items():
            source_lines = {
                line.strip()
                for line in inspect.getsource(tool).splitlines()
            }
            self.assertNotIn("pass", source_lines, tool_name)

    def test_read_only_tools_return_json_compatible_shapes(self):
        fixtures = [
            ("lookup_order", ("ORD-2001",), dict),
            (
                "lookup_orders_by_email",
                ("linh.pham@email.com",),
                list,
            ),
            (
                "check_return_eligibility",
                ("ORD-2001", "ORD-2001-A"),
                dict,
            ),
            (
                "check_inventory",
                ("Áo thun basic", "L", "Trắng"),
                dict,
            ),
            ("get_return_policy", (), dict),
        ]

        for tool_name, arguments, expected_type in fixtures:
            result = AVAILABLE_TOOLS[tool_name](*arguments)
            self.assertIsInstance(result, expected_type, tool_name)

    def test_react_prompt_uses_only_canonical_tool_names(self):
        for tool_name in CANONICAL_TOOL_NAMES:
            self.assertIn(tool_name, REACT_SYSTEM_PROMPT)

        self.assertNotIn("get_order_status", REACT_SYSTEM_PROMPT)
        self.assertNotIn("create_return_request", REACT_SYSTEM_PROMPT)

    def test_expected_tool_calls_use_canonical_names(self):
        config_path = PROJECT_ROOT / "config" / "test_cases.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))

        for case in data["test_cases"]:
            for expected_call in case.get("expected_tool_calls", []):
                tool_name = expected_call.split("(", 1)[0]
                self.assertIn(
                    tool_name,
                    CANONICAL_TOOL_NAMES,
                    f"{case['id']}: {expected_call}",
                )

    def test_intermediate_guardrail_accepts_current_action_contract(self):
        result = validate_output(
            (
                "Thought: Cần tra cứu đơn hàng.\n"
                "Action: lookup_order[ORD-2001]"
            ),
            is_final_answer=False,
        )

        self.assertTrue(result.allowed, result.summary())

    def test_final_guardrail_accepts_final_answer_prefix(self):
        result = validate_output(
            "Final Answer: Đơn hàng đã được giao.",
            is_final_answer=True,
        )

        self.assertTrue(result.allowed, result.summary())


class ReactParserTests(unittest.TestCase):
    def test_parses_current_unquoted_single_argument_contract(self):
        result = app.parse_agent_output(
            (
                "Thought: Cần tra cứu đơn hàng.\n"
                "Action: lookup_order[ORD-2001]"
            )
        )

        self.assertEqual("action", result.kind)
        self.assertEqual("Cần tra cứu đơn hàng.", result.action.thought)
        self.assertEqual("lookup_order", result.action.tool_name)
        self.assertEqual(["ORD-2001"], result.action.arguments)

    def test_also_parses_json_quoted_arguments(self):
        result = app.parse_agent_output(
            (
                "Thought: Cần tra cứu đơn hàng.\n"
                'Action: lookup_order["ORD-2001"]'
            )
        )

        self.assertEqual(["ORD-2001"], result.action.arguments)

    def test_parses_unicode_multi_argument_action(self):
        result = app.parse_agent_output(
            (
                "Thought: Cần kiểm tra tồn kho.\n"
                "Action: check_inventory[Áo thun basic, L, Trắng]"
            )
        )

        self.assertEqual(
            ["Áo thun basic", "L", "Trắng"],
            result.action.arguments,
        )

    def test_parses_empty_optional_arguments(self):
        result = app.parse_agent_output(
            (
                "Thought: Cần xem chính sách chung.\n"
                "Action: get_return_policy[]"
            )
        )

        self.assertEqual([], result.action.arguments)

    def test_parses_final_answer(self):
        result = app.parse_agent_output(
            "Final Answer: Đơn ORD-2001 đã được giao."
        )

        self.assertEqual("final", result.kind)
        self.assertEqual(
            "Đơn ORD-2001 đã được giao.",
            result.final_answer,
        )

    def test_reports_malformed_quoted_arguments(self):
        result = app.parse_agent_output(
            (
                "Thought: Cần tra cứu đơn.\n"
                'Action: lookup_order["ORD-2001]'
            )
        )

        self.assertEqual("error", result.kind)
        self.assertEqual("MALFORMED_ARGUMENTS", result.error_code)

    def test_rejects_mixed_action_and_final_answer(self):
        result = app.parse_agent_output(
            (
                "Thought: Cần tra cứu.\n"
                "Action: lookup_order[ORD-2001]\n"
                "Final Answer: Đơn đã giao."
            )
        )

        self.assertEqual("error", result.kind)
        self.assertEqual("MIXED_OUTPUT", result.error_code)

    def test_rejects_missing_public_thought(self):
        result = app.parse_agent_output(
            "Action: lookup_order[ORD-2001]"
        )

        self.assertEqual("error", result.kind)
        self.assertEqual("INVALID_FORMAT", result.error_code)


if __name__ == "__main__":
    unittest.main()
