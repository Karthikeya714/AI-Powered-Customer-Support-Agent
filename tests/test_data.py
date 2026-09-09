from pathlib import Path
from textwrap import dedent

import pytest

from scripts.inspect_dataset import build_brand_statistics, pass_a_rank_brands, pass_b_full_scan
from src.data.loader import load_raw_data

# A small synthetic dataset mirroring the real twcs.csv schema:
#   BrandA: 4 outbound tweets (2 of them replies), 2 customer tweets mentioning it
#   BrandB: 2 outbound tweets (1 of them a reply), 1 customer tweet mentioning it
SAMPLE_CSV = dedent(
    """\
    tweet_id,author_id,inbound,created_at,text,response_tweet_id,in_response_to_tweet_id
    1,BrandA,False,Mon Jan 01 00:00:00 +0000 2018,"@200 hello, how can we help?",2,
    2,200,True,Mon Jan 01 00:01:00 +0000 2018,@BrandA my order is late,3,1
    3,BrandA,False,Mon Jan 01 00:02:00 +0000 2018,"@200 sorry, DM us",,2
    4,BrandA,False,Mon Jan 01 00:03:00 +0000 2018,@201 hi there,5,
    5,201,True,Mon Jan 01 00:04:00 +0000 2018,@BrandA where is my refund,6,4
    6,BrandA,False,Mon Jan 01 00:05:00 +0000 2018,@201 refund processed,,5
    7,BrandB,False,Mon Jan 01 00:06:00 +0000 2018,@202 thanks for reaching out,8,
    8,202,True,Mon Jan 01 00:07:00 +0000 2018,@BrandB broken item,9,7
    9,BrandB,False,Mon Jan 01 00:08:00 +0000 2018,"@202 refund issued, see 3,4 for details",,8
    """
)


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "twcs_sample.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")
    return path


def test_load_raw_data_dtypes_and_multivalue_ids(sample_csv):
    df = load_raw_data(sample_csv)
    assert len(df) == 9
    assert df["inbound"].dtype == bool
    # comma-separated id lists must survive as strings, not get coerced to numeric
    assert df.loc[df["tweet_id"] == 9, "text"].iloc[0].endswith("see 3,4 for details")
    assert df.loc[df["tweet_id"] == 1, "response_tweet_id"].iloc[0] == "2"


def test_load_raw_data_sample_size(sample_csv):
    df = load_raw_data(sample_csv, sample_size=3)
    assert len(df) == 3


def test_pass_a_rank_brands(sample_csv):
    result = pass_a_rank_brands(sample_csv)
    assert result["total_rows"] == 9
    assert result["inbound_counts"][True] == 3
    assert result["inbound_counts"][False] == 6
    assert result["brand_outbound_count"]["BrandA"] == 4
    assert result["brand_outbound_count"]["BrandB"] == 2
    assert result["brand_reply_count"]["BrandA"] == 2
    assert result["brand_reply_count"]["BrandB"] == 1


def test_pass_b_full_scan_mentions_and_quality_stats(sample_csv):
    result = pass_b_full_scan(sample_csv, shortlist_handles=["BrandA", "BrandB"])
    assert result["customer_mentions_per_brand"]["BrandA"] == 2
    assert result["customer_mentions_per_brand"]["BrandB"] == 1
    assert result["duplicate_tweet_id_count"] == 0
    assert result["duplicate_content_count"] == 0
    assert len(result["buffered_rows"]) == 9  # every row involves a shortlisted brand here


def test_build_brand_statistics(sample_csv):
    pass_a = pass_a_rank_brands(sample_csv)
    pass_b = pass_b_full_scan(sample_csv, shortlist_handles=["BrandA", "BrandB"])
    stats = build_brand_statistics(pass_a, pass_b, ["BrandA", "BrandB"])

    brand_a = stats.set_index("brand").loc["BrandA"]
    assert brand_a["brand_messages"] == 4
    assert brand_a["conversations"] == 2
    assert brand_a["customer_messages"] == 2
    assert brand_a["total_tweets"] == 6

    # sorted descending by total_tweets, so BrandA (6) should rank above BrandB (3)
    assert stats.iloc[0]["brand"] == "BrandA"
