"""Phase 6 — majority-class intent baseline.

Deliberately trivial: always predicts the single most common intent. The
majority class is determined from the Phase 4 weak-labeled *training*
distribution (data/processed/intent_distribution.json), not from the
golden set itself — the golden set is only ever used for evaluation, never
to decide what the baseline predicts, so this stays comparable to how a
real classifier (Phase 7/8) is trained on non-golden data and evaluated
once on golden.
"""

from __future__ import annotations

import json

from src.config import get_logger, settings
from src.intents.labels import INTENTS
from evaluation.evaluate_intents import compute_intent_metrics

logger = get_logger(__name__)


def load_golden_set(path=None) -> list[dict]:
    path = path or (settings.data_golden_dir / "golden_set.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def compute_majority_intent(intent_distribution_path=None) -> str:
    """Majority class = most frequent intent in the Phase 4 weak-labeled
    knowledge-split training distribution."""
    path = intent_distribution_path or (settings.data_processed_dir / "intent_distribution.json")
    distribution = json.loads(open(path, encoding="utf-8").read())
    counts = distribution["intent_counts"]
    return max(counts, key=counts.get)


def predict(golden_records: list[dict], majority_intent: str) -> list[dict]:
    return [{"id": r["id"], "gold_intent": r["gold_intent"], "predicted_intent": majority_intent} for r in golden_records]


def main() -> None:
    golden_records = load_golden_set()
    majority_intent = compute_majority_intent()
    logger.info("Majority class (from knowledge-split weak labels): %s", majority_intent)

    predictions = predict(golden_records, majority_intent)

    labels = sorted(INTENTS.keys())
    y_true = [p["gold_intent"] for p in predictions]
    y_pred = [p["predicted_intent"] for p in predictions]
    metrics = compute_intent_metrics(y_true, y_pred, labels)
    metrics["majority_intent"] = majority_intent
    metrics["n_examples"] = len(golden_records)

    artifacts_predictions = settings.project_root / "artifacts" / "predictions"
    artifacts_metrics = settings.project_root / "artifacts" / "metrics"
    artifacts_predictions.mkdir(parents=True, exist_ok=True)
    artifacts_metrics.mkdir(parents=True, exist_ok=True)

    predictions_path = artifacts_predictions / "majority_baseline_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", predictions_path)

    metrics_path = artifacts_metrics / "majority_baseline_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Wrote %s", metrics_path)

    print(f"\n=== MAJORITY BASELINE ({len(golden_records)} golden examples) ===")
    print(f"Majority class: {majority_intent}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Macro F1: {metrics['macro_f1']:.4f}")
    print("\nPer-intent F1 (majority class only has non-zero recall):")
    for label in labels:
        row = metrics["per_intent"][label]
        print(f"  {label}: precision={row['precision']:.3f} recall={row['recall']:.3f} f1={row['f1']:.3f} support={row['support']}")


if __name__ == "__main__":
    main()
