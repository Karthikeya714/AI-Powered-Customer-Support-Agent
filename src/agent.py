"""Phase 12 — the complete customer-support agent: one clean interface
(`SupportAgent.handle(message)`) chaining intent classification, historical
case retrieval, grounded reply generation, and the escalation decision.

Two-stage escalation check, not one: classify + retrieve first (retrieval
is free/local; classification is one LLM call), then check whether the
case is ALREADY escalate-worthy on those signals alone (low confidence,
low similarity, a high-risk intent, risky message language) *before*
spending a second LLM call on generation. If so, skip generation entirely
(draft_reply=None). This isn't just theoretical efficiency — this project
hit real free-tier LLM quota limits during Phase 8 (see DECISION_LOG.md),
so avoiding a wasted second call per already-escalated case is a genuine,
demonstrated cost/reliability win.

Each dependency (classifier/retriever/generator) can be injected, so tests
can exercise the orchestration logic (which signals trigger which path,
error handling, field wiring) without making real API calls.
"""

from __future__ import annotations

import json
import sys

from src.config import get_logger
from src.escalation.decision import decide
from src.generation.reply_generator import ReplyGenerator
from src.intents.classifier import IntentClassifier
from src.retrieval.retriever import Retriever

logger = get_logger(__name__)


class SupportAgent:
    def __init__(self, classifier=None, retriever=None, generator=None):
        self.classifier = classifier or IntentClassifier()
        self.retriever = retriever or Retriever()
        self.generator = generator or ReplyGenerator()

    def handle(self, customer_message: str) -> dict:
        intent_result = self.classifier.predict(customer_message)
        if intent_result["error"]:
            logger.warning("Intent classification failed, falling back to UNKNOWN/0.0 confidence: %s", intent_result["error"])
        intent = intent_result["intent"] or "UNKNOWN"
        confidence = intent_result["confidence"]

        try:
            retrieved_cases = self.retriever.retrieve(customer_message)
        except Exception as e:  # retrieval failure must not crash the pipeline (architecture doc §26)
            logger.warning("Retrieval failed, proceeding with no retrieved cases: %s", e)
            retrieved_cases = []

        # Stage 1: would this already escalate on intent/retrieval signals alone?
        pre_decision = decide(customer_message, intent, confidence, retrieved_cases, reply_grounded=None)

        draft_reply = None
        evidence_ids: list[str] = []
        grounding_note = None
        reply_grounded = None

        if pre_decision["decision"] == "AUTO_HANDLE":
            gen_result = self.generator.generate(customer_message, intent, retrieved_cases)
            if gen_result["error"]:
                logger.warning("Reply generation failed: %s", gen_result["error"])
            draft_reply = gen_result["draft_reply"]
            evidence_ids = gen_result["evidence_ids"]
            grounding_note = gen_result["grounding_note"]
            reply_grounded = gen_result["grounded"]

        # Stage 2: final decision, now also accounting for the generated reply's own groundedness
        final_decision = decide(customer_message, intent, confidence, retrieved_cases, reply_grounded=reply_grounded)

        return {
            "customer_message": customer_message,
            "intent": {"label": intent, "confidence": confidence},
            "retrieved_cases": [{"case_id": c["case_id"], "similarity": c["similarity"]} for c in retrieved_cases],
            "draft_reply": draft_reply,
            "evidence_ids": evidence_ids,
            "grounding_note": grounding_note,
            "decision": {"action": final_decision["decision"], "reason": final_decision["reason"]},
        }


def main() -> None:
    agent = SupportAgent()
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        print(json.dumps(agent.handle(message), indent=2, ensure_ascii=False))
        return

    print("Enter a customer message (Ctrl+C to quit):")
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        print(json.dumps(agent.handle(message), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
