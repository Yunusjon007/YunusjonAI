import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mammo_ai import birads as br
from mammo_ai.db import Database
from mammo_ai.imaging import crop_breast, guess_from_filename, load_image
from mammo_ai.models.base import Backend, BreastPrediction
from mammo_ai.pipeline import Finding, analyze
from mammo_ai.report import LOCALE_DIR, available_languages, render


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, cancer=0.03, density=(0.1, 0.2, 0.6, 0.1)):
        self.cancer, self.density = cancer, list(density)
        self.calls = []

    def predict(self, views):
        self.calls.append(sorted(views))
        return BreastPrediction(cancer_prob=self.cancer, density_probs=self.density, sources=[self.name])


def breast_image(side: str, h=600, w=400) -> np.ndarray:
    """Synthetic breast: bright half-ellipse against the chest wall, plus a text label in a corner."""
    yy, xx = np.mgrid[0:h, 0:w]
    cx = w if side == "R" else 0
    mask = ((xx - cx) / (0.8 * w)) ** 2 + ((yy - h / 2) / (0.45 * h)) ** 2 <= 1
    img = np.zeros((h, w), np.uint8)
    img[mask] = 160
    img[10:20, (5 if side == "R" else w - 25) : (25 if side == "R" else w - 5)] = 255  # marker
    return img


def write_png(tmp_path: Path, name: str, side: str) -> str:
    p = tmp_path / name
    Image.fromarray(breast_image(side)).save(p)
    return str(p)


def write_dicom(tmp_path: Path, name: str, side: str, view: str, monochrome1=False) -> str:
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.1.2"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(str(tmp_path / name), {}, file_meta=meta, preamble=b"\0" * 128)
    arr = breast_image(side).astype(np.uint16) * 16
    if monochrome1:
        arr = arr.max() - arr
    ds.Rows, ds.Columns = arr.shape
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 12, 11
    ds.SamplesPerPixel, ds.PixelRepresentation = 1, 0
    ds.PhotometricInterpretation = "MONOCHROME1" if monochrome1 else "MONOCHROME2"
    ds.PixelData = arr.tobytes()
    ds.ImageLaterality, ds.ViewPosition = side, view
    ds.PatientID, ds.PatientAge, ds.Modality = "P-001", "052Y", "MG"
    path = tmp_path / name
    ds.save_as(str(path), enforce_file_format=True)
    return str(path)


def test_locales_have_all_english_keys():
    en = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))

    def keys(d, prefix=""):
        out = set()
        for k, v in d.items():
            out |= keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
        return out

    for lang in ("ru", "uz"):
        other = json.loads((LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        assert keys(en) == keys(other), lang
    assert {"en", "ru", "uz"} <= set(available_languages())


def test_birads_mapping_and_hierarchy():
    t = [0.10, 0.20, 0.35, 0.55, 0.80]
    assert [br.from_score(s, t) for s in (0.01, 0.15, 0.3, 0.5, 0.7, 0.95)] == ["1", "3", "4A", "4B", "4C", "5"]
    assert br.worst(["1", "3"]) == "3"
    assert br.worst(["3", "0"]) == "0"
    assert br.worst(["0", "4A"]) == "4A"
    assert br.worst(["2", "6"]) == "6"


def test_filename_and_laterality():
    assert guess_from_filename("pt1_R_CC.png") == ("R", "CC")
    assert guess_from_filename("LMLO.jpg") == ("L", "MLO")
    assert guess_from_filename("image.png") == (None, None)


def test_dicom_monochrome1_and_tags(tmp_path):
    img = load_image(write_dicom(tmp_path, "a.dcm", "L", "MLO", monochrome1=True))
    assert (img.laterality, img.view) == ("L", "MLO")
    assert img.meta["patient_id"] == "P-001"
    assert img.pixels.dtype == np.uint8
    # after MONOCHROME1 inversion tissue (left side for L) must be brighter than background
    assert img.pixels[:, :100].mean() > img.pixels[:, -50:].mean()


def test_png_laterality_estimated_and_crop(tmp_path):
    img = load_image(write_png(tmp_path, "scan.png", "R"))
    assert img.laterality == "R" and img.laterality_estimated
    cropped = crop_breast(img.pixels)
    assert cropped.shape[1] < img.pixels.shape[1]


def test_full_study_reports_and_db(tmp_path):
    files = [
        write_dicom(tmp_path, "rcc.dcm", "R", "CC"),
        write_dicom(tmp_path, "rmlo.dcm", "R", "MLO"),
        write_png(tmp_path, "L_CC.png", "L"),
        write_png(tmp_path, "L_MLO.png", "L"),
    ]
    backend = FakeBackend(cancer=0.03)
    findings = [Finding(side="L", type="lymph_node", location="uoq", size_mm="6")]
    res = analyze(files, backend, findings=findings)
    assert backend.calls == [["cc", "mlo"], ["cc", "mlo"]]
    assert res.breasts["R"].birads == "1"
    assert res.breasts["L"].birads == "2"  # benign finding entered by the radiologist
    assert res.overall == "2" and res.density == "C"
    assert res.patient["patient_id"] == "P-001"

    reports = {lang: render(res, lang) for lang in ("uz", "ru", "en")}
    assert "BI-RADS 2" in reports["uz"] and "Xavfsiz" in reports["uz"]
    assert "Доброкачественные" in reports["ru"]
    assert "heterogeneously dense" in reports["en"]
    assert "Intramammar limfa tugun" in reports["uz"]
    for text in reports.values():
        assert "{" not in text  # no unfilled placeholders

    db = Database(str(tmp_path / "db" / "m.sqlite3"))
    sid = db.save(res, reports, files)
    assert db.list_studies()[0]["overall_birads"] == "2"
    assert "BI-RADS" in db.get_report(sid, "ru")
    db.set_ground_truth(sid, final_birads="2", pathology="benign")
    assert db.list_studies()[0]["pathology"] == "benign"
    assert Path(db.export_csv(str(tmp_path / "out.csv"))).read_text().startswith("id,")


@pytest.mark.parametrize("score,cat", [(0.5, "4B"), (0.95, "5")])
def test_suspicious_and_override(tmp_path, score, cat):
    files = [write_png(tmp_path, "R_CC.png", "R")]
    res = analyze(files, FakeBackend(cancer=score, density=(0.7, 0.2, 0.05, 0.05)))
    assert res.breasts["R"].birads == cat and res.breasts["L"].birads is None
    text = render(res, "en")
    assert "Tissue diagnosis" in text and "No images of this breast" in text

    res = analyze(files, FakeBackend(cancer=score), overrides={"R": "3"})
    assert res.overall == "3" and res.breasts["R"].overridden
    assert "set by the radiologist" in render(res, "en")


def test_suspicious_finding_with_low_ai_category_is_flagged(tmp_path):
    files = [write_png(tmp_path, "L_CC.png", "L")]
    f = Finding(side="L", type="calcifications", morphology="fine_linear", distribution="segmental")
    res = analyze(files, FakeBackend(cancer=0.02), findings=[f])
    assert res.breasts["L"].birads == "1"
    assert "radiologist must set the final" in render(res, "en")
    assert "rentgenolog shifokor belgilashi shart" in render(res, "uz")


def test_dicom_age_format():
    from mammo_ai.imaging import _dicom_age

    assert _dicom_age("052Y") == "52" and _dicom_age("006M") == "006M"


def test_cli_writes_report_and_db(tmp_path, monkeypatch, capsys):
    import mammo_ai.cli as cli
    from mammo_ai.config import settings

    monkeypatch.setattr(cli, "load_backends", lambda _: FakeBackend(cancer=0.25))
    monkeypatch.setattr(cli, "load_detector", lambda _: None)
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "cli.sqlite3"))
    out = tmp_path / "r.md"
    files = [write_png(tmp_path, "R_CC.png", "R"), write_png(tmp_path, "L_MLO.png", "L")]
    assert cli.main([*files, "--lang", "uz,ru,en", "--out", str(out), "--left-birads", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "MAMMOGRAFIYA XULOSASI" in text and "ЗАКЛЮЧЕНИЕ МАММОГРАФИИ" in text and "MAMMOGRAPHY REPORT" in text
    assert "BI-RADS 4A" in text  # right: 25% -> 4A, overall = worst
    assert Database(settings.db_path).list_studies()[0]["left_birads"] == "2"


# ---- lesion detector, two-breast images ----------------------------------------------------------
from mammo_ai.detection import Detection, draw, finding_type  # noqa: E402
from mammo_ai.imaging import shows_two_breasts, split_two_breasts  # noqa: E402


class FakeDetector:
    name = "fake-detector"

    def __init__(self, boxes_for=None):
        self.boxes_for = boxes_for or (lambda px: [])

    def detect(self, pixels):
        return self.boxes_for(pixels)


def two_breast_png(tmp_path: Path) -> str:
    """Back-to-back CC views like a teaching image: R on the viewer's left, L on the right."""
    img = np.concatenate([breast_image("R"), breast_image("L")], axis=1)
    img[:, :8] = img[:, -8:] = 0
    p = tmp_path / "both.png"
    Image.fromarray(img).save(p)
    return str(p)


def test_two_breasts_in_one_image_are_split(tmp_path):
    path = two_breast_png(tmp_path)
    img = load_image(path)
    assert shows_two_breasts(img.pixels)
    parts = split_two_breasts(img)
    assert [p.laterality for p in parts] == ["R", "L"] and all(p.split_from_pair for p in parts)
    assert not shows_two_breasts(breast_image("R"))  # a single breast is never split
    assert split_two_breasts(img, force=False) == [img]

    res = analyze([path], FakeBackend())
    assert res.split and res.breasts["R"].views and res.breasts["L"].views
    assert "split in the middle automatically" in render(res, "en")


def test_detected_lesion_is_never_birads_1(tmp_path):
    files = [write_png(tmp_path, "R_CC.png", "R"), write_png(tmp_path, "L_CC.png", "L")]
    fa = Detection(100, 200, 160, 260, "mass", 0.81, "mass")
    det = FakeDetector(lambda px: [fa] if px[:, : px.shape[1] // 2].mean() > px[:, px.shape[1] // 2 :].mean() else [])
    res = analyze(files, FakeBackend(cancer=0.02), detector=det)
    left, right = res.breasts["L"], res.breasts["R"]
    assert left.birads == "3" and len(left.ai_findings) == 1  # low cancer score, but a mass is there
    assert right.birads == "1" and not right.ai_findings
    assert res.detector_used and "fake-detector" in res.models
    text = render(res, "uz")
    assert "qizil aylana" in text and "fibroadenoma" in text and "Hajmli hosila — ishonch 81%" in text
    assert "Hosila detektori o'rnatilmagan" not in text

    # circles are drawn on the left breast image only
    rgb = {label: px for px, label in res.thumbnails}
    l_img, r_img = rgb["L-CC"], rgb["R-CC"]
    assert l_img.ndim == 3 and (l_img[..., 0].astype(int) - l_img[..., 1]).max() > 100
    assert (r_img[..., 0].astype(int) - r_img[..., 1]).max() == 0
    saved = res.save_annotated(str(tmp_path / "ann"))
    assert len(saved) == 2 and all(Path(p).exists() for p in saved)


def test_without_detector_low_score_warns(tmp_path):
    res = analyze([write_png(tmp_path, "R_CC.png", "R")], FakeBackend(cancer=0.02))
    assert res.breasts["R"].birads == "1" and not res.detector_used
    for lang, phrase in (("uz", "ANIQLAMAYDI"), ("ru", "НЕ выявляет"), ("en", "does NOT detect")):
        assert phrase in render(res, lang)


def test_ai_finding_size_from_dicom_pixel_spacing(tmp_path):
    path = write_dicom(tmp_path, "l.dcm", "L", "CC")
    import pydicom

    ds = pydicom.dcmread(path)
    ds.ImagerPixelSpacing = [0.1, 0.1]
    ds.save_as(path)
    det = FakeDetector(lambda px: [Detection(10, 10, 160, 110, "mass", 0.9)])  # 150 px wide
    res = analyze([path], FakeBackend(), detector=det)
    assert res.breasts["L"].ai_findings[0].size_mm == "15"
    assert "≈ 15 mm" in render(res, "en")


def test_finding_type_mapping_and_draw():
    assert finding_type("Mass") == "mass" and finding_type("Suspicious Calcification") == "calcifications"
    assert finding_type("Focal Asymmetry") == "asymmetry" and finding_type("Architectural Distortion") == "distortion"
    assert finding_type("tumor") == "mass" and finding_type("object") == "ai_lesion"
    img = breast_image("L")
    out = draw(img, [Detection(50, 50, 120, 120, "mass", 0.5)])
    assert out.shape == (*img.shape, 3) and (out != np.repeat(img[..., None], 3, 2)).any()
