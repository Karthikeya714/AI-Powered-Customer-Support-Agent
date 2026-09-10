"""Phase 14 — run the LLM judge over Phase 13's generated replies.

Usage:
    python -m scripts.run_llm_judge

Outputs:
    artifacts/judge_results/llm_judge_results.jsonl
"""

from __future__ import annotations

import json

from evaluation.llm_judge import DIMENSIONS, LLMJudge
from src.config import get_logger, settings
from src.retrieval.index import load_case_metadata_by_id

logger = get_logger(__name__)

# Uses a different model than settings.llm_model (gemini-3.5-flash-lite,
# the classifier/generator default) deliberately: by the time this script
# ran, that model's free-tier daily quota (500 requests) was exhausted by
# the same day's Phase 8/10/13 calls. The judge is an independent scoring
# pass anyway -- using a sibling flash-lite model with separate quota is a
# reasonable adaptation, not a compromise to judge quality. See DECISION_LOG.md.
JUDGE_MODEL = "gemini-3.1-flash-lite"


def load_judgeable_examples(path=None) -> list[dict]:
    """Only golden examples the pipeline actually drafted a reply for —
    escalated-without-generation cases have nothing to judge.

    golden_predictions.jsonl only stores {case_id, similarity} per
    retrieved case (Phase 13 deliberately kept that file lean) — enrich
    back to full evidence text via the retrieval index's metadata, or the
    judge sees empty evidence and (correctly) can't verify groundedness
    against it. See DECISION_LOG.md."""
    path = path or (settings.project_root / "artifacts" / "predictions" / "golden_predictions.jsonl")
    case_metadata = load_case_metadata_by_id()

    examples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            pr = row.get("pipeline_result", {})
            if pr.get("draft_reply"):
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
                examples.append(
                    {
                        "id": row["id"],
                        "customer_message": row["customer_message"],
                        "predicted_intent": row["predicted_intent"],
                        "retrieved_cases": enriched_cases,
                        "draft_reply": pr["draft_reply"],
                    }
                )
    return examples


def _load_cache(path) -> dict[str, dict]:
    if not path.exists():
        return {}
    cache = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            cache[row["id"]] = row
    return cache


def main() -> None:
    examples = load_judgeable_examples()
    logger.info("%d examples have a draft_reply to judge", len(examples))

    out_path = settings.project_root / "artifacts" / "judge_results" / "llm_judge_results.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(out_path)

    judge = LLMJudge(model=JUDGE_MODEL)
    results = []
    with out_path.open("a", encoding="utf-8") as f:
        for i, ex in enumerate(examples, 1):
            cached = cache.get(ex["id"])
            if cached is not None and cached.get("error") is None:
                results.append(cached)
                continue

            logger.info("Judging %s (%d/%d)", ex["id"], i, len(examples))
            scores = judge.judge(ex["customer_message"], ex["predicted_intent"], ex["retrieved_cases"], ex["draft_reply"])
            row = {"id": ex["id"], **scores}
            results.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

    n_errors = sum(1 for r in results if r.get("error"))
    logger.info("Judged %d examples, %d errors", len(results), n_errors)

    print(f"\n=== LLM JUDGE RESULTS ({len(results)} replies judged, {n_errors} errors) ===")
    for dim in DIMENSIONS:
        vals = [r[dim] for r in results if r.get(dim) is not None]
        if vals:
            print(f"  {dim}: mean={sum(vals) / len(vals):.2f}")


if __name__ == "__main__":
    main()
