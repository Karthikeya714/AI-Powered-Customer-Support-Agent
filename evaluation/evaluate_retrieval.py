"""Retrieval quality metrics.

There's no manually-labeled retrieval-relevance ground truth — that would
need a separate human-labeling pass judging historical-case relevance per
query, which the plan doesn't require and which would risk becoming
circular with the golden set's own labeling. Instead this uses two cheap,
already-available proxies:

1. Similarity score statistics — how confidently the index finds nearby
   neighbors for golden queries. Low similarity is itself an escalation
   signal later (Phase 11: MIN_RETRIEVAL_SIMILARITY).
2. Intent-agreement@k — using Phase 4's weak intent labels (knowledge
   pool) and Phase 5's gold_intent labels (golden set) as an approximate
   topical-relevance signal: do the top-k retrieved historical cases
   share the query's true intent? This inherits the same known gap as
   the Phase 7 baseline: 3 intents have zero weak-label coverage, so
   agreement for those reads near 0 by construction — a labeling-coverage
   artifact, not a retrieval failure. Reported per-intent so it's visible,
   not hidden in an aggregate.
"""

from __future__ import annotations

import statistics


def _stats(values: list[float]) -> dict:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {"mean": statistics.mean(values), "median": statistics.median(values), "min": min(values), "max": max(values)}


def compute_retrieval_stats(golden_records: list[dict], retriever, top_k: int) -> dict:
    top1_similarities = []
    avg_topk_similarities = []
    intent_agreement_scores = []
    per_intent_agreement: dict[str, list[float]] = {}
    zero_results = 0

    for record in golden_records:
        results = retriever.retrieve(record["customer_message"], top_k=top_k)
        if not results:
            zero_results += 1
            continue

        top1_similarities.append(results[0]["similarity"])
        avg_topk_similarities.append(sum(r["similarity"] for r in results) / len(results))

        labeled_results = [r for r in results if r["weak_intent"] is not None]
        agreement = (
            sum(1 for r in labeled_results if r["weak_intent"] == record["gold_intent"]) / len(labeled_results) if labeled_results else 0.0
        )
        intent_agreement_scores.append(agreement)
        per_intent_agreement.setdefault(record["gold_intent"], []).append(agreement)

    return {
        "n_golden_queries": len(golden_records),
        "n_zero_results": zero_results,
        "top_k": top_k,
        "top1_similarity": _stats(top1_similarities),
        "avg_topk_similarity": _stats(avg_topk_similarities),
        "intent_agreement_at_k": {
            "overall_mean": statistics.mean(intent_agreement_scores) if intent_agreement_scores else None,
            "by_gold_intent": {intent: statistics.mean(scores) for intent, scores in sorted(per_intent_agreement.items())},
        },
    }
