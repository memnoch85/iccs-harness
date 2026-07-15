from __future__ import annotations

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


class LatencyBridgeSerializationTests(unittest.TestCase):
    def test_resolve_waits_for_in_progress_bridge_enqueue(self):
        callback_started = threading.Event()
        release_callback = threading.Event()
        resolve_finished = threading.Event()
        resolve_results = []

        def on_fire():
            callback_started.set()
            release_callback.wait(timeout=1.0)

        bridge = LatencyBridge(
            delay_seconds=0.01,
            on_fire=on_fire,
        )

        bridge.start()

        self.assertTrue(
            callback_started.wait(timeout=0.25)
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
            resolve_finished.wait(timeout=0.25)
        )

        resolver.join(timeout=0.25)

        self.assertEqual(
            resolve_results,
            [True],
        )


class FirstAudioOrderingSourceTests(unittest.TestCase):
    def test_streaming_callback_resolves_before_enqueue(self):
        start_marker = (
            "if (\n"
            "                    first_audio_for_request\n"
            "                    and request.first_audio_callback "
            "is not None\n"
            "                ):"
        )

        start = CHAT_SOURCE.index(start_marker)
        end = CHAT_SOURCE.index(
            "                return 1",
            start,
        )

        block = CHAT_SOURCE[start:end]

        self.assertLess(
            block.index(
                "request.first_audio_callback()"
            ),
            block.index(
                "enqueue_audio("
            ),
        )

    def test_fallback_resolves_before_enqueue(self):
        start = CHAT_SOURCE.index(
            "# Some Sherpa configurations return complete audio"
        )

        end = CHAT_SOURCE.index(
            "            elapsed = time.time() - start",
            start,
        )

        block = CHAT_SOURCE[start:end]

        self.assertLess(
            block.index(
                "request.first_audio_callback()"
            ),
            block.index(
                "enqueue_audio("
            ),
        )


if __name__ == "__main__":
    unittest.main()
