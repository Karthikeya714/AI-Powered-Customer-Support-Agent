"""Phase 5, step 2 — compile the manually-labeled golden evaluation set.

Reads data/golden/golden_candidates.jsonl (sampled by
scripts/sample_golden_candidates.py) and data/golden/gold_labels_draft.json
(manually assigned gold_intent/gold_action/gold_notes/keep for every
candidate — see docs/golden_set_methodology.md for how those labels were
produced), merges them, drops candidates marked keep=false, applies a
per-intent cap (deterministic, seeded) so no single intent dominates the
final set, and writes the final golden set.

Usage:
    python -m scripts.build_golden_set

Outputs:
    data/golden/golden_set.jsonl
    data/golden/golden_set.csv
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict

from src.config import get_logger, settings

logger = get_logger(__name__)

# Caps applied after keep=false filtering, so no single intent (especially
# ones that absorbed a lot of reclassified candidates, like
# feature_request_or_missing_content) dominates the golden set. Intents not
# listed here (the rarer, deliberately-oversampled risk categories) are
# kept in full.
INTENT_CAPS = {
    "feature_request_or_missing_content": 26,
    "playback_technical_issue": 28,
    "billing_subscription_issue": 24,
    "student_discount_issue": 18,
    "account_access_issue": 20,
    "family_plan_issue": 18,
}


def load_candidates(path) -> dict[str, dict]:
    candidates = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            candidates[c["candidate_id"]] = c
    return candidates


def apply_intent_caps(records: list[dict], seed: int) -> list[dict]:
    """Deterministically trim oversized intents, keeping ESCALATE examples
    preferentially (they're the rarer, more valuable signal for evaluating
    escalation behavior)."""
    by_intent: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_intent[r["gold_intent"]].append(r)

    rng = random.Random(seed)
    kept: list[dict] = []
    for intent, group in by_intent.items():
        cap = INTENT_CAPS.get(intent)
        if cap is None or len(group) <= cap:
            kept.extend(group)
            continue
        escalate = [r for r in group if r["gold_action"] == "ESCALATE"]
        auto_handle = [r for r in group if r["gold_action"] == "AUTO_HANDLE"]
        rng.shuffle(escalate)
        rng.shuffle(auto_handle)
        # keep all ESCALATE examples first (up to the cap), fill the rest with AUTO_HANDLE
        selected = escalate[:cap]
        remaining = cap - len(selected)
        selected.extend(auto_handle[:remaining])
        kept.extend(selected)
        logger.info("Capped %s: %d -> %d (kept %d ESCALATE, %d AUTO_HANDLE)", intent, len(group), len(selected), sum(1 for r in selected if r["gold_action"] == "ESCALATE"), sum(1 for r in selected if r["gold_action"] == "AUTO_HANDLE"))

    return kept


def main() -> None:
    candidates_path = settings.data_golden_dir / "golden_candidates.jsonl"
    labels_path = settings.data_golden_dir / "gold_labels_draft.json"

    candidates = load_candidates(candidates_path)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))

    missing = set(candidates) - set(labels)
    if missing:
        raise ValueError(f"{len(missing)} candidates have no label: {sorted(missing)[:5]}...")

    records = []
    for candidate_id, label in labels.items():
        if not label["keep"]:
            continue
        c = candidates[candidate_id]
        records.append(
            {
                "id": candidate_id.replace("gc_", "gold_"),
                "case_id": c["case_id"],
                "customer_message": c["customer_message"],
                "context": c["context"],
                "gold_intent": label["intent"],
                "gold_action": label["action"],
                "gold_notes": label["notes"],
            }
        )

    logger.info("%d candidates kept after quality filtering (of %d total)", len(records), len(labels))

    records = apply_intent_caps(records, settings.random_seed)
    records.sort(key=lambda r: r["id"])

    if not (150 <= len(records) <= 250):
        raise ValueError(f"Final golden set size {len(records)} is outside the required 150-250 range")

    settings.data_golden_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = settings.data_golden_dir / "golden_set.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    logger.info("Wrote %s (%d examples)", jsonl_path, len(records))

    csv_path = settings.data_golden_dir / "golden_set.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "case_id", "customer_message", "gold_intent", "gold_action", "gold_notes"])
        writer.writeheader()
        for r in records:
            row = {k: v for k, v in r.items() if k != "context"}
            writer.writerow(row)
    logger.info("Wrote %s", csv_path)

    intent_counts = Counter(r["gold_intent"] for r in records)
    action_counts = Counter(r["gold_action"] for r in records)
    print(f"\n=== GOLDEN SET: {len(records)} examples ===")
    print("\nIntent distribution:")
    for intent, count in intent_counts.most_common():
        print(f"  {intent}: {count}")
    print("\nAction distribution:", dict(action_counts))


if __name__ == "__main__":
    main()
