"""Phase 9 — retrieve historically similar support cases for a new
customer message.

Input: a customer message.
Output: the top-k most similar historical (customer_message,
brand_response) pairs from the knowledge index, with similarity scores
and source_ids preserved for traceability.
"""

from __future__ import annotations

from pathlib import Path

from src.config import get_logger, settings
from src.retrieval.embeddings import embed_texts, load_embedding_model
from src.retrieval.index import DEFAULT_INDEX_DIR, load_index

logger = get_logger(__name__)


class Retriever:
    def __init__(self, index_dir: Path = DEFAULT_INDEX_DIR, top_k: int | None = None):
        self.index, self.metadata = load_index(index_dir)
        self.model = load_embedding_model()
        self.default_top_k = top_k or settings.top_k
        logger.info("Retriever ready: %d indexed cases, default top_k=%d", self.index.ntotal, self.default_top_k)

    def retrieve(self, customer_message: str, top_k: int | None = None) -> list[dict]:
        k = top_k or self.default_top_k
        query_embedding = embed_texts([customer_message], model=self.model)
        similarities, indices = self.index.search(query_embedding, k)

        results = []
        for similarity, idx in zip(similarities[0], indices[0]):
            if idx == -1:  # FAISS pads with -1 when fewer than k results exist
                continue
            case = self.metadata[idx]
            results.append(
                {
                    "case_id": case["case_id"],
                    "similarity": float(similarity),
                    "customer_message": case["customer_message"],
                    "brand_response": case["brand_response"],
                    "source_ids": case["source_ids"],
                    "weak_intent": case.get("weak_intent"),
                }
            )
        return results
