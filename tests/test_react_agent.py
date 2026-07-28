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


if __name__ == "__main__":
    unittest.main()
