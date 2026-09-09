"""Phase 5, step 1 — sample candidate messages from golden_pool for manual
labeling. This does NOT assign gold labels; it only produces a diverse,
stratified pool of real candidates for a human to read and label.

Stratification uses the SAME frozen TF-IDF+KMeans model from Phase 4
(re-fit on knowledge-split data only, deterministic given the fixed seed)
to *transform* (never re-fit) golden_pool messages — this is only a
convenience for making sure sampling covers all intents, including rare
ones; it is never treated as a ground-truth label.

For the 3 intents with no dedicated cluster (account_security_compromise,
account_data_loss, cancellation_or_refund_request), a keyword search over
golden_pool text surfaces candidates instead.

Usage:
    python -m scripts.sample_golden_candidates

Output:
    data/golden/golden_candidates.jsonl
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict

from src.config import get_logger, settings
from src.intents.discovery import fit_tfidf_kmeans, load_knowledge_customer_messages
from src.intents.labels import CLUSTER_TO_INTENT

logger = get_logger(__name__)

N_CLUSTERS = 30  # must match scripts/build_intent_dataset.py for identical clusters

# Target counts per intent. Deliberately NOT proportional to real traffic —
# playback_technical_issue is the biggest real category but is capped so it
# doesn't dominate the golden set; rare-but-important risk intents are
# oversampled relative to their true frequency. See docs/golden_set_methodology.md.
TARGET_PER_INTENT = {
    "playback_technical_issue": 26,
    "account_access_issue": 20,
    "billing_subscription_issue": 20,
    "feature_request_or_missing_content": 16,
    "family_plan_issue": 14,
    "student_discount_issue": 14,
    "acknowledgment_closing": 12,
    "dm_followup": 12,
    "customer_service_feedback": 12,
    "account_security_compromise": 14,
    "account_data_loss": 14,
    "cancellation_or_refund_request": 14,
}
N_HARD_CASES = 20  # additional deliberately ambiguous/ low-cluster-confidence messages
N_OVERSAMPLE_FACTOR = 1.4  # fetch a modest buffer per bucket so unusable ones can be dropped during labeling

KEYWORD_INTENTS = {
    "account_security_compromise": [r"\bhack(ed|ing)?\b", r"\bcompromis", r"\bunauthori[sz]ed\b", r"\bstolen\b", r"\bsomeone (else )?(is )?us(ed|ing) my\b"],
    "account_data_loss": [r"\bdisappear", r"\b(playlists?|library|songs?) (is |are |has |have )?(gone|missing|lost|deleted)\b", r"\blost (my|all)( my)? (playlists?|music|songs?|liked)\b"],
    "cancellation_or_refund_request": [r"\bcancel(l?ed|ling)?\b", r"\brefund\b", r"\bmoney back\b", r"\bclose my account\b", r"\bunsubscribe\b"],
}


def load_golden_pool_cases(support_cases_path) -> list[dict]:
    cases = []
    with support_cases_path.open(encoding="utf-8") as f:
        for line in f:
            case = json.loads(line)
            if case["split"] == "golden_pool":
                cases.append(case)
    logger.info("Loaded %d golden_pool cases", len(cases))
    return cases


def keyword_match_intent(text: str) -> str | None:
    lowered = text.lower()
    for intent, patterns in KEYWORD_INTENTS.items():
        if any(re.search(p, lowered) for p in patterns):
            return intent
    return None


def main() -> None:
    support_cases_path = settings.data_processed_dir / "support_cases.jsonl"

    # Re-fit the identical clustering model from Phase 4 (same data, params,
    # seed => identical clusters) so we can transform golden_pool through it.
    knowledge_df = load_knowledge_customer_messages(support_cases_path)
    vectorizer, kmeans, _ = fit_tfidf_kmeans(knowledge_df["customer_message"].tolist(), N_CLUSTERS, settings.random_seed)

    golden_cases = load_golden_pool_cases(support_cases_path)
    texts = [c["customer_message"] for c in golden_cases]
    golden_matrix = vectorizer.transform(texts)  # transform only, never fit, on golden data
    clusters = kmeans.predict(golden_matrix)
    distances = kmeans.transform(golden_matrix).min(axis=1)  # distance to nearest centroid -> low-confidence proxy

    by_intent: dict[str, list[tuple[dict, float]]] = defaultdict(list)
    unmatched: list[tuple[dict, float]] = []

    for case, cluster_id, dist in zip(golden_cases, clusters, distances):
        cluster_intent = CLUSTER_TO_INTENT.get(int(cluster_id))
        keyword_intent = keyword_match_intent(case["customer_message"])
        # keyword hits take priority for the 3 intents with no dedicated cluster
        intent = keyword_intent or cluster_intent
        if intent:
            by_intent[intent].append((case, dist))
        else:
            unmatched.append((case, dist))

    rng = random.Random(settings.random_seed)
    candidates: list[dict] = []
    seen_case_ids: set[str] = set()

    for intent, target in TARGET_PER_INTENT.items():
        pool = by_intent.get(intent, [])
        rng.shuffle(pool)
        take = pool[: int(round(target * N_OVERSAMPLE_FACTOR))]
        logger.info("%s: %d candidates available, sampling up to %d", intent, len(pool), len(take))
        for case, dist in take:
            if case["case_id"] in seen_case_ids:
                continue
            seen_case_ids.add(case["case_id"])
            candidates.append(
                {
                    "candidate_id": f"gc_{len(candidates)+1:04d}",
                    "case_id": case["case_id"],
                    "customer_message": case["customer_message"],
                    "context": case["context"],
                    "brand_response": case["brand_response"],
                    "hint_intent": intent,
                    "hint_source": "keyword_search" if intent in KEYWORD_INTENTS else "cluster",
                }
            )

    # deliberately-hard bucket: messages farthest from any cluster centroid
    # (low clustering confidence), a reasonable proxy for ambiguous/atypical text
    all_scored = [(c, d) for intent_pool in by_intent.values() for (c, d) in intent_pool] + unmatched
    all_scored.sort(key=lambda x: -x[1])
    hard_added = 0
    for case, dist in all_scored:
        if hard_added >= int(round(N_HARD_CASES * N_OVERSAMPLE_FACTOR)):
            break
        if case["case_id"] in seen_case_ids:
            continue
        seen_case_ids.add(case["case_id"])
        candidates.append(
            {
                "candidate_id": f"gc_{len(candidates)+1:04d}",
                "case_id": case["case_id"],
                "customer_message": case["customer_message"],
                "context": case["context"],
                "brand_response": case["brand_response"],
                "hint_intent": None,
                "hint_source": "low_cluster_confidence",
            }
        )
        hard_added += 1

    settings.data_golden_dir.mkdir(parents=True, exist_ok=True)
    out_path = settings.data_golden_dir / "golden_candidates.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    logger.info("Wrote %d candidates to %s", len(candidates), out_path)
    print(f"\n{len(candidates)} candidates written. Unmatched (no cluster/keyword hint) pool size: {len(unmatched)}")


if __name__ == "__main__":
    main()
