import json
from unittest.mock import MagicMock, patch

from evaluation.llm_judge import DIMENSIONS, LLMJudge, build_judge_prompt

RETRIEVED_CASES = [{"case_id": "case_1", "similarity": 0.9, "customer_message": "Where is my refund?", "brand_response": "Please DM your transaction ID."}]


def _fake_interaction(status="completed", output_text=None, errors=None):
    interaction = MagicMock()
    interaction.status = status
    interaction.output_text = output_text
    interaction.errors = errors
    return interaction


def test_build_judge_prompt_includes_message_evidence_and_reply():
    prompt = build_judge_prompt("Where's my refund", "billing_subscription_issue", RETRIEVED_CASES, "Please DM us your transaction ID.")
    assert "Where's my refund" in prompt
    assert "billing_subscription_issue" in prompt
    assert "case_1" in prompt
    assert "Please DM us your transaction ID." in prompt


def test_build_judge_prompt_handles_no_evidence():
    prompt = build_judge_prompt("some message", "some_intent", [], "some reply")
    assert "none" in prompt.lower()


@patch("evaluation.llm_judge.genai.Client")
def test_judge_success(mock_client_cls):
    output = json.dumps(
        {"correctness": 5, "groundedness": 5, "helpfulness": 4, "tone": 5, "no_hallucination": 5, "justification": "Directly grounded in the evidence."}
    )
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text=output)
    mock_client_cls.return_value = mock_client

    judge = LLMJudge(api_key="dummy")
    result = judge.judge("Where's my refund", "billing_subscription_issue", RETRIEVED_CASES, "Please DM us your transaction ID.")

    assert result["correctness"] == 5
    assert result["error"] is None
    for dim in DIMENSIONS:
        assert 1 <= result[dim] <= 5


@patch("evaluation.llm_judge.genai.Client")
def test_judge_rejects_out_of_range_scores(mock_client_cls):
    output = json.dumps({"correctness": 7, "groundedness": 5, "helpfulness": 4, "tone": 5, "no_hallucination": 5, "justification": "x"})
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _fake_interaction(output_text=output)
    mock_client_cls.return_value = mock_client

    judge = LLMJudge(api_key="dummy")
    result = judge.judge("m", "i", RETRIEVED_CASES, "r")

    assert result["correctness"] is None
    assert result["error"] is not None


@patch("evaluation.llm_judge.time.sleep", return_value=None)
@patch("evaluation.llm_judge.genai.Client")
def test_judge_retries_then_fails_safely(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = RuntimeError("simulated failure")
    mock_client_cls.return_value = mock_client

    judge = LLMJudge(api_key="dummy")
    result = judge.judge("m", "i", RETRIEVED_CASES, "r")

    assert all(result[dim] is None for dim in DIMENSIONS)
    assert result["error"] is not None
    assert mock_client.interactions.create.call_count == 3
