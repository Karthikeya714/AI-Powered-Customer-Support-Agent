"""Phase 13 — evaluation harness: run the complete pipeline on the golden
set and compute intent, retrieval, and escalation metrics together.

Reuses Phase 8's already-computed classifier predictions
(artifacts/predictions/ai_classifier_predictions.jsonl) instead of
re-invoking the classifier here — it's the exact same model, prompt, and
golden-set inputs, so a second live classification pass would just
re-spend API quota to reproduce a number already measured and saved.
Retrieval is free/local and always run fresh. Generation is a genuinely
new call, made only when the pre-check (intent + retrieval signals alone)
doesn't already call for escalation — mirroring SupportAgent's own
two-stage design (src/agent.py), for the same reason: avoid a wasted LLM
call on a reply that would never be shown to the customer.

Reply-quality metrics (LLM-judge-scored correctness/groundedness/
helpfulness/tone/hallucination) are Phase 14's job specifically — this
harness saves the raw generated replies + evidence Phase 14 needs, but
does not build the judge itself.

Usage:
    python -m evaluation.run_evaluation

Outputs:
    artifacts/predictions/golden_predictions.jsonl   (full result per golden example)
    artifacts/metrics/intent_metrics.json            (reusing Phase 8's classifier predictions)
    artifacts/metrics/escalation_metrics.json
    artifacts/metrics/retrieval_metrics.json
    artifacts/plots/agent_intent_confusion_matrix.png
    artifacts/plots/escalation_confusion_matrix.png
"""

from __future__ import annotations

import json
import time

from baselines.majority import load_golden_set
from evaluation.evaluate_escalation import compute_escalation_metrics
from evaluation.evaluate_intents import compute_intent_metrics, plot_confusion_matrix
from evaluation.evaluate_retrieval import compute_retrieval_stats
from src.config import get_logger, settings
from src.escalation.decision import decide
from src.generation.reply_generator import ReplyGenerator
from src.intents.labels import INTENTS
from src.retrieval.retriever import Retriever

logger = get_logger(__name__)

CALL_PACING_SECONDS = 1.0


def load_classifier_predictions(path=None) -> dict[str, dict]:
    path = path or (settings.project_root / "artifacts" / "predictions" / "ai_classifier_predictions.jsonl")
    predictions = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            predictions[row["id"]] = row
    return predictions


def _load_cache(cache_path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    cache = {}
    with cache_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            cache[row["id"]] = row
    return cache


def run_pipeline_over_golden_set(golden_records: list[dict], classifier_predictions: dict[str, dict], retriever: Retriever, cache_path) -> list[dict]:
    cache = _load_cache(cache_path)
    generator = ReplyGenerator()
    results = []

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as cache_file:
        for i, record in enumerate(golden_records, 1):
            cached = cache.get(record["id"])
            if cached is not None and cached.get("error") is None:
                results.append(cached)
                continue

            try:
                clf = classifier_predictions[record["id"]]
                intent = clf["predicted_intent"] if clf["error"] is None else "UNKNOWN"
                confidence = clf["confidence"] if clf["error"] is None else 0.0

                retrieved_cases = retriever.retrieve(record["customer_message"])

                pre_decision = decide(record["customer_message"], intent, confidence, retrieved_cases, reply_grounded=None)

                draft_reply, evidence_ids, grounding_note, reply_grounded = None, [], None, None
                if pre_decision["decision"] == "AUTO_HANDLE":
                    logger.info("Generating reply for %s (%d/%d)", record["id"], i, len(golden_records))
                    gen_result = generator.generate(record["customer_message"], intent, retrieved_cases)
                    draft_reply = gen_result["draft_reply"]
                    evidence_ids = gen_result["evidence_ids"]
                    grounding_note = gen_result["grounding_note"]
                    reply_grounded = gen_result["grounded"]
                    time.sleep(CALL_PACING_SECONDS)
                else:
                    logger.info("Skipping generation for %s (%d/%d) -- already escalate-worthy", record["id"], i, len(golden_records))

                final_decision = decide(record["customer_message"], intent, confidence, retrieved_cases, reply_grounded=reply_grounded)

                result = {
                    "id": record["id"],
                    "predicted_intent": intent,
                    "confidence": confidence,
                    "retrieved_cases": [{"case_id": c["case_id"], "similarity": c["similarity"]} for c in retrieved_cases],
                    "draft_reply": draft_reply,
                    "evidence_ids": evidence_ids,
                    "grounding_note": grounding_note,
                    "predicted_action": final_decision["decision"],
                    "decision_reason": final_decision["reason"],
                    "error": None,
                }
            except Exception as e:
                logger.warning("Pipeline run failed for %s: %s", record["id"], e)
                result = {"id": record["id"], "error": str(e)}

            results.append(result)
            cache_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            cache_file.flush()

    return results


def main() -> None:
    golden_records = load_golden_set()
    all_labels = sorted(INTENTS.keys())
    classifier_predictions = load_classifier_predictions()
    retriever = Retriever()

    cache_path = settings.project_root / "artifacts" / "predictions" / "golden_predictions_raw_cache.jsonl"
    raw_results = run_pipeline_over_golden_set(golden_records, classifier_predictions, retriever, cache_path)
    raw_by_id = {r["id"]: r for r in raw_results}

    n_errors = sum(1 for r in raw_results if r.get("error"))
    if n_errors:
        logger.warning("%d/%d pipeline runs failed: %s", n_errors, len(golden_records), [r["id"] for r in raw_results if r.get("error")])

    y_true_intent, y_pred_intent = [], []
    y_true_action, y_pred_action = [], []
    predictions = []

    for record in golden_records:
        raw = raw_by_id[record["id"]]
        if raw.get("error"):
            predicted_intent, predicted_action = "PIPELINE_ERROR", "ESCALATE"
        else:
            predicted_intent = raw["predicted_intent"]
            predicted_action = raw["predicted_action"]

        y_true_intent.append(record["gold_intent"])
        y_pred_intent.append(predicted_intent)
        y_true_action.append(record["gold_action"])
        y_pred_action.append(predicted_action)

        predictions.append(
            {
                "id": record["id"],
                "customer_message": record["customer_message"],
                "gold_intent": record["gold_intent"],
                "gold_action": record["gold_action"],
                "predicted_intent": predicted_intent,
                "predicted_action": predicted_action,
                "pipeline_result": raw,
            }
        )

    intent_metrics = compute_intent_metrics(y_true_intent, y_pred_intent, all_labels)
    intent_metrics["n_golden"] = len(golden_records)
    intent_metrics["n_pipeline_errors"] = n_errors
    intent_metrics["note"] = "predicted_intent reuses Phase 8's classifier predictions -- not a new classification pass"

    escalation_metrics = compute_escalation_metrics(y_true_action, y_pred_action)
    retrieval_stats = compute_retrieval_stats(golden_records, retriever, top_k=settings.top_k)

    artifacts_predictions = settings.project_root / "artifacts" / "predictions"
    artifacts_metrics = settings.project_root / "artifacts" / "metrics"
    artifacts_plots = settings.project_root / "artifacts" / "plots"
    for d in (artifacts_predictions, artifacts_metrics, artifacts_plots):
        d.mkdir(parents=True, exist_ok=True)

    predictions_path = artifacts_predictions / "golden_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", predictions_path)

    (artifacts_metrics / "intent_metrics.json").write_text(json.dumps(intent_metrics, indent=2), encoding="utf-8")
    (artifacts_metrics / "escalation_metrics.json").write_text(json.dumps(escalation_metrics, indent=2), encoding="utf-8")
    (artifacts_metrics / "retrieval_metrics.json").write_text(json.dumps(retrieval_stats, indent=2), encoding="utf-8")
    logger.info("Wrote intent/escalation/retrieval metrics to artifacts/metrics/")

    plot_confusion_matrix(intent_metrics, artifacts_plots / "agent_intent_confusion_matrix.png", title="Full pipeline -- intent (reusing Phase 8 predictions)")
    plot_confusion_matrix(escalation_metrics, artifacts_plots / "escalation_confusion_matrix.png", title="Escalation decision")

    print(f"\n=== EVALUATION HARNESS ({len(golden_records)} golden examples) ===")
    print(f"\nIntent -- accuracy: {intent_metrics['accuracy']:.4f}  macro F1: {intent_metrics['macro_f1']:.4f}")
    print(f"\nEscalation -- accuracy: {escalation_metrics['accuracy']:.4f}")
    for label in escalation_metrics["labels"]:
        row = escalation_metrics["per_label"][label]
        print(f"  {label}: precision={row['precision']:.3f} recall={row['recall']:.3f} f1={row['f1']:.3f} support={row['support']}")
    print(f"  False auto-handle rate (dangerous): {escalation_metrics['false_auto_handle_rate']}")
    print(f"  False escalation rate (conservative): {escalation_metrics['false_escalation_rate']}")
    print(f"\nRetrieval -- mean top-1 similarity: {retrieval_stats['top1_similarity']['mean']:.4f}")
    print(f"\nPipeline errors: {n_errors}/{len(golden_records)}")


if __name__ == "__main__":
    main()
