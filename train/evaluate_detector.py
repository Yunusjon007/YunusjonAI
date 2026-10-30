"""Measure the lesion detector the way the app uses it, and write weights/detector.json.

recall = share of annotated lesions in the validation images that get a circle at the app's
threshold (MAMMO_DETECTOR_CONF); fp_per_image = circles that hit no lesion. The app trusts
"nothing found" (BI-RADS 1 without a warning) only when recall >= MAMMO_DETECTOR_MIN_RECALL (0.8).

    python train/evaluate_detector.py --data data/cbis_det/data.yaml
    python train/evaluate_detector.py --data data/cbis_det/data.yaml --images ~/Desktop/test_cases
    # --images: your own mammograms (PNG/JPG/DICOM) -> runs/check/*.png with circles, to look at
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mammo_ai.config import settings  # noqa: E402
from mammo_ai.detection import YoloDetector, draw, metrics_path  # noqa: E402


def read_yaml(path: str) -> dict:
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def val_dirs(data_yamls: list[str]) -> list[Path]:
    dirs = []
    for y in data_yamls:
        d = read_yaml(y)
        base = Path(d.get("path") or Path(y).parent)
        vals = d["val"] if isinstance(d["val"], list) else [d["val"]]
        dirs += [Path(v) if Path(v).is_absolute() else base / v for v in vals]
    return dirs


def hit(pred: tuple, gt: tuple) -> bool:
    """A circle counts for a lesion if its centre lies in the lesion box or IoU >= 0.2."""
    px0, py0, px1, py1 = pred
    gx0, gy0, gx1, gy1 = gt
    cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
    if gx0 <= cx <= gx1 and gy0 <= cy <= gy1:
        return True
    iw = max(0.0, min(px1, gx1) - max(px0, gx0))
    ih = max(0.0, min(py1, gy1) - max(py0, gy0))
    inter = iw * ih
    union = (px1 - px0) * (py1 - py0) + (gx1 - gx0) * (gy1 - gy0) - inter
    return union > 0 and inter / union >= 0.2


def evaluate(weights: str, data_yamls: list[str], conf: float, device: str = "auto") -> dict:
    import cv2

    det = YoloDetector(weights, conf=conf, device=device)
    lesions = found = false_pos = images = 0
    for vdir in val_dirs(data_yamls):
        for img_path in sorted(vdir.glob("*.png")):
            label = Path(str(img_path).replace("/images/", "/labels/")).with_suffix(".txt")
            px = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            h, w = px.shape
            gts = []
            if label.exists():
                for line in label.read_text().split("\n"):
                    if line.strip():
                        _, cx, cy, bw, bh = map(float, line.split())
                        gts.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
            preds = [(d.x0, d.y0, d.x1, d.y1) for d in det.detect(px)]
            images += 1
            lesions += len(gts)
            found += sum(any(hit(p, g) for p in preds) for g in gts)
            false_pos += sum(not any(hit(p, g) for g in gts) for p in preds)
    result = {
        "recall": found / lesions if lesions else 0.0,
        "fp_per_image": false_pos / images if images else 0.0,
        "lesions": lesions,
        "images": images,
        "conf": conf,
        "datasets": [Path(y).resolve().parent.name for y in data_yamls],
        "date": date.today().isoformat(),
    }
    try:  # standard detection metric for comparison with papers
        from ultralytics import YOLO

        m = YOLO(weights).val(data=data_yamls[0], device=det.device, verbose=False, plots=False)
        result["map50"] = float(m.box.map50)
    except Exception as exc:
        print(f"[mAP50 skipped: {exc}]")
    return result


def check_images(weights: str, folder: str, conf: float, out_dir: Path) -> None:
    import cv2

    from mammo_ai.imaging import crop_breast, load_image, split_two_breasts

    det = YoloDetector(weights, conf=conf)
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(Path(folder).expanduser().iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".dcm", ".dicom", ".webp"}:
            continue
        for part in split_two_breasts(load_image(path)):
            px = crop_breast(part.pixels)
            dets = det.detect(px)
            dst = out_dir / f"{path.stem}_{part.laterality}.png"
            cv2.imwrite(str(dst), cv2.cvtColor(draw(px, dets), cv2.COLOR_RGB2BGR))
            print(f"{dst.name}: {len(dets)} circle(s) " + ", ".join(f"{d.raw_label} {d.score:.0%}" for d in dets))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=settings.detector_weights)
    ap.add_argument("--data", action="append", required=True, help="data.yaml (repeat for several datasets)")
    ap.add_argument("--conf", type=float, default=settings.detector_conf)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--images", help="folder with your own mammograms to check visually")
    ap.add_argument("--out", default=str(ROOT / "runs" / "check"))
    args = ap.parse_args()

    result = evaluate(args.weights, args.data, args.conf, args.device)
    Path(metrics_path(args.weights)).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    verdict = "OK" if result["recall"] >= settings.detector_min_recall else "TOO LOW (the app keeps warning)"
    print(f"lesion recall {result['recall']:.0%} at conf {args.conf}: {verdict}")
    print(f"saved -> {metrics_path(args.weights)}")
    if args.images:
        check_images(args.weights, args.images, args.conf, Path(args.out))


if __name__ == "__main__":
    main()
