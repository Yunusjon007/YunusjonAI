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

### Patologiyani aylana bilan ko'rsatish (lezyon detektori)
Rak ehtimoli modeli **xavfsiz hosilalarni (fibroadenoma, kista) aniqlamaydi**, shuning uchun alohida
detektor kerak. U topgan har bir hosila rasmda **qizil aylana** bilan belgilanadi. Hosila topilgan bezga
**hech qachon BI-RADS 1** berilmaydi: rak bahosi past bo'lsa **3** chiqadi va izohda 2 yoki 0 ni tanlash
mumkinligi yoziladi.

Detektorning aniqligi o'lchanmagan bo'lsa yoki past bo'lsa (sezgirlik < 80%), u hech narsa topmasa ham
xulosada **ogohlantirish** chiqadi: "topmagani hosila yo'q degani emas". Tayyor detektor
(`scripts/download_detector.py`) sinovda fibroadenomani **topmadi** — uni ishlatish tavsiya etilmaydi.

#### O'z detektoringizni o'qitish (MacBook) — qadam-baqadam
Har bir buyruq `yunusjonai` papkasida, `(venv)` yoqilgan holda bajariladi.

**1. CBIS-DDSM ni yuklab oling** (ochiq, ro'yxatdan o'tish shart emas, ~6 GB):
<https://www.kaggle.com/datasets/awsaf49/cbis-ddsm-breast-cancer-image-dataset> → **Download**.
Zip'ni oching, masalan `~/Downloads/cbis-ddsm` papkasiga (ichida `csv/` va `jpeg/` bo'ladi).

**2. Papka tuzilishini tekshiring:**
```bash
python train/inspect_dataset.py --root ~/Downloads/cbis-ddsm
```

**3. O'qitish uchun tayyorlang** (30–60 daqiqa):
```bash
python train/prepare_cbis_det.py --root ~/Downloads/cbis-ddsm --out data/cbis_det
```
Oxirida `done -> data/cbis_det/data.yaml` chiqishi kerak. Agar "Too many files were not found" chiqsa,
2- va 3-qadam chiqishini menga yuboring.

**4. Qisqa sinov** (~30–60 daqiqa, hammasi ishlashini tekshirish uchun):
```bash
caffeinate -i python train/train_detector.py --data data/cbis_det/data.yaml --fraction 0.1 --epochs 3
```

**5. To'liq o'qitish** (MacBook Air'da taxminan 1–2 kun; Mac quvvatga ulangan, qopqog'i ochiq bo'lsin):
```bash
caffeinate -i python train/train_detector.py --data data/cbis_det/data.yaml
```
To'xtab qolsa, davom ettirish:
```bash
caffeinate -i python train/train_detector.py --data data/cbis_det/data.yaml --resume
```

**6. Natijani tekshirish.** O'qitish oxirida `lesion recall ..%` chiqadi va `weights/detector.json` ga
yoziladi. 80% va undan yuqori bo'lsa, dastur detektorga ishonadi. O'z rasmlaringizni (fibroadenoma va
boshqalar) bitta papkaga solib, aylanalarni ko'zingiz bilan tekshiring:
```bash
python train/evaluate_detector.py --data data/cbis_det/data.yaml --images ~/Desktop/test_cases
```
Aylanali rasmlar `runs/check/` papkasiga saqlanadi.

**7. VinDr-Mammo** (raqamli, 20 000 rasm) ruxsati kelganda, ikkala bazada birga qayta o'qiting:
```bash
python train/prepare_vindr_det.py --root /data/vindr-mammo --out data/vindr_det
```
```bash
caffeinate -i python train/train_detector.py --data data/cbis_det/data.yaml --data data/vindr_det/data.yaml
```

Bitta rasmda ikkala bez bo'lsa (o'quv rasmlari, ekran surati), rasm avtomatik o'rtadan bo'linadi:
chap yarmi o'ng bez, o'ng yarmi chap bez. Buni "Bitta rasmda ikkala bez" tugmasi bilan boshqarasiz.

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

### Обводка находок (детектор образований)
Модель вероятности рака **не выявляет доброкачественные образования** (фиброаденома, киста), поэтому
нужен детектор: найденные образования обводятся **красным кругом**. Железе с найденным образованием
**никогда не ставится BI-RADS 1**: при низкой оценке рака ставится **3** с пояснением.
Если точность детектора не измерена или низкая (чувствительность < 80%), при «ничего не найдено»
в заключении остаётся предупреждение. Готовый детектор (`scripts/download_detector.py`) на тесте
фиброаденому **не нашёл** — не рекомендуется.
Собственный детектор: CBIS-DDSM (Kaggle, открыто) → `train/prepare_cbis_det.py`, затем
`train/train_detector.py` (на Mac через MPS), проверка — `train/evaluate_detector.py`. Позже можно
добавить VinDr-Mammo (`train/prepare_vindr_det.py`, второй `--data`). Пошаговая инструкция —
в узбекском разделе выше.

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

### Lesion detector (circles)
The malignancy model does not detect benign lesions, so a YOLO detector marks findings with red circles.
A breast with a detected lesion is never assigned BI-RADS 1 (low score → 3).
"Nothing found" is trusted only for a detector whose measured lesion recall (`weights/detector.json`,
written by `train/evaluate_detector.py`) is at least `MAMMO_DETECTOR_MIN_RECALL` (0.8); otherwise the
conclusion carries a warning.
- Ready-made weights: `python scripts/download_detector.py` — missed a fibroadenoma in testing, not recommended.
- Your own detector: `train/prepare_cbis_det.py` (CBIS-DDSM, Kaggle JPEG or TCIA DICOM) and/or
  `train/prepare_vindr_det.py` → `train/train_detector.py --data ... [--data ...]` (MPS / CUDA / CPU,
  `--resume`) → `train/evaluate_detector.py --images your_cases/`.
- Ultralytics is AGPL-3.0.

Images that show both breasts side by side are split automatically (left half = right breast).

### Limitations
- Without a detector the model gives one score per breast and does **not** localise lesions.
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
| `MAMMO_DETECTOR_WEIGHTS` | `weights/detector.pt` |
| `MAMMO_DETECTOR_CONF` | `0.25` |

### Tests
```bash
pytest
```

### Project layout
```
mammo_ai/          imaging, models/, birads, pipeline, report, db, cli, locales/{uz,ru,en}.json
app.py             Gradio web UI
telegram_bot.py    Telegram bot
train/             prepare_vindr.py, train_birads.py, prepare_vindr_det.py, train_detector.py, calibrate.py
scripts/           download_detector.py
docs/              MODELS_AND_DATASETS.md
```
