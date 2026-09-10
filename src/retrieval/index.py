"""Build/save/load the FAISS vector index over knowledge-split support
cases, plus the case metadata needed to turn a retrieved vector back into
a (customer_message, brand_response, source_ids) result.

The index is built from knowledge-split data only. golden_pool must never
be indexed — retrieval/generation are evaluated against the golden set,
so indexing it would leak the evaluation targets into the system being
evaluated (see DECISION_LOG.md's data-leakage entries from earlier phases).

Index files live in data/index/, gitignored (regenerable via
scripts/build_index.py, per the project's reproducibility requirements —
not a source of truth to commit).
"""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

from src.config import get_logger, settings

logger = get_logger(__name__)

DEFAULT_INDEX_DIR = settings.project_root / "data" / "index"


def build_index(embeddings: np.ndarray) -> faiss.Index:
    """Exact inner-product search (cosine similarity, since embeddings are
    pre-normalized). ~37k documents is small enough that an approximate
    index (IVF/HNSW) would be unnecessary complexity for no real speed
    benefit — exact search is instant at this scale."""
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    return index


def save_index(index: faiss.Index, metadata: list[dict], index_dir: Path = DEFAULT_INDEX_DIR) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "knowledge.faiss"))
    with (index_dir / "knowledge_metadata.jsonl").open("w", encoding="utf-8") as f:
        for row in metadata:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("Saved index (%d vectors) and metadata to %s", index.ntotal, index_dir)


def load_index(index_dir: Path = DEFAULT_INDEX_DIR) -> tuple[faiss.Index, list[dict]]:
    index = faiss.read_index(str(index_dir / "knowledge.faiss"))
    metadata = []
    with (index_dir / "knowledge_metadata.jsonl").open(encoding="utf-8") as f:
        for line in f:
            metadata.append(json.loads(line))
    if index.ntotal != len(metadata):
        raise ValueError(f"Index/metadata mismatch: {index.ntotal} vectors vs {len(metadata)} metadata rows")
    return index, metadata


def load_case_metadata_by_id(index_dir: Path = DEFAULT_INDEX_DIR) -> dict[str, dict]:
    """case_id -> {customer_message, brand_response, ...} lookup, without
    loading the FAISS index itself — for enriching a {case_id, similarity}
    pair (e.g. from a saved prediction file) back into full evidence text."""
    metadata = []
    with (index_dir / "knowledge_metadata.jsonl").open(encoding="utf-8") as f:
        for line in f:
            metadata.append(json.loads(line))
    return {row["case_id"]: row for row in metadata}
