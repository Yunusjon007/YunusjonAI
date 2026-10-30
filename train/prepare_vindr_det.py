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

from mammo_ai.imaging import load_image  # noqa: E402
from yolo_common import write_example, write_yaml  # noqa: E402

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
        px = load_image(root / "images" / r["study_id"] / f"{image_id}.dicom").pixels
        write_example(px, boxes[image_id], out, split, image_id, args.size)
        if n % 200 == 0:
            print(f"{n}/{len(selected)}")

    print(f"done -> {write_yaml(out)}")


if __name__ == "__main__":
    main()
