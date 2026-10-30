"""Shared by prepare_vindr_det.py and prepare_cbis_det.py: one image + boxes -> YOLO training example."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mammo_ai.imaging import crop_box  # noqa: E402

# Same classes for every dataset so they can be trained together.
CLASSES = ["mass", "calcification", "asymmetry", "distortion"]


def write_example(
    pixels: np.ndarray, boxes: list[tuple[int, float, float, float, float]], out: Path, split: str, name: str, size: int
) -> int:
    """pixels: full uint8 image; boxes: (class, x0, y0, x1, y1) in full-image pixels.
    Crops to the breast exactly like the app does, so training and inference see the same images.
    Returns the number of boxes written."""
    import cv2

    png = out / "images" / split / f"{name}.png"
    txt = out / "labels" / split / f"{name}.txt"
    png.parent.mkdir(parents=True, exist_ok=True)
    txt.parent.mkdir(parents=True, exist_ok=True)

    x0, y0, x1, y1 = crop_box(pixels)
    crop = pixels[y0:y1, x0:x1]
    ch, cw = crop.shape
    scale = size / max(crop.shape)
    cv2.imwrite(str(png), cv2.resize(crop, (max(1, round(cw * scale)), max(1, round(ch * scale))), interpolation=cv2.INTER_AREA))

    lines = []
    for c, bx0, by0, bx1, by1 in boxes:
        bx0, bx1 = max(bx0 - x0, 0), min(bx1 - x0, cw)
        by0, by1 = max(by0 - y0, 0), min(by1 - y0, ch)
        if bx1 <= bx0 or by1 <= by0:
            continue
        lines.append(f"{c} {(bx0 + bx1) / 2 / cw:.6f} {(by0 + by1) / 2 / ch:.6f} {(bx1 - bx0) / cw:.6f} {(by1 - by0) / ch:.6f}")
    txt.write_text("\n".join(lines) + ("\n" if lines else ""))
    return len(lines)


def write_yaml(out: Path) -> Path:
    yaml = out / "data.yaml"
    yaml.write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    return yaml
