import json
import unittest
from unittest.mock import patch

import ollama_runtime


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def __iter__(self):
        return iter(self._lines)


class OllamaBenchmarkMetricsV41Tests(unittest.TestCase):
    def test_completion_state_exposes_latency_metrics(self):
        state = {}
        lines = [
            json.dumps(
                {
                    "message": {"content": "Paris."},
                    "done": False,
                }
            ).encode("utf-8") + b"\n",
            json.dumps(
                {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "eval_count": 3,
                    "load_duration": 100000000,
                    "prompt_eval_duration": 200000000,
                    "eval_duration": 300000000,
                    "prompt_eval_count": 42,
                }
            ).encode("utf-8") + b"\n",
        ]

        with patch.object(
            ollama_runtime,
            "load_system_prompt",
            return_value="SYSTEM",
        ), patch.object(
            ollama_runtime.urllib.request,
            "urlopen",
            return_value=_FakeResponse(lines),
        ):
            tokens = list(
                ollama_runtime.stream_ollama_response(
                    "Capital?",
                    completion_state=state,
                )
            )

        self.assertEqual(["Paris."], tokens)
        self.assertIsNotNone(state["first_token_seconds"])
        self.assertIsNotNone(state["total_seconds"])
        self.assertAlmostEqual(0.1, state["load_seconds"])
        self.assertAlmostEqual(0.2, state["prompt_eval_seconds"])
        self.assertAlmostEqual(0.3, state["generation_seconds"])
        self.assertEqual(42, state["prompt_tokens"])
        self.assertEqual(3, state["response_tokens"])


if __name__ == "__main__":
    unittest.main()
