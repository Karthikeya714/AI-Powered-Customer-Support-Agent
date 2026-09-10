"""Phase 14 — compare human scores (data/judge/human_eval_scores.jsonl,
filled in blind, without seeing the LLM's scores) against the LLM judge's
scores on the same subset.

Usage:
    python -m scripts.compute_human_agreement

Outputs:
    artifacts/judge_results/human_agreement.json
"""

from __future__ import annotations

import json

from evaluation.human_agreement import compute_agreement
from src.config import get_logger, settings

logger = get_logger(__name__)


def main() -> None:
    human_path = settings.data_golden_dir.parent / "judge" / "human_eval_scores.jsonl"
    llm_path = settings.project_root / "artifacts" / "judge_results" / "llm_judge_results.jsonl"

    human_scores = [json.loads(line) for line in human_path.open(encoding="utf-8")]
    llm_by_id = {json.loads(line)["id"]: json.loads(line) for line in llm_path.open(encoding="utf-8")}

    llm_scores = [llm_by_id[h["id"]] for h in human_scores]

    result = compute_agreement(human_scores, llm_scores)

    out_path = settings.project_root / "artifacts" / "judge_results" / "human_agreement.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %s", out_path)

    print(f"\n=== HUMAN vs LLM JUDGE AGREEMENT ({result['n_examples']} examples) ===")
    for dim, stats in result["per_dimension"].items():
        corr = f"{stats['pearson_correlation']:.3f}" if stats["pearson_correlation"] is not None else "n/a"
        print(f"  {dim}: exact_match={stats['exact_match_rate']:.2f} within_1={stats['within_one_point_rate']:.2f} mean_abs_diff={stats['mean_absolute_difference']:.2f} pearson_r={corr}")
    print(f"\nDisagreements (>=2 points): {result['n_disagreements']}")
    for d in result["disagreements"]:
        print(f"  {d['id']} | {d['dimension']}: human={d['human_score']} llm={d['llm_score']}")


if __name__ == "__main__":
    main()
