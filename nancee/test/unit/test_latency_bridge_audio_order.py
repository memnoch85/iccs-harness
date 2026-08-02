from __future__ import annotations

import ast
import threading
import time
import unittest
from pathlib import Path

from sherpa.latency_bridge import LatencyBridge

ROOT = Path(__file__).resolve().parents[2]

CHAT_SOURCE = (
    ROOT / "sherpa/nancee_chat.py"
).read_text(
    encoding="utf-8",
)

CHAT_TREE = ast.parse(CHAT_SOURCE)


def find_function(
    root,
    name,
):
    for node in ast.walk(root):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == name
        ):
            return node

    raise AssertionError(
        f"Function {name!r} was not found."
    )


def is_enqueue_audio_call(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "enqueue_audio"
    )


def is_first_audio_callback_call(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "first_audio_callback"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "request"
    )


def is_callback_count_zero(node):
    return (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "callback_count"
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
        and isinstance(
            node.comparators[0],
            ast.Constant,
        )
        and node.comparators[0].value == 0
    )


def first_matching_call(
    root,
    predicate,
):
    calls = [
        node
        for node in ast.walk(root)
        if predicate(node)
    ]

    if not calls:
        raise AssertionError(
            "Expected call was not found."
        )

    return min(
        calls,
        key=lambda node: (
            node.lineno,
            node.col_offset,
        ),
    )


class LatencyBridgeSerializationTests(unittest.TestCase):
    def test_resolve_waits_for_in_progress_bridge_enqueue(self):
        callback_started = threading.Event()
        release_callback = threading.Event()
        resolve_finished = threading.Event()
        resolve_results = []

        def on_fire():
            callback_started.set()
            release_callback.wait(
                timeout=1.0,
            )

        bridge = LatencyBridge(
            delay_seconds=0.01,
            on_fire=on_fire,
        )

        bridge.start()

        self.assertTrue(
            callback_started.wait(
                timeout=0.25,
            )
        )

        def resolve_bridge():
            resolve_results.append(
                bridge.resolve()
            )
            resolve_finished.set()

        resolver = threading.Thread(
            target=resolve_bridge,
            daemon=True,
        )

        resolver.start()

        time.sleep(0.03)

        self.assertFalse(
            resolve_finished.is_set()
        )

        release_callback.set()

        self.assertTrue(
            resolve_finished.wait(
                timeout=0.25,
            )
        )

        resolver.join(
            timeout=0.25,
        )

        self.assertEqual(
            resolve_results,
            [True],
        )


class FirstAudioOrderingSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tts_worker = find_function(
            CHAT_TREE,
            "tts_worker",
        )

    def test_streaming_callback_resolves_before_enqueue(self):
        callback_function = None

        for node in ast.walk(
            self.tts_worker
        ):
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name == "callback"
            ):
                callback_function = node
                break

        self.assertIsNotNone(
            callback_function,
        )

        callback_call = first_matching_call(
            callback_function,
            is_first_audio_callback_call,
        )

        enqueue_call = first_matching_call(
            callback_function,
            is_enqueue_audio_call,
        )

        self.assertLess(
            callback_call.lineno,
            enqueue_call.lineno,
        )

    def test_fallback_resolves_before_enqueue(self):
        fallback_if = None

        for node in ast.walk(
            self.tts_worker
        ):
            if (
                isinstance(node, ast.If)
                and is_callback_count_zero(
                    node.test
                )
            ):
                fallback_if = node
                break

        self.assertIsNotNone(
            fallback_if,
        )

        callback_call = first_matching_call(
            fallback_if,
            is_first_audio_callback_call,
        )

        enqueue_call = first_matching_call(
            fallback_if,
            is_enqueue_audio_call,
        )

        self.assertLess(
            callback_call.lineno,
            enqueue_call.lineno,
        )


if __name__ == "__main__":
    unittest.main()
