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


class ReactExecutorTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def lookup_order(order_id):
            self.calls.append(("lookup_order", order_id))
            return {
                "status": "delivered",
                "items": [
                    {
                        "item_id": "ORD-2001-A",
                        "name": "Áo thun basic",
                        "color": "Trắng",
                    }
                ],
            }

        def check_return_eligibility(order_id, item_id):
            self.calls.append(
                ("check_return_eligibility", order_id, item_id)
            )
            return {
                "eligible": True,
                "refund_method": "original_payment",
            }

        def check_inventory(product, size, color):
            self.calls.append(
                ("check_inventory", product, size, color)
            )
            return {"stock": 12}

        def initiate_return_request(
            order_id,
            item_id,
            reason,
            refund_method,
        ):
            self.calls.append(
                (
                    "initiate_return_request",
                    order_id,
                    item_id,
                    reason,
                    refund_method,
                )
            )
            return {"ticket_id": "RET-001", "status": "created"}

        def initiate_exchange_request(
            order_id,
            item_id,
            new_size,
            new_color,
        ):
            self.calls.append(
                (
                    "initiate_exchange_request",
                    order_id,
                    item_id,
                    new_size,
                    new_color,
                )
            )
            return {"ticket_id": "EXC-001", "status": "created"}

        self.tools = {
            "lookup_order": lookup_order,
            "check_return_eligibility": check_return_eligibility,
            "check_inventory": check_inventory,
            "initiate_return_request": initiate_return_request,
            "initiate_exchange_request": initiate_exchange_request,
        }
        self.specs = {
            "lookup_order": {
                "required_args": ["order_id"],
                "read_only": True,
            },
            "check_return_eligibility": {
                "required_args": ["order_id", "item_id"],
                "read_only": True,
            },
            "check_inventory": {
                "required_args": ["product", "size", "color"],
                "read_only": True,
            },
            "initiate_return_request": {
                "required_args": [
                    "order_id",
                    "item_id",
                    "reason",
                    "refund_method",
                ],
                "read_only": False,
                "requires_confirmation": True,
            },
            "initiate_exchange_request": {
                "required_args": [
                    "order_id",
                    "item_id",
                    "new_size",
                    "new_color",
                ],
                "read_only": False,
                "requires_confirmation": True,
            },
        }

    def action(self, tool_name, arguments):
        return app.AgentAction(
            thought="Quyết định kiểm thử.",
            tool_name=tool_name,
            arguments=arguments,
            raw_output="test",
        )

    def test_dispatches_read_only_tool_and_records_order_evidence(self):
        state = app.AgentState()

        result = app.execute_tool_action(
            self.action("lookup_order", ["ORD-2001"]),
            state,
            tools=self.tools,
            tool_specs=self.specs,
        )

        self.assertTrue(result.executed)
        self.assertEqual("delivered", result.observation["status"])
        self.assertIn("ORD-2001", state.orders)

    def test_unknown_tool_becomes_recoverable_observation(self):
        result = app.execute_tool_action(
            self.action("delete_order", ["ORD-2001"]),
            app.AgentState(),
            tools=self.tools,
            tool_specs=self.specs,
        )

        self.assertFalse(result.executed)
        self.assertEqual("UNKNOWN_TOOL", result.error_code)
        self.assertFalse(result.should_stop)

    def test_invalid_argument_count_does_not_call_tool(self):
        result = app.execute_tool_action(
            self.action("lookup_order", []),
            app.AgentState(),
            tools=self.tools,
            tool_specs=self.specs,
        )

        self.assertFalse(result.executed)
        self.assertEqual("INVALID_ARGUMENTS", result.error_code)
        self.assertEqual([], self.calls)

    def test_unexpected_tool_exception_is_sanitized(self):
        def exploding_tool(order_id):
            raise RuntimeError("database password must not leak")

        result = app.execute_tool_action(
            self.action("lookup_order", ["ORD-2001"]),
            app.AgentState(),
            tools={"lookup_order": exploding_tool},
            tool_specs={
                "lookup_order": {
                    "required_args": ["order_id"],
                    "read_only": True,
                }
            },
        )

        self.assertEqual("TOOL_EXCEPTION", result.error_code)
        self.assertNotIn(
            "database password",
            app.serialize_observation(result.observation),
        )

    def test_repeated_action_is_not_executed_twice(self):
        state = app.AgentState()
        action = self.action("lookup_order", ["ORD-2001"])

        first = app.execute_tool_action(
            action,
            state,
            tools=self.tools,
            tool_specs=self.specs,
        )
        second = app.execute_tool_action(
            action,
            state,
            tools=self.tools,
            tool_specs=self.specs,
        )
        third = app.execute_tool_action(
            action,
            state,
            tools=self.tools,
            tool_specs=self.specs,
        )

        self.assertTrue(first.executed)
        self.assertFalse(second.executed)
        self.assertEqual("REPEATED_ACTION", second.error_code)
        self.assertFalse(second.should_stop)
        self.assertTrue(third.should_stop)
        self.assertEqual(1, len(self.calls))

    def test_return_requires_confirmation(self):
        state = app.AgentState()
        state.eligibility[("ORD-2001", "ORD-2001-A")] = {
            "eligible": True,
            "refund_method": "original_payment",
        }

        result = app.execute_tool_action(
            self.action(
                "initiate_return_request",
                [
                    "ORD-2001",
                    "ORD-2001-A",
                    "không hợp",
                    "original_payment",
                ],
            ),
            state,
            tools=self.tools,
            tool_specs=self.specs,
            confirmation_handler=lambda current_action: False,
        )

        self.assertEqual("CONFIRMATION_DENIED", result.error_code)
        self.assertTrue(result.should_stop)
        self.assertEqual([], self.calls)

    def test_return_rejects_refund_method_not_supported_by_evidence(self):
        state = app.AgentState()
        state.eligibility[("ORD-2001", "ORD-2001-A")] = {
            "eligible": True,
            "refund_method": "store_credit",
        }

        result = app.execute_tool_action(
            self.action(
                "initiate_return_request",
                [
                    "ORD-2001",
                    "ORD-2001-A",
                    "không hợp",
                    "original_payment",
                ],
            ),
            state,
            tools=self.tools,
            tool_specs=self.specs,
            confirmation_handler=lambda current_action: True,
        )

        self.assertEqual("PRECONDITION_FAILED", result.error_code)
        self.assertEqual([], self.calls)

    def test_exchange_requires_positive_stock_for_exact_variant(self):
        state = self._exchange_ready_state(stock=0)

        result = app.execute_tool_action(
            self.action(
                "initiate_exchange_request",
                ["ORD-2001", "ORD-2001-A", "L", "Trắng"],
            ),
            state,
            tools=self.tools,
            tool_specs=self.specs,
            confirmation_handler=lambda current_action: True,
        )

        self.assertEqual("PRECONDITION_FAILED", result.error_code)
        self.assertEqual([], self.calls)

    def test_exchange_executes_once_when_all_evidence_is_present(self):
        state = self._exchange_ready_state(stock=12)

        result = app.execute_tool_action(
            self.action(
                "initiate_exchange_request",
                ["ORD-2001", "ORD-2001-A", "L", "Trắng"],
            ),
            state,
            tools=self.tools,
            tool_specs=self.specs,
            confirmation_handler=lambda current_action: True,
        )

        self.assertTrue(result.executed)
        self.assertEqual("EXC-001", result.observation["ticket_id"])
        self.assertEqual(
            [
                (
                    "initiate_exchange_request",
                    "ORD-2001",
                    "ORD-2001-A",
                    "L",
                    "Trắng",
                )
            ],
            self.calls,
        )

    def _exchange_ready_state(self, stock):
        state = app.AgentState()
        state.orders["ORD-2001"] = {
            "items": [
                {
                    "item_id": "ORD-2001-A",
                    "name": "Áo thun basic",
                    "color": "Trắng",
                }
            ]
        }
        state.eligibility[("ORD-2001", "ORD-2001-A")] = {
            "eligible": True,
            "refund_method": "original_payment",
        }
        state.inventory[("Áo thun basic", "L", "Trắng")] = {
            "stock": stock
        }
        return state


if __name__ == "__main__":
    unittest.main()
