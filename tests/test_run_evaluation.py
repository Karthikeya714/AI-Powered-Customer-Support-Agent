import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evaluation.run_evaluation import load_classifier_predictions, run_pipeline_over_golden_set

GOLDEN_RECORDS = [
    {"id": "gold_0001", "customer_message": "the app keeps crashing", "gold_intent": "playback_technical_issue", "gold_action": "AUTO_HANDLE"},
    {"id": "gold_0002", "customer_message": "someone stole my account", "gold_intent": "account_security_compromise", "gold_action": "ESCALATE"},
]

CLASSIFIER_PREDICTIONS = {
    "gold_0001": {"id": "gold_0001", "predicted_intent": "playback_technical_issue", "confidence": 0.95, "error": None},
    "gold_0002": {"id": "gold_0002", "predicted_intent": "account_security_compromise", "confidence": 0.99, "error": None},
}

STRONG_RETRIEVAL = [{"case_id": "case_1", "similarity": 0.9, "customer_message": "m", "brand_response": "r", "source_ids": [1], "weak_intent": None}]


@pytest.fixture
def classifier_predictions_file(tmp_path: Path) -> Path:
    path = tmp_path / "ai_classifier_predictions.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in CLASSIFIER_PREDICTIONS.values():
            f.write(json.dumps(row) + "\n")
    return path


def test_load_classifier_predictions(classifier_predictions_file):
    predictions = load_classifier_predictions(classifier_predictions_file)
    assert predictions["gold_0001"]["predicted_intent"] == "playback_technical_issue"
    assert predictions["gold_0002"]["confidence"] == 0.99


def _retriever_returning(cases):
    m = MagicMock()
    m.retrieve.return_value = cases
    return m


def test_run_pipeline_skips_generation_for_high_risk_intent(tmp_path):
    retriever = _retriever_returning(STRONG_RETRIEVAL)
    cache_path = tmp_path / "cache.jsonl"

    from unittest.mock import patch

    with patch("evaluation.run_evaluation.ReplyGenerator") as mock_gen_cls:
        mock_generator = MagicMock()
        mock_generator.generate.return_value = {
            "draft_reply": "please DM us your details",
            "grounded": True,
            "evidence_ids": ["case_1"],
            "grounding_note": "note",
            "error": None,
        }
        mock_gen_cls.return_value = mock_generator

        results = run_pipeline_over_golden_set(GOLDEN_RECORDS, CLASSIFIER_PREDICTIONS, retriever, cache_path)

    by_id = {r["id"]: r for r in results}
    assert by_id["gold_0001"]["predicted_action"] == "AUTO_HANDLE"
    assert by_id["gold_0002"]["predicted_action"] == "ESCALATE"
    assert by_id["gold_0002"]["draft_reply"] is None
    # generator was called for the auto-handle-leaning case, not the high-risk one
    assert mock_generator.generate.call_count == 1


def test_run_pipeline_resumes_from_cache(tmp_path):
    cache_path = tmp_path / "cache.jsonl"
    # pre-populate the cache with a successful result for gold_0001 only
    cache_path.write_text(json.dumps({"id": "gold_0001", "predicted_action": "AUTO_HANDLE", "error": None}) + "\n", encoding="utf-8")

    retriever = _retriever_returning(STRONG_RETRIEVAL)

    from unittest.mock import patch

    with patch("evaluation.run_evaluation.ReplyGenerator") as mock_gen_cls:
        mock_generator = MagicMock()
        mock_generator.generate.return_value = {"draft_reply": None, "grounded": False, "evidence_ids": [], "grounding_note": None, "error": None}
        mock_gen_cls.return_value = mock_generator

        results = run_pipeline_over_golden_set(GOLDEN_RECORDS, CLASSIFIER_PREDICTIONS, retriever, cache_path)

    assert len(results) == 2
    by_id = {r["id"]: r for r in results}
    assert by_id["gold_0001"]["predicted_action"] == "AUTO_HANDLE"  # came from cache, untouched
    # only gold_0002 needed fresh work
    mock_generator.generate.assert_not_called()  # gold_0002 is high-risk -> pre-check escalates -> no generation
