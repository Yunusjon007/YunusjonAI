"""Loading mammograms (DICOM, PNG, JPG) and basic preprocessing."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
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
    pixel_spacing: float | None = None  # mm per pixel (DICOM), None for PNG/JPG
    split_from_pair: bool = False  # cut out of an image that showed both breasts
    detections: list = field(default_factory=list)  # detection.Detection, in `pixels` coordinates

    @property
    def label(self) -> str:
        return f"{self.laterality or '?'}-{self.view or '?'}"


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    lo, hi = np.percentile(arr, 0.5), np.percentile(arr, 99.5)
    if hi <= lo:
        lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:  # uniform image
        return np.zeros(arr.shape, np.uint8)
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
    spacing = getattr(ds, "ImagerPixelSpacing", None) or getattr(ds, "PixelSpacing", None)
    img = MammoImage(_to_uint8(arr), str(path), lat if lat in {"R", "L"} else None, view, meta=meta)
    img.pixel_spacing = float(spacing[0]) if spacing else None
    return img


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


def tissue_mask(pixels: np.ndarray) -> np.ndarray:
    """Breast vs. background. Otsu alone can split dense from fatty tissue, so the threshold
    is lowered well below it to keep grey fatty areas (where e.g. fibroadenomas sit)."""
    import cv2

    blur = cv2.GaussianBlur(pixels, (5, 5), 0)
    otsu, _ = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (blur > max(10.0, 0.4 * otsu)).astype(np.uint8) * 255


def crop_box(pixels: np.ndarray, margin: int = 10) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the breast: bounding box of the largest tissue component."""
    import cv2

    full = (0, 0, pixels.shape[1], pixels.shape[0])
    small_scale = 512 / max(pixels.shape)
    small = cv2.resize(pixels, None, fx=small_scale, fy=small_scale, interpolation=cv2.INTER_AREA)
    n, _, stats, _ = cv2.connectedComponentsWithStats(tissue_mask(small))
    if n <= 1:
        return full
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = stats[idx, :4]
    x0 = max(int(x / small_scale) - margin, 0)
    y0 = max(int(y / small_scale) - margin, 0)
    x1 = min(int((x + w) / small_scale) + margin, pixels.shape[1])
    y1 = min(int((y + h) / small_scale) + margin, pixels.shape[0])
    if (x1 - x0) * (y1 - y0) <= 0.05 * pixels.size:
        return full
    return x0, y0, x1, y1


def crop_breast(pixels: np.ndarray, margin: int = 10) -> np.ndarray:
    """Remove background and labels around the breast."""
    x0, y0, x1, y1 = crop_box(pixels, margin)
    return pixels[y0:y1, x0:x1]


def shows_two_breasts(pixels: np.ndarray) -> bool:
    """Both CC (or MLO) views side by side, chest walls touching in the middle (teaching images,
    screenshots of a viewer). A single breast always has tissue at its chest-wall edge."""
    h, w = pixels.shape
    if w / h < 1.15:
        return False
    cols = (tissue_mask(pixels) > 0).mean(0)
    edge = max(3, w // 40)
    center = cols[w // 2 - edge : w // 2 + edge].mean()
    return cols[:edge].mean() < 0.25 and cols[-edge:].mean() < 0.25 and center > 0.5


def split_two_breasts(img: MammoImage, force: bool | None = None) -> list[MammoImage]:
    """force: True = always split, False = never, None = detect automatically.
    Standard hanging: right breast on the viewer's left, left breast on the viewer's right."""
    if force is False or (force is None and not shows_two_breasts(img.pixels)):
        return [img]
    w = img.pixels.shape[1]
    halves = [("R", img.pixels[:, : w // 2]), ("L", img.pixels[:, w // 2 :])]
    return [
        replace(img, pixels=np.ascontiguousarray(px), laterality=side, laterality_estimated=False,
                split_from_pair=True, meta=dict(img.meta), detections=[])
        for side, px in halves
    ]
