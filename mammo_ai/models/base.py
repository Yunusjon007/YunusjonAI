from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DENSITY_CLASSES = ["A", "B", "C", "D"]
BIRADS_CLASSES = ["1", "2", "3", "4", "5"]


@dataclass
class BreastPrediction:
    """Model output for one breast (all its views together)."""

    cancer_prob: float | None = None
    density_probs: list[float] | None = None  # order: A, B, C, D
    birads_probs: list[float] | None = None  # order: 1, 2, 3, 4, 5
    sources: list[str] = field(default_factory=list)

    @property
    def density(self) -> str | None:
        if self.density_probs is None:
            return None
        return DENSITY_CLASSES[int(np.argmax(self.density_probs))]


class Backend:
    name = "base"

    def predict(self, views: dict[str, np.ndarray]) -> BreastPrediction:
        """views: {"cc": uint8 HxW, "mlo": uint8 HxW, ...} for one breast, already cropped."""
        raise NotImplementedError


def softmax_if_needed(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    if x.min() >= 0 and abs(x.sum() - 1) < 1e-3:
        return x
    e = np.exp(x - x.max())
    return e / e.sum()


def sigmoid_if_needed(x: float) -> float:
    x = float(x)
    return x if 0.0 <= x <= 1.0 else float(1 / (1 + np.exp(-x)))
