"""Wrapper around ianpan/mammoscreen (Apache-2.0, https://huggingface.co/ianpan/mammoscreen).

Ensemble of 3 EfficientNetV2-S nets, pretrained on CBIS-DDSM and trained on the RSNA
Screening Mammography challenge data. Outputs a cancer probability and ACR density (A-D).
The weights are downloaded from Hugging Face on first use (~hundreds of MB).
"""
from __future__ import annotations

import numpy as np

from .base import Backend, BreastPrediction, sigmoid_if_needed, softmax_if_needed


def _resolve_device(device: str) -> str:
    import torch

    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


def _to_numpy(x) -> np.ndarray:
    if hasattr(x, "detach"):
        x = x.detach().cpu().float().numpy()
    return np.asarray(x)


class MammoscreenBackend(Backend):
    name = "mammoscreen"

    def __init__(self, model_id: str, device: str = "auto", crop_model_id: str | None = None):
        import torch
        from transformers import AutoModel

        self.device = _resolve_device(device)
        self.model = AutoModel.from_pretrained(model_id, trust_remote_code=True).eval().to(self.device)
        self.cropper = None
        if crop_model_id:
            try:
                self.cropper = AutoModel.from_pretrained(crop_model_id, trust_remote_code=True).eval().to(self.device)
            except Exception as exc:  # cropper is optional
                print(f"[mammoscreen] crop model not loaded ({exc}); using OpenCV crop")
        self._torch = torch

    def _hf_crop(self, img: np.ndarray) -> np.ndarray:
        torch = self._torch
        shape = torch.tensor([img.shape[:2]]).to(self.device)
        x = self.cropper.preprocess(img)
        x = torch.from_numpy(x).expand(1, 1, -1, -1).float().to(self.device)
        with torch.inference_mode():
            coords = self.cropper(x, shape)
        x0, y0, w, h = (int(v) for v in _to_numpy(coords).reshape(-1)[:4])
        crop = img[y0 : y0 + h, x0 : x0 + w]
        return crop if crop.size else img

    def predict(self, views: dict[str, np.ndarray]) -> BreastPrediction:
        inputs = {}
        for key, img in views.items():
            if self.cropper is not None:
                try:
                    img = self._hf_crop(img)
                except Exception as exc:
                    print(f"[mammoscreen] HF crop failed ({exc}); using image as is")
            inputs[key] = img
        with self._torch.inference_mode():
            out = self.model(inputs, device=self.device)

        cancer = density = None
        if isinstance(out, dict):
            for k, v in out.items():
                k = k.lower()
                if "cancer" in k:
                    cancer = sigmoid_if_needed(_to_numpy(v).reshape(-1)[0])
                elif "density" in k:
                    density = softmax_if_needed(_to_numpy(v).reshape(-1, 4)[0]).tolist()
        else:  # tuple/list: (cancer, density)
            cancer = sigmoid_if_needed(_to_numpy(out[0]).reshape(-1)[0])
            if len(out) > 1:
                density = softmax_if_needed(_to_numpy(out[1]).reshape(-1, 4)[0]).tolist()
        return BreastPrediction(cancer_prob=cancer, density_probs=density, sources=[self.name])
