"""Phase 14 — LLM-as-judge for generated reply quality.

Scores a (customer_message, retrieved evidence, draft_reply) triple on 5
dimensions, 1-5 each, following the plan's suggested rubric. Framed so
higher is always better on every dimension, including hallucination
(scored as "no_hallucination": 5 = no unsupported claims, 1 = severe
hallucination) — avoids a mixed-direction rubric that's easy to misread
when aggregating scores.

Kept self-contained (own retry/backoff, like src/intents/classifier.py
and src/generation/reply_generator.py) rather than extracting a shared
LLM-call helper — this is now the third near-identical copy of that
logic, which is reason enough to extract it, but Phase 13's live
evaluation run was still using ReplyGenerator when this was written;
touching shared code mid-run was avoided on principle (see
DECISION_LOG.md). Worth doing as a follow-up cleanup once nothing is
depending on the current file's exact behavior.
"""

from __future__ import annotations

import re
import time

from google import genai
from pydantic import BaseModel, Field, ValidationError

from src.config import get_logger, settings

logger = get_logger(__name__)

REQUEST_TIMEOUT_MS = 30_000
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 45.0
RATE_LIMIT_MAX_BACKOFF_SECONDS = 90.0
_RETRY_AFTER_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)

RUBRIC_DESCRIPTION = """Score the drafted customer-support reply on 5 dimensions, each 1-5 (5=best, 1=worst):

1. correctness: Does the reply correctly address what the customer specifically asked or reported?
2. groundedness: Are the reply's claims actually supported by the historical evidence provided? (5 = every claim traces to the evidence; 1 = the reply asserts things the evidence doesn't support)
3. helpfulness: Would this reply actually help the customer make progress, even if it's just an honest holding response?
4. tone: Is the tone appropriate for customer support — professional and empathetic, not curt or robotic?
5. no_hallucination: Does the reply avoid inventing policies, refund amounts, deadlines, guarantees, or account actions not shown in the evidence? (5 = invents nothing; 1 = invents significant unsupported claims)

Be strict and impartial. Do not give a high score just because the reply sounds polite — check the actual claims against the evidence."""


class ReplyJudgment(BaseModel):
    correctness: int = Field(ge=1, le=5)
    groundedness: int = Field(ge=1, le=5)
    helpfulness: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)
    no_hallucination: int = Field(ge=1, le=5)
    justification: str = Field(description="One or two sentences explaining the scores, especially any score below 4")


DIMENSIONS = ["correctness", "groundedness", "helpfulness", "tone", "no_hallucination"]


def build_judge_prompt(customer_message: str, intent: str, retrieved_cases: list[dict], draft_reply: str) -> str:
    lines = [RUBRIC_DESCRIPTION, "", f"CUSTOMER MESSAGE:\n{customer_message}", "", f"INTENT: {intent}", ""]
    if retrieved_cases:
        lines.append("HISTORICAL EVIDENCE PROVIDED TO THE REPLY-DRAFTING MODEL:")
        for case in retrieved_cases:
            lines.append(f"\n[{case.get('case_id', '?')}] Customer: {case.get('customer_message', '')}")
            lines.append(f"Brand: {case.get('brand_response', '')}")
    else:
        lines.append("HISTORICAL EVIDENCE PROVIDED: none.")
    lines.append(f"\nDRAFTED REPLY TO SCORE:\n{draft_reply}")
    return "\n".join(lines)


class LLMJudge:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or settings.llm_model
        self.client = genai.Client(api_key=api_key or settings.llm_api_key, http_options={"timeout": REQUEST_TIMEOUT_MS})

    def judge(self, customer_message: str, intent: str, retrieved_cases: list[dict], draft_reply: str) -> dict:
        prompt = build_judge_prompt(customer_message, intent, retrieved_cases, draft_reply)

        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                interaction = self.client.interactions.create(
                    model=self.model,
                    system_instruction="You are a strict, impartial quality reviewer for customer-support replies.",
                    input=prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": ReplyJudgment.model_json_schema(),
                    },
                )
                if interaction.status != "completed":
                    raise RuntimeError(f"interaction status={interaction.status!r} errors={interaction.errors!r}")

                parsed = ReplyJudgment.model_validate_json(interaction.output_text)
                return {**parsed.model_dump(), "error": None}
            except (RuntimeError, ValidationError, ValueError) as e:
                last_error = str(e)
                logger.warning("Judge attempt %d/%d failed: %s", attempt, MAX_RETRIES, last_error)
                backoff = RETRY_BACKOFF_SECONDS * attempt
            except Exception as e:
                last_error = str(e)
                logger.warning("Judge attempt %d/%d raised %s: %s", attempt, MAX_RETRIES, type(e).__name__, last_error)
                if getattr(e, "status_code", None) == 429 or getattr(e, "code", None) == 429:
                    match = _RETRY_AFTER_RE.search(last_error)
                    backoff = min(float(match.group(1)) + 2.0, RATE_LIMIT_MAX_BACKOFF_SECONDS) if match else RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
                else:
                    backoff = RETRY_BACKOFF_SECONDS * attempt

            if attempt < MAX_RETRIES:
                time.sleep(backoff)

        logger.error("Judge failed after %d attempts: %s", MAX_RETRIES, last_error)
        return {dim: None for dim in DIMENSIONS} | {"justification": None, "error": last_error}
