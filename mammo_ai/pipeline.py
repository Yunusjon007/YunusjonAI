"""From image files to a structured study result."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from . import birads as br
from .config import Settings, settings as default_settings
from .imaging import MammoImage, crop_breast, load_image
from .models import Backend, BreastPrediction

SIDES = ("R", "L")

# Findings that are benign by definition in the ACR lexicon (BI-RADS 2).
_SUSPICIOUS = {
    "shape": {"irregular"},
    "margin": {"microlobulated", "indistinct", "spiculated"},
    "morphology": {"amorphous", "coarse_heterogeneous", "fine_pleomorphic", "fine_linear"},
    "distribution": {"linear", "segmental"},
    "asym_type": {"developing"},
}


@dataclass
class Finding:
    side: str
    type: str  # key of "finding_type" in the locale files
    shape: str = ""
    margin: str = ""
    density: str = ""
    morphology: str = ""
    distribution: str = ""
    asym_type: str = ""
    location: str = ""
    clock: str = ""
    depth: str = ""
    size_mm: str = ""
    assoc: list[str] = field(default_factory=list)
    note: str = ""

    def is_suspicious(self) -> bool:
        if self.type == "distortion":
            return True
        return any(getattr(self, k) in v for k, v in _SUSPICIOUS.items()) or "skin_retraction" in self.assoc

    def is_benign(self) -> bool:
        if self.type in {"lymph_node", "skin_lesion"}:
            return True
        if self.type == "mass":
            return self.density == "fat"
        if self.type == "calcifications":
            return self.morphology == "benign"
        return False


@dataclass
class BreastResult:
    side: str
    views: list[str] = field(default_factory=list)
    prediction: BreastPrediction | None = None
    birads: str | None = None
    ai_birads: str | None = None
    overridden: bool = False
    laterality_estimated: bool = False
    findings: list[Finding] = field(default_factory=list)

    @property
    def examined(self) -> bool:
        return self.prediction is not None or self.overridden


@dataclass
class StudyResult:
    breasts: dict[str, BreastResult]
    overall: str | None
    density: str | None
    density_conf: float | None
    patient: dict
    indication: str = ""
    comparison: str = ""
    models: list[str] = field(default_factory=list)
    thumbnails: list[tuple[np.ndarray, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("thumbnails")
        return d


def _views_dict(images: list[MammoImage]) -> list[dict[str, np.ndarray]]:
    """Group a breast's images into {"cc": ..., "mlo": ...} pairs (the model's expected input)."""
    is_cc = [(i.view or "").startswith("CC") or i.view == "XCCL" for i in images]
    cc = [i for i, c in zip(images, is_cc) if c]
    mlo = [i for i, c in zip(images, is_cc) if not c]
    groups = []
    while cc or mlo:
        g = {}
        if cc:
            g["cc"] = cc.pop(0).pixels
        if mlo:
            g["mlo"] = mlo.pop(0).pixels
        groups.append(g)
    return groups


def _combine(preds: list[BreastPrediction]) -> BreastPrediction:
    out = BreastPrediction(sources=sorted({s for p in preds for s in p.sources}))
    cancers = [p.cancer_prob for p in preds if p.cancer_prob is not None]
    if cancers:
        out.cancer_prob = max(cancers)
    for attr in ("density_probs", "birads_probs"):
        vals = [getattr(p, attr) for p in preds if getattr(p, attr) is not None]
        if vals:
            setattr(out, attr, np.mean(vals, 0).tolist())
    return out


def analyze(
    paths: list[str],
    backend: Backend,
    patient: dict | None = None,
    findings: list[Finding] | None = None,
    overrides: dict[str, str] | None = None,
    indication: str = "",
    comparison: str = "",
    side_override: dict[str, str] | None = None,
    cfg: Settings = default_settings,
) -> StudyResult:
    """paths: DICOM/PNG/JPG files of one study. overrides: {"R": "4B"} set by the radiologist.
    side_override: {path: "R"|"L"} when the user knows the side better than the file does."""
    images = [load_image(p) for p in paths]
    for img in images:
        if side_override and side_override.get(img.source) in SIDES:
            img.laterality, img.laterality_estimated = side_override[img.source], False
        img.pixels = crop_breast(img.pixels)

    patient = dict(patient or {})
    for img in images:  # fill blanks from DICOM tags
        for k, v in img.meta.items():
            if v and not patient.get(k):
                patient[k] = v

    findings = findings or []
    overrides = overrides or {}
    breasts: dict[str, BreastResult] = {}
    models: set[str] = set()
    for side in SIDES:
        side_imgs = [i for i in images if i.laterality == side]
        res = BreastResult(side, views=[i.label for i in side_imgs], findings=[f for f in findings if f.side == side])
        res.laterality_estimated = any(i.laterality_estimated for i in side_imgs)
        if side_imgs:
            res.prediction = _combine([backend.predict(g) for g in _views_dict(side_imgs)])
            models.update(res.prediction.sources)
            res.ai_birads = br.assess(res.prediction, cfg.birads_thresholds)
            res.birads = res.ai_birads
            if res.birads == "1" and res.findings and all(f.is_benign() for f in res.findings):
                res.birads = "2"
        if overrides.get(side) in br.CATEGORIES:
            res.birads, res.overridden = overrides[side], True
        breasts[side] = res

    cats = [b.birads for b in breasts.values() if b.birads]
    overall = br.worst(cats) if cats else None

    density = conf = None
    dens = [(b.prediction.density_probs) for b in breasts.values() if b.prediction and b.prediction.density_probs]
    if dens:
        # ACR: the composition of the denser breast describes the study.
        best = max(dens, key=lambda p: int(np.argmax(p)))
        density, conf = "ABCD"[int(np.argmax(best))], float(max(best))

    thumbs = [(i.pixels, i.label) for i in images]
    return StudyResult(breasts, overall, density, conf, patient, indication, comparison, sorted(models), thumbs)
