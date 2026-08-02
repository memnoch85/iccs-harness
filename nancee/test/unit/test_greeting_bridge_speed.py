import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CONFIG_SOURCE = (
    ROOT / "sherpa/config.py"
).read_text(encoding="utf-8")

CHAT_SOURCE = (
    ROOT / "sherpa/nancee_chat.py"
).read_text(encoding="utf-8")


class GreetingBridgeSpeedTests(unittest.TestCase):
    def test_dedicated_greeting_speed_exists(self):
        self.assertIn(
            "TTS_GREETING_BRIDGE_SPEED = float(",
            CONFIG_SOURCE,
        )

        self.assertIn(
            '"NANCEE_TTS_GREETING_BRIDGE_SPEED"',
            CONFIG_SOURCE,
        )

    def test_default_greeting_speed_is_one_point_one(self):
        config_block = CONFIG_SOURCE.split(
            "TTS_GREETING_BRIDGE_SPEED = float(",
            1,
        )[1].split(
            "TTS_FILLER_SPEED = float(",
            1,
        )[0]

        self.assertIn(
            '"1.1"',
            config_block,
        )

    def test_greeting_bank_uses_dedicated_speed(self):
        self.assertEqual(
            CHAT_SOURCE.count(
                "speed=TTS_GREETING_BRIDGE_SPEED,"
            ),
            1,
        )

    def test_normal_bridge_default_is_unchanged(self):
        self.assertIn(
            "speed=TTS_FILLER_SPEED,",
            CHAT_SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
