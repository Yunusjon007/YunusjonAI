"""CBIS-DDSM mass + calcification ROIs -> YOLO detection dataset (for train/train_detector.py).

CBIS-DDSM is public (CC BY 3.0, no registration): scanned-film mammograms with ROI masks for every
mass and calcification. Two download options are supported:

  * Kaggle JPEG version (~6 GB, easiest on a laptop):
    https://www.kaggle.com/datasets/awsaf49/cbis-ddsm-breast-cancer-image-dataset
    -> folder with csv/ and jpeg/<SeriesInstanceUID>/*.jpg
  * Original TCIA DICOM version (~160 GB): https://www.cancerimagingarchive.net/collection/cbis-ddsm/
    -> folders named like Mass-Training_P_00001_LEFT_CC/.../*.dcm

    python train/prepare_cbis_det.py --root ~/Downloads/cbis-ddsm --out data/cbis_det

If many images cannot be found, the script prints what it looked for and what is on disk;
send that output (and the output of train/inspect_dataset.py) to get the converter adjusted.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mammo_ai.imaging import load_image  # noqa: E402
from yolo_common import write_example, write_yaml  # noqa: E402

CASE_CSVS = {
    "mass_case_description_train_set.csv": (0, "train"),
    "mass_case_description_test_set.csv": (0, "val"),
    "calc_case_description_train_set.csv": (1, "train"),
    "calc_case_description_test_set.csv": (1, "val"),
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".dcm"}


def find_csvs(root: Path) -> dict[str, Path]:
    found = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f in CASE_CSVS:
                found[f] = Path(dirpath) / f
    return found


class FileIndex:
    """Finds the image files of a CSV path such as
    'Mass-Training_P_00001_LEFT_CC/<StudyUID>/<SeriesUID>/000000.dcm' in either layout:
    Kaggle: <any>/<SeriesUID>/*.jpg     TCIA: <any>/Mass-Training_P_00001_LEFT_CC/**/*.dcm"""

    def __init__(self, root: Path):
        self.by_dir: dict[str, list[Path]] = defaultdict(list)  # directory name -> files below it
        for dirpath, _, files in os.walk(root):
            images = [Path(dirpath) / f for f in files if Path(f).suffix.lower() in IMAGE_EXT]
            if not images:
                continue
            for part in Path(dirpath).relative_to(root).parts:
                self.by_dir[part].extend(images)

    def lookup(self, csv_path: str) -> list[Path]:
        parts = [p for p in csv_path.strip().replace("\\", "/").split("/") if p]
        if len(parts) >= 3 and parts[2] in self.by_dir:  # series UID (Kaggle)
            return self.by_dir[parts[2]]
        if parts and parts[0] in self.by_dir:  # case folder (TCIA)
            return self.by_dir[parts[0]]
        return []


def read_gray(path: Path) -> np.ndarray:
    return load_image(path).pixels


def pick_full(files: list[Path]) -> np.ndarray | None:
    """The full mammogram is the largest image of its series."""
    imgs = [read_gray(f) for f in files]
    return max(imgs, key=lambda a: a.size) if imgs else None


def pick_mask(files: list[Path], full_shape: tuple[int, int]) -> np.ndarray | None:
    """A ROI series holds the small cropped patch and the full-size binary mask: take the image
    closest to the full mammogram size (JPEG conversion can change it by a few pixels)."""
    import cv2

    best, best_err = None, None
    for f in files:
        a = read_gray(f)
        err = abs(a.shape[0] - full_shape[0]) / full_shape[0] + abs(a.shape[1] - full_shape[1]) / full_shape[1]
        if best_err is None or err < best_err:
            best, best_err = a, err
    if best is None or best_err > 0.1:  # only the cropped patch was found
        return None
    if best.shape != full_shape:
        best = cv2.resize(best, (full_shape[1], full_shape[0]), interpolation=cv2.INTER_NEAREST)
    return best


def mask_box(mask: np.ndarray) -> tuple[float, float, float, float] | None:
    ys, xs = np.nonzero(mask > 127)
    if len(xs) == 0:
        return None
    return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="downloaded CBIS-DDSM folder (Kaggle JPEG or TCIA DICOM)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=1024, help="long side of the saved PNG")
    ap.add_argument("--limit", type=int, default=0, help="only the first N images (quick test)")
    args = ap.parse_args()
    root, out = Path(args.root).expanduser(), Path(args.out)

    csvs = find_csvs(root)
    if not csvs:
        print(f"No CBIS-DDSM case CSVs ({', '.join(CASE_CSVS)}) under {root}.")
        print("Run: python train/inspect_dataset.py --root", root)
        return 1
    print("CSV files:", ", ".join(sorted(csvs)))

    # One entry per full mammogram, with all its abnormalities.
    studies: dict[str, dict] = {}
    for name, path in csvs.items():
        cls, split = CASE_CSVS[name]
        for r in csv.DictReader(open(path, encoding="utf-8")):
            image_path = r.get("image file path", "").strip()
            st = studies.setdefault(image_path, {"split": split, "rois": []})
            st["rois"].append((cls, r.get("ROI mask file path", "").strip(), r.get("cropped image file path", "").strip()))

    print(f"full mammograms in CSVs: {len(studies)}; indexing files under {root} ...")
    index = FileIndex(root)
    keys = list(studies)[: args.limit or None]
    missing_full, missing_mask, written_boxes = [], [], 0
    for n, image_path in enumerate(keys):
        st = studies[image_path]
        full = pick_full(index.lookup(image_path))
        if full is None:
            missing_full.append(image_path)
            continue
        boxes = []
        for cls, roi_path, crop_path in st["rois"]:
            mask = pick_mask(index.lookup(roi_path), full.shape)
            if mask is None:  # some exports store the mask under the cropped-image series
                mask = pick_mask(index.lookup(crop_path), full.shape)
            box = mask_box(mask) if mask is not None else None
            if box is None:
                missing_mask.append(roi_path)
                continue
            boxes.append((cls, *box))
        name = image_path.split("/")[0] or f"img{n}"
        written_boxes += write_example(full, boxes, out, st["split"], name, args.size)
        if n % 200 == 0:
            print(f"{n}/{len(keys)}")

    print(f"\nwritten: {len(keys) - len(missing_full)} images, {written_boxes} boxes")
    print(f"not found: {len(missing_full)} full images, {len(missing_mask)} ROI masks")
    if len(missing_full) > 0.1 * max(len(keys), 1) or len(missing_mask) > 0.1 * max(written_boxes, 1):
        print("\n!!! Too many files were not found. Send this whole output to adjust the converter.")
        for p in (missing_full + missing_mask)[:5]:
            print("  looked for:", p)
        sample = sorted(index.by_dir)[:10]
        print("  directory names on disk (sample):", sample)
        return 2
    print(f"done -> {write_yaml(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
