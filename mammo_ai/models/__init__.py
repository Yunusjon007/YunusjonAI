"""Model backends. Every backend is optional; available ones are combined."""
from __future__ import annotations

import os

import numpy as np

from ..config import Settings
from .base import Backend, BreastPrediction


class Ensemble(Backend):
    name = "ensemble"

    def __init__(self, backends: list[Backend]):
        if not backends:
            raise RuntimeError(
                "No AI model could be loaded. Install requirements (torch, transformers, timm) and make sure "
                "huggingface.co is reachable, or put a trained checkpoint at MAMMO_BIRADS_CKPT."
            )
        self.backends = backends

    def predict(self, views: dict[str, np.ndarray]) -> BreastPrediction:
        preds = [b.predict(views) for b in self.backends]
        out = BreastPrediction()
        for p in preds:
            out.sources += p.sources
            if p.cancer_prob is not None:
                out.cancer_prob = p.cancer_prob if out.cancer_prob is None else max(out.cancer_prob, p.cancer_prob)
            if p.birads_probs is not None:
                out.birads_probs = p.birads_probs
        densities = [p.density_probs for p in preds if p.density_probs is not None]
        if densities:
            out.density_probs = np.mean(densities, 0).tolist()
        return out


def load_backends(settings: Settings) -> Ensemble:
    backends: list[Backend] = []
    errors = []
    try:
        from .mammoscreen import MammoscreenBackend

        backends.append(
            MammoscreenBackend(
                settings.mammoscreen_id,
                settings.device,
                settings.mammo_crop_id if settings.use_hf_crop else None,
            )
        )
    except Exception as exc:
        errors.append(f"mammoscreen: {exc}")
    if os.path.exists(settings.local_birads_ckpt):
        try:
            from .local_birads import LocalBiradsBackend

            backends.append(LocalBiradsBackend(settings.local_birads_ckpt, settings.device))
        except Exception as exc:
            errors.append(f"local_birads: {exc}")
    for e in errors:
        print(f"[models] not loaded -> {e}")
    return Ensemble(backends)


__all__ = ["Backend", "BreastPrediction", "Ensemble", "load_backends"]
