import json
import unittest
from unittest.mock import patch

import ollama_runtime
from warmup_contract import (
    CONTEXT_PRIME_EXPECTED_REPLY,
    CONTEXT_PRIME_NUM_PREDICT,
    CONTEXT_PRIME_TEMPERATURE,
    CONTEXT_PRIME_USER_TEXT,
)


class _FakeResponse:
    def __init__(self, lines=None, payload=None):
        self._lines = lines or []
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self, *_args, **_kwargs):
        if self._payload is None:
            return b""

        return json.dumps(self._payload).encode("utf-8")


class OllamaPrimeAndCompletionStateTests(unittest.TestCase):
    def test_prime_contract_remains_one_token_at_zero_temperature(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(
                request.data.decode("utf-8")
            )
            return _FakeResponse(
                payload={
                    "message": {"content": "k"},
                    "load_duration": 0,
                    "prompt_eval_count": 2,
                    "prompt_eval_duration": 0,
                    "eval_duration": 0,
                    "eval_count": 1,
                }
            )

        with patch.object(
            ollama_runtime,
            "load_system_prompt",
            return_value="SYSTEM",
        ), patch.object(
            ollama_runtime.urllib.request,
            "urlopen",
            side_effect=fake_urlopen,
        ):
            result = ollama_runtime.prime_ollama_context(
                history=[],
                memory_context="",
            )

        payload = captured["payload"]

        self.assertEqual(
            payload["options"]["temperature"],
            CONTEXT_PRIME_TEMPERATURE,
        )
        self.assertEqual(
            payload["options"]["num_predict"],
            CONTEXT_PRIME_NUM_PREDICT,
        )
        self.assertEqual(
            payload["messages"][-1]["content"],
            CONTEXT_PRIME_USER_TEXT,
        )

        self.assertEqual(
            result["prime_reply"],
            CONTEXT_PRIME_EXPECTED_REPLY,
        )

    def test_stream_records_done_reason_without_changing_tokens(self):
        state = {}

        lines = [
            json.dumps(
                {
                    "message": {
                        "content": "Hello."
                    },
                    "done": False,
                }
            ).encode("utf-8") + b"\n",
            json.dumps(
                {
                    "message": {
                        "content": ""
                    },
                    "done": True,
                    "done_reason": "length",
                    "eval_count": 48,
                    "load_duration": 0,
                    "prompt_eval_duration": 0,
                    "eval_duration": 0,
                    "prompt_eval_count": 10,
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
            return_value=_FakeResponse(lines=lines),
        ):
            tokens = list(
                ollama_runtime.stream_ollama_response(
                    "Test",
                    completion_state=state,
                )
            )

        self.assertEqual(tokens, ["Hello."])
        self.assertEqual(
            state["done_reason"],
            "length",
        )
        self.assertEqual(
            state["response_tokens"],
            48,
        )


if __name__ == "__main__":
    unittest.main()
