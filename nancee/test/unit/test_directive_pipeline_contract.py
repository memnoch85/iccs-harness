from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT / "sherpa/nancee_chat.py"
).read_text(encoding="utf-8")


class DirectivePipelineContractTests(unittest.TestCase):
    def test_directive_repair_is_imported(self):
        self.assertIn(
            (
                "from directive_perspective import "
                "repair_directive_perspective"
            ),
            SOURCE,
        )

    def test_directive_is_buffered_before_clarify(self):
        directive_marker = (
            'elif response_policy.name == "directive":'
        )

        clarify_marker = (
            'elif response_policy.name == "clarify":'
        )

        self.assertIn(
            directive_marker,
            SOURCE,
        )

        self.assertLess(
            SOURCE.index(directive_marker),
            SOURCE.index(clarify_marker),
        )

    def test_directive_branch_repairs_before_tts(self):
        start = SOURCE.index(
            'elif response_policy.name == "directive":'
        )

        end = SOURCE.index(
            'elif response_policy.name == "clarify":',
            start,
        )

        block = SOURCE[start:end]

        self.assertIn(
            "collect_text_response(",
            block,
        )

        self.assertIn(
            "repair_directive_perspective(",
            block,
        )

        self.assertIn(
            "enqueue_complete_response(",
            block,
        )

        self.assertLess(
            block.index(
                "repair_directive_perspective("
            ),
            block.index(
                "enqueue_complete_response("
            ),
        )


if __name__ == "__main__":
    unittest.main()
