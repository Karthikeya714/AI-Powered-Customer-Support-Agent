import json
from pathlib import Path

import pytest

from baselines.tfidf_classifier import build_pipeline, load_training_data, select_best_C

# Two clearly separable synthetic "intents" so a tiny model can actually learn something.
TRAIN_TEXTS = [
    "my password is wrong and I cannot log in to my account",
    "login failed, forgot my password again",
    "can't sign in, password reset not working",
    "locked out of my account, need to log in",
    "the song keeps skipping and playback freezes",
    "music stops playing randomly, playback is broken",
    "app crashes every time I try to play a song",
    "streaming keeps buffering and playback fails",
]
TRAIN_LABELS = [
    "account_access_issue",
    "account_access_issue",
    "account_access_issue",
    "account_access_issue",
    "playback_technical_issue",
    "playback_technical_issue",
    "playback_technical_issue",
    "playback_technical_issue",
]


@pytest.fixture
def training_data_file(tmp_path: Path) -> Path:
    path = tmp_path / "support_cases_with_intents.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for text, label in zip(TRAIN_TEXTS, TRAIN_LABELS):
            f.write(json.dumps({"case_id": "c", "customer_message": text, "weak_intent": label}) + "\n")
    return path


def test_load_training_data(training_data_file):
    texts, labels = load_training_data(training_data_file)
    assert texts == TRAIN_TEXTS
    assert labels == TRAIN_LABELS


def test_build_pipeline_fits_and_predicts():
    pipeline = build_pipeline(C=1.0)
    pipeline.fit(TRAIN_TEXTS, TRAIN_LABELS)
    preds = pipeline.predict(["I can't log in, password not accepted"])
    assert preds[0] == "account_access_issue"


def test_select_best_C_picks_a_candidate_and_reports_metrics():
    all_labels = sorted(set(TRAIN_LABELS))
    best_C, val_metrics = select_best_C(TRAIN_TEXTS, TRAIN_LABELS, TRAIN_TEXTS, TRAIN_LABELS, all_labels)

    from baselines.tfidf_classifier import CANDIDATE_C_VALUES

    assert best_C in CANDIDATE_C_VALUES
    assert "macro_f1" in val_metrics
    assert 0.0 <= val_metrics["macro_f1"] <= 1.0
