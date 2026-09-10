import json
from unittest.mock import MagicMock, patch

from src.generation.prompts import build_user_prompt
from src.generation.reply_generator import MAX_RETRIES, ReplyGenerator

RETRIEVED_CASES = [
    {"case_id": "case_1", "similarity": 0.9, "customer_message": "Where is my refund?", "brand_response": "Please DM your transaction ID."},
    {"case_id": "case_2", "similarity": 0.8, "customer_message": "Refund pending", "brand_response": "We'll check the status."},
]


def _fake_interaction(status="completed", output_text=None, errors=None):
    interaction = MagicMock()
    interaction.status = status
    interaction.output_text = output_text
    interaction.errors = errors
    return interaction


def test_build_user_prompt_includes_cases_and_intent():
    prompt = build_user_prompt("My refund hasn't arrived", "billing_subscription_issue", RETRIEVED_CASES)
    assert "My refund hasn't arrived" in prompt
    assert "billing_subscription_issue" in prompt
    assert "case_1" in prompt
    assert "Please DM your transaction ID." in prompt


def test_build_user_prompt_handles_no_retrieved_cases():
    prompt = build_user_prompt("some message", "some_intent", [])
    assert "none retrieved" in prompt.lower()


@patch("src.generation.reply_generator.genai.Client")
def test_generate_success(mock_client_cls):
    output = json.dumps(
        {
            "draft_reply": "Sorry for the delay. Please DM us your transaction ID so we can check.",
            "grounded": True,
            "evidence_ids": ["case_1", "case_2"],
            "grounding_note": "Both cases show the standard refund-status request pattern.",
        }
    )
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text=output)
    mock_client_cls.return_value = mock_client

    generator = ReplyGenerator(api_key="dummy")
    result = generator.generate("Where's my refund", "billing_subscription_issue", RETRIEVED_CASES)

    assert result["grounded"] is True
    assert result["evidence_ids"] == ["case_1", "case_2"]
    assert result["error"] is None


@patch("src.generation.reply_generator.genai.Client")
def test_generate_drops_hallucinated_evidence_ids(mock_client_cls):
    # model cites a case_id that was never retrieved -- must be filtered, not trusted
    output = json.dumps(
        {
            "draft_reply": "We'll look into it.",
            "grounded": True,
            "evidence_ids": ["case_1", "case_999_not_retrieved"],
            "grounding_note": "Based on similar cases.",
        }
    )
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text=output)
    mock_client_cls.return_value = mock_client

    generator = ReplyGenerator(api_key="dummy")
    result = generator.generate("Where's my refund", "billing_subscription_issue", RETRIEVED_CASES)

    assert result["evidence_ids"] == ["case_1"]


@patch("src.generation.reply_generator.genai.Client")
def test_generate_normalizes_evidence_ids_missing_case_prefix(mock_client_cls):
    # observed real behavior: the model sometimes cites "1" instead of "case_1"
    # -- a real, valid citation, just missing the prefix; must not be dropped
    output = json.dumps(
        {
            "draft_reply": "We'll look into it.",
            "grounded": True,
            "evidence_ids": ["1"],
            "grounding_note": "Based on case 1.",
        }
    )
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text=output)
    mock_client_cls.return_value = mock_client

    generator = ReplyGenerator(api_key="dummy")
    result = generator.generate("Where's my refund", "billing_subscription_issue", RETRIEVED_CASES)

    assert result["evidence_ids"] == ["case_1"]


@patch("src.generation.reply_generator.time.sleep", return_value=None)
@patch("src.generation.reply_generator.genai.Client")
def test_generate_retries_then_fails_safely(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = RuntimeError("simulated API failure")
    mock_client_cls.return_value = mock_client

    # fallback_model=None isolates single-model retry behavior from whatever
    # LLM_FALLBACK_MODEL happens to be set in the environment
    generator = ReplyGenerator(api_key="dummy", fallback_model=None)
    result = generator.generate("some message", "some_intent", RETRIEVED_CASES)

    assert result["draft_reply"] is None
    assert result["grounded"] is False
    assert result["error"] is not None
    assert mock_client.interactions.create.call_count == MAX_RETRIES


@patch("src.generation.reply_generator.time.sleep", return_value=None)
@patch("src.generation.reply_generator.genai.Client")
def test_generate_falls_back_to_second_model_when_primary_exhausted(mock_client_cls, mock_sleep):
    success_output = json.dumps(
        {
            "draft_reply": "We'll look into it.",
            "grounded": True,
            "evidence_ids": ["case_1"],
            "grounding_note": "Based on case 1.",
        }
    )
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = [
        RuntimeError("simulated primary failure"),
        RuntimeError("simulated primary failure"),
        RuntimeError("simulated primary failure"),
        _fake_interaction(output_text=success_output),
    ]
    mock_client_cls.return_value = mock_client

    generator = ReplyGenerator(api_key="dummy", model="primary-model", fallback_model="backup-model")
    result = generator.generate("some message", "billing_subscription_issue", RETRIEVED_CASES)

    assert result["error"] is None
    assert result["model"] == "backup-model"
    assert mock_client.interactions.create.call_count == 4  # 3 failed on primary + 1 successful on fallback
    assert mock_client.interactions.create.call_args.kwargs["model"] == "backup-model"


@patch("src.generation.reply_generator.time.sleep", return_value=None)
@patch("src.generation.reply_generator.genai.Client")
def test_generate_fails_safely_when_primary_and_fallback_both_exhausted(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = RuntimeError("simulated failure")
    mock_client_cls.return_value = mock_client

    generator = ReplyGenerator(api_key="dummy", model="primary-model", fallback_model="backup-model")
    result = generator.generate("some message", "some_intent", RETRIEVED_CASES)

    assert result["draft_reply"] is None
    assert result["error"] is not None
    assert mock_client.interactions.create.call_count == 6  # MAX_RETRIES on each of two models
