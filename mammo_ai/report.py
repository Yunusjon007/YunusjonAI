"""Render a StudyResult as a full mammography report (Markdown) in any language under locales/."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import birads as br
from .config import settings
from .pipeline import BreastResult, Finding, StudyResult

LOCALE_DIR = Path(__file__).parent / "locales"


def available_languages() -> list[str]:
    return sorted(p.stem for p in LOCALE_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def load_locale(lang: str) -> dict:
    """Missing keys fall back to English, so a new language can be translated gradually."""
    base = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
    path = LOCALE_DIR / f"{lang}.json"
    if lang != "en" and path.exists():
        _deep_update(base, json.loads(path.read_text(encoding="utf-8")))
    return base


def _deep_update(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def _finding_text(f: Finding, t: dict) -> str:
    parts = []
    for key, table in (
        ("shape", "shape"),
        ("margin", "margin"),
        ("density", "mass_density"),
        ("morphology", "morphology"),
        ("distribution", "distribution"),
        ("asym_type", "asym_type"),
    ):
        val = getattr(f, key)
        if val:
            parts.append(f"{t['field'][key]}: {t[table].get(val, val)}")
    if f.size_mm:
        parts.append(f"{t['field']['size']}: {t['size_mm'].format(size=f.size_mm)}")
    loc = [t["location"].get(f.location, f.location)] if f.location else []
    if f.clock:
        loc.append(t["clock_fmt"].format(clock=f.clock))
    if f.depth:
        loc.append(t["depth"].get(f.depth, f.depth))
    if loc:
        parts.append(f"{t['field']['location']}: {', '.join(loc)}")
    if f.assoc:
        parts.append(f"{t['field']['assoc']}: {', '.join(t['assoc'].get(a, a) for a in f.assoc)}")
    if f.note:
        parts.append(f"{t['field']['note']}: {f.note}")
    name = t["finding_type"].get(f.type, f.type)
    return f"{name} — " + "; ".join(parts) if parts else name


def _ai_finding_line(f: Finding, t: dict) -> str:
    size = t["ai_finding_size"].format(size=f.size_mm) if f.size_mm else ""
    return t["ai_finding_line"].format(
        type=t["finding_type"].get(f.type, f.type), score=f"{(f.score or 0) * 100:.0f}", size=size, image=f.image
    )


def _breast_section(b: BreastResult, t: dict, detector_used: bool = False) -> list[str]:
    lines = [f"**{t['side'][b.side]}**" + (f" ({', '.join(b.views)})" if b.views else "")]
    p = b.prediction
    if p is None:
        lines.append(f"- {t['not_examined']}")
        return lines
    if p.cancer_prob is not None:
        level = br.suspicion_level(p.cancer_prob, settings.birads_thresholds)
        lines.append("- " + t["ai_score"].format(score=f"{p.cancer_prob * 100:.1f}", level=t["level"][level]))
    if p.birads_probs is not None:
        probs = ", ".join(f"{c}: {v * 100:.0f}%" for c, v in zip(["1", "2", "3", "4", "5"], p.birads_probs))
        lines.append("- " + t["ai_birads_model"].format(probs=probs))
    ai = b.ai_birads or "1"
    if br.rank(ai) >= br.rank("4A"):
        lines.append("- " + t["ai_suspicious"])
    elif ai == "3":
        lines.append("- " + t["ai_indeterminate"])
    else:
        lines.append("- " + t["ai_no_suspicious"])
    if b.ai_findings:
        lines.append("- " + t["ai_findings"])
        lines += [f"  - {_ai_finding_line(f, t)}" for f in b.ai_findings]
        if p.cancer_prob is not None and br.from_score(p.cancer_prob, settings.birads_thresholds) == "1":
            lines.append(f"- {t['benign_mass_note']}")
    elif not detector_used and ai in {"1", "2"}:
        lines.append(f"- **⚠️ {t['detector_missing']}**")
    if b.findings:
        lines.append("- " + t["radiologist_findings"])
        lines += [f"  - {_finding_text(f, t)}" for f in b.findings]
        low = b.birads and br.rank(b.birads) < br.rank("4A")
        if low and not b.overridden and any(f.is_suspicious() for f in b.findings):
            lines.append(f"- **{t['findings_need_category']}**")
    if b.laterality_estimated:
        lines.append(f"- _{t['laterality_estimated']}_")
    return lines


def render(result: StudyResult, lang: str = "uz") -> str:
    t = load_locale(lang)
    pt = result.patient
    out = [f"# {t['title']}", "", f"> {t['draft_note']}", ""]

    out.append(f"## {t['section_patient']}")
    for key, label in (
        ("patient_id", "patient_id"),
        ("patient_name", "patient_name"),
        ("patient_age", "age"),
        ("study_date", "study_date"),
        ("manufacturer", "device"),
    ):
        if pt.get(key):
            out.append(f"- **{t[label]}:** {pt[key]}")
    out.append(f"- **{t['indication']}:** {result.indication or t['indication_default']}")
    out.append("")

    views = [v for b in result.breasts.values() for v in b.views]
    out += [f"## {t['section_technique']}", t["technique_text"].format(views=", ".join(views) or t["views_unknown"])]
    if result.split:
        out.append(f"_{t['split_note']}_")
    out.append("")
    out += [f"## {t['section_comparison']}", result.comparison or t["comparison_none"], ""]

    out.append(f"## {t['section_composition']}")
    if result.density:
        conf = f" ({t['density_confidence'].format(pct=round(result.density_conf * 100))})" if result.density_conf else ""
        out.append(t["density"][result.density] + conf)
    else:
        out.append(t["density_unknown"])
    out.append("")

    out.append(f"## {t['section_findings']}")
    for side in ("R", "L"):
        out += _breast_section(result.breasts[side], t, result.detector_used) + [""]

    out.append(f"## {t['section_impression']}")
    for side in ("R", "L"):
        b = result.breasts[side]
        if b.birads:
            out.append(
                f"- **{t['side_short'][side]}: BI-RADS {b.birads}** — {t['birads'][b.birads]} "
                f"({t['risk'].format(risk=br.MALIGNANCY_RISK[b.birads])})"
            )
    if result.overall:
        out.append(f"- **{t['overall']}: BI-RADS {result.overall}** — {t['birads'][result.overall]}")
    out.append("")

    out.append(f"## {t['section_recommendation']}")
    if result.overall:
        out.append(f"- {t['rec'][result.overall]}")
    if result.density in {"C", "D"} and result.overall in {"1", "2", "3"}:
        out.append(f"- {t['dense_note'].format(density=result.density)}")
    out.append("")

    out.append(f"## {t['section_ai']}")
    if result.models:
        out.append(f"- {t['models_used'].format(models=', '.join(result.models))}")
    if any(b.overridden for b in result.breasts.values()):
        out.append(f"- {t['override_note']}")
    else:
        out.append(f"- {t['threshold_note']}")
    if not result.detector_used:
        out.append(f"- {t['detector_missing']}")
    out += ["", f"**{t['disclaimer']}**", "", t["signature"], ""]
    return "\n".join(out)


def render_many(result: StudyResult, langs: list[str]) -> str:
    return "\n\n---\n\n".join(render(result, lang) for lang in langs)
