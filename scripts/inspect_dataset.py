"""Phase 1 — inspect the raw Customer Support on Twitter dataset.

Runs two streaming passes over the ~3M-row CSV (never loading it fully into
memory) to answer: what does the dataset contain, which brands have enough
usable conversations, are customer/brand messages identifiable, and can
conversations be reconstructed.

Usage:
    python scripts/inspect_dataset.py

Outputs:
    data/processed/brand_statistics.csv
    data/processed/dataset_summary.json
    data/processed/sample_conversations.txt
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from src.config import get_logger, settings
from src.data.loader import default_raw_path, iter_raw_chunks

logger = get_logger(__name__)

CHUNKSIZE = 200_000
N_SHORTLIST = 20  # brands carried from pass A into the deeper pass B analysis
N_SAMPLE_CONVERSATIONS_PER_BRAND = 3


# ---------------------------------------------------------------------------
# Pass A: cheap scan (3 columns) to rank brands by volume and pick a shortlist
# ---------------------------------------------------------------------------


def pass_a_rank_brands(path: Path) -> dict:
    usecols = ["author_id", "inbound", "in_response_to_tweet_id"]
    total_rows = 0
    inbound_counts = Counter()  # True -> customer rows, False -> brand rows
    brand_outbound_count = Counter()  # brand -> total tweets sent by that account
    brand_reply_count = Counter()  # brand -> tweets that are replies (support interactions)

    for chunk in iter_raw_chunks(path, chunksize=CHUNKSIZE, usecols=usecols):
        total_rows += len(chunk)
        inbound_counts.update(chunk["inbound"].value_counts().to_dict())

        brand_rows = chunk[~chunk["inbound"]]
        brand_outbound_count.update(brand_rows["author_id"].value_counts().to_dict())

        replies = brand_rows[brand_rows["in_response_to_tweet_id"].notna()]
        brand_reply_count.update(replies["author_id"].value_counts().to_dict())

    logger.info("Pass A complete: %d rows scanned, %d distinct brand accounts", total_rows, len(brand_outbound_count))
    return {
        "total_rows": total_rows,
        "inbound_counts": dict(inbound_counts),
        "brand_outbound_count": brand_outbound_count,
        "brand_reply_count": brand_reply_count,
    }


# ---------------------------------------------------------------------------
# Pass B: full-column scan for global data-quality stats + shortlisted-brand detail
# ---------------------------------------------------------------------------


def _build_mention_regex(handles: list[str]) -> re.Pattern:
    escaped = [re.escape(h) for h in handles]
    return re.compile(r"@(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _build_mention_mask_regex(handles: list[str]) -> re.Pattern:
    escaped = [re.escape(h) for h in handles]
    return re.compile(r"@(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def pass_b_full_scan(path: Path, shortlist_handles: list[str]) -> dict:
    mention_re = _build_mention_regex(shortlist_handles)
    mention_mask_re = _build_mention_mask_regex(shortlist_handles)
    handle_lower_to_canonical = {h.lower(): h for h in shortlist_handles}
    shortlist_set = set(shortlist_handles)

    missing_counts = Counter()
    seen_tweet_ids: set[int] = set()
    duplicate_tweet_id_count = 0
    seen_content_hashes: set[int] = set()
    duplicate_content_count = 0

    has_response_count = 0  # got at least one reply (response_tweet_id not null)
    has_in_response_to_count = 0  # is itself a reply (in_response_to_tweet_id not null)

    date_min = None
    date_max = None
    month_histogram = Counter()

    customer_mentions_per_brand = Counter()
    buffered_rows: list[pd.DataFrame] = []

    for chunk in iter_raw_chunks(path, chunksize=CHUNKSIZE):
        for col in chunk.columns:
            missing_counts[col] += int(chunk[col].isna().sum())

        for tid in chunk["tweet_id"]:
            if tid in seen_tweet_ids:
                duplicate_tweet_id_count += 1
            else:
                seen_tweet_ids.add(tid)

        content_keys = chunk["author_id"].fillna("") + "|" + chunk["created_at"].fillna("") + "|" + chunk["text"].fillna("")
        for key in content_keys:
            h = hash(key)
            if h in seen_content_hashes:
                duplicate_content_count += 1
            else:
                seen_content_hashes.add(h)

        has_response_count += int(chunk["response_tweet_id"].notna().sum())
        has_in_response_to_count += int(chunk["in_response_to_tweet_id"].notna().sum())

        parsed_dates = pd.to_datetime(chunk["created_at"], format="%a %b %d %H:%M:%S %z %Y", errors="coerce")
        chunk_min, chunk_max = parsed_dates.min(), parsed_dates.max()
        if pd.notna(chunk_min):
            date_min = chunk_min if date_min is None else min(date_min, chunk_min)
        if pd.notna(chunk_max):
            date_max = chunk_max if date_max is None else max(date_max, chunk_max)
        month_histogram.update(parsed_dates.dropna().dt.strftime("%Y-%m").value_counts().to_dict())

        customer_rows = chunk[chunk["inbound"]]
        for text in customer_rows["text"].fillna(""):
            for match in mention_re.finditer(text):
                canonical = handle_lower_to_canonical.get(match.group(1).lower())
                if canonical:
                    customer_mentions_per_brand[canonical] += 1
                    break  # count each customer tweet once, for its first mentioned brand

        relevant = chunk[(~chunk["inbound"] & chunk["author_id"].isin(shortlist_set)) | (chunk["inbound"] & chunk["text"].fillna("").str.contains(mention_mask_re))]
        if len(relevant) > 0:
            buffered_rows.append(relevant)

    logger.info("Pass B complete: duplicate tweet_ids=%d, duplicate content rows=%d", duplicate_tweet_id_count, duplicate_content_count)

    buffered = pd.concat(buffered_rows, ignore_index=True) if buffered_rows else pd.DataFrame(columns=chunk.columns)

    return {
        "missing_counts": dict(missing_counts),
        "duplicate_tweet_id_count": duplicate_tweet_id_count,
        "duplicate_content_count": duplicate_content_count,
        "has_response_count": has_response_count,
        "has_in_response_to_count": has_in_response_to_count,
        "date_min": str(date_min) if date_min is not None else None,
        "date_max": str(date_max) if date_max is not None else None,
        "month_histogram": dict(sorted(month_histogram.items())),
        "customer_mentions_per_brand": dict(customer_mentions_per_brand),
        "buffered_rows": buffered,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def build_brand_statistics(pass_a: dict, pass_b: dict, shortlist_handles: list[str]) -> pd.DataFrame:
    rows = []
    for brand in shortlist_handles:
        brand_messages = pass_a["brand_outbound_count"].get(brand, 0)
        conversations = pass_a["brand_reply_count"].get(brand, 0)
        customer_messages = pass_b["customer_mentions_per_brand"].get(brand, 0)
        rows.append(
            {
                "brand": brand,
                "total_tweets": brand_messages + customer_messages,
                "conversations": conversations,
                "customer_messages": customer_messages,
                "brand_messages": brand_messages,
            }
        )
    df = pd.DataFrame(rows).sort_values("total_tweets", ascending=False).reset_index(drop=True)
    return df


def sample_conversations(buffered: pd.DataFrame, shortlist_handles: list[str], per_brand: int) -> str:
    """Reconstruct a few short threads per shortlisted brand from the buffered rows."""
    if buffered.empty:
        return "No buffered rows available for sampling."

    by_id = {row.tweet_id: row for row in buffered.itertuples()}
    lines: list[str] = []

    for brand in shortlist_handles:
        brand_replies = buffered[(~buffered["inbound"]) & (buffered["author_id"] == brand) & (buffered["in_response_to_tweet_id"].notna())]
        if brand_replies.empty:
            continue
        sample = brand_replies.sample(n=min(per_brand, len(brand_replies)), random_state=settings.random_seed)

        lines.append(f"\n=== {brand} ===")
        for row in sample.itertuples():
            lines.append(f"\n--- conversation rooted at brand tweet {row.tweet_id} ---")
            # walk backwards: brand reply -> customer tweet it replies to -> what that replies to
            chain = [row]
            current = row
            for _ in range(4):
                parent_id = getattr(current, "in_response_to_tweet_id", None)
                if pd.isna(parent_id):
                    break
                try:
                    parent_id = int(str(parent_id).split(",")[0])
                except ValueError:
                    break
                parent = by_id.get(parent_id)
                if parent is None:
                    break
                chain.append(parent)
                current = parent
            for turn in reversed(chain):
                speaker = "CUSTOMER" if turn.inbound else "BRAND"
                lines.append(f"  [{speaker}] ({turn.tweet_id}) {turn.text}")

    return "\n".join(lines)


def main() -> None:
    raw_path = default_raw_path()
    logger.info("Reading raw dataset from %s", raw_path)

    pass_a = pass_a_rank_brands(raw_path)
    shortlist_handles = [b for b, _ in pass_a["brand_outbound_count"].most_common(N_SHORTLIST)]
    logger.info("Shortlisted %d brands by outbound tweet volume: %s", len(shortlist_handles), shortlist_handles)

    pass_b = pass_b_full_scan(raw_path, shortlist_handles)

    brand_stats = build_brand_statistics(pass_a, pass_b, shortlist_handles)

    settings.data_processed_dir.mkdir(parents=True, exist_ok=True)
    brand_stats_path = settings.data_processed_dir / "brand_statistics.csv"
    brand_stats.to_csv(brand_stats_path, index=False)
    logger.info("Wrote %s", brand_stats_path)

    summary = {
        "total_rows": pass_a["total_rows"],
        "customer_rows": pass_a["inbound_counts"].get(True, 0),
        "brand_rows": pass_a["inbound_counts"].get(False, 0),
        "distinct_brand_accounts": len(pass_a["brand_outbound_count"]),
        "shortlisted_brands": shortlist_handles,
        "missing_value_counts": pass_b["missing_counts"],
        "duplicate_tweet_id_count": pass_b["duplicate_tweet_id_count"],
        "duplicate_content_row_count": pass_b["duplicate_content_count"],
        "rows_with_a_reply": pass_b["has_response_count"],
        "rows_that_are_a_reply": pass_b["has_in_response_to_count"],
        "date_min": pass_b["date_min"],
        "date_max": pass_b["date_max"],
        "monthly_tweet_counts": pass_b["month_histogram"],
    }
    summary_path = settings.data_processed_dir / "dataset_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info("Wrote %s", summary_path)

    convo_text = sample_conversations(pass_b["buffered_rows"], shortlist_handles[:8], N_SAMPLE_CONVERSATIONS_PER_BRAND)
    convo_path = settings.data_processed_dir / "sample_conversations.txt"
    convo_path.write_text(convo_text, encoding="utf-8")
    logger.info("Wrote %s", convo_path)

    print("\n=== TOP BRANDS BY TOTAL TWEETS ===")
    print(brand_stats.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
