"""Phase 11 — escalation decision engine.

Escalation is a feature, not a failure: the agent should prefer sending a
case to a human whenever it lacks sufficient evidence or the issue looks
high-risk, rather than confidently auto-handling something it shouldn't.

Thresholds (MIN_INTENT_CONFIDENCE, MIN_RETRIEVAL_SIMILARITY) are read from
config, calibrated on a validation sample drawn from golden_pool cases NOT
in golden_set — never fit to the golden set itself (see
scripts/calibrate_escalation_thresholds.py and DECISION_LOG.md).
"""

from __future__ import annotations

import re

from src.config import settings

# Intents that are inherently high-risk regardless of confidence/evidence
# quality — the same principle applied while hand-labeling the golden
# set's gold_action (docs/golden_set_methodology.md): these always warrant
# a human, because a confidently-wrong automated reply here is
# specifically dangerous (fraud/security), not just unhelpful.
HIGH_RISK_INTENTS = {"account_security_compromise"}

_REPEATED_COMPLAINT_RE = re.compile(
    r"\b(again|repeatedly|several times|multiple times|\d+(st|nd|rd|th)\s+time|"
    r"keeps?\s+happening|ignored|no response|haven'?t heard)\b",
    re.IGNORECASE,
)
_LEGAL_SENSITIVE_RE = re.compile(
    r"\b(lawyer|legal action|sue|lawsuit|attorney|discriminat|threat(en)?(ing)?)\b",
    re.IGNORECASE,
)


def decide(
    customer_message: str,
    intent: str,
    intent_confidence: float,
    retrieved_cases: list[dict],
    reply_grounded: bool | None = None,
) -> dict:
    """Returns {"decision": "AUTO_HANDLE" | "ESCALATE", "reason": "..."}.

    reply_grounded is optional (None if generation hasn't run yet, or
    failed) — treated the same as False, since no verified-grounded reply
    exists to safely send.
    """
    reasons: list[str] = []

    if intent in HIGH_RISK_INTENTS:
        reasons.append(f"'{intent}' is a high-risk intent that always requires human review")

    if intent_confidence < settings.min_intent_confidence:
        reasons.append(f"intent confidence {intent_confidence:.2f} is below the {settings.min_intent_confidence:.2f} threshold")

    top1_similarity = retrieved_cases[0]["similarity"] if retrieved_cases else 0.0
    if not retrieved_cases:
        reasons.append("no historical cases were retrieved")
    elif top1_similarity < settings.min_retrieval_similarity:
        reasons.append(f"best retrieval similarity {top1_similarity:.2f} is below the {settings.min_retrieval_similarity:.2f} threshold")

    if reply_grounded is False:
        reasons.append("the generated reply was not grounded in the retrieved evidence")

    if _LEGAL_SENSITIVE_RE.search(customer_message):
        reasons.append("message contains legal/highly sensitive language")

    if _REPEATED_COMPLAINT_RE.search(customer_message):
        reasons.append("message indicates a repeated/unresolved complaint")

    if reasons:
        return {"decision": "ESCALATE", "reason": "; ".join(reasons)}

    return {
        "decision": "AUTO_HANDLE",
        "reason": (
            f"Common '{intent}' issue with sufficient intent confidence ({intent_confidence:.2f}), "
            f"strong retrieval evidence (similarity {top1_similarity:.2f}), and no risk signals detected."
        ),
    }
