"""Lesion detection (boxes) and drawing circles around detected lesions.

Any Ultralytics YOLO checkpoint works: the ready-made CBIS-DDSM mass detector
(scripts/download_detector.py) or your own one trained with train/train_detector.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .config import Settings


@dataclass
class Detection:
    x0: float
    y0: float
    x1: float
    y1: float
    label: str  # finding type key: mass | calcifications | asymmetry | distortion | ai_lesion
    score: float
    raw_label: str = ""

    @property
    def size_px(self) -> float:
        return max(self.x1 - self.x0, self.y1 - self.y0)


def finding_type(raw: str) -> str:
    """Map a detector class name to a finding type of the report lexicon."""
    r = raw.lower()
    if "mass" in r or "tumor" in r or "nodule" in r:
        return "mass"
    if "calc" in r:
        return "calcifications"
    if "asym" in r:
        return "asymmetry"
    if "distortion" in r:
        return "distortion"
    return "ai_lesion"


class YoloDetector:
    name = "yolo-detector"

    def __init__(self, weights: str, conf: float = 0.25, device: str = "auto", max_det: int = 5):
        from ultralytics import YOLO

        self.model = YOLO(weights)
        self.conf = conf
        self.max_det = max_det  # most confident boxes per image
        self.device = _device(device)

    def detect(self, pixels: np.ndarray) -> list[Detection]:
        rgb = np.repeat(pixels[..., None], 3, axis=2)
        res = self.model.predict(rgb, conf=self.conf, device=self.device, max_det=self.max_det, verbose=False)[0]
        names = res.names
        out = []
        for (x0, y0, x1, y1), score, cls in zip(
            res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy(), res.boxes.cls.cpu().numpy()
        ):
            raw = str(names.get(int(cls), cls)) if isinstance(names, dict) else str(names[int(cls)])
            out.append(Detection(float(x0), float(y0), float(x1), float(y1), finding_type(raw), float(score), raw))
        return out


def _device(device: str) -> str:
    if device != "auto":
        return device
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_detector(settings: Settings):
    """Returns None when no detector weights are installed (the app still works, with a warning)."""
    if not os.path.exists(settings.detector_weights):
        print(f"[detector] not installed ({settings.detector_weights}); run scripts/download_detector.py")
        return None
    try:
        return YoloDetector(settings.detector_weights, settings.detector_conf, settings.device)
    except Exception as exc:
        print(f"[detector] not loaded -> {type(exc).__name__}: {exc}")
        return None


def draw(pixels: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """Grayscale image -> RGB image with a red circle (ellipse) around each detection."""
    import cv2

    rgb = cv2.cvtColor(pixels, cv2.COLOR_GRAY2RGB)
    scale = max(pixels.shape) / 1000
    thick = max(2, int(3 * scale))
    for d in detections:
        cx, cy = (d.x0 + d.x1) / 2, (d.y0 + d.y1) / 2
        ax = max((d.x1 - d.x0) * 0.65, 12 * scale)
        ay = max((d.y1 - d.y0) * 0.65, 12 * scale)
        cv2.ellipse(rgb, (int(cx), int(cy)), (int(ax), int(ay)), 0, 0, 360, (255, 40, 40), thick, cv2.LINE_AA)
        text = f"{d.raw_label or d.label} {d.score * 100:.0f}%"
        org = (int(max(cx - ax, 0)), int(max(cy - ay - 8 * scale, 14 * scale)))
        font = max(0.5, 0.8 * scale)
        cv2.putText(rgb, text, org, cv2.FONT_HERSHEY_SIMPLEX, font, (255, 40, 40), max(1, thick // 2 + 1), cv2.LINE_AA)
    return rgb
