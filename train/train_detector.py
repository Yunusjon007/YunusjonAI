"""Train the lesion detector (YOLO) that draws circles around findings.

Works on a MacBook (Apple M-chip, device "mps"), NVIDIA GPU ("cuda") or CPU.

    python train/prepare_vindr_det.py --root /data/vindr-mammo --out data/vindr_det
    caffeinate -i python train/train_detector.py --data data/vindr_det/data.yaml      # macOS: keep awake

Quick trial on 10% of the data first:  --fraction 0.1 --epochs 3
The best checkpoint is copied to weights/detector.pt, which the app loads automatically.
Ultralytics is AGPL-3.0 licensed (fine for your own use; check it before selling the software).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mammo_ai.detection import _device  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="data.yaml from prepare_vindr_det.py")
    ap.add_argument("--model", default="yolo11s.pt", help="start weights (yolo11n.pt is faster, yolo11m.pt better)")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--device", default="auto", help="auto | mps | cuda | cpu")
    ap.add_argument("--fraction", type=float, default=1.0, help="use only part of the training images")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--project", default=str(ROOT / "runs"))
    ap.add_argument("--out", default=str(ROOT / "weights" / "detector.pt"))
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=_device(args.device),
        fraction=args.fraction,
        workers=args.workers,
        project=args.project,
        name="detector",
        exist_ok=True,
        # mammograms: no colour changes, no vertical flips that break anatomy; mild geometry only
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.2, fliplr=0.5, flipud=0.0, degrees=5, scale=0.2, mosaic=0.5,
    )
    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, args.out)
    print(f"best checkpoint -> {args.out}")
    metrics = model.trainer.metrics or {}
    for k in ("metrics/mAP50(B)", "metrics/mAP50-95(B)", "metrics/recall(B)"):
        if k in metrics:
            print(f"{k}: {metrics[k]:.3f}")


if __name__ == "__main__":
    main()
