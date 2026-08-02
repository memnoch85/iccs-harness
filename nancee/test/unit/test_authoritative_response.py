import unittest

from authoritative_response import (
    prepare_authoritative_response,
    session_memory_response_is_grounded,
)




MEMORY_CONTEXT = (
    "Confirmed user memory. In quotes, I/me/my means the human user; "
    "answer as you/your.\n"
    "- User said: \"I bought a blue backpack yesterday at Macy's.\""
)


class AuthoritativeResponseTests(unittest.TestCase):


    def test_grounded_session_answer_is_accepted(self):
        answer, action = prepare_authoritative_response(
            "You bought a blue backpack.",
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
            fact_miss=True,
        )
        self.assertEqual("I don't remember that yet.", answer)
        self.assertEqual("fact_miss_accepted", action)


if __name__ == "__main__":
    unittest.main()

