import numpy as np
import pytest

from evaluation.evaluate_retrieval import compute_retrieval_stats
from src.retrieval.index import build_index, load_index, save_index
from src.retrieval.retriever import Retriever


def _toy_embeddings():
    # 4 unit vectors spread around a circle so nearest-neighbor is unambiguous
    return np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [0.0, -1.0]], dtype="float32")


def _toy_metadata():
    return [
        {"case_id": "c1", "customer_message": "m1", "brand_response": "r1", "source_ids": [1], "weak_intent": "a"},
        {"case_id": "c2", "customer_message": "m2", "brand_response": "r2", "source_ids": [2], "weak_intent": "b"},
        {"case_id": "c3", "customer_message": "m3", "brand_response": "r3", "source_ids": [3], "weak_intent": None},
        {"case_id": "c4", "customer_message": "m4", "brand_response": "r4", "source_ids": [4], "weak_intent": "a"},
    ]


def test_build_save_load_index_roundtrip(tmp_path):
    embeddings = _toy_embeddings()
    metadata = _toy_metadata()

    index = build_index(embeddings)
    assert index.ntotal == 4

    save_index(index, metadata, index_dir=tmp_path)
    loaded_index, loaded_metadata = load_index(index_dir=tmp_path)

    assert loaded_index.ntotal == 4
    assert loaded_metadata == metadata

    query = np.array([[0.9, 0.1]], dtype="float32")  # close to c1's vector [1, 0]
    similarities, indices = loaded_index.search(query, 2)
    assert loaded_metadata[indices[0][0]]["case_id"] == "c1"


def test_load_index_rejects_mismatched_metadata(tmp_path):
    save_index(build_index(_toy_embeddings()), _toy_metadata()[:2], index_dir=tmp_path)  # metadata truncated on purpose
    with pytest.raises(ValueError):
        load_index(index_dir=tmp_path)


def test_retriever_retrieve_returns_ranked_results(tmp_path, monkeypatch):
    save_index(build_index(_toy_embeddings()), _toy_metadata(), index_dir=tmp_path)

    # avoid depending on a real embedding model in this test: any query text
    # maps to a fixed vector close to c1's
    monkeypatch.setattr("src.retrieval.retriever.load_embedding_model", lambda: "fake-model")
    monkeypatch.setattr("src.retrieval.retriever.embed_texts", lambda texts, model=None: np.array([[0.9, 0.1]], dtype="float32"))

    retriever = Retriever(index_dir=tmp_path, top_k=2)
    results = retriever.retrieve("anything")

    assert len(results) == 2
    assert results[0]["case_id"] == "c1"
    assert results[0]["similarity"] > results[1]["similarity"]
    assert results[0]["weak_intent"] == "a"
    assert results[0]["source_ids"] == [1]


class _FakeRetriever:
    def __init__(self, canned_results):
        self.canned_results = canned_results

    def retrieve(self, customer_message, top_k=None):
        return self.canned_results.get(customer_message, [])


def test_compute_retrieval_stats():
    golden_records = [
        {"customer_message": "q1", "gold_intent": "a"},
        {"customer_message": "q2", "gold_intent": "b"},
        {"customer_message": "q3", "gold_intent": "c"},  # will get zero results
    ]
    canned = {
        "q1": [{"similarity": 0.9, "weak_intent": "a"}, {"similarity": 0.8, "weak_intent": "a"}],
        "q2": [{"similarity": 0.5, "weak_intent": "x"}, {"similarity": 0.4, "weak_intent": None}],
        "q3": [],
    }
    retriever = _FakeRetriever(canned)

    stats = compute_retrieval_stats(golden_records, retriever, top_k=2)

    assert stats["n_golden_queries"] == 3
    assert stats["n_zero_results"] == 1
    assert stats["top1_similarity"]["mean"] == pytest.approx((0.9 + 0.5) / 2)
    # q1: both results have weak_intent "a" == gold_intent "a" -> agreement 1.0
    assert stats["intent_agreement_at_k"]["by_gold_intent"]["a"] == pytest.approx(1.0)
    # q2: only 1 of 2 results has a weak_intent, and it's "x" != gold "b" -> agreement 0.0
    assert stats["intent_agreement_at_k"]["by_gold_intent"]["b"] == pytest.approx(0.0)
    # q3 got zero results and is excluded entirely
    assert "c" not in stats["intent_agreement_at_k"]["by_gold_intent"]
