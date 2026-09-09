"""Phase 7 — TF-IDF + Logistic Regression intent baseline.

Trained only on the Phase 4 weak-labeled knowledge-split data (never
golden). A validation split carved from that same non-golden pool is used
to pick the regularization strength C; the golden set is touched exactly
once, for final evaluation.

Pipeline: customer message -> TF-IDF -> Logistic Regression -> intent.
"""

from __future__ import annotations

import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from baselines.majority import load_golden_set
from evaluation.evaluate_intents import compute_intent_metrics, plot_confusion_matrix
from src.config import get_logger, settings
from src.intents.labels import INTENTS

logger = get_logger(__name__)

CANDIDATE_C_VALUES = [0.1, 1.0, 10.0]
VALIDATION_FRACTION = 0.15


def load_training_data(path=None) -> tuple[list[str], list[str]]:
    """The weak-labeled knowledge pool from Phase 4 — 9 of the 12 intents
    have weak-label coverage (see docs/intent_definitions.md); the other 3
    (account_security_compromise, account_data_loss,
    cancellation_or_refund_request) get zero training examples here by
    design, so this classifier can never predict them. Expected, not a bug.
    """
    path = path or (settings.data_processed_dir / "support_cases_with_intents.jsonl")
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            texts.append(row["customer_message"])
            labels.append(row["weak_intent"])
    return texts, labels


def build_pipeline(C: float) -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=10_000, ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words="english")),
            # class_weight="balanced" matters here: playback_technical_issue is ~41% of
            # training data vs ~1% for the smallest covered intent, so an unweighted
            # model would mostly relearn the majority-class baseline.
            ("clf", LogisticRegression(C=C, class_weight="balanced", max_iter=1000, random_state=settings.random_seed)),
        ]
    )


def select_best_C(X_train, y_train, X_val, y_val, all_labels: list[str]) -> tuple[float, dict]:
    best_C, best_score, best_val_metrics = None, -1.0, None
    for C in CANDIDATE_C_VALUES:
        pipeline = build_pipeline(C)
        pipeline.fit(X_train, y_train)
        val_preds = pipeline.predict(X_val)
        metrics = compute_intent_metrics(y_val, list(val_preds), all_labels)
        logger.info("C=%.2f -> validation macro F1=%.4f, accuracy=%.4f", C, metrics["macro_f1"], metrics["accuracy"])
        if metrics["macro_f1"] > best_score:
            best_C, best_score, best_val_metrics = C, metrics["macro_f1"], metrics
    return best_C, best_val_metrics


def main() -> None:
    texts, labels = load_training_data()
    logger.info("Loaded %d weakly-labeled training examples across %d intents", len(texts), len(set(labels)))

    X_train, X_val, y_train, y_val = train_test_split(
        texts, labels, test_size=VALIDATION_FRACTION, random_state=settings.random_seed, stratify=labels
    )
    logger.info("Train: %d, Validation: %d", len(X_train), len(X_val))

    all_labels = sorted(INTENTS.keys())
    best_C, val_metrics = select_best_C(X_train, y_train, X_val, y_val, all_labels)
    logger.info("Selected C=%.2f (validation macro F1=%.4f)", best_C, val_metrics["macro_f1"])

    final_pipeline = build_pipeline(best_C)
    final_pipeline.fit(X_train, y_train)

    golden_records = load_golden_set()
    golden_texts = [r["customer_message"] for r in golden_records]
    golden_true = [r["gold_intent"] for r in golden_records]
    golden_preds = final_pipeline.predict(golden_texts)

    metrics = compute_intent_metrics(golden_true, list(golden_preds), all_labels)
    metrics["selected_C"] = best_C
    metrics["validation_macro_f1"] = val_metrics["macro_f1"]
    metrics["n_train"] = len(X_train)
    metrics["n_validation"] = len(X_val)
    metrics["n_golden"] = len(golden_records)

    predictions = [{"id": r["id"], "gold_intent": r["gold_intent"], "predicted_intent": pred} for r, pred in zip(golden_records, golden_preds)]

    artifacts_predictions = settings.project_root / "artifacts" / "predictions"
    artifacts_metrics = settings.project_root / "artifacts" / "metrics"
    artifacts_predictions.mkdir(parents=True, exist_ok=True)
    artifacts_metrics.mkdir(parents=True, exist_ok=True)

    predictions_path = artifacts_predictions / "tfidf_baseline_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", predictions_path)

    metrics_path = artifacts_metrics / "tfidf_baseline_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Wrote %s", metrics_path)

    plot_path = settings.project_root / "artifacts" / "plots" / "tfidf_baseline_confusion_matrix.png"
    plot_confusion_matrix(metrics, plot_path, title="TF-IDF + Logistic Regression baseline")
    logger.info("Wrote %s", plot_path)

    print(f"\n=== TF-IDF + LOGISTIC REGRESSION BASELINE ({len(golden_records)} golden examples) ===")
    print(f"Selected C: {best_C} (validation macro F1={val_metrics['macro_f1']:.4f})")
    print(f"Golden accuracy: {metrics['accuracy']:.4f}")
    print(f"Golden macro F1: {metrics['macro_f1']:.4f}")
    print("\nPer-intent F1:")
    for label in all_labels:
        row = metrics["per_intent"][label]
        print(f"  {label}: precision={row['precision']:.3f} recall={row['recall']:.3f} f1={row['f1']:.3f} support={row['support']}")


if __name__ == "__main__":
    main()
