import json

import pytest

from scripts.build_golden_set import apply_intent_caps
from scripts.sample_golden_candidates import keyword_match_intent
from src.config import settings
from src.intents.labels import INTENTS

GOLDEN_SET_PATH = settings.data_golden_dir / "golden_set.jsonl"


def test_keyword_match_intent():
    assert keyword_match_intent("my account got hacked help") == "account_security_compromise"
    assert keyword_match_intent("all my playlists disappeared") == "account_data_loss"
    assert keyword_match_intent("please cancel my subscription") == "cancellation_or_refund_request"
    assert keyword_match_intent("the song keeps skipping") is None


def test_apply_intent_caps_keeps_escalate_first():
    records = [{"gold_intent": "x", "gold_action": "AUTO_HANDLE"} for _ in range(8)]
    records += [{"gold_intent": "x", "gold_action": "ESCALATE"} for _ in range(3)]

    capped = apply_intent_caps(records, seed=42)

    assert len(capped) == 8 + 3  # no cap configured for intent "x" -> unchanged
    # now with an explicit cap smaller than the ESCALATE count
    import scripts.build_golden_set as bgs

    bgs.INTENT_CAPS["x"] = 5
    try:
        capped = apply_intent_caps(records, seed=42)
    finally:
        del bgs.INTENT_CAPS["x"]

    assert len(capped) == 5
    assert sum(1 for r in capped if r["gold_action"] == "ESCALATE") == 3  # all ESCALATE kept
    assert sum(1 for r in capped if r["gold_action"] == "AUTO_HANDLE") == 2


def test_apply_intent_caps_is_deterministic():
    records = [{"gold_intent": "y", "gold_action": "AUTO_HANDLE", "id": i} for i in range(10)]
    import scripts.build_golden_set as bgs

    bgs.INTENT_CAPS["y"] = 4
    try:
        result_a = apply_intent_caps(records, seed=7)
        result_b = apply_intent_caps(records, seed=7)
    finally:
        del bgs.INTENT_CAPS["y"]

    assert [r["id"] for r in result_a] == [r["id"] for r in result_b]


@pytest.fixture(scope="module")
def golden_records():
    with GOLDEN_SET_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.mark.skipif(not GOLDEN_SET_PATH.exists(), reason="golden set not built in this environment")
class TestGoldenSetContents:
    def test_size_within_required_range(self, golden_records):
        assert 150 <= len(golden_records) <= 250

    def test_every_intent_represented(self, golden_records):
        seen_intents = {r["gold_intent"] for r in golden_records}
        assert seen_intents == set(INTENTS.keys())

    def test_schema_and_valid_values(self, golden_records):
        ids_seen = set()
        for r in golden_records:
            assert r["id"] not in ids_seen
            ids_seen.add(r["id"])
            assert r["customer_message"].strip()
            assert r["gold_intent"] in INTENTS
            assert r["gold_action"] in {"AUTO_HANDLE", "ESCALATE"}

    def test_both_actions_present_in_meaningful_numbers(self, golden_records):
        actions = [r["gold_action"] for r in golden_records]
        assert actions.count("AUTO_HANDLE") >= 50
        assert actions.count("ESCALATE") >= 50

    def test_no_case_id_leaks_from_knowledge_split(self, golden_records):
        support_cases_path = settings.data_processed_dir / "support_cases.jsonl"
        if not support_cases_path.exists():
            pytest.skip("full support_cases.jsonl not present in this environment")

        golden_case_ids = {r["case_id"] for r in golden_records}
        with support_cases_path.open(encoding="utf-8") as f:
            for line in f:
                case = json.loads(line)
                if case["case_id"] in golden_case_ids:
                    assert case["split"] == "golden_pool", f"{case['case_id']} leaked from {case['split']}"
