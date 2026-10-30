"""MammoAI: open-source mammography analysis with BI-RADS reports in Uzbek, Russian and English.

Decision-support tool only, not a certified medical device.
"""
from .config import settings
from .pipeline import Finding, StudyResult, analyze
from .report import available_languages, render, render_many

__all__ = ["settings", "analyze", "Finding", "StudyResult", "render", "render_many", "available_languages"]
