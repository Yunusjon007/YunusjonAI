"""SQLite database of analysed studies, their images and reports (also usable as a dataset for retraining)."""
from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .pipeline import StudyResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS studies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    patient_id TEXT, patient_name TEXT, patient_age TEXT, study_date TEXT,
    indication TEXT,
    density TEXT,
    right_score REAL, left_score REAL,
    right_birads TEXT, left_birads TEXT, overall_birads TEXT,
    ai_overall_birads TEXT,
    models TEXT,
    result_json TEXT,
    -- ground truth filled in later (e.g. biopsy) -> used to calibrate thresholds / retrain
    final_birads TEXT, pathology TEXT
);
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    study_id INTEGER NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    path TEXT NOT NULL, label TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    study_id INTEGER NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    lang TEXT NOT NULL, text TEXT NOT NULL,
    PRIMARY KEY (study_id, lang)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.files_dir = self.path.parent / "images"
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def save(self, result: StudyResult, reports: dict[str, str], files: list[str], keep_images: bool = True) -> int:
        from . import birads as br

        b = result.breasts
        ai_cats = [x.ai_birads for x in b.values() if x.ai_birads]
        score = lambda s: b[s].prediction.cancer_prob if b[s].prediction else None  # noqa: E731
        p = result.patient
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO studies (created_at, patient_id, patient_name, patient_age, study_date, indication,
                   density, right_score, left_score, right_birads, left_birads, overall_birads, ai_overall_birads,
                   models, result_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    p.get("patient_id"), p.get("patient_name"), p.get("patient_age"), p.get("study_date"),
                    result.indication, result.density, score("R"), score("L"),
                    b["R"].birads, b["L"].birads, result.overall,
                    br.worst(ai_cats) if ai_cats else None,
                    ",".join(result.models), json.dumps(result.to_dict(), ensure_ascii=False, default=str),
                ),
            )
            study_id = cur.lastrowid
            labels = [label for _, label in result.thumbnails]
            for i, f in enumerate(files):
                stored = f
                if keep_images:
                    dest = self.files_dir / str(study_id)
                    dest.mkdir(parents=True, exist_ok=True)
                    stored = str(shutil.copy2(f, dest / Path(f).name))
                c.execute(
                    "INSERT INTO images (study_id, path, label) VALUES (?,?,?)",
                    (study_id, stored, labels[i] if i < len(labels) else None),
                )
            for lang, text in reports.items():
                c.execute("INSERT INTO reports (study_id, lang, text) VALUES (?,?,?)", (study_id, lang, text))
        return study_id

    def set_ground_truth(self, study_id: int, final_birads: str | None = None, pathology: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE studies SET final_birads = COALESCE(?, final_birads), pathology = COALESCE(?, pathology) "
                "WHERE id = ?",
                (final_birads, pathology, study_id),
            )

    def list_studies(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, created_at, patient_id, patient_name, patient_age, density, right_birads, left_birads, "
                "overall_birads, final_birads, pathology FROM studies ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_report(self, study_id: int, lang: str) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT text FROM reports WHERE study_id = ? AND lang = ?", (study_id, lang)).fetchone()
        return row["text"] if row else None

    def export_csv(self, out_path: str) -> str:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM studies ORDER BY id").fetchall()
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=[k for k in rows[0].keys() if k != "result_json"])
                w.writeheader()
                for r in rows:
                    w.writerow({k: r[k] for k in w.fieldnames})
        return out_path
