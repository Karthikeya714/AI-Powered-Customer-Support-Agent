"""Phase 10 — grounded reply generation.

Given a customer message, its predicted intent, and retrieved historical
cases, drafts a reply grounded in that evidence. The LLM must not invent
policies, amounts, deadlines, guarantees, or unverifiable account actions —
if the evidence is insufficient it should say so (grounded=false) rather
than hallucinate a confident answer (see src/generation/prompts.py for the
exact grounding rules given to the model).

Kept fully self-contained (its own retry/backoff, not shared with
src/intents/classifier.py) rather than extracting a common LLM-call helper
right now — Phase 8's classifier is mid-evaluation-run at time of writing,
and touching its already-tested code for a DRY cleanup is unnecessary risk
for no behavioral benefit. Worth revisiting once Phase 14 (LLM judge) adds
a third call site.
"""

from __future__ import annotations

import re
import time

from google import genai
from pydantic import BaseModel, Field, ValidationError

from src.config import get_logger, settings
from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)

REQUEST_TIMEOUT_MS = 30_000
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 45.0
RATE_LIMIT_MAX_BACKOFF_SECONDS = 90.0
_RETRY_AFTER_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)


class ReplyGeneration(BaseModel):
    draft_reply: str = Field(description="The drafted customer-support reply, or a short honest holding reply if evidence is insufficient")
    grounded: bool = Field(description="True only if the reply's claims are actually supported by the given historical cases")
    evidence_ids: list[str] = Field(default_factory=list, description="case_ids of historical cases that meaningfully informed this reply")
    grounding_note: str = Field(description="One brief sentence explaining the grounding decision")


class ReplyGenerator:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or settings.llm_model
        self.client = genai.Client(api_key=api_key or settings.llm_api_key, http_options={"timeout": REQUEST_TIMEOUT_MS})

    def generate(self, customer_message: str, intent: str, retrieved_cases: list[dict]) -> dict:
        """Returns a dict with draft_reply/grounded/evidence_ids/grounding_note
        on success, or draft_reply=None and a populated "error" on failure —
        callers must handle both (fail safely, never crash on bad LLM output;
        treating a failed generation as grounded=False is a safe default for
        Phase 11's escalation logic to key off)."""
        user_prompt = build_user_prompt(customer_message, intent, retrieved_cases)
        valid_case_ids = {c["case_id"] for c in retrieved_cases}

        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                interaction = self.client.interactions.create(
                    model=self.model,
                    system_instruction=SYSTEM_PROMPT,
                    input=user_prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": ReplyGeneration.model_json_schema(),
                    },
                )
                if interaction.status != "completed":
                    raise RuntimeError(f"interaction status={interaction.status!r} errors={interaction.errors!r}")

                parsed = ReplyGeneration.model_validate_json(interaction.output_text)

                kept_ids = [cid for cid in parsed.evidence_ids if cid in valid_case_ids]
                dropped = set(parsed.evidence_ids) - set(kept_ids)
                if dropped:
                    logger.warning("Dropping evidence_ids not among retrieved cases: %s", dropped)

                return {
                    "draft_reply": parsed.draft_reply,
                    "grounded": parsed.grounded,
                    "evidence_ids": kept_ids,
                    "grounding_note": parsed.grounding_note,
                    "error": None,
                }
            except (RuntimeError, ValidationError, ValueError) as e:
                last_error = str(e)
                logger.warning("Generation attempt %d/%d failed: %s", attempt, MAX_RETRIES, last_error)
                backoff = RETRY_BACKOFF_SECONDS * attempt
            except Exception as e:  # network/rate-limit/transient API errors
                last_error = str(e)
                logger.warning("Generation attempt %d/%d raised %s: %s", attempt, MAX_RETRIES, type(e).__name__, last_error)
                if getattr(e, "status_code", None) == 429 or getattr(e, "code", None) == 429:
                    match = _RETRY_AFTER_RE.search(last_error)
                    backoff = min(float(match.group(1)) + 2.0, RATE_LIMIT_MAX_BACKOFF_SECONDS) if match else RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
                else:
                    backoff = RETRY_BACKOFF_SECONDS * attempt

            if attempt < MAX_RETRIES:
                logger.info("Retrying in %.1fs", backoff)
                time.sleep(backoff)

        logger.error("Generation failed after %d attempts: %s", MAX_RETRIES, last_error)
        return {"draft_reply": None, "grounded": False, "evidence_ids": [], "grounding_note": None, "error": last_error}
