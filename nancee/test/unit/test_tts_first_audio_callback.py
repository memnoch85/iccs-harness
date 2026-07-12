import unittest

from sherpa.tts_request import build_tts_request


class TtsFirstAudioCallbackTests(unittest.TestCase):
    def test_build_request_preserves_first_audio_callback(self):
        calls = []

        def callback():
            calls.append("called")

        request = build_tts_request(
            text="Hello.",
            normal_speed=1.3,
            emphasis_speed=0.8,
            first_audio_callback=callback,
        )

        self.assertIsNotNone(request)
        self.assertIs(request.first_audio_callback, callback)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
