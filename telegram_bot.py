"""MammoAI Telegram bot.

Send mammograms (DICOM as a file, PNG/JPG as a file or photo), then /tahlil.
Keys are read from environment variables, never written in the code:

    export TELEGRAM_API_ID=...  TELEGRAM_API_HASH=...  MAMMO_BOT_TOKEN=...
    export MAMMO_ALLOWED_USERS=dr_radiologist_valiyev      # comma separated, empty = everyone
    python telegram_bot.py
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from telethon import TelegramClient, events

from mammo_ai.config import settings
from mammo_ai.db import Database
from mammo_ai.models import load_backends
from mammo_ai.pipeline import analyze
from mammo_ai.report import available_languages, render

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
BOT_TOKEN = os.environ["MAMMO_BOT_TOKEN"]
ALLOWED = {u.strip().lstrip("@").lower() for u in os.getenv("MAMMO_ALLOWED_USERS", "").split(",") if u.strip()}

HELP = (
    "MammoAI 🩺\n"
    "1) Rasmlarni yuboring / Отправьте снимки / Send images (DICOM, PNG, JPG; R-CC, R-MLO, L-CC, L-MLO)\n"
    "2) /tahlil — tahlil / анализ / analyze\n"
    "/uz /ru /en /all — til / язык / language\n"
    "/clear — tozalash / очистить\n\n"
    "⚠️ Tibbiy buyum emas. Не является медицинским изделием. Not a medical device."
)

bot = TelegramClient("mammo_bot_session", API_ID, API_HASH)
pending: dict[int, list[str]] = defaultdict(list)
user_lang: dict[int, str] = {}
work_dir = Path(tempfile.mkdtemp(prefix="mammo_bot_"))
db = Database(settings.db_path)
_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = load_backends(settings)
    return _backend


async def allowed(event) -> bool:
    if event.is_group or event.out:
        return False
    if not ALLOWED:
        return True
    sender = await event.get_sender()
    return bool(sender and (getattr(sender, "username", "") or "").lower() in ALLOWED)


def chunks(text: str, size: int = 4000):
    text = re.sub(r"^#+ (.*)$", r"**\1**", text, flags=re.M)  # Telegram has no Markdown headings
    while text:
        cut = text.rfind("\n", 0, size) if len(text) > size else len(text)
        cut = cut if cut > 0 else size
        yield text[:cut]
        text = text[cut:].lstrip("\n")


@bot.on(events.NewMessage(pattern=r"^/(start|help)"))
async def on_help(event):
    if await allowed(event):
        await event.reply(HELP)


@bot.on(events.NewMessage(pattern=r"^/(uz|ru|en|all)$"))
async def on_lang(event):
    if await allowed(event):
        user_lang[event.sender_id] = event.pattern_match.group(1)
        await event.reply(f"✅ {user_lang[event.sender_id]}")


@bot.on(events.NewMessage(pattern=r"^/clear$"))
async def on_clear(event):
    if await allowed(event):
        pending.pop(event.sender_id, None)
        await event.reply("🗑 OK")


@bot.on(events.NewMessage(func=lambda e: e.file is not None))
async def on_file(event):
    if not await allowed(event):
        return
    uid = event.sender_id
    name = event.file.name or f"image_{event.id}{event.file.ext or '.jpg'}"
    path = await event.download_media(file=str(work_dir / f"{uid}_{event.id}_{name}"))
    pending[uid].append(path)
    await event.reply(f"📥 {len(pending[uid])} — /tahlil")


@bot.on(events.NewMessage(pattern=r"^/(tahlil|analyze|анализ)"))
async def on_analyze(event):
    if not await allowed(event):
        return
    uid = event.sender_id
    files = pending.pop(uid, [])
    if not files:
        await event.reply("Avval rasm yuboring / Сначала отправьте снимки / Send images first")
        return
    lang = user_lang.get(uid, settings.default_lang)
    langs = available_languages() if lang == "all" else [lang]
    await event.reply("⏳ ...")
    try:
        result = await asyncio.to_thread(analyze, files, backend())
    except Exception as exc:
        await event.reply(f"❌ {exc}")
        return
    reports = {lg: render(result, lg) for lg in langs}
    study_id = db.save(result, reports, files)
    for lg in langs:
        for part in chunks(f"#{study_id}\n" + reports[lg]):
            await event.respond(part)
    out = work_dir / f"mammo_report_{study_id}.md"
    out.write_text("\n\n---\n\n".join(reports.values()), encoding="utf-8")
    await event.respond(file=str(out))


if __name__ == "__main__":
    bot.start(bot_token=BOT_TOKEN)
    print("MammoAI bot ishga tushdi...")
    bot.run_until_disconnected()
