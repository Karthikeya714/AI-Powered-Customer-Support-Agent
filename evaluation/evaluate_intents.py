"""Shared intent-classification metrics, used by every intent
baseline/classifier (majority, TF-IDF+LogReg, the AI classifier) so
Accuracy/Macro F1/per-intent F1/confusion-matrix are computed identically
across all of them for a fair comparison.
"""

from __future__ import annotations

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
