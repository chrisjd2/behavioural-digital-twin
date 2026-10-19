"""Per-user ranking metrics (ADR-0001). Scores and labels are keyed by news ID."""

from collections.abc import Mapping


def auc(scores: Mapping[str, float], labels: Mapping[str, int]) -> float:
    """Probability a clicked item outranks a non-clicked one; ties count half."""
    positives = [scores[i] for i, label in labels.items() if label == 1]
    negatives = [scores[i] for i, label in labels.items() if label == 0]
    if not positives or not negatives:
        raise ValueError("AUC needs both clicked and non-clicked items")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))
