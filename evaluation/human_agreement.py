"""Phase 14 — human vs LLM-judge agreement analysis.

Compares human-assigned rubric scores (filled in by hand, using the SAME
rubric as evaluation/llm_judge.py, on a subset the human scorer never saw
the LLM's scores for) against the LLM judge's scores on that same subset,
and reports per-dimension agreement so we can honestly state how
trustworthy the automated judge is — not just assert that it is.
"""

from __future__ import annotations

import statistics

from evaluation.llm_judge import DIMENSIONS


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) == 1 or len(set(ys)) == 1:
        return None  # undefined when there's no variance to correlate
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    std_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    return cov / (std_x * std_y)


def compute_agreement(human_scores: list[dict], llm_scores: list[dict]) -> dict:
    """Both lists must be aligned by index (same example, same order)."""
    per_dimension = {}

    for dim in DIMENSIONS:
        human_vals = [h[dim] for h in human_scores]
        llm_vals = [l[dim] for l in llm_scores]

        per_dimension[dim] = {
            "exact_match_rate": sum(1 for h, l in zip(human_vals, llm_vals) if h == l) / len(human_vals),
            "within_one_point_rate": sum(1 for h, l in zip(human_vals, llm_vals) if abs(h - l) <= 1) / len(human_vals),
            "mean_absolute_difference": statistics.mean(abs(h - l) for h, l in zip(human_vals, llm_vals)),
            "pearson_correlation": _pearson([float(v) for v in human_vals], [float(v) for v in llm_vals]),
        }

    disagreements = []
    for h, l in zip(human_scores, llm_scores):
        for dim in DIMENSIONS:
            if abs(h[dim] - l[dim]) >= 2:
                disagreements.append(
                    {
                        "id": h.get("id") or l.get("id"),
                        "dimension": dim,
                        "human_score": h[dim],
                        "llm_score": l[dim],
                    }
                )

    return {
        "n_examples": len(human_scores),
        "per_dimension": per_dimension,
        "n_disagreements": len(disagreements),
        "disagreements": disagreements,
    }
