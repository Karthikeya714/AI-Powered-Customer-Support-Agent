import json
from pathlib import Path

import pytest

from baselines.majority import compute_majority_intent, predict


@pytest.fixture
def intent_distribution_file(tmp_path: Path) -> Path:
    path = tmp_path / "intent_distribution.json"
    path.write_text(
        json.dumps({"total_labeled": 10, "intent_counts": {"a": 3, "b": 7, "c": 1}}),
        encoding="utf-8",
    )
    return path


def test_compute_majority_intent(intent_distribution_file):
    assert compute_majority_intent(intent_distribution_file) == "b"


def test_predict_repeats_majority_for_every_record():
    golden_records = [
        {"id": "gold_0001", "gold_intent": "a"},
        {"id": "gold_0002", "gold_intent": "b"},
        {"id": "gold_0003", "gold_intent": "b"},
    ]

    predictions = predict(golden_records, majority_intent="b")

    assert all(p["predicted_intent"] == "b" for p in predictions)
    assert [p["gold_intent"] for p in predictions] == ["a", "b", "b"]
    assert [p["id"] for p in predictions] == ["gold_0001", "gold_0002", "gold_0003"]
