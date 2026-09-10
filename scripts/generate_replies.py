"""Phase 10 — generate grounded example replies for manual inspection.

Uses gold_intent (not a predicted intent) so reply-generation quality can
be assessed independently of intent-classification accuracy — chaining a
*predicted* intent through this step is the full agent's job (Phase 12).

Usage:
    python -m scripts.generate_replies

Outputs:
    artifacts/predictions/reply_generation_examples.json
"""

from __future__ import annotations

import json
import random

from baselines.majority import load_golden_set
from src.config import get_logger, settings
from src.generation.reply_generator import ReplyGenerator
from src.retrieval.retriever import Retriever

logger = get_logger(__name__)

N_EXAMPLES = 15


def main() -> None:
    golden_records = load_golden_set()
    retriever = Retriever()
    generator = ReplyGenerator()

    rng = random.Random(settings.random_seed)
    sample = rng.sample(golden_records, min(N_EXAMPLES, len(golden_records)))

    examples = []
    for record in sample:
        retrieved = retriever.retrieve(record["customer_message"])
        result = generator.generate(record["customer_message"], record["gold_intent"], retrieved)
        examples.append(
            {
                "id": record["id"],
                "customer_message": record["customer_message"],
                "gold_intent": record["gold_intent"],
                "gold_action": record["gold_action"],
                "retrieved_case_ids": [c["case_id"] for c in retrieved],
                "draft_reply": result["draft_reply"],
                "grounded": result["grounded"],
                "evidence_ids": result["evidence_ids"],
                "grounding_note": result["grounding_note"],
                "error": result["error"],
            }
        )
        logger.info("Generated reply for %s (grounded=%s)", record["id"], result["grounded"])

    out_path = settings.project_root / "artifacts" / "predictions" / "reply_generation_examples.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %s", out_path)

    def _safe(text) -> str:
        # Windows console (cp1252) can't render some source characters (curly
        # quotes, emoji); this only affects the printed preview, never the
        # saved JSON, which stays full-fidelity UTF-8.
        return str(text).encode("ascii", errors="replace").decode("ascii")

    n_grounded = sum(1 for e in examples if e["grounded"])
    n_errors = sum(1 for e in examples if e["error"])
    print(f"\n=== GENERATED {len(examples)} EXAMPLE REPLIES ===")
    print(f"Grounded: {n_grounded}/{len(examples)}   Errors: {n_errors}/{len(examples)}")
    for e in examples[:3]:
        print(f"\n[{e['id']}] intent={e['gold_intent']} grounded={e['grounded']}")
        print(f"Customer: {_safe(e['customer_message'][:100])}")
        print(f"Reply: {_safe(e['draft_reply'])}")
        print(f"Evidence: {e['evidence_ids']}")


if __name__ == "__main__":
    main()
