"""Train the lesion detector (YOLO) that draws circles around findings.

Works on a MacBook (Apple M-chip, device "mps"), NVIDIA GPU ("cuda") or CPU.

    python train/prepare_cbis_det.py --root ~/Downloads/cbis-ddsm --out data/cbis_det
    caffeinate -i python train/train_detector.py --data data/cbis_det/data.yaml        # macOS: keep awake

Several datasets together (e.g. when VinDr-Mammo access arrives):
    --data data/cbis_det/data.yaml --data data/vindr_det/data.yaml
Quick trial first:  --fraction 0.1 --epochs 3
If the Mac slept or the run stopped:  --resume

The best checkpoint is copied to weights/detector.pt and measured on the validation images
(weights/detector.json); the app loads both automatically.
Ultralytics is AGPL-3.0 licensed (fine for your own use; check it before selling the software).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluate_detector import evaluate, read_yaml  # noqa: E402
from mammo_ai.config import settings  # noqa: E402
from mammo_ai.detection import _device, metrics_path  # noqa: E402


def combine(data_yamls: list[str], project: Path) -> str:
    """One data.yaml listing the train/val folders of every dataset (same class names)."""
    if len(data_yamls) == 1:
        return data_yamls[0]
    import yaml

    train, val, names = [], [], None
    for y in data_yamls:
        d = read_yaml(y)
        base = Path(d.get("path") or Path(y).parent).resolve()
        train.append(str(base / d["train"]))
        val.append(str(base / d["val"]))
        if names is not None and d["names"] != names:
            raise SystemExit(f"class names differ in {y}: {d['names']} vs {names}")
        names = d["names"]
    project.mkdir(parents=True, exist_ok=True)
    out = project / "combined.yaml"
    out.write_text(yaml.safe_dump({"train": train, "val": val, "names": names}, allow_unicode=True))
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="append", required=True, help="data.yaml (repeat for several datasets)")
    ap.add_argument("--model", default="yolo11s.pt", help="start weights (yolo11n.pt is faster, yolo11m.pt better)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--device", default="auto", help="auto | mps | cuda | cpu")
    ap.add_argument("--fraction", type=float, default=1.0, help="use only part of the training images")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--resume", action="store_true", help="continue the last interrupted run")
    ap.add_argument("--project", default=str(ROOT / "runs"))
    ap.add_argument("--out", default=str(ROOT / "weights" / "detector.pt"))
    args = ap.parse_args()

    from ultralytics import YOLO

    project = Path(args.project)
    last = project / "detector" / "weights" / "last.pt"
    if args.resume:
        if not last.exists():
            raise SystemExit(f"nothing to resume: {last} not found")
        model = YOLO(str(last))
        model.train(resume=True)
    else:
        model = YOLO(args.model)
        model.train(
            data=combine(args.data, project),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=_device(args.device),
            fraction=args.fraction,
            workers=args.workers,
            project=str(project),
            name="detector",
            exist_ok=True,
            # mammograms: no colour changes, no vertical flips that break anatomy; mild geometry only
            hsv_h=0.0, hsv_s=0.0, hsv_v=0.2, fliplr=0.5, flipud=0.0, degrees=5, scale=0.2, mosaic=0.5,
        )
    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, args.out)
    print(f"best checkpoint -> {args.out}")

    result = evaluate(args.out, args.data, settings.detector_conf, args.device)
    Path(metrics_path(args.out)).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    ok = result["recall"] >= settings.detector_min_recall
    print(f"lesion recall {result['recall']:.0%}: " + ("OK" if ok else "TOO LOW — the app keeps its warning"))


if __name__ == "__main__":
    main()
