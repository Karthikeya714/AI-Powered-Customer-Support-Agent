import pytest

from evaluation.human_agreement import compute_agreement


def _score(id_, correctness=5, groundedness=5, helpfulness=5, tone=5, no_hallucination=5):
    return {"id": id_, "correctness": correctness, "groundedness": groundedness, "helpfulness": helpfulness, "tone": tone, "no_hallucination": no_hallucination}


def test_perfect_agreement():
    human = [_score("a"), _score("b", correctness=3)]
    llm = [_score("a"), _score("b", correctness=3)]

    result = compute_agreement(human, llm)

    assert result["n_examples"] == 2
    assert result["n_disagreements"] == 0
    for dim, stats in result["per_dimension"].items():
        assert stats["exact_match_rate"] == 1.0
        assert stats["mean_absolute_difference"] == 0.0


def test_detects_large_disagreement():
    human = [_score("a", groundedness=5)]
    llm = [_score("a", groundedness=1)]  # a 4-point gap on one dimension

    result = compute_agreement(human, llm)

    assert result["n_disagreements"] == 1
    assert result["disagreements"][0]["dimension"] == "groundedness"
    assert result["disagreements"][0]["human_score"] == 5
    assert result["disagreements"][0]["llm_score"] == 1
    assert result["per_dimension"]["groundedness"]["exact_match_rate"] == 0.0
    assert result["per_dimension"]["groundedness"]["mean_absolute_difference"] == 4.0


def test_small_disagreement_not_flagged():
    # a 1-point gap is within tolerance, not a "disagreement"
    human = [_score("a", tone=4)]
    llm = [_score("a", tone=3)]

    result = compute_agreement(human, llm)

    assert result["n_disagreements"] == 0
    assert result["per_dimension"]["tone"]["within_one_point_rate"] == 1.0


def test_pearson_correlation_positive_for_correlated_scores():
    human = [_score("a", correctness=1), _score("b", correctness=3), _score("c", correctness=5)]
    llm = [_score("a", correctness=2), _score("b", correctness=3), _score("c", correctness=4)]

    result = compute_agreement(human, llm)

    assert result["per_dimension"]["correctness"]["pearson_correlation"] == pytest.approx(1.0)


def test_pearson_correlation_none_when_no_variance():
    human = [_score("a", correctness=5), _score("b", correctness=5)]
    llm = [_score("a", correctness=5), _score("b", correctness=4)]

    result = compute_agreement(human, llm)

    assert result["per_dimension"]["correctness"]["pearson_correlation"] is None
