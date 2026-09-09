from pathlib import Path
from textwrap import dedent

import pytest

from src.data.conversation_builder import TweetGraph, assign_split, build_cases, fetch_full_rows

# Three SpotifyCares threads (customer author ids 6001/6002/6003 are kept
# visually distinct from tweet ids to avoid confusion when reading this file):
#   thread 1 (tweet ids 100-101): single-turn, customer mentions the brand
#   thread 2 (tweet ids 200-203): multi-turn — tweet 200 is the customer's
#     opening message with NO @mention, only reachable via graph traversal,
#     not Phase 1's regex approach
#   thread 3 (tweet ids 300-302): a multi-part brand reply ("1/2" then
#     "2/2") — both parts must resolve back to the same customer message
# Plus one unrelated brand (OtherBrand) that must never appear in results.
SAMPLE_CSV = dedent(
    """\
    tweet_id,author_id,inbound,created_at,text,response_tweet_id,in_response_to_tweet_id
    100,SpotifyCares,False,Mon Jan 01 00:00:10 +0000 2018,"sure, we can help!",,101
    101,6001,True,Mon Jan 01 00:00:00 +0000 2018,@SpotifyCares my music stopped,100,
    200,6002,True,Mon Jan 01 01:00:00 +0000 2018,I have an issue,201,
    201,SpotifyCares,False,Mon Jan 01 01:01:00 +0000 2018,@6002 can you tell us more?,202,200
    202,6002,True,Mon Jan 01 01:02:00 +0000 2018,@SpotifyCares it's about playback,203,201
    203,SpotifyCares,False,Mon Jan 01 01:03:00 +0000 2018,@6002 try restarting the app,,202
    300,6003,True,Mon Jan 01 02:00:00 +0000 2018,@SpotifyCares billing issue,301,
    301,SpotifyCares,False,Mon Jan 01 02:01:00 +0000 2018,@6003 checking now (1/2),302,300
    302,SpotifyCares,False,Mon Jan 01 02:02:00 +0000 2018,@6003 refunded (2/2),,301
    900,OtherBrand,False,Mon Jan 01 03:00:00 +0000 2018,@6099 unrelated reply,,901
    901,6099,True,Mon Jan 01 02:59:00 +0000 2018,@OtherBrand unrelated issue,900,
    """
)


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "twcs_sample.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")
    return path


def test_find_relevant_tweet_ids_excludes_other_brands(sample_csv):
    graph = TweetGraph.build(sample_csv)
    ids = graph.find_relevant_tweet_ids("SpotifyCares")
    assert ids == {100, 101, 200, 201, 202, 203, 300, 301, 302}


def test_build_cases_reconstructs_threads(sample_csv):
    graph = TweetGraph.build(sample_csv)
    relevant_ids = graph.find_relevant_tweet_ids("SpotifyCares")
    full_rows = fetch_full_rows(sample_csv, relevant_ids)

    cases, stats = build_cases(full_rows, "SpotifyCares")
    by_case_id = {c["case_id"]: c for c in cases}

    # one case per brand reply tweet: 100, 201, 203, 301, 302
    assert stats["brand_reply_candidates"] == 5
    assert stats["cases_built"] == 5
    assert set(by_case_id) == {"case_100", "case_201", "case_203", "case_301", "case_302"}

    # single-turn case from thread 1
    c100 = by_case_id["case_100"]
    assert c100["customer_message"] == "@SpotifyCares my music stopped"
    assert c100["context"] == []
    assert c100["source_ids"] == [101, 100]

    # multi-turn case from thread 2: two prior context turns, oldest first
    c203 = by_case_id["case_203"]
    assert c203["customer_message"] == "@SpotifyCares it's about playback"
    assert [t["speaker"] for t in c203["context"]] == ["customer", "brand"]
    assert c203["context"][0]["text"] == "I have an issue"
    assert c203["context"][1]["text"] == "@6002 can you tell us more?"
    assert c203["source_ids"] == [200, 201, 202, 203]

    # first part of the multi-part reply resolves directly, no context
    c301 = by_case_id["case_301"]
    assert c301["customer_message"] == "@SpotifyCares billing issue"
    assert c301["brand_response"] == "@6003 checking now (1/2)"
    assert c301["source_ids"] == [300, 301]

    # second part must skip past the brand-authored 301 to reach the same
    # customer message, and record 301 in source_ids for traceability
    c302 = by_case_id["case_302"]
    assert c302["customer_message"] == "@SpotifyCares billing issue"
    assert c302["brand_response"] == "@6003 refunded (2/2)"
    assert c302["source_ids"] == [300, 301, 302]


def test_assign_split_is_deterministic_and_covers_all_cases():
    cases = [{"case_id": f"c{i}"} for i in range(100)]
    assign_split(cases, golden_pool_fraction=0.2, seed=42)

    splits = {c["split"] for c in cases}
    assert splits == {"knowledge", "golden_pool"}
    golden_count = sum(1 for c in cases if c["split"] == "golden_pool")
    assert golden_count == 20

    cases_2 = [{"case_id": f"c{i}"} for i in range(100)]
    assign_split(cases_2, golden_pool_fraction=0.2, seed=42)
    assert [c["split"] for c in cases] == [c["split"] for c in cases_2]
