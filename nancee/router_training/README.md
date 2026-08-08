# routerMon training

`routerMon` is the voice harness's small local intent classifier. It does not generate text and it does not call Ollama. The runtime keeps a few deterministic fast paths where an exact rule is cheaper and more certain, then sends the remaining utterances to this classifier.

The checked-in `training_data.csv` is the directly editable training source. It currently contains 1,308 examples across the 12 intent labels used by the runtime:

- `affirmative`
- `clarify`
- `detailed`
- `directive`
- `farewell`
- `greeting`
- `memory_store`
- `model_recall`
- `negative`
- `normal`
- `question`
- `recall`

Assistant names are intentionally not part of the training contract. A user may name the assistant whatever they want; intent should come from the request, not from one hard-coded wake/name token.

## Model shape

`train_router_mon.py` builds one scikit-learn `Pipeline` containing:

1. a `FeatureUnion` of word TF-IDF features (1-2 word n-grams) and `char_wb` TF-IDF features (3-5 character n-grams), and
2. `LogisticRegression` over the resulting sparse feature matrix.

The character features help with speech-recognition/spelling variation. The word features carry phrase meaning such as `what did I say` versus `what did you say`.

The trained artifact is a small dictionary containing metadata plus the fitted pipeline. Runtime inference calls `predict_proba()` once and uses the highest-probability class.

## Retrain

Use a desktop or other development machine:

```bash
cd nancee/router_training
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "scikit-learn==1.9.0" joblib
python train_router_mon.py
```

The script runs 5-fold stratified cross-validation, writes `routerMon_confusion_matrix.csv`, then trains on the complete dataset and writes `routerMon.joblib`.

Do not optimize only for the cross-validation percentage. Keep a separate set of real Whisper transcripts that never appears in `training_data.csv`. Misrouted real speech is the most valuable new training data.

## Deploy to the Pi

The runtime deliberately does not train. Copy only a tested `routerMon.joblib` into:

```text
nancee/sherpa/routerMon.joblib
```

The runtime loader checks the scikit-learn version recorded in the artifact and refuses a different runtime version. This is intentional: scikit-learn documents pickle/joblib-style persisted estimators as version-sensitive and warns against loading untrusted artifacts.

Only load a `joblib` artifact you trust.

## Runtime routing boundary

Deterministic code remains responsible for things that are cheaper or require state/payload extraction:

- invalid input and exact exit commands
- `hello`/`hi` with zero to two following words
- obvious exact affirmative/negative/farewell phrases
- explicit `remember/save/store...` commands so the memory payload can be extracted
- direct memory correction and perspective correction
- yes/no answers to the assistant's immediately previous question
- the structural overshare rule for `detailed`

Everything else is classified by `routerMon`.

The short `hello`/`hi` fast route deliberately disables the latency bridge and lets the normal greeting response arrive by itself.

The router never adds its intent, confidence, reasoning, or classifier metadata to the LLM prompt.

## User recall versus model recall

The two memory directions are intentionally separate:

```text
What did I say about X?
    -> recall
    -> user-memory FTS5
```

```text
What did you say about X?
    -> model_recall
    -> assistant-memory FTS5
```

Assistant memory stores responses only when the selected route is `question` or `detailed`. Its search index contains both the original user request and the generated assistant answer, but only the original assistant answer is replayed.

`model_recall` does not inject assistant memory into the prompt and does not call Ollama. It retrieves the already-generated answer from the separate FTS5 archive and speaks it directly. The completed user/assistant pair is then handled by the existing rolling-history and ICCS completed-turn prime just like any other completed turn.

## ICCS boundary

Do not train or load routerMon inside ICCS. The live application calls `load_router_mon()` only after the exact ICCS startup prime has completed.

This routing patch does not change:

- the system prompt
- the ICCS warmup messages
- `memory_context`
- the stable prefix contract
- prefix identity/fingerprinting
- startup prime behavior
- completed-turn `prime_next()` behavior

Existing user-memory enrichment still uses the existing `retrieved_context` path. No classifier output or model-memory overlay is added to it.

## Official scikit-learn references

- Text classification using TF-IDF/sparse features: https://scikit-learn.org/stable/auto_examples/text/plot_document_classification_20newsgroups.html
- Text feature extraction pipeline example: https://scikit-learn.org/stable/auto_examples/model_selection/plot_grid_search_text_feature_extraction.html
- `TfidfVectorizer`: https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html
- `LogisticRegression`: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html
- Model persistence / joblib cautions: https://scikit-learn.org/stable/model_persistence.html

## `ask me ...` follow-up memory

An `ask me ...` request is still classified as `directive`; it is not a new intent.
The router extracts the topic only after routerMon has selected `directive` and
keeps it as one-turn runtime state. If the next user turn is a short `normal`
answer that would otherwise be too small to store by itself, the harness stores
a self-contained user-memory sentence using the existing FTS5 archive.

Example:

```text
User:      Ask me what I bought at the store yesterday.
Assistant: What did you buy at the store yesterday?
User:      A watch.
```

The short answer remains `normal`, but the existing user-memory store receives a
self-contained fact similar to:

```text
When asked what I bought at the store yesterday, I answered: A watch.
```

This state is bookkeeping only. It is not a new prompt field, does not enter the
stable ICCS prefix, and does not change warmup.
