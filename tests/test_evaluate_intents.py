from evaluation.evaluate_intents import compute_intent_metrics


def test_compute_intent_metrics_perfect_predictions():
    labels = ["a", "b"]
    y_true = ["a", "a", "b", "b"]
    y_pred = ["a", "a", "b", "b"]

    metrics = compute_intent_metrics(y_true, y_pred, labels)

    assert metrics["accuracy"] == 1.0
    assert metrics["macro_f1"] == 1.0
    assert metrics["per_intent"]["a"]["f1"] == 1.0
    assert metrics["per_intent"]["b"]["f1"] == 1.0
    assert metrics["confusion_matrix"]["a"]["a"] == 2
    assert metrics["confusion_matrix"]["a"]["b"] == 0


def test_compute_intent_metrics_always_predicts_one_class():
    # mirrors the majority baseline: always predicts "a"
    labels = ["a", "b", "c"]
    y_true = ["a", "a", "b", "c"]
    y_pred = ["a", "a", "a", "a"]

    metrics = compute_intent_metrics(y_true, y_pred, labels)

    assert metrics["accuracy"] == 0.5  # 2/4 correct
    assert metrics["per_intent"]["a"]["recall"] == 1.0  # every true "a" was predicted
    assert metrics["per_intent"]["a"]["precision"] == 0.5  # 2 of 4 "a" predictions were right
    assert metrics["per_intent"]["b"]["recall"] == 0.0
    assert metrics["per_intent"]["b"]["f1"] == 0.0
    assert metrics["confusion_matrix"]["b"]["a"] == 1  # true b, predicted a
