import unittest

from speaker_state import (
    SpeakerState,
    extract_direct_speaker_name,
    extract_handoff_speaker_name,
    direct_speaker_identity_response,
    direct_speaker_return_response,
    looks_like_current_speaker_query,
)


class SpeakerExtractionV42Tests(unittest.TestCase):
    def test_direct_introduction_is_detected(self):
        self.assertEqual(
            "Daniel",
            extract_direct_speaker_name(
                "Hi, this is Daniel. I like to cross-country ski."
            ),
        )

    def test_relation_fact_is_not_self_identification(self):
        self.assertIsNone(
            extract_direct_speaker_name("My dad's name is Daniel.")
        )

    def test_age_statement_is_not_a_name(self):
        self.assertIsNone(
            extract_direct_speaker_name("I'm old as fuck.")
        )

    def test_handoff_name_is_detected(self):
        text = (
            "I'm gonna hand this headset over to my dad. "
            "His name is Daniel. He's gonna talk to you, okay?"
        )
        self.assertEqual("Daniel", extract_handoff_speaker_name(text))

    def test_current_speaker_queries_are_detected(self):
        for text in (
            "Do you recall who's talking to you right now?",
            "Who are you speaking with?",
            "Do you remember who you were talking to?",
            "Who am I?",
            "Do you recall who I am?",
            "Do you remember my name?",
            "What is my name?",
        ):
            with self.subTest(text=text):
                self.assertTrue(looks_like_current_speaker_query(text))


class SpeakerStateV42Tests(unittest.TestCase):
    def test_primary_speaker_adds_no_prompt_overhead(self):
        state = SpeakerState(primary_name="Anders")
        self.assertEqual("Anders", state.current_name)
        self.assertEqual("", state.prompt_context())

    def test_direct_introduction_updates_current_speaker(self):
        state = SpeakerState(primary_name="Anders")
        update = state.observe("Hi, this is Daniel.")
        self.assertEqual("identified", update.action)
        self.assertTrue(update.changed)
        self.assertEqual("Daniel", state.current_name)
        self.assertIn("ACTIVE SPEAKER: Daniel", state.prompt_context())

    def test_handoff_primes_the_next_speaker_before_activation(self):
        state = SpeakerState(primary_name="Anders")
        update = state.observe(
            "I'm handing this headset to my dad. His name is Daniel."
        )
        self.assertEqual("handoff_pending", update.action)
        self.assertEqual("Anders", state.current_name)
        self.assertEqual("Daniel", state.pending_name)
        self.assertIn("ACTIVE SPEAKER: Daniel", state.next_prompt_context())

        activated = state.begin_turn()
        self.assertEqual("handoff_activated", activated.action)
        self.assertEqual("Daniel", state.current_name)
        self.assertIsNone(state.pending_name)

    def test_primary_return_clears_temporary_context(self):
        for text in (
            "I'm back.",
            "Okay I'm back.",
            "All right, I'm back.",
            "So, I'm back.",
        ):
            with self.subTest(text=text):
                state = SpeakerState(primary_name="Anders")
                state.observe("This is Daniel.")
                update = state.observe(text)
                self.assertEqual("primary_returned", update.action)
                self.assertEqual("Anders", state.current_name)
                self.assertEqual("", state.prompt_context())

    def test_identity_response_is_only_the_current_name(self):
        self.assertEqual(
            "Daniel.",
            direct_speaker_identity_response("Daniel"),
        )
        self.assertEqual(
            "Anders.",
            direct_speaker_identity_response("Anders"),
        )

    def test_unknown_identity_response_is_brief(self):
        self.assertEqual(
            "I don't know.",
            direct_speaker_identity_response(None),
        )

    def test_return_response_is_name_neutral(self):
        self.assertEqual(
            "Welcome back.",
            direct_speaker_return_response(),
        )


if __name__ == "__main__":
    unittest.main()
