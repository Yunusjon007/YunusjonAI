"""Check the AI score -> BI-RADS thresholds against biopsy / follow-up results.

Ground truth comes from the app database ("Baza" tab: Final BI-RADS + Biopsy) or from a CSV
with columns score,label (label 1 = malignant). Prints AUC and sensitivity / specificity / PPV at every
threshold, and the 4A cut-off that reaches the requested sensitivity.

    python train/calibrate.py --db data/mammo.sqlite3 --target-sensitivity 0.9
    python train/calibrate.py --csv my_validation.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mammo_ai.config import settings  # noqa: E402


def load(args) -> tuple[np.ndarray, np.ndarray]:
    if args.csv:
        rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
        return np.array([float(r["score"]) for r in rows]), np.array([int(r["label"]) for r in rows])
    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT MAX(COALESCE(right_score, 0), COALESCE(left_score, 0)), pathology FROM studies "
        "WHERE pathology IN ('benign', 'malignant', 'high-risk') "
        "OR final_birads IN ('1', '2')"
    ).fetchall()
    return np.array([r[0] for r in rows]), np.array([1 if r[1] == "malignant" else 0 for r in rows])


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    pos, neg = scores[labels == 1], scores[labels == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=settings.db_path)
    ap.add_argument("--csv")
    ap.add_argument("--target-sensitivity", type=float, default=0.9)
    args = ap.parse_args()

    scores, labels = load(args)
    print(f"cases {len(labels)}  malignant {int(labels.sum())}  AUC {auc(scores, labels):.3f}")
    if not labels.sum() or labels.all():
        print("Need both malignant and non-malignant cases.")
        return
    print(f"{'threshold':>10} {'category>=':>10} {'sens':>6} {'spec':>6} {'PPV':>6}")
    for t, cat in zip(settings.birads_thresholds, ["3", "4A", "4B", "4C", "5"]):
        pred = scores >= t
        tp, fp = int((pred & (labels == 1)).sum()), int((pred & (labels == 0)).sum())
        sens = tp / labels.sum()
        spec = 1 - fp / (labels == 0).sum()
        ppv = tp / max(tp + fp, 1)
        print(f"{t:>10.3f} {cat:>10} {sens:>6.2f} {spec:>6.2f} {ppv:>6.2f}")
    cut = float(np.quantile(scores[labels == 1], 1 - args.target_sensitivity, method="lower"))
    print(f"\n4A cut-off for sensitivity {args.target_sensitivity:.0%}: {cut:.3f}")
    print("Set it with MAMMO_BIRADS_THRESHOLDS (5 comma-separated values; the 2nd one is the 4A cut-off).")


if __name__ == "__main__":
    main()
