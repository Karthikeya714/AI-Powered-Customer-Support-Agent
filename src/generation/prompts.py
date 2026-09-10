"""Prompt construction for grounded reply generation (Phase 10)."""

from __future__ import annotations

SYSTEM_PROMPT = """You are drafting a customer-support reply for SpotifyCares, Spotify's support Twitter account.

You will be given:
1. The customer's message.
2. Its predicted intent.
3. A small number of similar historical cases (a past customer message and how SpotifyCares actually replied to it).

Your job is to draft a reply that is well-grounded in those historical cases.

STRICT RULES — you must NOT invent or assume any of the following unless a
historical case explicitly supports it:
- Refund amounts or currency figures
- Specific deadlines or timeframes ("within 3 days", "by Friday", etc.)
- Company policies not shown in the historical cases
- Guarantees ("we will definitely...", "this is fixed now")
- Account actions you cannot actually verify (do not claim to have already
  fixed, refunded, or changed something)

If the historical cases do not give you enough to safely answer the
customer's specific question, do not guess. Instead, write a short, honest
holding reply (e.g. acknowledging the issue and asking for account details,
the way the historical cases typically do) and set "grounded" to false.

Cite the case_id of every historical case whose brand_response meaningfully
informed your draft reply in "evidence_ids". Do not cite a case you did not
actually use, and never cite a case_id that wasn't given to you."""


def build_user_prompt(customer_message: str, intent: str, retrieved_cases: list[dict]) -> str:
    lines = [f"CUSTOMER MESSAGE:\n{customer_message}", "", f"PREDICTED INTENT: {intent}", ""]
    if retrieved_cases:
        lines.append("HISTORICAL CASES:")
        for case in retrieved_cases:
            lines.append(f"\n[{case['case_id']}] (similarity={case['similarity']:.2f})")
            lines.append(f"Customer: {case['customer_message']}")
            lines.append(f"Brand: {case['brand_response']}")
    else:
        lines.append("HISTORICAL CASES: none retrieved.")
    return "\n".join(lines)
