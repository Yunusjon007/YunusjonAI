"""Command line:  python -m mammo_ai.cli RCC.dcm RMLO.dcm LCC.png LMLO.jpg --lang uz,ru,en --out report.md"""
from __future__ import annotations

import argparse
import sys

from .config import settings
from .db import Database
from .models import load_backends
from .pipeline import analyze
from .report import available_languages, render, render_many


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MammoAI: mammogram -> BI-RADS report")
    ap.add_argument("files", nargs="+", help="DICOM / PNG / JPG images of one study")
    ap.add_argument("--lang", default=settings.default_lang, help=f"comma separated, any of {available_languages()}")
    ap.add_argument("--out", help="write the report to this file (Markdown)")
    ap.add_argument("--patient-id", default="")
    ap.add_argument("--age", default="")
    ap.add_argument("--indication", default="")
    ap.add_argument("--right-birads", help="radiologist override for the right breast, e.g. 4B")
    ap.add_argument("--left-birads", help="radiologist override for the left breast")
    ap.add_argument("--no-db", action="store_true", help="do not save the study to the database")
    args = ap.parse_args(argv)

    langs = [x.strip() for x in args.lang.split(",") if x.strip()]
    backend = load_backends(settings)
    overrides = {k: v for k, v in (("R", args.right_birads), ("L", args.left_birads)) if v}
    result = analyze(
        args.files,
        backend,
        patient={"patient_id": args.patient_id, "patient_age": args.age},
        overrides=overrides,
        indication=args.indication,
    )
    reports = {lang: render(result, lang) for lang in langs}
    text = render_many(result, langs)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    if not args.no_db:
        study_id = Database(settings.db_path).save(result, reports, args.files)
        print(f"\n[saved to database: study #{study_id}, {settings.db_path}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
