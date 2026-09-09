"""Phase 3 — clean the raw tweets for the selected brand and reconstruct
normalized support-case records.

Usage:
    python -m scripts.build_processed_dataset

Outputs:
    data/processed/support_cases.jsonl         (full cleaned dataset, gitignored — regenerate via this script)
    data/processed/support_cases_sample.jsonl   (50 random cases, human-inspectable, committed)
    data/processed/preprocessing_stats.json
"""

from __future__ import annotations

import json
import random
from collections import Counter

from src.config import get_logger, settings
from src.data.cleaner import find_duplicate_mask, is_usable_text
from src.data.conversation_builder import TweetGraph, assign_split, build_cases, fetch_full_rows
from src.data.loader import default_raw_path

logger = get_logger(__name__)

GOLDEN_POOL_FRACTION = 0.15
SAMPLE_SIZE = 50


def main() -> None:
    brand = settings.selected_brand
    if not brand:
        raise RuntimeError("SELECTED_BRAND is not set — see .env.example / DECISION_LOG.md Phase 2 entry.")

    raw_path = default_raw_path()
    logger.info("Building processed dataset for brand=%s from %s", brand, raw_path)

    graph = TweetGraph.build(raw_path)
    relevant_ids = graph.find_relevant_tweet_ids(brand)
    full_rows = fetch_full_rows(raw_path, relevant_ids)

    n_before_cleaning = len(full_rows)

    usable_mask = full_rows["text"].apply(is_usable_text)
    n_unusable = int((~usable_mask).sum())
    full_rows = full_rows[usable_mask]

    duplicate_mask = find_duplicate_mask(full_rows)
    n_duplicates = int(duplicate_mask.sum())
    full_rows = full_rows[~duplicate_mask]

    n_after_cleaning = len(full_rows)
    logger.info(
        "Cleaning: %d rows fetched, %d dropped as unusable text, %d dropped as duplicates, %d remain",
        n_before_cleaning,
        n_unusable,
        n_duplicates,
        n_after_cleaning,
    )

    cases, case_stats = build_cases(full_rows, brand)
    assign_split(cases, GOLDEN_POOL_FRACTION, settings.random_seed)

    # Some brand replies' in_response_to_tweet_id points to a customer tweet
    # that ALSO has another, semantically unrelated brand reply pointing at
    # it (a mis-threading artifact in the raw data, not a reconstruction
    # bug — see DECISION_LOG.md). Surface how common this is.
    customer_tweet_case_counts = Counter(c["customer_tweet_id"] for c in cases)
    cases_sharing_a_customer_tweet = sum(count for count in customer_tweet_case_counts.values() if count > 1)

    split_counts = {"knowledge": 0, "golden_pool": 0}
    for case in cases:
        split_counts[case["split"]] += 1

    settings.data_processed_dir.mkdir(parents=True, exist_ok=True)

    cases_path = settings.data_processed_dir / "support_cases.jsonl"
    with cases_path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
    logger.info("Wrote %s (%d cases)", cases_path, len(cases))

    rng = random.Random(settings.random_seed)
    sample = rng.sample(cases, min(SAMPLE_SIZE, len(cases)))
    sample_path = settings.data_processed_dir / "support_cases_sample.jsonl"
    with sample_path.open("w", encoding="utf-8") as f:
        for case in sample:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
    logger.info("Wrote %s (%d cases)", sample_path, len(sample))

    stats = {
        "brand": brand,
        "raw_rows_fetched_for_brand_threads": n_before_cleaning,
        "rows_dropped_unusable_text": n_unusable,
        "rows_dropped_duplicate": n_duplicates,
        "rows_after_cleaning": n_after_cleaning,
        "brand_reply_candidates": case_stats["brand_reply_candidates"],
        "cases_built": case_stats["cases_built"],
        "cases_dropped_no_customer_ancestor": case_stats["no_customer_ancestor_found"],
        "multi_turn_cases": case_stats["multi_turn_cases"],
        "single_turn_cases": case_stats["cases_built"] - case_stats["multi_turn_cases"],
        "cases_sharing_a_customer_tweet_with_another_case": cases_sharing_a_customer_tweet,
        "pct_cases_sharing_a_customer_tweet": round(100 * cases_sharing_a_customer_tweet / max(len(cases), 1), 2),
        "pct_brand_replies_usable_as_cases": round(100 * case_stats["cases_built"] / max(case_stats["brand_reply_candidates"], 1), 2),
        "split_counts": split_counts,
        "golden_pool_fraction_target": GOLDEN_POOL_FRACTION,
        "random_seed": settings.random_seed,
    }
    stats_path = settings.data_processed_dir / "preprocessing_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    logger.info("Wrote %s", stats_path)

    print("\n=== PREPROCESSING SUMMARY ===")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
