"""MammoAI web interface.  Run:  python app.py   then open http://127.0.0.1:7860"""
from __future__ import annotations

import os
import tempfile
from dataclasses import asdict

import gradio as gr

from mammo_ai import birads as br
from mammo_ai.config import settings
from mammo_ai.db import Database
from mammo_ai.pipeline import Finding, analyze
from mammo_ai.report import available_languages, load_locale, render, render_many

UZ, EN = load_locale("uz"), load_locale("en")
FINDING_FIELDS = ["type", "shape", "margin", "density", "morphology", "distribution", "asym_type", "location", "depth"]
_TABLE = {"type": "finding_type", "density": "mass_density"}


def _choices(table: str) -> list[tuple[str, str]]:
    """Dropdown options "uzbek (english)" -> key, plus an empty option."""
    return [("—", "")] + [(f"{UZ[table][k]} ({EN[table][k]})", k) for k in EN[table]]


def _field_label(key: str) -> str:
    if key == "type":
        return "Topilma / Находка / Finding"
    if key == "asym_type":
        return f"{UZ['finding_type']['asymmetry']} ({EN['finding_type']['asymmetry']})"
    return f"{UZ['field'][key]} ({EN['field'][key]})"


class App:
    def __init__(self, backend=None, db: Database | None = None, detector="auto"):
        self._backend = backend
        self._detector = detector  # "auto" = load weights/detector.pt on first use (None if absent)
        self.db = db or Database(settings.db_path)

    @property
    def detector(self):
        if self._detector == "auto":
            from mammo_ai.detection import load_detector

            self._detector = load_detector(settings)
        return self._detector

    @property
    def backend(self):
        if self._backend is None:
            from mammo_ai.models import load_backends

            self._backend = load_backends(settings)
        return self._backend

    def run(self, files, lang, split, patient_id, patient_name, age, indication, comparison, r_over, l_over, findings):
        if not files:
            return [], "⚠️ Rasm yuklang / Загрузите снимки / Upload images", None
        paths = [f if isinstance(f, str) else f.name for f in files]
        try:
            backend = self.backend
        except Exception as exc:
            return [], f"❌ AI model yuklanmadi / модель не загружена / model not loaded:\n\n```\n{exc}\n```", None
        langs = available_languages() if lang == "all" else [lang]
        try:
            result = analyze(
                paths,
                backend,
                patient={"patient_id": patient_id, "patient_name": patient_name, "patient_age": age},
                findings=[Finding(**f) for f in findings or []],
                overrides={k: v for k, v in (("R", r_over), ("L", l_over)) if v},
                indication=indication,
                comparison=comparison,
                detector=self.detector,
                split_pairs={"auto": None, "yes": True, "no": False}[split],
            )
        except Exception as exc:
            return [], f"❌ Tahlil xatosi / ошибка анализа / analysis error:\n\n```\n{exc}\n```", None
        reports = {lg: render(result, lg) for lg in langs}
        study_id = self.db.save(result, reports, paths)
        text = render_many(result, langs)
        out = os.path.join(tempfile.mkdtemp(), f"mammo_report_{study_id}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        gallery = [(px, label) for px, label in result.thumbnails]
        status = "🎯 detektor: yoqilgan / включён / on" if result.detector_used else (
            "⚠️ detektor o'rnatilmagan / не установлен / not installed — `python scripts/download_detector.py`"
        )
        return gallery, f"`#{study_id}` · {status}\n\n" + text, out

    def history(self):
        rows = self.db.list_studies()
        cols = ["id", "created_at", "patient_id", "patient_name", "patient_age", "density",
                "right_birads", "left_birads", "overall_birads", "final_birads", "pathology"]
        return [[r[c] for c in cols] for r in rows]

    def show(self, study_id, lang):
        if not study_id:
            return ""
        return self.db.get_report(int(study_id), lang) or "—"

    def set_truth(self, study_id, final_birads, pathology):
        if study_id:
            self.db.set_ground_truth(int(study_id), final_birads or None, pathology or None)
        return self.history()

    def export(self):
        return self.db.export_csv(os.path.join(tempfile.mkdtemp(), "mammo_studies.csv"))


def add_finding(findings, side, clock, size, assoc, note, *values):
    if not values[0]:  # finding type is required
        return findings, _findings_rows(findings)
    f = dict(zip(FINDING_FIELDS, values), side=side, clock=clock or "", size_mm=f"{size:g}" if size else "",
             assoc=list(assoc or []), note=note or "")
    findings = (findings or []) + [asdict(Finding(**f))]
    return findings, _findings_rows(findings)


def _findings_rows(findings):
    return [
        [f["side"], UZ["finding_type"][f["type"]], UZ["location"].get(f["location"], ""), f["size_mm"]]
        for f in findings or []
    ]


def build(app: App) -> gr.Blocks:
    cats = [("AI", "")] + [(c, c) for c in br.CATEGORIES]
    langs = [(load_locale(lg)["lang_name"], lg) for lg in available_languages()] + [("Hammasi / Все / All", "all")]
    with gr.Blocks(title="MammoAI") as demo:
        gr.Markdown(
            "# MammoAI — mammografiya / маммография / mammography\n"
            "DICOM, PNG, JPG → ACR zichlik + BI-RADS xulosa (O'zbek · Русский · English). "
            "**Tibbiy buyum emas — yakuniy xulosani rentgenolog beradi.**"
        )
        findings = gr.State([])
        with gr.Tab("Tahlil / Анализ / Analysis"):
            with gr.Row():
                with gr.Column(scale=1):
                    files = gr.File(label="Rasmlar / Снимки / Images (R-CC, R-MLO, L-CC, L-MLO)", file_count="multiple")
                    lang = gr.Dropdown(langs, value=settings.default_lang, label="Til / Язык / Language")
                    split = gr.Radio(
                        [("Avto / Авто / Auto", "auto"), ("Ha / Да / Yes", "yes"), ("Yo'q / Нет / No", "no")],
                        value="auto",
                        label="Bitta rasmda ikkala bez / Обе железы на одном снимке / Both breasts in one image",
                    )
                    with gr.Accordion("Bemor / Пациент / Patient", open=False):
                        patient_id = gr.Textbox(label="ID")
                        patient_name = gr.Textbox(label="F.I.Sh. / ФИО / Name")
                        age = gr.Textbox(label="Yosh / Возраст / Age")
                        indication = gr.Textbox(label="Ko'rsatma / Показание / Indication")
                        comparison = gr.Textbox(label="Solishtirish / Сравнение / Comparison")
                    with gr.Accordion("Shifokor topilmalari / Находки врача / Radiologist findings", open=False):
                        side = gr.Radio([("O'ng / Right", "R"), ("Chap / Left", "L")], value="R", label="Tomon / Side")
                        values = [
                            gr.Dropdown(_choices(_TABLE.get(k, k)), value="", label=_field_label(k))
                            for k in FINDING_FIELDS
                        ]
                        with gr.Row():
                            clock = gr.Dropdown([""] + [str(h) for h in range(1, 13)], value="", label="Soat / Часы / Clock")
                            size = gr.Number(label="O'lcham / Размер / Size, mm", value=None, minimum=0)
                        assoc = gr.CheckboxGroup(_choices("assoc")[1:], label=_field_label("assoc"))
                        note = gr.Textbox(label="Izoh / Примечание / Note")
                        with gr.Row():
                            add_btn = gr.Button("➕ Qo'shish / Добавить / Add")
                            clear_btn = gr.Button("🗑 Tozalash / Очистить / Clear")
                        table = gr.Dataframe(headers=["side", "type", "location", "mm"], interactive=False)
                    with gr.Row():
                        r_over = gr.Dropdown(cats, value="", label="BI-RADS R (override)")
                        l_over = gr.Dropdown(cats, value="", label="BI-RADS L (override)")
                    run_btn = gr.Button("Tahlil qilish / Анализировать / Analyze", variant="primary")
                with gr.Column(scale=2):
                    gallery = gr.Gallery(
                        label="Topilmalar aylana bilan / Находки обведены / Findings circled", columns=4, height=420
                    )
                    report = gr.Markdown()
                    download = gr.File(label="Xulosa (.md)")
        with gr.Tab("Baza / База / Database"):
            hist = gr.Dataframe(
                headers=["id", "date", "patient_id", "name", "age", "density", "R", "L", "overall", "final", "pathology"],
                interactive=False,
            )
            with gr.Row():
                refresh = gr.Button("🔄")
                export_btn = gr.Button("CSV")
                csv_file = gr.File()
            with gr.Row():
                sid = gr.Number(label="Study #", precision=0)
                view_lang = gr.Dropdown(langs[:-1], value=settings.default_lang, label="Til / Язык")
                view_btn = gr.Button("Ko'rish / Открыть / Open")
            with gr.Row():
                final = gr.Dropdown([("", "")] + [(c, c) for c in br.CATEGORIES], label="Final BI-RADS")
                pathology = gr.Dropdown(["", "benign", "malignant", "high-risk"], label="Biopsiya / Biopsy")
                truth_btn = gr.Button("💾")
            saved = gr.Markdown()

        add_btn.click(add_finding, [findings, side, clock, size, assoc, note, *values], [findings, table])
        clear_btn.click(lambda: ([], []), None, [findings, table])
        run_btn.click(
            app.run,
            [files, lang, split, patient_id, patient_name, age, indication, comparison, r_over, l_over, findings],
            [gallery, report, download],
        )
        refresh.click(app.history, None, hist)
        export_btn.click(app.export, None, csv_file)
        view_btn.click(app.show, [sid, view_lang], saved)
        truth_btn.click(app.set_truth, [sid, final, pathology], hist)
        demo.load(app.history, None, hist)
    return demo


if __name__ == "__main__":
    build(App()).launch(
        server_name=os.getenv("HOST", "127.0.0.1"),
        server_port=int(os.getenv("PORT", "7860")),
        share=os.getenv("GRADIO_SHARE") == "1",
    )
