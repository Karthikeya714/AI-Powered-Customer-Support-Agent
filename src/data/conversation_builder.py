"""Reconstruct conversation threads for one brand and build normalized
support-case records from them.

Reconstruction needs exact id-graph traversal (a customer's mid-thread reply
doesn't always repeat the "@brand" mention), unlike Phase 1's cheap
mention-regex approximation which was only used to rank/compare brands.
"""

from __future__ import annotations

import random
from collections import Counter, deque
from pathlib import Path

import pandas as pd

from src.config import get_logger
from src.data.loader import iter_raw_chunks

logger = get_logger(__name__)

LIGHT_COLUMNS = ["tweet_id", "author_id", "inbound", "created_at", "response_tweet_id", "in_response_to_tweet_id"]
FULL_COLUMNS = ["tweet_id", "author_id", "inbound", "created_at", "text", "response_tweet_id", "in_response_to_tweet_id"]

MAX_BFS_HOPS_PER_SEED = 15
MAX_COMPONENT_SIZE = 200  # safety valve; real Twitter support threads are far smaller
MAX_CONTEXT_TURNS = 5


def _parse_id_list(value) -> list[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [int(v) for v in str(value).split(",") if v]


def _first_id(value) -> int | None:
    ids = _parse_id_list(value)
    return ids[0] if ids else None


class TweetGraph:
    """A lightweight id -> (author_id, inbound, in_response_to, response_ids)
    index over the FULL dataset (no tweet text), built once via a chunked
    scan, used to correctly walk conversation threads without holding every
    tweet's text in memory.
    """

    def __init__(self, author_by_id: dict, inbound_by_id: dict, parent_by_id: dict, children_by_id: dict):
        self.author_by_id = author_by_id
        self.inbound_by_id = inbound_by_id
        self.parent_by_id = parent_by_id
        self.children_by_id = children_by_id

    def __len__(self) -> int:
        return len(self.author_by_id)

    @classmethod
    def build(cls, path: Path) -> "TweetGraph":
        chunks = list(iter_raw_chunks(path, usecols=LIGHT_COLUMNS))
        df = pd.concat(chunks, ignore_index=True)
        logger.info("Built lightweight tweet graph over %d rows", len(df))

        author_by_id = dict(zip(df["tweet_id"], df["author_id"]))
        inbound_by_id = dict(zip(df["tweet_id"], df["inbound"]))
        parent_by_id = {tid: _first_id(v) for tid, v in zip(df["tweet_id"], df["in_response_to_tweet_id"])}
        children_by_id = {tid: _parse_id_list(v) for tid, v in zip(df["tweet_id"], df["response_tweet_id"])}
        return cls(author_by_id, inbound_by_id, parent_by_id, children_by_id)

    def find_relevant_tweet_ids(self, brand: str) -> set[int]:
        """BFS out from every tweet authored by `brand` to collect the full
        set of tweet ids in those conversation threads (ancestors + descendants),
        regardless of whether intermediate tweets mention the brand by name.
        """
        seeds = [tid for tid, author in self.author_by_id.items() if author == brand and not self.inbound_by_id[tid]]
        logger.info("%d seed tweets authored by %s", len(seeds), brand)

        visited: set[int] = set()
        oversized_components = 0

        for seed in seeds:
            if seed in visited:
                continue
            component: set[int] = set()
            queue = deque([(seed, 0)])
            truncated = False
            while queue:
                tid, depth = queue.popleft()
                if tid in component or tid not in self.author_by_id or depth > MAX_BFS_HOPS_PER_SEED:
                    continue
                component.add(tid)
                if len(component) > MAX_COMPONENT_SIZE:
                    truncated = True
                    break
                neighbors = self.children_by_id.get(tid, [])
                parent = self.parent_by_id.get(tid)
                if parent is not None:
                    neighbors = neighbors + [parent]
                for n in neighbors:
                    if n not in component:
                        queue.append((n, depth + 1))
            if truncated:
                oversized_components += 1
            visited |= component

        if oversized_components:
            logger.warning(
                "%d of %d seed threads exceeded the %d-node safety cap and were truncated",
                oversized_components,
                len(seeds),
                MAX_COMPONENT_SIZE,
            )

        logger.info("Collected %d relevant tweet ids across %d threads", len(visited), len(seeds))
        return visited


def fetch_full_rows(path: Path, tweet_ids: set[int]) -> pd.DataFrame:
    """Second chunked pass: pull full rows (including text) only for the
    given tweet ids, instead of holding every tweet's text in memory."""
    matched_chunks = []
    for chunk in iter_raw_chunks(path, usecols=FULL_COLUMNS):
        matched = chunk[chunk["tweet_id"].isin(tweet_ids)]
        if len(matched) > 0:
            matched_chunks.append(matched)
    result = pd.concat(matched_chunks, ignore_index=True) if matched_chunks else pd.DataFrame(columns=FULL_COLUMNS)
    logger.info("Fetched %d full rows for %d requested tweet ids", len(result), len(tweet_ids))
    return result


def build_cases(full_rows: pd.DataFrame, brand: str, max_context_turns: int = MAX_CONTEXT_TURNS) -> tuple[list[dict], Counter]:
    """One case per brand reply tweet that can be traced back to a customer
    message, walking past any brand-authored intermediate tweets (e.g.
    multi-part "1/2" "2/2" replies) to find the nearest customer ancestor.
    """
    by_id = full_rows.set_index("tweet_id", drop=False).to_dict("index")

    stats = Counter()
    cases: list[dict] = []

    brand_replies = full_rows[
        (full_rows["author_id"] == brand) & (~full_rows["inbound"]) & (full_rows["in_response_to_tweet_id"].notna())
    ]
    stats["brand_reply_candidates"] = len(brand_replies)

    for row in brand_replies.itertuples():
        current_id = _first_id(row.in_response_to_tweet_id)
        depth = 0
        customer_row = None
        intermediate_brand_ids: list[int] = []
        while current_id is not None and current_id in by_id and depth < 10:
            node = by_id[current_id]
            if node["inbound"]:
                customer_row = node
                break
            intermediate_brand_ids.append(int(current_id))  # e.g. a "1/2" part of a multi-part reply
            current_id = _first_id(node["in_response_to_tweet_id"])
            depth += 1

        if customer_row is None:
            stats["no_customer_ancestor_found"] += 1
            continue

        context = []
        current_id = _first_id(customer_row["in_response_to_tweet_id"])
        depth = 0
        while current_id is not None and current_id in by_id and depth < max_context_turns:
            node = by_id[current_id]
            context.append({"speaker": "customer" if node["inbound"] else "brand", "text": node["text"], "tweet_id": int(current_id)})
            current_id = _first_id(node["in_response_to_tweet_id"])
            depth += 1
        context.reverse()  # oldest first

        source_ids = (
            [c["tweet_id"] for c in context]
            + [int(customer_row["tweet_id"])]
            + list(reversed(intermediate_brand_ids))
            + [int(row.tweet_id)]
        )

        cases.append(
            {
                "case_id": f"case_{row.tweet_id}",
                "conversation_id": f"conv_{source_ids[0]}",
                "brand": brand,
                "customer_message": customer_row["text"],
                "brand_response": row.text,
                "context": context,
                "customer_tweet_id": int(customer_row["tweet_id"]),
                "brand_tweet_id": int(row.tweet_id),
                "customer_timestamp": customer_row["created_at"],
                "brand_timestamp": row.created_at,
                "source_ids": source_ids,
            }
        )
        stats["cases_built"] += 1
        if context:
            stats["multi_turn_cases"] += 1

    return cases, stats


def assign_split(cases: list[dict], golden_pool_fraction: float, seed: int) -> None:
    """Deterministically tag each case "knowledge" or "golden_pool" in place.

    golden_pool is held out entirely from index-building/training; Phase 5
    samples the manually-labelled golden evaluation set only from this pool.
    """
    rng = random.Random(seed)
    indices = list(range(len(cases)))
    rng.shuffle(indices)
    n_golden = int(len(cases) * golden_pool_fraction)
    golden_indices = set(indices[:n_golden])
    for i, case in enumerate(cases):
        case["split"] = "golden_pool" if i in golden_indices else "knowledge"
