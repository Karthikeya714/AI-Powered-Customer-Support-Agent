"""Embedding generation for retrieval — encodes customer messages (both
historical knowledge-pool cases and new queries) into vectors using a
local sentence-transformers model.

Local and free by design: this project already depends on one
rate-limited LLM API (Gemini, Phase 8) for intent classification.
Embeddings don't need an LLM's reasoning ability, so running them locally
avoids a second network dependency, avoids rate limits on ~37k documents,
and keeps retrieval fully reproducible offline once the model is cached.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import get_logger, settings

logger = get_logger(__name__)

_model_cache: dict[str, SentenceTransformer] = {}


def load_embedding_model(model_name: str | None = None) -> SentenceTransformer:
    model_name = model_name or settings.embedding_model
    if model_name not in _model_cache:
        logger.info("Loading embedding model %s", model_name)
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def embed_texts(texts: list[str], model: SentenceTransformer | None = None, batch_size: int = 64) -> np.ndarray:
    """Returns L2-normalized float32 embeddings, so inner-product search
    over them is equivalent to cosine similarity."""
    model = model or load_embedding_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 200,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return np.asarray(embeddings, dtype="float32")
