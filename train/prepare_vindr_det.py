"""VinDr-Mammo lesion boxes -> YOLO detection dataset (for train/train_detector.py).

VinDr-Mammo (https://physionet.org/content/vindr-mammo/, free PhysioNet credentialed access) has
`finding_annotations.csv` with a box per finding. Images are cropped to the breast (same crop as the
app uses), resized so the long side is --size pixels and saved as PNG; boxes are moved accordingly.

Classes: 0 mass, 1 calcification, 2 asymmetry, 3 distortion.

    python train/prepare_vindr_det.py --root /data/vindr-mammo --out data/vindr_det
"""
from __future__ import annotations

import argparse
import ast
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mammo_ai.imaging import crop_box, load_image  # noqa: E402

CLASSES = ["mass", "calcification", "asymmetry", "distortion"]
CATEGORY_TO_CLASS = {
    "Mass": 0,
    "Suspicious Calcification": 1,
    "Asymmetry": 2,
    "Focal Asymmetry": 2,
    "Global Asymmetry": 2,
    "Architectural Distortion": 3,
}


def parse_categories(raw: str) -> list[str]:
    try:
        return list(ast.literal_eval(raw))
    except (ValueError, SyntaxError):
        return [raw]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="folder with finding_annotations.csv and images/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=1024, help="long side of the saved PNG")
    ap.add_argument("--neg-ratio", type=float, default=1.0, help="images without findings per positive image")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    import cv2

    root, out = Path(args.root), Path(args.out)
    images: dict[str, dict] = {}
    boxes: dict[str, list] = defaultdict(list)
    for r in csv.DictReader(open(root / "finding_annotations.csv", encoding="utf-8")):
        images[r["image_id"]] = r
        cls = [CATEGORY_TO_CLASS[c] for c in parse_categories(r["finding_categories"]) if c in CATEGORY_TO_CLASS]
        if cls and r["xmin"] not in ("", "nan"):
            box = [float(r[k]) for k in ("xmin", "ymin", "xmax", "ymax")]
            boxes[r["image_id"]] += [(c, *box) for c in sorted(set(cls))]

    positives = [i for i in images if boxes[i]]
    negatives = [i for i in images if not boxes[i]]
    random.Random(args.seed).shuffle(negatives)
    selected = positives + negatives[: int(len(positives) * args.neg_ratio)]
    print(f"images with findings: {len(positives)}, negatives used: {len(selected) - len(positives)}")

    for n, image_id in enumerate(selected):
        r = images[image_id]
        split = "val" if r["split"] == "test" else "train"
        png = out / "images" / split / f"{image_id}.png"
        txt = out / "labels" / split / f"{image_id}.txt"
        png.parent.mkdir(parents=True, exist_ok=True)
        txt.parent.mkdir(parents=True, exist_ok=True)

        px = load_image(root / "images" / r["study_id"] / f"{image_id}.dicom").pixels
        x0, y0, x1, y1 = crop_box(px)
        crop = px[y0:y1, x0:x1]
        scale = args.size / max(crop.shape)
        w, h = max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))
        cv2.imwrite(str(png), cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA))

        lines = []
        for c, bx0, by0, bx1, by1 in boxes[image_id]:
            # into crop coordinates, clipped, then normalised
            bx0, bx1 = max(bx0 - x0, 0), min(bx1 - x0, crop.shape[1])
            by0, by1 = max(by0 - y0, 0), min(by1 - y0, crop.shape[0])
            if bx1 <= bx0 or by1 <= by0:
                continue
            cw, ch = crop.shape[1], crop.shape[0]
            lines.append(
                f"{c} {(bx0 + bx1) / 2 / cw:.6f} {(by0 + by1) / 2 / ch:.6f} {(bx1 - bx0) / cw:.6f} {(by1 - by0) / ch:.6f}"
            )
        txt.write_text("\n".join(lines) + ("\n" if lines else ""))
        if n % 200 == 0:
            print(f"{n}/{len(selected)}")

    yaml = out / "data.yaml"
    yaml.write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    print(f"done -> {yaml}")


if __name__ == "__main__":
    main()
