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


@patch("src.generation.reply_generator.time.sleep", return_value=None)
@patch("src.generation.reply_generator.genai.Client")
def test_generate_retries_then_fails_safely(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = RuntimeError("simulated API failure")
    mock_client_cls.return_value = mock_client

    generator = ReplyGenerator(api_key="dummy")
    result = generator.generate("some message", "some_intent", RETRIEVED_CASES)

    assert result["draft_reply"] is None
    assert result["grounded"] is False
    assert result["error"] is not None
    assert mock_client.interactions.create.call_count == MAX_RETRIES
