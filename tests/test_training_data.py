"""Training-data converters on tiny fake datasets laid out like the real downloads."""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "train"), str(ROOT / "tests")]

import prepare_cbis_det  # noqa: E402
from evaluate_detector import hit  # noqa: E402
from test_pipeline import breast_image, write_dicom  # noqa: E402

from mammo_ai.imaging import crop_box  # noqa: E402

LESION = (120, 260, 180, 320)  # x0, y0, x1, y1 in the full image
FIELDS = ["patient_id", "breast density", "left or right breast", "image view", "abnormality id",
          "abnormality type", "assessment", "pathology", "subtlety",
          "image file path", "cropped image file path", "ROI mask file path"]


def full_and_mask(side="L"):
    full = breast_image(side)
    mask = np.zeros_like(full)
    x0, y0, x1, y1 = LESION
    mask[y0:y1, x0:x1] = 255
    return full, mask


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def row(case: str, roi_case: str, full_uid: str, roi_uid: str, crop_uid: str) -> dict:
    return {
        "patient_id": "P_00001", "breast density": "2", "left or right breast": "LEFT", "image view": "CC",
        "abnormality id": "1", "abnormality type": "mass", "assessment": "3", "pathology": "BENIGN", "subtlety": "4",
        "image file path": f"{case}/1.3.study/{full_uid}/000000.dcm",
        "cropped image file path": f"{roi_case}/1.3.study2/{crop_uid}/000000.dcm",
        "ROI mask file path": f"{roi_case}/1.3.study2/{roi_uid}/000001.dcm\n",  # real CSVs have stray newlines
    }


def kaggle_layout(root: Path, mask_size_off: int = 1):
    """jpeg/<SeriesUID>/1-1.jpg; the ROI series holds the small crop and the full-size mask."""
    full, mask = full_and_mask()
    (root / "jpeg" / "uid.full").mkdir(parents=True)
    Image.fromarray(full).save(root / "jpeg" / "uid.full" / "1-1.jpg", quality=95)
    roi = root / "jpeg" / "uid.roi"
    roi.mkdir(parents=True)
    Image.fromarray(full[250:330, 110:190]).save(roi / "1-1.jpg")  # cropped patch
    m = Image.fromarray(mask).resize((mask.shape[1] + mask_size_off, mask.shape[0]), Image.NEAREST)
    m.save(roi / "1-2.jpg", quality=95)  # JPEG conversion changed the size slightly
    case = "Mass-Training_P_00001_LEFT_CC"
    write_csv(root / "csv" / "mass_case_description_train_set.csv",
              [row(case, case + "_1", "uid.full", "uid.roi", "uid.roi")])


def tcia_layout(root: Path):
    """Case folders with DICOMs; UIDs in the CSV do not match folder names."""
    full, mask = full_and_mask()
    case = "Mass-Test_P_00002_LEFT_CC"
    write_dicom(_mk(root / case / "07-20-2016-x" / "1.000000-full mammogram images-123"), "1-1.dcm", "L", "CC")
    roi_dir = _mk(root / (case + "_1") / "07-21-2016-x" / "1.000000-ROI mask images-456")
    _save_dicom(roi_dir / "1-1.dcm", full[250:330, 110:190])
    _save_dicom(roi_dir / "1-2.dcm", mask)
    write_csv(root / "CBIS-DDSM" / "mass_case_description_test_set.csv",
              [row(case, case + "_1", "1.3.6.nomatch", "1.3.6.nomatch2", "1.3.6.nomatch3")])


def _mk(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_dicom(path: Path, arr: np.ndarray):
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.1.2"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Rows, ds.Columns = arr.shape
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 8, 8, 7
    ds.SamplesPerPixel, ds.PixelRepresentation = 1, 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = arr.astype(np.uint8).tobytes()
    ds.save_as(str(path), enforce_file_format=True)


def expected_yolo_box(size: int = 1024):
    full, _ = full_and_mask()
    x0, y0, x1, y1 = crop_box(full)
    cw, ch = x1 - x0, y1 - y0
    lx0, ly0, lx1, ly1 = LESION
    return ((lx0 + lx1) / 2 - x0) / cw, ((ly0 + ly1) / 2 - y0) / ch, (lx1 - lx0) / cw, (ly1 - ly0) / ch


def read_labels(out: Path, split: str) -> list[list[float]]:
    files = list((out / "labels" / split).glob("*.txt"))
    assert len(files) == 1
    return [list(map(float, line.split())) for line in files[0].read_text().split("\n") if line.strip()]


@pytest.mark.parametrize("layout,split", [(kaggle_layout, "train"), (tcia_layout, "val")])
def test_cbis_converter_puts_box_on_the_lesion(tmp_path, monkeypatch, layout, split):
    root, out = tmp_path / "cbis", tmp_path / "out"
    layout(root)
    monkeypatch.setattr(sys, "argv", ["x", "--root", str(root), "--out", str(out)])
    assert prepare_cbis_det.main() == 0
    labels = read_labels(out, split)
    assert len(labels) == 1 and labels[0][0] == 0  # one mass
    assert labels[0][1:] == pytest.approx(expected_yolo_box(), abs=0.01)
    assert (out / "data.yaml").read_text().count("mass") == 1
    assert len(list((out / "images" / split).glob("*.png"))) == 1


def test_cbis_converter_reports_missing_files(tmp_path, monkeypatch, capsys):
    root = tmp_path / "cbis"
    kaggle_layout(root)
    (root / "jpeg" / "uid.full" / "1-1.jpg").unlink()
    monkeypatch.setattr(sys, "argv", ["x", "--root", str(root), "--out", str(tmp_path / "out")])
    assert prepare_cbis_det.main() == 2
    text = capsys.readouterr().out
    assert "Too many files were not found" in text and "looked for: Mass-Training_P_00001_LEFT_CC/" in text


def test_cbis_converter_without_csvs(tmp_path, monkeypatch, capsys):
    (tmp_path / "empty").mkdir()
    monkeypatch.setattr(sys, "argv", ["x", "--root", str(tmp_path / "empty"), "--out", str(tmp_path / "o")])
    assert prepare_cbis_det.main() == 1
    assert "inspect_dataset.py" in capsys.readouterr().out


def test_hit_rule():
    gt = (100, 100, 200, 200)
    assert hit((140, 140, 160, 160), gt)  # centre inside
    assert hit((60, 60, 190, 190), gt)  # big overlap
    assert not hit((300, 300, 350, 350), gt)
