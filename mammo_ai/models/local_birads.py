"""Your own BI-RADS (1-5) + density (A-D) classifier, trained with train/train_birads.py
on an open dataset such as VinDr-Mammo (which has per-breast BI-RADS and density labels)."""
from __future__ import annotations

import numpy as np

from .base import BIRADS_CLASSES, DENSITY_CLASSES, Backend, BreastPrediction


def build_net(backbone: str = "tf_efficientnetv2_s", pretrained: bool = False):
    import timm
    import torch.nn as nn

    class BiradsNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = timm.create_model(backbone, pretrained=pretrained, in_chans=1, num_classes=0)
            dim = self.encoder.num_features
            self.dropout = nn.Dropout(0.2)
            self.birads_head = nn.Linear(dim, len(BIRADS_CLASSES))
            self.density_head = nn.Linear(dim, len(DENSITY_CLASSES))

        def forward(self, x):
            f = self.dropout(self.encoder(x))
            return self.birads_head(f), self.density_head(f)

    return BiradsNet()


def to_tensor(img: np.ndarray, size: tuple[int, int]):
    """uint8 HxW -> float tensor 1x1xHxW, normalized to [-1, 1]."""
    import cv2
    import torch

    img = cv2.resize(img, (size[1], size[0]), interpolation=cv2.INTER_AREA)
    x = torch.from_numpy(img).float().div(255.0).sub(0.5).div(0.5)
    return x[None, None]


def orient_left(img: np.ndarray) -> np.ndarray:
    """Flip so the chest wall is always on the left (as during training)."""
    h, w = img.shape
    return img[:, ::-1] if img[:, w // 2 :].mean() > img[:, : w // 2].mean() else img


class LocalBiradsBackend(Backend):
    name = "local_birads"

    def __init__(self, ckpt_path: str, device: str = "auto"):
        import torch

        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        self.size = tuple(ckpt.get("img_size", (1024, 512)))
        self.net = build_net(ckpt.get("backbone", "tf_efficientnetv2_s"))
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.eval().to(self.device)
        self._torch = torch

    def predict(self, views: dict[str, np.ndarray]) -> BreastPrediction:
        torch = self._torch
        birads, density = [], []
        with torch.inference_mode():
            for img in views.values():
                x = to_tensor(np.ascontiguousarray(orient_left(img)), self.size).to(self.device)
                b, d = self.net(x)
                birads.append(torch.softmax(b, 1)[0].cpu().numpy())
                density.append(torch.softmax(d, 1)[0].cpu().numpy())
        return BreastPrediction(
            birads_probs=np.mean(birads, 0).tolist(),
            density_probs=np.mean(density, 0).tolist(),
            sources=[self.name],
        )
