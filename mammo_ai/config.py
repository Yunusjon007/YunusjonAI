"""Settings for MammoAI. Every value can be overridden with an environment variable."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_float_list(name: str, default: list[float]) -> list[float]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [float(x) for x in raw.split(",")]


@dataclass
class Settings:
    # Pretrained open-source model (Apache-2.0): cancer probability + ACR density.
    # https://huggingface.co/ianpan/mammoscreen
    mammoscreen_id: str = os.getenv("MAMMO_SCREEN_MODEL", "ianpan/mammoscreen")
    # Optional cropper from the same author; our own OpenCV crop is used if it fails.
    mammo_crop_id: str = os.getenv("MAMMO_CROP_MODEL", "ianpan/mammo-crop")
    use_hf_crop: bool = os.getenv("MAMMO_USE_HF_CROP", "0") == "1"
    # Optional checkpoint trained with train/train_birads.py (direct BI-RADS 1-5 + density).
    local_birads_ckpt: str = os.getenv("MAMMO_BIRADS_CKPT", str(ROOT / "weights" / "birads_model.pt"))
    device: str = os.getenv("MAMMO_DEVICE", "auto")  # auto | cpu | cuda | mps
    # Lesion detector (YOLO). Draws circles around findings; without it benign lesions are not detected.
    detector_weights: str = os.getenv("MAMMO_DETECTOR_WEIGHTS", str(ROOT / "weights" / "detector.pt"))
    detector_conf: float = float(os.getenv("MAMMO_DETECTOR_CONF", "0.25"))

    # Upper bounds of the AI malignancy score for each BI-RADS category:
    # score < t[0] -> 1, < t[1] -> 3, < t[2] -> 4A, < t[3] -> 4B, < t[4] -> 4C, else 5.
    # These defaults are NOT clinically validated. Calibrate them on your own
    # biopsy-proven data (see README, "Calibration").
    birads_thresholds: list[float] = field(
        default_factory=lambda: _env_float_list("MAMMO_BIRADS_THRESHOLDS", [0.10, 0.20, 0.35, 0.55, 0.80])
    )

    db_path: str = os.getenv("MAMMO_DB", str(ROOT / "data" / "mammo.sqlite3"))
    default_lang: str = os.getenv("MAMMO_LANG", "uz")


settings = Settings()
