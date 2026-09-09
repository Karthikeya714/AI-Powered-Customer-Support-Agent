"""Exploratory tool for discovering candidate intent themes from real
customer messages. This is NOT the final classifier — it assists a human in
proposing categories, which get manually reviewed, merged, and written into
`src/intents/labels.py`.

Uses TF-IDF + KMeans rather than an LLM: no LLM_API_KEY is configured for
this project, and this also produces the vectorizer/clustering machinery
reused to weakly-label the knowledge pool for baseline training (Phase 7
needs labeled non-golden data; see scripts/build_intent_dataset.py).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from src.config import get_logger

logger = get_logger(__name__)

TFIDF_PARAMS = dict(max_features=5000, ngram_range=(1, 2), stop_words="english", min_df=5, sublinear_tf=True)


def load_knowledge_customer_messages(support_cases_path: Path) -> pd.DataFrame:
    """Load only split=="knowledge" cases — intent discovery must never look
    at golden_pool, even indirectly, to avoid shaping category definitions
    around examples that will later be used for evaluation."""
    rows = []
    with support_cases_path.open(encoding="utf-8") as f:
        for line in f:
            case = json.loads(line)
            if case["split"] == "knowledge":
                rows.append({"case_id": case["case_id"], "customer_message": case["customer_message"]})
    df = pd.DataFrame(rows)
    logger.info("Loaded %d knowledge-split customer messages", len(df))
    return df


def fit_tfidf_kmeans(texts: list[str], n_clusters: int, seed: int, tfidf_params: dict | None = None) -> tuple[TfidfVectorizer, KMeans, list[int]]:
    vectorizer = TfidfVectorizer(**(tfidf_params if tfidf_params is not None else TFIDF_PARAMS))
    matrix = vectorizer.fit_transform(texts)
    kmeans = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    labels = kmeans.fit_predict(matrix).tolist()
    return vectorizer, kmeans, labels


def top_terms_per_cluster(vectorizer: TfidfVectorizer, kmeans: KMeans, n_terms: int = 15) -> dict[int, list[str]]:
    terms = vectorizer.get_feature_names_out()
    result = {}
    for cluster_id, center in enumerate(kmeans.cluster_centers_):
        top_indices = center.argsort()[::-1][:n_terms]
        result[cluster_id] = [terms[i] for i in top_indices]
    return result


def sample_examples_per_cluster(texts: list[str], labels: list[int], n_clusters: int, n_per_cluster: int, seed: int) -> dict[int, list[str]]:
    rng = random.Random(seed)
    by_cluster: dict[int, list[str]] = {c: [] for c in range(n_clusters)}
    for text, label in zip(texts, labels):
        by_cluster[label].append(text)
    return {c: rng.sample(msgs, min(n_per_cluster, len(msgs))) for c, msgs in by_cluster.items()}
