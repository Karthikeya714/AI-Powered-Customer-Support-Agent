"""Row-level and text-level cleaning for the raw Twitter support data."""

from __future__ import annotations

import re

import pandas as pd

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse newlines/repeated whitespace. Does not strip mentions, URLs,
    or punctuation — those are left intact for later phases to decide on."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def is_usable_text(text: str | None, min_length: int = 2) -> bool:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return False
    normalized = normalize_text(str(text))
    return len(normalized) >= min_length


def find_duplicate_mask(df: pd.DataFrame) -> pd.Series:
    """True for rows that are exact duplicates (same author, timestamp, text)
    of an earlier row — keeps the first occurrence, flags the rest."""
    key = df["author_id"].fillna("") + "|" + df["created_at"].fillna("") + "|" + df["text"].fillna("")
    return key.duplicated(keep="first")
