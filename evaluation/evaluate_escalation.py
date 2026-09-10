"""Escalation decision metrics — accuracy, precision/recall/F1 (treating
ESCALATE as the positive class, since it's the safety-critical direction),
plus the two named rates from the plan:

- false_auto_handle_rate: of cases that should have escalated, what
  fraction did the system dangerously auto-handle instead? (1 - recall
  on ESCALATE) This is the metric that matters most — an unsafe
  automatic response is worse than an unnecessary escalation.
- false_escalation_rate: of cases that could safely have been
  auto-handled, what fraction did the system escalate instead? (1 -
  recall on AUTO_HANDLE / 1 - specificity) A cost/efficiency metric, not
  a safety one.
"""

from __future__ import annotations

from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

LABELS = ["AUTO_HANDLE", "ESCALATE"]


def compute_escalation_metrics(y_true: list[str], y_pred: list[str]) -> dict:
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, zero_division=0)

    cm = confusion_matrix(y_true, y_pred, labels=LABELS)
    tn, fp = int(cm[0][0]), int(cm[0][1])  # true AUTO_HANDLE: correctly kept / wrongly escalated
    fn, tp = int(cm[1][0]), int(cm[1][1])  # true ESCALATE: wrongly auto-handled (dangerous) / correctly escalated

    return {
        "labels": LABELS,
        "accuracy": float(accuracy),
        "per_label": {
            label: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(s)}
            for label, p, r, f, s in zip(LABELS, precision, recall, f1, support)
        },
        "confusion_matrix": {
            "AUTO_HANDLE": {"AUTO_HANDLE": tn, "ESCALATE": fp},
            "ESCALATE": {"AUTO_HANDLE": fn, "ESCALATE": tp},
        },
        "false_auto_handle_rate": (fn / (fn + tp)) if (fn + tp) > 0 else None,
        "false_escalation_rate": (fp / (fp + tn)) if (fp + tn) > 0 else None,
        "n_examples": len(y_true),
    }
