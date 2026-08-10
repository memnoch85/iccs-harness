from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer


ROOT = Path(__file__).resolve().parent
TRAINING_CSV = ROOT / "training_data.csv"
MODEL_FILE = ROOT / "routerMon.joblib"
CONFUSION_FILE = ROOT / "routerMon_confusion_matrix.csv"

RANDOM_STATE = 42

SHERPA_ROOT = ROOT.parent / "sherpa"

if str(SHERPA_ROOT) not in sys.path:
    sys.path.insert(0, str(SHERPA_ROOT))

from router_features import router_mon_structural_features

OVERSHARE_RULES = {
    "min_words": 30,
    "min_chars": 170,
    "min_structure_points": 3,
}


def load_rows() -> tuple[list[str], list[str]]:
    texts: list[str] = []
    intents: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_text: dict[str, str] = {}

    with TRAINING_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames != ["text", "intent"]:
            raise SystemExit(
                "training_data.csv must contain exactly: text,intent"
            )

        for line_number, row in enumerate(reader, start=2):
            text = str(row.get("text", "")).strip()
            intent = str(row.get("intent", "")).strip()

            if not text or not intent:
                raise SystemExit(
                    f"blank text/intent at CSV line {line_number}"
                )

            pair = (text, intent)

            if pair in seen_pairs:
                raise SystemExit(
                    f"duplicate text/intent pair at CSV line {line_number}: {pair}"
                )

            prior_intent = seen_text.get(text)

            if prior_intent is not None and prior_intent != intent:
                raise SystemExit(
                    "same text appears under multiple intents: "
                    f"{text!r} -> {prior_intent!r}, {intent!r}"
                )

            seen_pairs.add(pair)
            seen_text[text] = intent
            texts.append(text)
            intents.append(intent)

    return texts, intents


def build_pipeline() -> Pipeline:
    features = FeatureUnion([
        (
            "word_tfidf",
            TfidfVectorizer(
                lowercase=True,
                analyzer="word",
                ngram_range=(1, 2),
                min_df=1,
                sublinear_tf=True,
                max_features=8000,
            ),
        ),
        (
            "char_tfidf",
            TfidfVectorizer(
                lowercase=True,
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=1,
                sublinear_tf=True,
                max_features=12000,
            ),
        ),
        (
            "structure",
            FunctionTransformer(
                router_mon_structural_features,
                validate=False,
            ),
        ),
    ])

    classifier = LogisticRegression(
        solver="lbfgs",
        max_iter=2000,
        C=1.0,
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )

    return Pipeline([
        ("features", features),
        ("classifier", classifier),
    ])


def write_confusion_matrix(
    labels: list[str],
    matrix,
) -> None:
    with CONFUSION_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual\\predicted", *labels])

        for label, row in zip(labels, matrix):
            writer.writerow([label, *[int(value) for value in row]])


def main() -> None:
    if not TRAINING_CSV.is_file():
        raise SystemExit(f"missing training data: {TRAINING_CSV}")

    texts, intents = load_rows()
    labels = sorted(set(intents))

    print("routerMon training")
    print("==================")
    print(f"scikit-learn: {sklearn.__version__}")
    print(f"examples:      {len(texts)}")
    print(f"intents:       {len(labels)}")
    print()

    pipeline = build_pipeline()
    cv = StratifiedKFold(
        n_splits=5,
        shuffle=True,
        random_state=RANDOM_STATE,
    )

    print("Running 5-fold stratified cross-validation...")
    started = time.perf_counter()
    predictions = cross_val_predict(
        pipeline,
        texts,
        intents,
        cv=cv,
        method="predict",
    )
    elapsed = time.perf_counter() - started
    accuracy = accuracy_score(intents, predictions)

    print(f"Cross-validation finished in {elapsed:.3f}s")
    print(f"Cross-validated accuracy: {accuracy:.2%}")
    print()
    print(
        classification_report(
            intents,
            predictions,
            digits=3,
            zero_division=0,
        )
    )

    matrix = confusion_matrix(
        intents,
        predictions,
        labels=labels,
    )
    write_confusion_matrix(labels, matrix)
    print(f"Confusion matrix: {CONFUSION_FILE}")

    print("Training final model on all examples...")
    pipeline.fit(texts, intents)

    artifact = {
        "name": "routerMon",
        "artifact_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scikit_learn_version": sklearn.__version__,
        "training_examples": len(texts),
        "classes": labels,
        "cross_validated_accuracy": float(accuracy),
        "overshare_rules": OVERSHARE_RULES,
        "pipeline": pipeline,
    }

    joblib.dump(artifact, MODEL_FILE)
    print(f"Model: {MODEL_FILE}")
    print()
    print("Copy the tested artifact into the runtime only after validation:")
    print(f"  cp {MODEL_FILE.name} ../sherpa/routerMon.joblib")


if __name__ == "__main__":
    main()
