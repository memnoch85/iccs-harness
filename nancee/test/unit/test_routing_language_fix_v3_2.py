from __future__ import annotations

import unittest
from unittest.mock import patch

from directive_perspective import repair_directive_perspective
from input_router import route_user_input
from router_mon import RouterMonResult


class RoutingLanguageFixV32Tests(unittest.TestCase):
    def test_explicit_remember_command_stores_statement(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("memory_store", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "Remember that I bought a blue ceramic mug yesterday."
            )

        self.assertEqual("memory_store", route.kind)
        self.assertTrue(route.reason.startswith("routerMon:memory_store:"))
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I bought a blue ceramic mug yesterday.",
            route.recall_storage_text,
        )

    def test_remember_this_command_strips_command_text(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("memory_store", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "Remember this: I keep the spare fuse in the glove box."
            )

        self.assertEqual("memory_store", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I keep the spare fuse in the glove box.",
            route.recall_storage_text,
        )

    def test_dont_forget_command_stores_statement(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("memory_store", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "Don't forget that I parked beside the west elevator."
            )

        self.assertEqual("memory_store", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I parked beside the west elevator.",
            route.recall_storage_text,
        )

    def test_rich_finch_update_remains_detailed(self):
        text = (
            "My name is Anders and Finch is one of my favorite bands. "
            "They are from Temecula, California. "
            "They are a post-hardcore punk-screamo-emo type of scene. "
            "Not a lot of people listen to them anymore, "
            "but I'm still a big fan."
        )

        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult(
                "detailed",
                0.9,
                "routerMon",
            ),
        ):
            route = route_user_input(text)

        self.assertEqual("detailed", route.kind)
        self.assertTrue(route.store_recall)

    def test_immediate_ask_me_preserves_or(self):
        repaired, changed = repair_directive_perspective(
            (
                "Ask me if I finished wiring the power board "
                "or checked the fuses."
            ),
            (
                "Have you wired the power board "
                "and checked the fuses yet?"
            ),
        )

        self.assertTrue(changed)
        self.assertEqual(
            (
                "Have you wired the power board "
                "or checked the fuses yet?"
            ),
            repaired,
        )

    def test_future_ask_me_does_not_claim_scheduling(self):
        repaired, changed = repair_directive_perspective(
            (
                "Ask me tomorrow whether I've finished wiring "
                "the power board and checked the fuses."
            ),
            "Will you tell me if it's done?",
        )

        self.assertTrue(changed)
        self.assertEqual(
            (
                "I can't schedule that yet, but you asked me to check "
                "tomorrow whether you've finished wiring the power board "
                "and checked the fuses."
            ),
            repaired,
        )


if __name__ == "__main__":
    unittest.main()
