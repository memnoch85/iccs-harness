import unittest
from dataclasses import dataclass

from authoritative_response import (
    prepare_authoritative_response,
    session_memory_response_is_grounded,
)


@dataclass(frozen=True)
class Hit:
    key: str
    value: str


MEMORY_CONTEXT = (
    "Confirmed user memory. In quotes, I/me/my means the human user; "
    "answer as you/your.\n"
    "- User said: \"I bought a blue backpack yesterday at Macy's.\""
)


class AuthoritativeResponseTests(unittest.TestCase):
    def test_correct_profile_answer_is_trimmed(self):
        answer, action = prepare_authoritative_response(
            "Your name is Anders. How can I help?",
            profile_hits=[Hit("name", "Anders")],
            fact_miss=False,
        )
        self.assertEqual("Your name is Anders.", answer)
        self.assertEqual("accepted", action)

    def test_wrong_profile_answer_is_replaced(self):
        answer, action = prepare_authoritative_response(
            "Your name is Nancee.",
            profile_hits=[Hit("name", "Anders")],
            fact_miss=False,
        )
        self.assertEqual("You're Anders.", answer)
        self.assertEqual("profile_fallback", action)

    def test_grounded_session_answer_is_accepted(self):
        answer, action = prepare_authoritative_response(
            "You bought a blue backpack.",
            profile_hits=[],
            fact_miss=False,
            retrieved_context=MEMORY_CONTEXT,
        )
        self.assertEqual("You bought a blue backpack.", answer)
        self.assertEqual("accepted", action)

    def test_purchase_paraphrase_is_grounded(self):
        self.assertTrue(
            session_memory_response_is_grounded(
                "You purchased it from Macy's.",
                MEMORY_CONTEXT,
            )
        )

    def test_off_topic_session_answer_is_blocked(self):
        answer, action = prepare_authoritative_response(
            "You went skiing in Denver.",
            profile_hits=[],
            fact_miss=False,
            retrieved_context=MEMORY_CONTEXT,
        )
        self.assertEqual(
            "I don't remember that clearly enough.",
            answer,
        )
        self.assertEqual("memory_grounding_fallback", action)

    def test_fact_miss_drops_guessed_second_sentence(self):
        answer, action = prepare_authoritative_response(
            "I don't remember that yet. Could it be Anna?",
            profile_hits=[],
            fact_miss=True,
        )
        self.assertEqual("I don't remember that yet.", answer)
        self.assertEqual("fact_miss_accepted", action)


if __name__ == "__main__":
    unittest.main()

