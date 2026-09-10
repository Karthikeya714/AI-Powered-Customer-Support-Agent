"""Phase 11 — calibrate MIN_RETRIEVAL_SIMILARITY on a validation sample.

Per the plan: "avoid arbitrary thresholds... tune them using validation
data, not the golden set." This draws a validation sample from
golden_pool cases that are NOT in golden_set.jsonl (so it never touches
the actual evaluation set), runs the (free, local, no-API-key-needed)
retriever over it, and reports the top-1 similarity distribution so a
data-informed threshold can be chosen — rather than the placeholder 0.5
default from Phase 0, chosen before any real embeddings existed to
calibrate against.

Usage:
    python -m scripts.calibrate_escalation_thresholds
"""

from __future__ import annotations

import json
import random
import statistics

from src.config import get_logger, settings
from src.retrieval.retriever import Retriever

logger = get_logger(__name__)

N_VALIDATION_SAMPLES = 200


def load_validation_cases() -> list[dict]:
    golden_set_path = settings.data_golden_dir / "golden_set.jsonl"
    used_case_ids = set()
    with golden_set_path.open(encoding="utf-8") as f:
        for line in f:
            used_case_ids.add(json.loads(line)["case_id"])

    support_cases_path = settings.data_processed_dir / "support_cases.jsonl"
    validation_cases = []
    with support_cases_path.open(encoding="utf-8") as f:
        for line in f:
            case = json.loads(line)
            if case["split"] == "golden_pool" and case["case_id"] not in used_case_ids:
                validation_cases.append(case)

    logger.info("%d golden_pool cases available for validation (excluding the %d used in golden_set)", len(validation_cases), len(used_case_ids))
    return validation_cases


def main() -> None:
    validation_cases = load_validation_cases()
    rng = random.Random(settings.random_seed)
    sample = rng.sample(validation_cases, min(N_VALIDATION_SAMPLES, len(validation_cases)))

    retriever = Retriever()
    top1_similarities = []
    for case in sample:
        results = retriever.retrieve(case["customer_message"])
        if results:
            top1_similarities.append(results[0]["similarity"])

    top1_similarities.sort()
    n = len(top1_similarities)
    percentiles = {p: top1_similarities[int(n * p / 100)] for p in [1, 5, 10, 25, 50]}

    report = {
        "n_validation_samples": n,
        "mean": statistics.mean(top1_similarities),
        "median": statistics.median(top1_similarities),
        "min": min(top1_similarities),
        "max": max(top1_similarities),
        "percentiles": percentiles,
        "current_config_default": settings.min_retrieval_similarity,
    }

    out_path = settings.project_root / "artifacts" / "metrics" / "escalation_threshold_calibration.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote %s", out_path)

    print("\n=== RETRIEVAL SIMILARITY CALIBRATION (validation sample, not golden_set) ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
