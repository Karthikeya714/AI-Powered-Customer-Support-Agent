from evaluation.evaluate_escalation import compute_escalation_metrics


def test_perfect_predictions():
    y_true = ["AUTO_HANDLE", "AUTO_HANDLE", "ESCALATE", "ESCALATE"]
    y_pred = ["AUTO_HANDLE", "AUTO_HANDLE", "ESCALATE", "ESCALATE"]

    metrics = compute_escalation_metrics(y_true, y_pred)

    assert metrics["accuracy"] == 1.0
    assert metrics["false_auto_handle_rate"] == 0.0
    assert metrics["false_escalation_rate"] == 0.0


def test_false_auto_handle_rate_is_the_dangerous_error():
    # 2 truly ESCALATE cases, system auto-handled both (worst case)
    y_true = ["ESCALATE", "ESCALATE"]
    y_pred = ["AUTO_HANDLE", "AUTO_HANDLE"]

    metrics = compute_escalation_metrics(y_true, y_pred)

    assert metrics["false_auto_handle_rate"] == 1.0
    assert metrics["false_escalation_rate"] is None  # no true AUTO_HANDLE cases to measure it against
    assert metrics["confusion_matrix"]["ESCALATE"]["AUTO_HANDLE"] == 2


def test_false_escalation_rate_is_the_conservative_error():
    # 2 truly AUTO_HANDLE cases, system escalated both (safe but costly)
    y_true = ["AUTO_HANDLE", "AUTO_HANDLE"]
    y_pred = ["ESCALATE", "ESCALATE"]

    metrics = compute_escalation_metrics(y_true, y_pred)

    assert metrics["false_escalation_rate"] == 1.0
    assert metrics["false_auto_handle_rate"] is None
    assert metrics["confusion_matrix"]["AUTO_HANDLE"]["ESCALATE"] == 2


def test_mixed_case_rates():
    y_true = ["ESCALATE", "ESCALATE", "ESCALATE", "AUTO_HANDLE", "AUTO_HANDLE"]
    y_pred = ["ESCALATE", "AUTO_HANDLE", "ESCALATE", "AUTO_HANDLE", "ESCALATE"]

    metrics = compute_escalation_metrics(y_true, y_pred)

    # 1 of 3 true ESCALATE cases wrongly auto-handled
    assert metrics["false_auto_handle_rate"] == 1 / 3
    # 1 of 2 true AUTO_HANDLE cases wrongly escalated
    assert metrics["false_escalation_rate"] == 1 / 2
    assert metrics["n_examples"] == 5
