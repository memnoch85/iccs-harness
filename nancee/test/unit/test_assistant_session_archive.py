from __future__ import annotations

import unittest

from assistant_session_archive import AssistantSessionArchive


class AssistantSessionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.archive = AssistantSessionArchive(max_turns=8)

    def tearDown(self):
        self.archive.close()

    def test_topic_recall_returns_stored_assistant_response(self):
        archive = self.archive
        expected = (
            "It reuses an identical prompt prefix to reduce prompt work."
        )
        archive.add_response(
            user_text="What is automatic prefix caching?",
            assistant_text=expected,
        )

        answer = archive.retrieve_response(
            "What did you say about prefix caching?"
        )

        self.assertEqual(expected, answer)

    def test_source_question_is_searchable_even_if_answer_uses_pronoun(self):
        archive = self.archive
        expected = "It turns weighted text features into class probabilities."
        archive.add_response(
            user_text="How does logistic regression classify TF-IDF text?",
            assistant_text=expected,
        )

        answer = archive.retrieve_response(
            "What did you say about logistic regression?"
        )

        self.assertEqual(expected, answer)

    def test_topic_free_model_recall_uses_latest_stored_response(self):
        archive = self.archive
        archive.add_response(
            user_text="What is caching?",
            assistant_text="First useful answer about caching.",
        )
        archive.add_response(
            user_text="What is routing?",
            assistant_text="Second useful answer about routing.",
        )

        answer = archive.retrieve_response("What did you say earlier?")

        self.assertEqual("Second useful answer about routing.", answer)

    def test_unmatched_topic_does_not_fall_back_to_unrelated_latest(self):
        archive = self.archive
        archive.add_response(
            user_text="What is caching?",
            assistant_text="A useful answer about caching.",
        )

        answer = archive.retrieve_response(
            "What did you say about penguins?"
        )

        self.assertEqual("", answer)


if __name__ == "__main__":
    unittest.main()
