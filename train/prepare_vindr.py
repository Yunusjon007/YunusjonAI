"""Convert VinDr-Mammo (https://physionet.org/content/vindr-mammo/) to the CSV used by train_birads.py.

VinDr-Mammo: 5,000 exams / 20,000 images from Vietnam, per-breast BI-RADS (1-5) and ACR density (A-D)
labels, plus lesion boxes. Access requires a free PhysioNet credentialed account.

    python train/prepare_vindr.py --root /data/vindr-mammo --out data/vindr.csv --png-dir data/vindr_png

--png-dir (recommended) pre-crops and stores 8-bit PNGs of height 1024, which makes training ~10x faster.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mammo_ai.imaging import crop_breast, load_image  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="folder with breast-level_annotations.csv and images/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--png-dir")
    ap.add_argument("--height", type=int, default=1024)
    args = ap.parse_args()

    root = Path(args.root)
    rows = list(csv.DictReader(open(root / "breast-level_annotations.csv", encoding="utf-8")))
    out_rows = []
    for i, r in enumerate(rows):
        src = root / "images" / r["study_id"] / f"{r['image_id']}.dicom"
        path = str(src)
        if args.png_dir:
            import cv2

            dst = Path(args.png_dir) / f"{r['image_id']}.png"
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                px = crop_breast(load_image(src).pixels)
                scale = args.height / px.shape[0]
                px = cv2.resize(px, (max(1, int(px.shape[1] * scale)), args.height), interpolation=cv2.INTER_AREA)
                cv2.imwrite(str(dst), px)
            path = str(dst)
        out_rows.append(
            {
                "path": path,
                "laterality": r["laterality"],
                "view": r["view_position"],
                "birads": r["breast_birads"].replace("BI-RADS", "").strip(),
                "density": r["breast_density"].replace("DENSITY", "").strip(),
                "split": "val" if r["split"] == "test" else "train",
            }
        )
        if i % 500 == 0:
            print(f"{i}/{len(rows)}")
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    print(f"saved {len(out_rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
