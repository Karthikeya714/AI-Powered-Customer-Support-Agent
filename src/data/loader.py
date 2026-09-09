"""Loading utilities for the raw Customer Support on Twitter dataset.

The raw CSV has ~3M rows. Use `iter_raw_chunks` for any full-dataset scan
(streaming, low memory) and `load_raw_data` only for small samples.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Sequence

import pandas as pd

from src.config import settings

RAW_COLUMNS = [
    "tweet_id",
    "author_id",
    "inbound",
    "created_at",
    "text",
    "response_tweet_id",
    "in_response_to_tweet_id",
]

# response_tweet_id / in_response_to_tweet_id can hold comma-separated lists
# of ids, so they must stay strings rather than being inferred as numeric.
DTYPES = {
    "tweet_id": "int64",
    "author_id": "str",
    "inbound": "bool",
    "created_at": "str",
    "text": "str",
    "response_tweet_id": "str",
    "in_response_to_tweet_id": "str",
}


def default_raw_path() -> Path:
    return settings.data_raw_dir / "customer-support-on-twitter" / "twcs.csv"


def _dtypes_for(usecols: Sequence[str] | None) -> dict:
    if usecols is None:
        return dict(DTYPES)
    return {col: dtype for col, dtype in DTYPES.items() if col in usecols}


def iter_raw_chunks(
    path: Path | None = None,
    chunksize: int = 200_000,
    usecols: Sequence[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Stream the raw dataset in chunks so the full 3M rows never sit in memory at once."""
    csv_path = path or default_raw_path()
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw dataset not found at {csv_path}")
    reader = pd.read_csv(
        csv_path,
        chunksize=chunksize,
        usecols=list(usecols) if usecols else None,
        dtype=_dtypes_for(usecols),
    )
    yield from reader


def load_raw_data(
    path: Path | None = None,
    sample_size: int | None = None,
    usecols: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Load the raw dataset into memory, optionally only the first `sample_size` rows.

    Intended for small samples/inspection only. For statistics over the full
    dataset, use `iter_raw_chunks` instead.
    """
    csv_path = path or default_raw_path()
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw dataset not found at {csv_path}")
    return pd.read_csv(
        csv_path,
        nrows=sample_size,
        usecols=list(usecols) if usecols else None,
        dtype=_dtypes_for(usecols),
    )
