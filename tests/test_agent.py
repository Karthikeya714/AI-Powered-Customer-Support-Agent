from unittest.mock import MagicMock

from src.agent import SupportAgent

STRONG_RETRIEVAL = [
    {"case_id": "case_1", "similarity": 0.9, "customer_message": "m", "brand_response": "r", "source_ids": [1], "weak_intent": None}
]


def _classifier_returning(intent, confidence, error=None):
    m = MagicMock()
    m.predict.return_value = {"intent": intent, "confidence": confidence, "reasoning": "x", "raw_response": "{}", "error": error}
    return m


def _retriever_returning(cases):
    m = MagicMock()
    m.retrieve.return_value = cases
    return m


def _generator_returning(draft_reply, grounded, evidence_ids=None, error=None):
    m = MagicMock()
    m.generate.return_value = {
        "draft_reply": draft_reply,
        "grounded": grounded,
        "evidence_ids": evidence_ids or [],
        "grounding_note": "note",
        "error": error,
    }
    return m


def test_auto_handle_path_calls_generator_and_returns_draft():
    classifier = _classifier_returning("playback_technical_issue", 0.95)
    retriever = _retriever_returning(STRONG_RETRIEVAL)
    generator = _generator_returning("Sorry for the trouble, please DM us.", grounded=True, evidence_ids=["case_1"])

    agent = SupportAgent(classifier=classifier, retriever=retriever, generator=generator)
    result = agent.handle("the app keeps crashing")

    assert result["decision"]["action"] == "AUTO_HANDLE"
    assert result["draft_reply"] == "Sorry for the trouble, please DM us."
    assert result["evidence_ids"] == ["case_1"]
    assert result["intent"] == {"label": "playback_technical_issue", "confidence": 0.95}
    assert result["retrieved_cases"] == [{"case_id": "case_1", "similarity": 0.9}]
    generator.generate.assert_called_once()


def test_low_confidence_escalates_without_calling_generator():
    classifier = _classifier_returning("playback_technical_issue", 0.3)
    retriever = _retriever_returning(STRONG_RETRIEVAL)
    generator = _generator_returning("should never be used", grounded=True)

    agent = SupportAgent(classifier=classifier, retriever=retriever, generator=generator)
    result = agent.handle("something vague")

    assert result["decision"]["action"] == "ESCALATE"
    assert result["draft_reply"] is None
    generator.generate.assert_not_called()  # the efficiency optimization actually fires


def test_high_risk_intent_escalates_without_calling_generator():
    classifier = _classifier_returning("account_security_compromise", 0.99)
    retriever = _retriever_returning(STRONG_RETRIEVAL)
    generator = _generator_returning("should never be used", grounded=True)

    agent = SupportAgent(classifier=classifier, retriever=retriever, generator=generator)
    result = agent.handle("someone stole my account")

    assert result["decision"]["action"] == "ESCALATE"
    assert result["draft_reply"] is None
    generator.generate.assert_not_called()


def test_ungrounded_reply_flips_decision_to_escalate_after_generation():
    classifier = _classifier_returning("playback_technical_issue", 0.95)
    retriever = _retriever_returning(STRONG_RETRIEVAL)
    generator = _generator_returning("a guessed reply", grounded=False)

    agent = SupportAgent(classifier=classifier, retriever=retriever, generator=generator)
    result = agent.handle("the app keeps crashing")

    generator.generate.assert_called_once()  # pre-check passed, so generation WAS attempted
    assert result["decision"]["action"] == "ESCALATE"
    assert "grounded" in result["decision"]["reason"]


def test_classification_failure_falls_back_to_escalate_not_a_crash():
    classifier = _classifier_returning(None, 0.0, error="simulated total failure")
    retriever = _retriever_returning(STRONG_RETRIEVAL)
    generator = _generator_returning("x", grounded=True)

    agent = SupportAgent(classifier=classifier, retriever=retriever, generator=generator)
    result = agent.handle("some message")

    assert result["intent"]["label"] == "UNKNOWN"
    assert result["decision"]["action"] == "ESCALATE"
    generator.generate.assert_not_called()


def test_retrieval_exception_falls_back_to_empty_results_not_a_crash():
    classifier = _classifier_returning("playback_technical_issue", 0.95)
    retriever = MagicMock()
    retriever.retrieve.side_effect = RuntimeError("index unavailable")
    generator = _generator_returning("x", grounded=True)

    agent = SupportAgent(classifier=classifier, retriever=retriever, generator=generator)
    result = agent.handle("some message")

    assert result["retrieved_cases"] == []
    assert result["decision"]["action"] == "ESCALATE"
    assert "no historical cases" in result["decision"]["reason"]
