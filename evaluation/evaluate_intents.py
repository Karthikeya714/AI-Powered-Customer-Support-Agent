"""Shared intent-classification metrics, used by every intent
baseline/classifier (majority, TF-IDF+LogReg, the AI classifier) so
Accuracy/Macro F1/per-intent F1/confusion-matrix are computed identically
across all of them for a fair comparison.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe: no GUI backend required to save PNGs
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support


def compute_intent_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    accuracy = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)

    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per_intent = {
        label: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(s)}
        for label, p, r, f, s in zip(labels, precision, recall, f1, support)
    }

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    confusion = {true_label: {pred_label: int(cm[i][j]) for j, pred_label in enumerate(labels)} for i, true_label in enumerate(labels)}

    return {
        "accuracy": float(accuracy),
        "macro_f1": float(macro_f1),
        "per_intent": per_intent,
        "confusion_matrix": confusion,
        "labels": labels,
    }


def plot_confusion_matrix(metrics: dict, output_path: Path, title: str) -> None:
    labels = metrics["labels"]
    cm = np.array([[metrics["confusion_matrix"][true][pred] for pred in labels] for true in labels])

    side = max(4.0, 1 + 0.6 * len(labels))  # a small label count (e.g. escalation's 2x2) still needs a readable minimum size
    fig, ax = plt.subplots(figsize=(side, side))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45 if len(labels) <= 4 else 90, ha="right" if len(labels) <= 4 else "center")
    ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)

    max_val = cm.max() if cm.max() > 0 else 1
    for i in range(len(labels)):
        for j in range(len(labels)):
            value = cm[i, j]
            color = "white" if value > max_val / 2 else "black"
            ax.text(j, i, str(value), ha="center", va="center", color=color, fontsize=8)

    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
