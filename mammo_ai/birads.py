"""ACR BI-RADS (5th edition) categories and the mapping from model outputs to a suggested category."""
from __future__ import annotations

from .models.base import BIRADS_CLASSES, BreastPrediction

CATEGORIES = ["0", "1", "2", "3", "4A", "4B", "4C", "5", "6"]

# ACR hierarchy for the overall (both breasts) assessment, least to most abnormal.
_HIERARCHY = ["1", "2", "3", "6", "0", "4", "4A", "4B", "4C", "5"]

# Likelihood of malignancy per ACR BI-RADS Atlas, 5th edition.
MALIGNANCY_RISK = {
    "0": "N/A",
    "1": "0%",
    "2": "0%",
    "3": ">0% - ≤2%",
    "4": ">2% - <95%",
    "4A": ">2% - ≤10%",
    "4B": ">10% - ≤50%",
    "4C": ">50% - <95%",
    "5": "≥95%",
    "6": "N/A",
}


def rank(cat: str) -> int:
    return _HIERARCHY.index(cat)


def worst(cats: list[str]) -> str:
    return max(cats, key=rank)


def from_score(score: float, thresholds: list[float]) -> str:
    """Malignancy score (0-1) -> BI-RADS category, using the configured upper bounds."""
    for cat, t in zip(["1", "3", "4A", "4B", "4C"], thresholds):
        if score < t:
            return cat
    return "5"


def suspicion_level(score: float, thresholds: list[float]) -> str:
    cat = from_score(score, thresholds)
    return {"1": "low", "3": "low_intermediate"}.get(cat, "high" if cat in {"4C", "5"} else "intermediate")


def assess(pred: BreastPrediction, thresholds: list[float]) -> str:
    """Suggested BI-RADS for one breast. If several models are present, the more severe answer wins."""
    cats = []
    if pred.cancer_prob is not None:
        cats.append(from_score(pred.cancer_prob, thresholds))
    if pred.birads_probs is not None:
        idx = max(range(len(BIRADS_CLASSES)), key=lambda i: pred.birads_probs[i])
        cat = BIRADS_CLASSES[idx]
        if cat == "4":
            cat = "4A"
        cats.append(cat)
    return worst(cats) if cats else "0"
