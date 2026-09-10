"""Phase 9 — build the FAISS retrieval index over knowledge-split support
cases. golden_pool is never indexed (see src/retrieval/index.py).

Usage:
    python -m scripts.build_index

Outputs:
    data/index/knowledge.faiss           (gitignored, regenerable)
    data/index/knowledge_metadata.jsonl  (gitignored, regenerable)
"""

from __future__ import annotations

import json

from src.config import get_logger, settings
from src.retrieval.embeddings import embed_texts, load_embedding_model
from src.retrieval.index import DEFAULT_INDEX_DIR, build_index, save_index

logger = get_logger(__name__)


def load_knowledge_cases(support_cases_path=None) -> list[dict]:
    path = support_cases_path or (settings.data_processed_dir / "support_cases.jsonl")
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            case = json.loads(line)
            if case["split"] == "knowledge":
                cases.append(case)
    return cases


def load_weak_intents(path=None) -> dict[str, str]:
    """Phase 4's weak intent labels, keyed by case_id — only ~49% of
    knowledge cases have one (the rest fell into discarded/noise
    clusters); missing ones are left as None in the index metadata."""
    path = path or (settings.data_processed_dir / "support_cases_with_intents.jsonl")
    if not path.exists():
        return {}
    weak_intents = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            weak_intents[row["case_id"]] = row["weak_intent"]
    return weak_intents


def main() -> None:
    cases = load_knowledge_cases()
    logger.info("Loaded %d knowledge-split cases to index", len(cases))
    weak_intents = load_weak_intents()

    texts = [c["customer_message"] for c in cases]
    model = load_embedding_model()
    embeddings = embed_texts(texts, model=model)
    logger.info("Computed embeddings: shape=%s", embeddings.shape)

    index = build_index(embeddings)

    metadata = [
        {
            "case_id": c["case_id"],
            "customer_message": c["customer_message"],
            "brand_response": c["brand_response"],
            "source_ids": c["source_ids"],
            "weak_intent": weak_intents.get(c["case_id"]),
        }
        for c in cases
    ]
    save_index(index, metadata, DEFAULT_INDEX_DIR)

    print(f"\nBuilt index over {len(cases)} knowledge-split cases -> {DEFAULT_INDEX_DIR}")


if __name__ == "__main__":
    main()
