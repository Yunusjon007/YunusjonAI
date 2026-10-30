"""Train a BI-RADS (1-5) + ACR density (A-D) classifier.

Input CSV columns: path, birads (1-5), density (A-D), split (train/val). Any dataset can be used
(VinDr-Mammo via prepare_vindr.py, KAU-BCMD, your own PACS export...). Images: DICOM/PNG/JPG.

    python train/train_birads.py --csv data/vindr.csv --epochs 15 --out weights/birads_model.pt

The saved checkpoint is picked up automatically by the app (MAMMO_BIRADS_CKPT).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402

from mammo_ai.imaging import crop_breast, load_image  # noqa: E402
from mammo_ai.models.base import BIRADS_CLASSES, DENSITY_CLASSES  # noqa: E402
from mammo_ai.models.local_birads import build_net, orient_left, to_tensor  # noqa: E402


class MammoDataset(Dataset):
    def __init__(self, rows: list[dict], size: tuple[int, int], train: bool):
        self.rows, self.size, self.train = rows, size, train

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        px = load_image(r["path"]).pixels
        px = np.ascontiguousarray(orient_left(crop_breast(px)))
        x = to_tensor(px, self.size)[0]
        if self.train:
            if torch.rand(1) < 0.5:
                x = x.flip(1)  # vertical flip keeps the chest wall on the left
            x = x * (0.85 + 0.3 * torch.rand(1)) + 0.1 * (torch.rand(1) - 0.5)  # contrast / brightness
        return x, BIRADS_CLASSES.index(r["birads"]), DENSITY_CLASSES.index(r["density"])


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, n: int) -> float:
    f1 = []
    for c in range(n):
        tp = np.sum((y_pred == c) & (y_true == c))
        fp = np.sum((y_pred == c) & (y_true != c))
        fn = np.sum((y_pred != c) & (y_true == c))
        if tp + fp + fn:
            f1.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1)) if f1 else 0.0


def evaluate(net, loader, device) -> dict:
    net.eval()
    yb, pb, yd, pd = [], [], [], []
    with torch.inference_mode():
        for x, b, d in loader:
            ob, od = net(x.to(device))
            yb += b.tolist(); pb += ob.argmax(1).cpu().tolist()  # noqa: E702
            yd += d.tolist(); pd += od.argmax(1).cpu().tolist()  # noqa: E702
    yb, pb, yd, pd = map(np.array, (yb, pb, yd, pd))
    return {
        "birads_acc": float((yb == pb).mean()),
        "birads_f1": macro_f1(yb, pb, len(BIRADS_CLASSES)),
        "density_acc": float((yd == pd).mean()),
        "density_f1": macro_f1(yd, pd, len(DENSITY_CLASSES)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default="weights/birads_model.pt")
    ap.add_argument("--backbone", default="tf_efficientnetv2_s")
    ap.add_argument("--height", type=int, default=1024)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-pretrained", action="store_true", help="do not download ImageNet weights")
    args = ap.parse_args()

    rows = [r for r in csv.DictReader(open(args.csv, encoding="utf-8")) if r["birads"] in BIRADS_CLASSES]
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] != "train"]
    size = (args.height, args.width)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"train {len(train_rows)}  val {len(val_rows)}  device {device}")

    # Class weights: BI-RADS 1 dominates screening data, 4-5 are rare.
    counts = np.bincount([BIRADS_CLASSES.index(r["birads"]) for r in train_rows], minlength=len(BIRADS_CLASSES))
    w_birads = torch.tensor(1.0 / np.sqrt(np.maximum(counts, 1)), dtype=torch.float32)
    w_birads = (w_birads / w_birads.mean()).to(device)

    train_dl = DataLoader(MammoDataset(train_rows, size, True), args.batch, shuffle=True,
                          num_workers=args.workers, drop_last=len(train_rows) > args.batch)
    val_dl = DataLoader(MammoDataset(val_rows, size, False), args.batch, num_workers=args.workers)

    net = build_net(args.backbone, pretrained=not args.no_pretrained).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, args.lr, total_steps=args.epochs * max(len(train_dl), 1))
    scaler = torch.amp.GradScaler(enabled=device == "cuda")

    best = -1.0
    for epoch in range(args.epochs):
        net.train()
        losses = []
        for x, b, d in train_dl:
            x, b, d = x.to(device), b.to(device), d.to(device)
            with torch.autocast(device, enabled=device == "cuda"):
                ob, od = net(x)
                loss = F.cross_entropy(ob, b, weight=w_birads) + F.cross_entropy(od, d)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            losses.append(loss.item())
        metrics = evaluate(net, val_dl, device) if val_rows else {"birads_f1": 0.0}
        print(f"epoch {epoch + 1}/{args.epochs}  loss {np.mean(losses):.4f}  " +
              "  ".join(f"{k} {v:.3f}" for k, v in metrics.items()))
        if metrics["birads_f1"] >= best:
            best = metrics["birads_f1"]
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": net.state_dict(), "backbone": args.backbone, "img_size": size,
                        "metrics": metrics, "epoch": epoch + 1}, args.out)
            print(f"  saved -> {args.out}")


if __name__ == "__main__":
    main()
