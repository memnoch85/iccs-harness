from __future__ import annotations

import re

import numpy as np


def router_mon_structural_features(texts):
    """
    Return numeric utterance-structure features for routerMon.

    These measurements are inputs to logistic regression.
    They do not directly choose a route.
    """
    rows = []

    for value in texts:
        text = str(value)
        lowered = text.lower()

        word_count = len(
            re.findall(r"\b[\w']+\b", text)
        )

        char_count = len(text)

        sentence_count = max(
            1,
            len(re.findall(r"[.!?]+", text)),
        )

        structure_points = (
            len(re.findall(r"[,;:]", text))
            + len(
                re.findall(
                    r"\b(?:and|but|because|so|while|then|"
                    r"although|though|however)\b",
                    lowered,
                )
            )
        )

        rows.append(
            [
                min(word_count, 80) / 40.0,
                min(char_count, 500) / 250.0,
                min(sentence_count, 10) / 5.0,
                min(structure_points, 16) / 8.0,
            ]
        )

    return np.asarray(rows, dtype=np.float64)
