# routerMon Training

If routerMon sends a phrase to the wrong route, add training examples, retrain the model, and test it again.

## 1. Add Training Examples

Open:

```text
nancee/router_training/training_data.csv
```

Each row contains:

```text
text,intent
```

For example:

```csv
the service restarted fine,normal
the service restarted successfully,normal
restart the service,directive
restart the service again,directive
```

Valid intents are:

```text
affirmative
clarify
detailed
directive
farewell
greeting
memory_store
model_recall
negative
normal
question
recall
```

Add the phrase that routed incorrectly and a few similar examples.

When useful, also add examples showing the opposite route:

```csv
not this time,negative
not right now,negative
not Tuesday Wednesday,memory_store
not the USB controller the power board,memory_store
```

Do not add the exact same `text,intent` pair twice. The trainer will stop if duplicate examples are found.

## 2. Retrain

From the repository root:

```bash
source nancee/sherpa/venv/bin/activate
python3 nancee/router_training/train_router_mon.py
```

The trainer runs cross-validation and creates:

```text
nancee/router_training/routerMon.joblib
```

If training reports an error, fix it before continuing.

## 3. Copy the New Model Into the Runtime

```bash
cp nancee/router_training/routerMon.joblib \
   nancee/sherpa/routerMon.joblib
```

## 4. Run the Tests

```bash
bash nancee/test/run_unit_tests.sh
```

The test run should finish with:

```text
OK
```

## 5. Test the Routing Again

Run the voice harness:

```bash
source nancee/sherpa/venv/bin/activate
python3 nancee/sherpa/nancee_chat.py
```

Repeat the phrase that routed incorrectly.

Also test a nearby phrase that should use a different route.

Example:

```text
The service restarted fine.
-> normal

Restart the service.
-> directive
```

If routing is still wrong, add better examples to `training_data.csv` and repeat the process.

## scikit-learn References

- Text classification using TF-IDF/sparse features: [https://scikit-learn.org/stable/auto_examples/text/plot_document_classification_20newsgroups.html](https://scikit-learn.org/stable/auto_examples/text/plot_document_classification_20newsgroups.html)
- Text feature extraction pipeline example: [https://scikit-learn.org/stable/auto_examples/model_selection/plot_grid_search_text_feature_extraction.html](https://scikit-learn.org/stable/auto_examples/model_selection/plot_grid_search_text_feature_extraction.html)
- `TfidfVectorizer`: [https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)
- `LogisticRegression`: [https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)
- Model persistence: [https://scikit-learn.org/stable/model_persistence.html](https://scikit-learn.org/stable/model_persistence.html)
