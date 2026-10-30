"""Loading mammograms (DICOM, PNG, JPG) and basic preprocessing."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

DICOM_EXT = {".dcm", ".dicom", ""}
RASTER_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


@dataclass(eq=False)
class MammoImage:
    pixels: np.ndarray  # uint8, HxW, breast tissue bright
    source: str
    laterality: str | None = None  # "R" | "L"
    view: str | None = None  # "CC" | "MLO" | other DICOM ViewPosition
    laterality_estimated: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.laterality or '?'}-{self.view or '?'}"


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    lo, hi = np.percentile(arr, 0.5), np.percentile(arr, 99.5)
    if hi <= lo:
        lo, hi = float(arr.min()), float(arr.max() or 1)
    arr = np.clip((arr - lo) / (hi - lo), 0, 1)
    return (arr * 255).astype(np.uint8)


def _is_dicom(path: Path) -> bool:
    if path.suffix.lower() in {".dcm", ".dicom"}:
        return True
    try:
        with open(path, "rb") as f:
            f.seek(128)
            return f.read(4) == b"DICM"
    except OSError:
        return False


def _dicom_age(age: str) -> str:
    """DICOM AS value "052Y" -> "52"; other units (D/W/M) are kept as is."""
    m = re.fullmatch(r"0*(\d+)Y", age.strip())
    return m.group(1) if m else age


def load_dicom(path: Path) -> MammoImage:
    import pydicom

    try:  # pydicom >= 3
        from pydicom.pixels import apply_modality_lut, apply_voi_lut
    except ImportError:  # pydicom 2.x
        from pydicom.pixel_data_handlers.util import apply_modality_lut, apply_voi_lut

    ds = pydicom.dcmread(str(path))
    arr = ds.pixel_array
    if arr.ndim == 3:  # multi-frame (e.g. tomosynthesis) -> central frame
        arr = arr[arr.shape[0] // 2]
    arr = apply_modality_lut(arr, ds)
    try:
        arr = apply_voi_lut(arr, ds, index=0)
    except Exception:
        pass
    if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
        arr = arr.max() - arr
    lat = str(getattr(ds, "ImageLaterality", "") or getattr(ds, "Laterality", "")).upper() or None
    view = str(getattr(ds, "ViewPosition", "") or "").upper() or None
    meta = {
        "patient_id": str(getattr(ds, "PatientID", "") or ""),
        "patient_name": str(getattr(ds, "PatientName", "") or ""),
        "patient_age": _dicom_age(str(getattr(ds, "PatientAge", "") or "")),
        "study_date": str(getattr(ds, "StudyDate", "") or ""),
        "manufacturer": str(getattr(ds, "Manufacturer", "") or ""),
        "modality": str(getattr(ds, "Modality", "") or ""),
    }
    return MammoImage(_to_uint8(arr), str(path), lat if lat in {"R", "L"} else None, view, meta=meta)


def load_raster(path: Path) -> MammoImage:
    img = Image.open(path)
    if img.mode in {"I;16", "I;16B", "I", "F"}:
        arr = _to_uint8(np.array(img))
    else:
        arr = np.array(img.convert("L"))
    return MammoImage(arr, str(path))


_LAT_VIEW = re.compile(r"(?:^|[^A-Z])(R|L|RIGHT|LEFT)[ _\-.]*(CC|MLO|ML|LM|XCCL)(?:[^A-Z]|$)")


def guess_from_filename(name: str) -> tuple[str | None, str | None]:
    m = _LAT_VIEW.search(Path(name).stem.upper())
    if not m:
        return None, None
    return m.group(1)[0], m.group(2)


def estimate_laterality(pixels: np.ndarray) -> str:
    """Chest wall side carries more tissue: right breast -> chest wall on the image's right."""
    h, w = pixels.shape
    left = float(pixels[:, : w // 2].mean())
    right = float(pixels[:, w // 2 :].mean())
    return "R" if right > left else "L"


def load_image(path: str | Path) -> MammoImage:
    path = Path(path)
    img = load_dicom(path) if _is_dicom(path) else load_raster(path)
    if img.laterality is None or img.view is None:
        lat, view = guess_from_filename(path.name)
        img.laterality = img.laterality or lat
        img.view = img.view or view
    if img.laterality is None:
        img.laterality = estimate_laterality(img.pixels)
        img.laterality_estimated = True
    return img


def crop_breast(pixels: np.ndarray, margin: int = 10) -> np.ndarray:
    """Remove background and labels: keep the bounding box of the largest bright component."""
    import cv2

    small_scale = 512 / max(pixels.shape)
    small = cv2.resize(pixels, None, fx=small_scale, fy=small_scale, interpolation=cv2.INTER_AREA)
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return pixels
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = stats[idx, :4]
    x0 = max(int(x / small_scale) - margin, 0)
    y0 = max(int(y / small_scale) - margin, 0)
    x1 = min(int((x + w) / small_scale) + margin, pixels.shape[1])
    y1 = min(int((y + h) / small_scale) + margin, pixels.shape[0])
    crop = pixels[y0:y1, x0:x1]
    return crop if crop.size > 0.05 * pixels.size else pixels
