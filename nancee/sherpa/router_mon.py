from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MODEL_PATH = Path(__file__).with_name("routerMon.joblib")
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

@dataclass(frozen=True)
class RouterMonResult:
    intent: str
    confidence: float
    source: str


_artifact: dict[str, Any] | None = None
_pipeline: Any | None = None
_model_path: Path | None = None


def _configured_model_path() -> Path:
    configured = os.getenv("NANCEE_ROUTERMON_MODEL", "").strip()

    if configured:
        return Path(configured).expanduser().resolve()

    return DEFAULT_MODEL_PATH


def _pipeline_classes(pipeline: Any) -> set[str]:
    classifier = getattr(pipeline, "named_steps", {}).get("classifier")
    classes = getattr(classifier, "classes_", None)

    if classes is None:
        classes = getattr(pipeline, "classes_", None)

    if classes is None:
        return set()

    return {str(value) for value in classes}


def load_router_mon(model_path: str | Path | None = None) -> None:
    """Load and validate routerMon once.

    nancee_chat calls this only after the exact ICCS startup prime completes.
    Importing the router therefore does not deserialize the classifier or load
    scikit-learn during the ICCS warmup path.
    """
    global _artifact
    global _pipeline
    global _model_path

    requested_path = (
        Path(model_path).expanduser().resolve()
        if model_path is not None
        else _configured_model_path()
    )

    if _pipeline is not None:
        if _model_path != requested_path:
            raise RuntimeError(
                "routerMon is already loaded from a different path: "
                f"{_model_path}"
            )
        return

    if not requested_path.is_file():
        raise RuntimeError(
            "routerMon model is missing: "
            f"{requested_path}. Copy the trusted routerMon.joblib file "
            "to nancee/sherpa before starting Nancee."
        )

    try:
        import joblib
        import sklearn
    except ImportError as exc:
        raise RuntimeError(
            "routerMon requires joblib and scikit-learn in the Nancee "
            "runtime virtual environment."
        ) from exc

    try:
        loaded = joblib.load(requested_path)
    except Exception as exc:
        raise RuntimeError(
            f"Unable to load routerMon model {requested_path}: {exc}"
        ) from exc

    if isinstance(loaded, dict):
        artifact = loaded
        pipeline = artifact.get("pipeline")
    else:
        artifact = {}
        pipeline = loaded

    if pipeline is None or not hasattr(pipeline, "predict_proba"):
        raise RuntimeError(
            "routerMon.joblib does not contain a classifier with predict_proba()."
        )

    trained_version = str(artifact.get("scikit_learn_version", "")).strip()

    if trained_version and trained_version != sklearn.__version__:
        raise RuntimeError(
            "routerMon scikit-learn version mismatch: "
            f"trained={trained_version} runtime={sklearn.__version__}. "
            "Use the same scikit-learn version used to train the artifact."
        )

    classes = _pipeline_classes(pipeline)
    missing = sorted(REQUIRED_INTENTS - classes)

    if missing:
        raise RuntimeError(
            "routerMon.joblib is missing required intents: "
            + ", ".join(missing)
        )

    _artifact = artifact
    _pipeline = pipeline
    _model_path = requested_path

    print(
        "[ROUTERMON] "
        f"loaded=true path={requested_path} "
        f"classes={len(classes)} "
        f"sklearn={sklearn.__version__}",
        flush=True,
    )

def classify_router_mon(text: str) -> RouterMonResult:
    """Return one intent from the preloaded local routerMon classifier."""
    if _pipeline is None:
        load_router_mon()

    pipeline = _pipeline

    if pipeline is None:
        raise RuntimeError("routerMon failed to initialize.")

    probabilities = pipeline.predict_proba([str(text)])[0]
    classifier = getattr(pipeline, "named_steps", {}).get("classifier")
    classes = getattr(classifier, "classes_", None)

    if classes is None:
        classes = getattr(pipeline, "classes_", None)

    if classes is None:
        raise RuntimeError("routerMon classifier does not expose classes_.")

    best_index = int(probabilities.argmax())

    return RouterMonResult(
        intent=str(classes[best_index]),
        confidence=float(probabilities[best_index]),
        source="routerMon",
    )
