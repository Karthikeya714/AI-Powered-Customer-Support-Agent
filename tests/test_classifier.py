import json
from unittest.mock import MagicMock, patch

from src.intents.classifier import IntentClassifier, IntentPrediction, SYSTEM_PROMPT
from src.intents.labels import INTENTS


def _fake_interaction(status="completed", output_text=None, errors=None):
    interaction = MagicMock()
    interaction.status = status
    interaction.output_text = output_text
    interaction.errors = errors
    return interaction


def test_system_prompt_mentions_every_intent():
    for name in INTENTS:
        assert name in SYSTEM_PROMPT


def test_intent_prediction_rejects_unknown_intent():
    payload = {"intent": "not_a_real_intent", "confidence": 0.9, "reasoning": "x"}
    try:
        IntentPrediction.model_validate(payload)
        assert False, "expected a validation error for an unapproved intent"
    except Exception:
        pass


@patch("src.intents.classifier.genai.Client")
def test_predict_success(mock_client_cls):
    valid_intent = next(iter(INTENTS))
    output = json.dumps({"intent": valid_intent, "confidence": 0.87, "reasoning": "matches the description"})
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text=output)
    mock_client_cls.return_value = mock_client

    classifier = IntentClassifier(api_key="dummy")
    result = classifier.predict("some customer message")

    assert result["intent"] == valid_intent
    assert result["confidence"] == 0.87
    assert result["error"] is None


@patch("src.intents.classifier.time.sleep", return_value=None)
@patch("src.intents.classifier.genai.Client")
def test_predict_retries_then_fails_safely(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = RuntimeError("simulated API failure")
    mock_client_cls.return_value = mock_client

    # fallback_model=None isolates single-model retry behavior from whatever
    # LLM_FALLBACK_MODEL happens to be set in the environment
    classifier = IntentClassifier(api_key="dummy", fallback_model=None)
    result = classifier.predict("some customer message")

    assert result["intent"] is None
    assert result["confidence"] == 0.0
    assert result["error"] is not None
    assert mock_client.interactions.create.call_count == 3  # MAX_RETRIES


@patch("src.intents.classifier.genai.Client")
def test_predict_fails_safely_on_invalid_json(mock_client_cls):
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text="not valid json")
    mock_client_cls.return_value = mock_client

    classifier = IntentClassifier(api_key="dummy", fallback_model=None)
    result = classifier.predict("some customer message")

    assert result["intent"] is None
    assert result["error"] is not None


@patch("src.intents.classifier.time.sleep", return_value=None)
@patch("src.intents.classifier.genai.Client")
def test_predict_falls_back_to_second_model_when_primary_exhausted(mock_client_cls, mock_sleep):
    valid_intent = next(iter(INTENTS))
    success_output = json.dumps({"intent": valid_intent, "confidence": 0.9, "reasoning": "matches"})
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = [
        RuntimeError("simulated primary failure"),
        RuntimeError("simulated primary failure"),
        RuntimeError("simulated primary failure"),
        _fake_interaction(output_text=success_output),
    ]
    mock_client_cls.return_value = mock_client

    classifier = IntentClassifier(api_key="dummy", model="primary-model", fallback_model="backup-model")
    result = classifier.predict("some customer message")

    assert result["intent"] == valid_intent
    assert result["error"] is None
    assert result["model"] == "backup-model"
    assert mock_client.interactions.create.call_count == 4  # 3 failed on primary + 1 successful on fallback
    assert mock_client.interactions.create.call_args.kwargs["model"] == "backup-model"


@patch("src.intents.classifier.time.sleep", return_value=None)
@patch("src.intents.classifier.genai.Client")
def test_predict_fails_safely_when_primary_and_fallback_both_exhausted(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = RuntimeError("simulated failure")
    mock_client_cls.return_value = mock_client

    classifier = IntentClassifier(api_key="dummy", model="primary-model", fallback_model="backup-model")
    result = classifier.predict("some customer message")

    assert result["intent"] is None
    assert result["error"] is not None
    assert mock_client.interactions.create.call_count == 6  # MAX_RETRIES on each of two models
