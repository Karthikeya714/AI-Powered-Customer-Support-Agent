import json
from pathlib import Path

import pytest

from src.intents.discovery import fit_tfidf_kmeans, load_knowledge_customer_messages, sample_examples_per_cluster, top_terms_per_cluster
from src.intents.labels import CLUSTER_TO_INTENT, INTENTS


@pytest.fixture
def support_cases_file(tmp_path: Path) -> Path:
    cases = [
        {"case_id": "c1", "customer_message": "my password is not working and I cannot log in", "split": "knowledge"},
        {"case_id": "c2", "customer_message": "login failed, forgot my password", "split": "knowledge"},
        {"case_id": "c3", "customer_message": "the song keeps skipping and freezing during playback", "split": "knowledge"},
        {"case_id": "c4", "customer_message": "playback freezes and the app crashes constantly", "split": "knowledge"},
        {"case_id": "c5", "customer_message": "this message should not appear, wrong split", "split": "golden_pool"},
    ]
    path = tmp_path / "support_cases.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")
    return path


def test_load_knowledge_customer_messages_excludes_golden_pool(support_cases_file):
    df = load_knowledge_customer_messages(support_cases_file)
    assert len(df) == 4
    assert "wrong split" not in " ".join(df["customer_message"])


def test_fit_tfidf_kmeans_separates_distinct_topics(support_cases_file):
    df = load_knowledge_customer_messages(support_cases_file)
    texts = df["customer_message"].tolist()
    vectorizer, kmeans, labels = fit_tfidf_kmeans(texts, n_clusters=2, seed=42, tfidf_params={"min_df": 1, "stop_words": "english"})

    # the two login-themed messages should cluster together, separately
    # from the two playback-themed messages
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[0] != labels[2]

    top_terms = top_terms_per_cluster(vectorizer, kmeans, n_terms=5)
    assert set(top_terms.keys()) == {0, 1}
    assert all(len(terms) == 5 for terms in top_terms.values())


def test_sample_examples_per_cluster_is_deterministic(support_cases_file):
    df = load_knowledge_customer_messages(support_cases_file)
    texts = df["customer_message"].tolist()
    _, _, labels = fit_tfidf_kmeans(texts, n_clusters=2, seed=42, tfidf_params={"min_df": 1, "stop_words": "english"})

    result_a = sample_examples_per_cluster(texts, labels, n_clusters=2, n_per_cluster=1, seed=7)
    result_b = sample_examples_per_cluster(texts, labels, n_clusters=2, n_per_cluster=1, seed=7)
    assert result_a == result_b
    assert set(result_a.keys()) == {0, 1}


def test_labels_are_internally_consistent():
    # every mapped cluster must point to a real intent (or None for noise)
    for cluster_id, intent in CLUSTER_TO_INTENT.items():
        assert intent is None or intent in INTENTS, f"cluster {cluster_id} maps to undefined intent {intent}"

    for name, definition in INTENTS.items():
        assert definition["description"], f"{name} has no description"
        assert len(definition["examples"]) >= 2, f"{name} needs at least 2 grounded examples"

    assert 8 <= len(INTENTS) <= 15
