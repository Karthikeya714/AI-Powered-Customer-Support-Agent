"""Phase 4 — discover intent themes, then (once src/intents/labels.py has a
CLUSTER_TO_INTENT mapping) weakly-label the knowledge pool with them.

This script is meant to run twice:
  1. Before labels.py exists: writes the raw cluster discovery report only.
     A human reads it and writes src/intents/labels.py from real clusters.
  2. After labels.py has CLUSTER_TO_INTENT filled in: also applies the
     mapping to every knowledge-split case and writes the labeled dataset
     (used to train the Phase 7 TF-IDF baseline and, later, to sanity-check
     the Phase 8 classifier).

Usage:
    python -m scripts.build_intent_dataset

Outputs:
    data/processed/intent_discovery_clusters.json   (always)
    data/processed/support_cases_with_intents.jsonl  (only once CLUSTER_TO_INTENT exists)
    data/processed/intent_distribution.json          (only once CLUSTER_TO_INTENT exists)
"""

from __future__ import annotations

import json
from collections import Counter

from src.config import get_logger, settings
from src.intents.discovery import fit_tfidf_kmeans, load_knowledge_customer_messages, sample_examples_per_cluster, top_terms_per_cluster

logger = get_logger(__name__)

N_CLUSTERS = 30
N_EXAMPLES_PER_CLUSTER = 8


def main() -> None:
    support_cases_path = settings.data_processed_dir / "support_cases.jsonl"
    df = load_knowledge_customer_messages(support_cases_path)
    texts = df["customer_message"].tolist()

    logger.info("Fitting TF-IDF + KMeans (k=%d) over %d messages", N_CLUSTERS, len(texts))
    vectorizer, kmeans, labels = fit_tfidf_kmeans(texts, N_CLUSTERS, settings.random_seed)
    df["cluster"] = labels

    top_terms = top_terms_per_cluster(vectorizer, kmeans, n_terms=15)
    examples = sample_examples_per_cluster(texts, labels, N_CLUSTERS, N_EXAMPLES_PER_CLUSTER, settings.random_seed)
    sizes = Counter(labels)

    discovery_report = {
        "n_clusters": N_CLUSTERS,
        "n_messages": len(texts),
        "clusters": [
            {
                "cluster_id": c,
                "size": sizes[c],
                "top_terms": top_terms[c],
                "examples": examples[c],
            }
            for c in range(N_CLUSTERS)
        ],
    }
    settings.data_processed_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.data_processed_dir / "intent_discovery_clusters.json"
    report_path.write_text(json.dumps(discovery_report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %s", report_path)

    try:
        from src.intents.labels import CLUSTER_TO_INTENT, INTENTS
    except ImportError:
        CLUSTER_TO_INTENT = {}
        INTENTS = {}

    if not CLUSTER_TO_INTENT:
        print("\nNo CLUSTER_TO_INTENT mapping found in src/intents/labels.py yet.")
        print(f"Inspect {report_path} and write the final intent taxonomy + mapping, then re-run this script.")
        return

    unknown_intents = set(CLUSTER_TO_INTENT.values()) - {None} - set(INTENTS)
    if unknown_intents:
        raise ValueError(f"CLUSTER_TO_INTENT references intents not defined in INTENTS: {unknown_intents}")
    missing_clusters = set(range(N_CLUSTERS)) - set(CLUSTER_TO_INTENT)
    if missing_clusters:
        raise ValueError(f"CLUSTER_TO_INTENT is missing entries for clusters: {sorted(missing_clusters)}")

    df["weak_intent"] = df["cluster"].map(CLUSTER_TO_INTENT)
    labeled = df[df["weak_intent"].notna()]
    dropped = len(df) - len(labeled)
    logger.info("%d/%d knowledge messages mapped to an intent (%d in discarded/noise clusters)", len(labeled), len(df), dropped)

    labeled_path = settings.data_processed_dir / "support_cases_with_intents.jsonl"
    with labeled_path.open("w", encoding="utf-8") as f:
        for row in labeled.itertuples():
            f.write(json.dumps({"case_id": row.case_id, "customer_message": row.customer_message, "weak_intent": row.weak_intent}, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", labeled_path)

    distribution = Counter(labeled["weak_intent"])
    distribution_report = {
        "total_labeled": len(labeled),
        "total_discarded_as_noise": dropped,
        "intent_counts": dict(distribution.most_common()),
    }
    distribution_path = settings.data_processed_dir / "intent_distribution.json"
    distribution_path.write_text(json.dumps(distribution_report, indent=2), encoding="utf-8")
    logger.info("Wrote %s", distribution_path)

    print("\n=== WEAK INTENT LABEL DISTRIBUTION (knowledge split) ===")
    print(json.dumps(distribution_report, indent=2))


if __name__ == "__main__":
    main()
