"""Phase 14 — sample a subset of judged replies for blind human scoring.

Writes a template (message, intent, evidence, draft_reply) with NO LLM
scores shown, so the human scoring pass is genuinely independent.

Usage:
    python -m scripts.sample_human_eval

Outputs:
    data/judge/human_eval_template.jsonl
"""

from __future__ import annotations

import json
import random

from src.config import get_logger, settings
from src.retrieval.index import load_case_metadata_by_id

logger = get_logger(__name__)

N_HUMAN_SAMPLES = 30


def main() -> None:
    judge_results_path = settings.project_root / "artifacts" / "judge_results" / "llm_judge_results.jsonl"
    predictions_path = settings.project_root / "artifacts" / "predictions" / "golden_predictions.jsonl"

    judged_ids = set()
    with judge_results_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("error") is None:
                judged_ids.add(row["id"])
    logger.info("%d successfully-judged examples available", len(judged_ids))

    case_metadata = load_case_metadata_by_id()

    examples_by_id = {}
    with predictions_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["id"] in judged_ids:
                pr = row["pipeline_result"]
                enriched_cases = []
                for c in pr.get("retrieved_cases", []):
                    full = case_metadata.get(c["case_id"], {})
                    enriched_cases.append(
                        {
                            "case_id": c["case_id"],
                            "similarity": c["similarity"],
                            "customer_message": full.get("customer_message", ""),
                            "brand_response": full.get("brand_response", ""),
                        }
                    )
                examples_by_id[row["id"]] = {
                    "id": row["id"],
                    "customer_message": row["customer_message"],
                    "predicted_intent": row["predicted_intent"],
                    "retrieved_cases": enriched_cases,
                    "draft_reply": pr["draft_reply"],
                }

    rng = random.Random(settings.random_seed)
    sample_ids = rng.sample(sorted(examples_by_id), min(N_HUMAN_SAMPLES, len(examples_by_id)))

    out_dir = settings.data_golden_dir.parent / "judge"
    out_dir.mkdir(parents=True, exist_ok=True)
    template_path = out_dir / "human_eval_template.jsonl"
    with template_path.open("w", encoding="utf-8") as f:
        for eid in sample_ids:
            f.write(json.dumps(examples_by_id[eid], ensure_ascii=False) + "\n")

    logger.info("Wrote %d examples to %s (blind -- no LLM scores included)", len(sample_ids), template_path)
    print(f"Wrote {len(sample_ids)} examples for human scoring to {template_path}")


if __name__ == "__main__":
    main()
