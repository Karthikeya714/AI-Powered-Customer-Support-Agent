"""Phase 9 — evaluate retrieval quality on the golden set and save example
retrievals for manual inspection.

Usage:
    python -m scripts.evaluate_retrieval

Outputs:
    artifacts/metrics/retrieval_stats.json
    artifacts/predictions/retrieval_examples.json
"""

from __future__ import annotations

import json
import random

from baselines.majority import load_golden_set
from evaluation.evaluate_retrieval import compute_retrieval_stats
from src.config import get_logger, settings
from src.retrieval.retriever import Retriever

logger = get_logger(__name__)

N_EXAMPLES = 10


def main() -> None:
    golden_records = load_golden_set()
    retriever = Retriever()

    stats = compute_retrieval_stats(golden_records, retriever, top_k=settings.top_k)

    metrics_path = settings.project_root / "artifacts" / "metrics" / "retrieval_stats.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    logger.info("Wrote %s", metrics_path)

    rng = random.Random(settings.random_seed)
    sample = rng.sample(golden_records, min(N_EXAMPLES, len(golden_records)))
    examples = []
    for record in sample:
        results = retriever.retrieve(record["customer_message"])
        examples.append(
            {
                "query_id": record["id"],
                "query": record["customer_message"],
                "gold_intent": record["gold_intent"],
                "retrieved": results,
            }
        )

    examples_path = settings.project_root / "artifacts" / "predictions" / "retrieval_examples.json"
    examples_path.write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %s", examples_path)

    print(f"\n=== RETRIEVAL QUALITY (golden set, top_k={settings.top_k}) ===")
    print(json.dumps(stats, indent=2))

    print("\n=== EXAMPLE RETRIEVAL ===")
    ex = examples[0]
    print(f"Query: {ex['query']}")
    print(f"Gold intent: {ex['gold_intent']}")
    for r in ex["retrieved"][:3]:
        print(f"  [{r['similarity']:.3f}] Customer: {r['customer_message'][:80]}")
        print(f"          Brand: {r['brand_response'][:80]}")


if __name__ == "__main__":
    main()
