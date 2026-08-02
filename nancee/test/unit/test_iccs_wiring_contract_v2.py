from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "sherpa" / "nancee_chat.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def main_function():
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node

    raise AssertionError("main() was not found")


def calls_named(root, name):
    return [
        node
        for node in ast.walk(root)
        if (
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == name)
                or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            )
        )
    ]


class IccsWiringContractTests(unittest.TestCase):
    def test_chat_imports_factory_not_raw_prime_or_request(self):
        self.assertIn("create_ollama_iccs", SOURCE)
        self.assertNotIn("prime_ollama_context", SOURCE)
        self.assertNotIn("stream_ollama_response", SOURCE)

    def test_startup_uses_synchronous_gateway_prime(self):
        self.assertIn("iccs = create_ollama_iccs()", SOURCE)
        self.assertIn("iccs.prime_startup(", SOURCE)
        self.assertIn('reason="startup"', SOURCE)

    def test_real_request_uses_gateway_and_runtime_prefix_contract(self):
        main = main_function()
        gateway_calls = calls_named(main, "respond")

        self.assertEqual(1, len(gateway_calls))
        call_source = ast.get_source_segment(SOURCE, gateway_calls[0])
        self.assertIn("require_exact_prefix=require_exact_iccs_prefix", call_source)
        self.assertIn("history=request_history", call_source)
        self.assertIn("memory_context=""", call_source)

    def test_completed_turn_prime_occurs_after_history_update_before_audio_drain(self):
        main = main_function()
        add_turn = max(calls_named(main, "add_turn"), key=lambda node: node.lineno)
        prime_calls = calls_named(main, "prime_next")
        completed = [
            node
            for node in prime_calls
            if 'reason="completed_turn"' in ast.get_source_segment(SOURCE, node)
        ]
        drains = calls_named(main, "wait_for_audio_to_drain")

        self.assertEqual(1, len(completed))
        completed_prime = completed[0]
        later_drain = min(
            node for node in drains if node.lineno > completed_prime.lineno
        )

        self.assertLess(add_turn.lineno, completed_prime.lineno)
        self.assertLess(completed_prime.lineno, later_drain.lineno)

    def test_error_and_empty_response_paths_schedule_recovery(self):
        self.assertIn('reason="request_recovery"', SOURCE)
        self.assertIn('reason="empty_response_recovery"', SOURCE)

    def test_shutdown_is_protected_by_finally(self):
        main = main_function()
        finally_nodes = [node for node in ast.walk(main) if isinstance(node, ast.Try) and node.finalbody]
        shutdown_calls = calls_named(main, "close")

        self.assertTrue(finally_nodes)
        self.assertTrue(shutdown_calls)
        self.assertTrue(
            any(
                any(
                    shutdown.lineno >= statement.lineno
                    and shutdown.lineno <= getattr(statement, "end_lineno", statement.lineno)
                    for statement in try_node.finalbody
                )
                for try_node in finally_nodes
                for shutdown in shutdown_calls
            )
        )


if __name__ == "__main__":
    unittest.main()
