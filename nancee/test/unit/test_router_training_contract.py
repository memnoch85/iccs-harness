from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRAINING_CSV = ROOT / "router_training" / "training_data.csv"
TRAIN_SCRIPT = ROOT / "router_training" / "train_router_mon.py"

REQUIRED_INTENTS = {
    "affirmative",
    "clarify",
    "detailed",
    "directive",
    "farewell",
    "greeting",
    "memory_store",
    "model_recall",
    "negative",
    "normal",
    "question",
    "recall",
}


class RouterTrainingContractTests(unittest.TestCase):
    def _rows(self):
        with TRAINING_CSV.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_training_data_has_expected_intents_and_size(self):
        rows = self._rows()
        labels = {row["intent"] for row in rows}

        self.assertGreaterEqual(len(rows), 1308)
        self.assertEqual(REQUIRED_INTENTS, labels)


def test_model_owned_routing_examples_are_merged(self):
    examples = {
        (row["text"].strip().lower(), row["intent"].strip())
        for row in self.rows
    }

    required = {
        (
            "actually it was the power board not the usb controller",
            "memory_store",
        ),
        (
            "was it you or me who bought the backpack",
            "recall",
        ),
        (
            "hello explain exactly how the context cache works "
            "from beginning to end",
            "detailed",
        ),
        (
            "hello",
            "greeting",
        ),
    }

    self.assertTrue(required.issubset(examples))

    def test_training_data_does_not_bake_in_assistant_name(self):
        for row in self._rows():
            with self.subTest(text=row["text"]):
                self.assertIsNone(
                    re.search(
                        r"\b(?:nancee|nancy)\b",
                        row["text"],
                        flags=re.IGNORECASE,
                    )
                )

    def test_training_script_keeps_word_char_and_logistic_regression_shape(self):
        source = TRAIN_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('analyzer="word"', source)
        self.assertIn('analyzer="char_wb"', source)
        self.assertIn("LogisticRegression(", source)
        self.assertIn("FeatureUnion([", source)
        self.assertIn("StratifiedKFold(", source)


if __name__ == "__main__":
    unittest.main()
