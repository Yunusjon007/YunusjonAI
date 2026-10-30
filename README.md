# YunusjonAI — MammoAI

Ochiq kodli mammografiya yordamchisi: **DICOM / PNG / JPG** → ACR zichlik (A–D) → **BI-RADS (0–6)** →
to'liq xulosa **o'zbek, rus va ingliz** tillarida. Veb-interfeys, Telegram bot, CLI va SQLite baza.

> ⚠️ **Tibbiy buyum emas / Не является медицинским изделием / Not a medical device.**
> Xulosa — rentgenolog uchun qoralama. Окончательное заключение даёт врач. The radiologist signs the final report.

[O'zbekcha](#ozbekcha) · [Русский](#русский) · [English](#english)

---

## O'zbekcha

### Qanday ishlaydi
1. Rasm yuklanadi (DICOM: VOI LUT, MONOCHROME1, teglar — tomon, proyeksiya, bemor ID, yosh avtomatik olinadi;
   PNG/JPG: tomon fayl nomidan `R_CC`, `LMLO` yoki tasvirdan aniqlanadi).
2. Ko'krak bezi kesib olinadi, har bir tomon uchun CC + MLO juftlanadi.
3. Ochiq model **ianpan/mammoscreen** (Apache-2.0) xavfli o'sma ehtimoli va zichlikni beradi.
   Agar `weights/birads_model.pt` bo'lsa (o'zingiz o'qitgan model) — to'g'ridan-to'g'ri BI-RADS ham qo'shiladi.
4. Ehtimol → BI-RADS: `<10% → 1`, `<20% → 3`, `<35% → 4A`, `<55% → 4B`, `<80% → 4C`, `≥80% → 5`.
   **Bu chegaralar klinik tasdiqlanmagan** — o'z biopsiya natijalaringizda `train/calibrate.py` bilan sozlang.
5. Shifokor topilmalarni (hosila, kalsinat, asimmetriya, joylashuv, o'lcham...) qo'shishi va BI-RADS ni
   qo'lda o'zgartirishi mumkin. Xulosa ACR BI-RADS leksikonida uch tilda chiqadi va bazaga saqlanadi.

### O'rnatish
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
Birinchi ishga tushirishda model huggingface.co dan yuklab olinadi (internet kerak).

### Ishga tushirish
```bash
python app.py                      # veb: http://127.0.0.1:7860
python -m mammo_ai.cli RCC.dcm RMLO.dcm LCC.dcm LMLO.dcm --lang uz,ru,en --out xulosa.md
python telegram_bot.py             # avval TELEGRAM_API_ID, TELEGRAM_API_HASH, MAMMO_BOT_TOKEN ni o'rnating
```

### Boshqa tilga moslash
`mammo_ai/locales/en.json` ni nusxalang, masalan `kk.json` (qozoq), matnlarni tarjima qiling — til avtomatik
paydo bo'ladi. Tarjima qilinmagan kalitlar inglizcha qoladi.

### O'z modelingizni o'qitish (BI-RADS to'g'ridan-to'g'ri)
```bash
python train/prepare_vindr.py --root /data/vindr-mammo --out data/vindr.csv --png-dir data/vindr_png
python train/train_birads.py --csv data/vindr.csv --epochs 15 --out weights/birads_model.pt
```
Ochiq modellar va bazalar ro'yxati: [docs/MODELS_AND_DATASETS.md](docs/MODELS_AND_DATASETS.md).

---

## Русский

### Как работает
1. Загрузка снимков (DICOM: VOI LUT, MONOCHROME1, теги — сторона, проекция, ID и возраст пациента;
   PNG/JPG: сторона по имени файла `R_CC`, `LMLO` или по изображению).
2. Автоматическая обрезка железы, объединение CC + MLO для каждой стороны.
3. Открытая модель **ianpan/mammoscreen** (Apache-2.0): вероятность злокачественности + плотность ACR.
   При наличии `weights/birads_model.pt` (ваша дообученная модель) добавляется прямой прогноз BI-RADS.
4. Вероятность → BI-RADS по порогам (`MAMMO_BIRADS_THRESHOLDS`). **Пороги клинически не валидированы** —
   откалибруйте их на своих данных с биопсией (`train/calibrate.py`).
5. Врач может добавить находки (образование, кальцинаты, асимметрия, локализация, размер) и изменить
   категорию BI-RADS. Заключение формируется по лексикону ACR BI-RADS на трёх языках и сохраняется в базу.

### Установка и запуск
```bash
pip install -r requirements.txt
```
```bash
python app.py
```
```bash
python -m mammo_ai.cli снимок1.dcm снимок2.dcm --lang ru --out заключение.md
```

### Добавить язык
Скопируйте `mammo_ai/locales/en.json` в `<код>.json` и переведите значения.

---

## English

### How it works
1. Load images (DICOM with VOI LUT / MONOCHROME1 handling and tags; PNG/JPG with side from the file name or the image).
2. Crop the breast, pair CC + MLO per side.
3. Open model **ianpan/mammoscreen** (Apache-2.0, trained on CBIS-DDSM + RSNA) gives a malignancy score and
   ACR density. An optional checkpoint trained with `train/train_birads.py` adds a direct BI-RADS 1–5 prediction.
4. Score → BI-RADS via configurable thresholds (`MAMMO_BIRADS_THRESHOLDS`) — **not clinically validated, calibrate locally**.
5. The radiologist can add lexicon-based findings and override the category. Reports are rendered from
   `mammo_ai/locales/*.json` and every study is stored in SQLite (`data/mammo.sqlite3`) with images, reports,
   and later biopsy ground truth (for calibration / retraining; CSV export in the "Database" tab).

### Limitations
- The model gives one score per breast; it does **not** localise lesions. Findings are described by the radiologist.
- Trained mostly on screening data from other populations — validate on your own equipment and patients.

### Settings (environment variables)
| Variable | Default |
|---|---|
| `MAMMO_BIRADS_THRESHOLDS` | `0.10,0.20,0.35,0.55,0.80` |
| `MAMMO_BIRADS_CKPT` | `weights/birads_model.pt` |
| `MAMMO_DB` | `data/mammo.sqlite3` |
| `MAMMO_LANG` | `uz` |
| `MAMMO_DEVICE` | `auto` (`cpu` / `cuda`) |
| `MAMMO_USE_HF_CROP` | `0` |

### Tests
```bash
pytest
```

### Project layout
```
mammo_ai/          imaging, models/, birads, pipeline, report, db, cli, locales/{uz,ru,en}.json
app.py             Gradio web UI
telegram_bot.py    Telegram bot
train/             prepare_vindr.py, train_birads.py, calibrate.py
docs/              MODELS_AND_DATASETS.md
```
