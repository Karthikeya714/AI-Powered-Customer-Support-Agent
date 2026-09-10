"""Phase 8 — LLM-based intent classifier.

Given a customer message, returns one of the 12 approved intents plus a
confidence score. "Never invent a new label" is enforced structurally via
a JSON schema enum constraint (Gemini structured output), not just a
prompt instruction — an out-of-schema response fails validation rather
than silently returning a bad label.
"""

from __future__ import annotations

import json
import re
import time
from enum import Enum

from google import genai
from pydantic import BaseModel, Field, ValidationError

from src.config import get_logger, settings
from src.intents.labels import INTENTS

logger = get_logger(__name__)

# The free tier for this model enforces ~20 requests/minute (seen via live
# 429s: "limit: 20, model: gemini-3.6-flash"). 3.5s spacing keeps steady-state
# calls to ~17/min, safely under that.
CALL_PACING_SECONDS = 3.5

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 45.0  # used when the API's "retry in Xs" can't be parsed
RATE_LIMIT_MAX_BACKOFF_SECONDS = 90.0
_RETRY_AFTER_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)

_IntentEnum = Enum("_IntentEnum", {name: name for name in INTENTS})


class IntentPrediction(BaseModel):
    intent: _IntentEnum = Field(description="One of the approved intent labels")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that the predicted intent is correct")
    reasoning: str = Field(description="One brief sentence explaining the choice")


def _build_system_prompt() -> str:
    lines = [
        "You are an intent classifier for SpotifyCares, Spotify's customer support Twitter account.",
        "Classify the customer's message into exactly ONE of the following intents.",
        "Only ever return one of these exact intent names — never invent a new one, even if none fits perfectly; pick the closest.",
        "",
    ]
    for name, definition in INTENTS.items():
        lines.append(f"- {name}: {definition['description']}")
        if definition.get("boundary_notes"):
            lines.append(f"  Boundary: {definition['boundary_notes']}")
    lines.append("")
    lines.append(
        "Give a confidence between 0 and 1. Use a LOW confidence (below 0.5) when the message is "
        "genuinely ambiguous, off-topic, non-English, or could plausibly fit more than one intent — "
        "do not force high confidence just to pick an answer."
    )
    return "\n".join(lines)


SYSTEM_PROMPT = _build_system_prompt()


REQUEST_TIMEOUT_MS = 30_000  # without this, a dropped connection hangs forever instead of raising

_UNSET = object()  # sentinel so callers can pass fallback_model=None to explicitly disable it,
                    # distinct from "not specified, use settings.llm_fallback_model"


class IntentClassifier:
    def __init__(self, api_key: str | None = None, model: str | None = None, fallback_model=_UNSET):
        self.model = model or settings.llm_model
        self.fallback_model = settings.llm_fallback_model if fallback_model is _UNSET else fallback_model
        self.client = genai.Client(api_key=api_key or settings.llm_api_key, http_options={"timeout": REQUEST_TIMEOUT_MS})

    def predict(self, customer_message: str) -> dict:
        """Returns a dict with intent/confidence/reasoning on success, or
        intent=None and a populated "error" on failure — callers must
        handle both (fail safely, never crash the pipeline on bad LLM output).

        Tries self.model first; if it exhausts all retries (e.g. its daily
        quota is exhausted), falls back to self.fallback_model with a fresh
        retry budget, when one is configured and differs from the primary.
        """
        result = self._predict_with_model(self.model, customer_message)
        if result["error"] is not None and self.fallback_model and self.fallback_model != self.model:
            logger.warning(
                "Primary model %s exhausted retries (%s); falling back to %s",
                self.model, result["error"], self.fallback_model,
            )
            result = self._predict_with_model(self.fallback_model, customer_message)
        return result

    def _predict_with_model(self, model: str, customer_message: str) -> dict:
        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                interaction = self.client.interactions.create(
                    model=model,
                    system_instruction=SYSTEM_PROMPT,
                    input=customer_message,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": IntentPrediction.model_json_schema(),
                    },
                )
                if interaction.status != "completed":
                    raise RuntimeError(f"interaction status={interaction.status!r} errors={interaction.errors!r}")

                parsed = IntentPrediction.model_validate_json(interaction.output_text)
                return {
                    "intent": parsed.intent.value,
                    "confidence": parsed.confidence,
                    "reasoning": parsed.reasoning,
                    "raw_response": interaction.output_text,
                    "model": model,
                    "error": None,
                }
            except (RuntimeError, ValidationError, ValueError) as e:
                last_error = str(e)
                logger.warning("Classification attempt %d/%d (%s) failed: %s", attempt, MAX_RETRIES, model, last_error)
                backoff = RETRY_BACKOFF_SECONDS * attempt
            except Exception as e:  # network/rate-limit/transient API errors
                last_error = str(e)
                logger.warning("Classification attempt %d/%d (%s) raised %s: %s", attempt, MAX_RETRIES, model, type(e).__name__, last_error)
                if getattr(e, "status_code", None) == 429 or getattr(e, "code", None) == 429:
                    match = _RETRY_AFTER_RE.search(last_error)
                    backoff = min(float(match.group(1)) + 2.0, RATE_LIMIT_MAX_BACKOFF_SECONDS) if match else RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
                else:
                    backoff = RETRY_BACKOFF_SECONDS * attempt

            if attempt < MAX_RETRIES:
                logger.info("Retrying in %.1fs", backoff)
                time.sleep(backoff)

        logger.error("Classification failed after %d attempts on %s: %s", MAX_RETRIES, model, last_error)
        return {"intent": None, "confidence": 0.0, "reasoning": None, "raw_response": None, "model": model, "error": last_error}


def _load_cache(cache_path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    cache = {}
    with cache_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            cache[row["id"]] = row
    return cache


def classify_golden_set(golden_records: list[dict], cache_path) -> list[dict]:
    """Classifies every golden record, reusing a local cache
    (artifacts/predictions/ai_classifier_raw_cache.jsonl) so re-running
    this doesn't re-spend API calls on already-successful predictions.
    """
    cache = _load_cache(cache_path)
    classifier = IntentClassifier()
    results = []

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as cache_file:
        for i, record in enumerate(golden_records, 1):
            cached = cache.get(record["id"])
            if cached is not None and cached.get("error") is None:
                results.append(cached)
                continue

            logger.info("Classifying %s (%d/%d)", record["id"], i, len(golden_records))
            prediction = classifier.predict(record["customer_message"])
            row = {"id": record["id"], **prediction}
            results.append(row)
            cache_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            cache_file.flush()
            time.sleep(CALL_PACING_SECONDS)

    return results


def main() -> None:
    from baselines.majority import load_golden_set
    from evaluation.evaluate_intents import compute_intent_metrics, plot_confusion_matrix

    golden_records = load_golden_set()
    all_labels = sorted(INTENTS.keys())

    cache_path = settings.project_root / "artifacts" / "predictions" / "ai_classifier_raw_cache.jsonl"
    raw_results = classify_golden_set(golden_records, cache_path)
    raw_by_id = {r["id"]: r for r in raw_results}

    n_errors = sum(1 for r in raw_results if r.get("error"))
    if n_errors:
        logger.warning("%d/%d classifications failed even after retries", n_errors, len(golden_records))

    predictions = []
    for record in golden_records:
        raw = raw_by_id[record["id"]]
        predicted_intent = raw["intent"] if raw["intent"] is not None else "CLASSIFICATION_ERROR"
        predictions.append(
            {
                "id": record["id"],
                "gold_intent": record["gold_intent"],
                "predicted_intent": predicted_intent,
                "confidence": raw.get("confidence"),
                "reasoning": raw.get("reasoning"),
                "error": raw.get("error"),
            }
        )

    y_true = [p["gold_intent"] for p in predictions]
    y_pred = [p["predicted_intent"] for p in predictions]
    metrics = compute_intent_metrics(y_true, y_pred, all_labels)
    metrics["n_golden"] = len(golden_records)
    metrics["n_classification_errors"] = n_errors
    metrics["model"] = settings.llm_model

    artifacts_predictions = settings.project_root / "artifacts" / "predictions"
    artifacts_metrics = settings.project_root / "artifacts" / "metrics"
    artifacts_predictions.mkdir(parents=True, exist_ok=True)
    artifacts_metrics.mkdir(parents=True, exist_ok=True)

    predictions_path = artifacts_predictions / "ai_classifier_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", predictions_path)

    metrics_path = artifacts_metrics / "ai_classifier_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Wrote %s", metrics_path)

    plot_path = settings.project_root / "artifacts" / "plots" / "ai_classifier_confusion_matrix.png"
    plot_confusion_matrix(metrics, plot_path, title=f"AI classifier ({settings.llm_model})")
    logger.info("Wrote %s", plot_path)

    print(f"\n=== AI INTENT CLASSIFIER ({settings.llm_model}, {len(golden_records)} golden examples) ===")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Macro F1: {metrics['macro_f1']:.4f}")
    print(f"Classification errors (after retries): {n_errors}")
    print("\nPer-intent F1:")
    for label in all_labels:
        row = metrics["per_intent"][label]
        print(f"  {label}: precision={row['precision']:.3f} recall={row['recall']:.3f} f1={row['f1']:.3f} support={row['support']}")

    print("\n=== COMPARISON TABLE ===")
    print(f"{'Model':<35} {'Accuracy':>10} {'Macro F1':>10}")
    for name, path in [
        ("Majority baseline", artifacts_metrics / "majority_baseline_metrics.json"),
        ("TF-IDF + LogReg baseline", artifacts_metrics / "tfidf_baseline_metrics.json"),
        (f"AI classifier ({settings.llm_model})", metrics_path),
    ]:
        if path.exists():
            m = json.loads(path.read_text(encoding="utf-8"))
            print(f"{name:<35} {m['accuracy']:>10.4f} {m['macro_f1']:>10.4f}")
        else:
            print(f"{name:<35} {'(missing)':>10} {'(missing)':>10}")


if __name__ == "__main__":
    main()
