from src.config import settings
from src.escalation.decision import decide

STRONG_CASE = [{"case_id": "case_1", "similarity": 0.9, "customer_message": "m", "brand_response": "r"}]


def test_auto_handle_when_everything_looks_safe():
    result = decide(
        customer_message="the app keeps crashing when I play a song",
        intent="playback_technical_issue",
        intent_confidence=0.95,
        retrieved_cases=STRONG_CASE,
        reply_grounded=True,
    )
    assert result["decision"] == "AUTO_HANDLE"
    assert "playback_technical_issue" in result["reason"]


def test_escalates_high_risk_intent_even_with_high_confidence():
    result = decide(
        customer_message="my account got hacked",
        intent="account_security_compromise",
        intent_confidence=0.99,
        retrieved_cases=STRONG_CASE,
        reply_grounded=True,
    )
    assert result["decision"] == "ESCALATE"
    assert "high-risk" in result["reason"]


def test_escalates_low_intent_confidence():
    result = decide(
        customer_message="something about my account",
        intent="account_access_issue",
        intent_confidence=0.3,
        retrieved_cases=STRONG_CASE,
    )
    assert result["decision"] == "ESCALATE"
    assert "confidence" in result["reason"]


def test_escalates_low_retrieval_similarity():
    weak_case = [{"case_id": "case_1", "similarity": 0.2, "customer_message": "m", "brand_response": "r"}]
    result = decide(
        customer_message="a fairly generic message",
        intent="playback_technical_issue",
        intent_confidence=0.9,
        retrieved_cases=weak_case,
    )
    assert result["decision"] == "ESCALATE"
    assert "similarity" in result["reason"]


def test_escalates_when_nothing_retrieved():
    result = decide(
        customer_message="a fairly generic message",
        intent="playback_technical_issue",
        intent_confidence=0.9,
        retrieved_cases=[],
    )
    assert result["decision"] == "ESCALATE"
    assert "no historical cases" in result["reason"]


def test_escalates_ungrounded_reply():
    result = decide(
        customer_message="a fairly generic message",
        intent="playback_technical_issue",
        intent_confidence=0.9,
        retrieved_cases=STRONG_CASE,
        reply_grounded=False,
    )
    assert result["decision"] == "ESCALATE"
    assert "grounded" in result["reason"]


def test_escalates_repeated_complaint_language():
    result = decide(
        customer_message="this is the 3rd time I'm reporting this, still not fixed",
        intent="playback_technical_issue",
        intent_confidence=0.9,
        retrieved_cases=STRONG_CASE,
    )
    assert result["decision"] == "ESCALATE"
    assert "repeated" in result["reason"]


def test_escalates_legal_sensitive_language():
    result = decide(
        customer_message="I'm going to sue if this isn't fixed",
        intent="billing_subscription_issue",
        intent_confidence=0.9,
        retrieved_cases=STRONG_CASE,
    )
    assert result["decision"] == "ESCALATE"
    assert "legal" in result["reason"]


def test_missing_reply_grounded_is_not_penalized_when_none():
    # reply_grounded=None means generation hasn't run yet (e.g. called
    # right after classification+retrieval, before generation) -- should
    # not itself trigger escalation, unlike an explicit False
    result = decide(
        customer_message="the app keeps crashing",
        intent="playback_technical_issue",
        intent_confidence=0.95,
        retrieved_cases=STRONG_CASE,
        reply_grounded=None,
    )
    assert result["decision"] == "AUTO_HANDLE"


def test_thresholds_are_read_from_config():
    assert settings.min_intent_confidence == 0.6
    assert settings.min_retrieval_similarity == 0.70
